#!/usr/bin/env python3
"""Create a regular-file-only Panther X2 boot-chain candidate, never flash disks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import zlib

SECTOR = 512
GAP_START = 64 * SECTOR
GAP_END = 32768 * SECTOR
CHUNK = 8 * 1024 * 1024
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "compat/inputs.json"


def regular(path: Path) -> None:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"Not a regular file (symlinks/devices refused): {path}")


def digest(path: Path, outside_gap: bool = False) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        if outside_gap:
            h.update(f.read(GAP_START))
            f.seek(GAP_END)
        while data := f.read(CHUNK):
            h.update(data)
    return h.hexdigest()


def gpt_header(f, lba: int) -> tuple:
    f.seek(lba * SECTOR)
    sector = f.read(SECTOR)
    if len(sector) != SECTOR:
        raise ValueError("Truncated GPT header")
    fields = struct.unpack_from("<8sIIIIQQQQ16sQIII", sector)
    signature, revision, size, crc, reserved = fields[:5]
    if signature != b"EFI PART" or revision != 0x10000 or not 92 <= size <= SECTOR or reserved:
        raise ValueError("Invalid GPT header")
    header = bytearray(sector[:size])
    header[16:20] = bytes(4)
    if zlib.crc32(header) != crc or fields[5] != lba:
        raise ValueError("GPT header checksum/location mismatch")
    return fields


def partition_layout(path: Path) -> list[dict]:
    size = path.stat().st_size
    if size < GAP_END + SECTOR or size % SECTOR:
        raise ValueError("Invalid image length")
    with path.open("rb") as f:
        mbr = f.read(SECTOR)
        if mbr[510:512] != b"\x55\xaa" or mbr[450] != 0xEE:
            raise ValueError("Expected protective GPT MBR")
        header = gpt_header(f, 1)
        _, _, _, _, _, _, backup, first, last, disk_id, entries_lba, count, stride, crc = header
        if backup != size // SECTOR - 1 or not 0 < first <= last < backup:
            raise ValueError("GPT does not describe this image")
        if not 1 <= count <= 4096 or not 128 <= stride <= 4096 or stride % 8:
            raise ValueError("Invalid GPT entry dimensions")
        if entries_lba < 2 or entries_lba * SECTOR + count * stride > GAP_START:
            raise ValueError("GPT entries overlap bootloader gap")
        f.seek(entries_lba * SECTOR)
        entries = f.read(count * stride)
        if len(entries) != count * stride or zlib.crc32(entries) != crc:
            raise ValueError("GPT entries checksum mismatch")
        mirror = gpt_header(f, backup)
        if mirror[6] != 1 or mirror[7:10] != (first, last, disk_id) or mirror[11:] != header[11:]:
            raise ValueError("Backup GPT mismatch")
        if not last < mirror[10] < backup or mirror[10] * SECTOR + len(entries) > backup * SECTOR:
            raise ValueError("Backup GPT entries outside reserved area")
        f.seek(mirror[10] * SECTOR)
        if f.read(len(entries)) != entries:
            raise ValueError("Backup GPT entries differ")
    partitions = []
    for index in range(count):
        entry = entries[index * stride:(index + 1) * stride]
        if entry[:16] == bytes(16):
            continue
        start, end = struct.unpack_from("<QQ", entry, 32)
        if not first <= start <= end <= last:
            raise ValueError("Partition outside GPT usable sectors")
        partitions.append({"index": index + 1, "start": start, "end": end})
    partitions.sort(key=lambda p: p["start"])
    if not partitions or partitions[0]["start"] * SECTOR != GAP_END:
        raise ValueError("Expected first partition at 16 MiB; refusing a different layout")
    if any(a["end"] >= b["start"] for a, b in zip(partitions, partitions[1:])):
        raise ValueError("Overlapping GPT partitions")
    return partitions


def make_gap(manifest: dict, loader_dir: Path) -> bytes:
    spec = manifest["boot_gap"]
    if (spec["start"], spec["end"]) != (GAP_START, GAP_END):
        raise ValueError("Unexpected boot gap in manifest")
    gap = bytearray(GAP_END - GAP_START)
    ranges = []
    for item in manifest["loaders"]:
        name = item["name"]
        if Path(name).name != name:
            raise ValueError("Invalid loader filename")
        path = loader_dir / name
        regular(path)
        if path.stat().st_size != item["size"]:
            raise ValueError(f"Loader size mismatch: {name}")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Loader SHA-256 mismatch: {name}")
        start = item["offset"] - GAP_START
        end = start + len(data)
        if not 0 <= start < end <= len(gap) or any(start < b and a < end for a, b in ranges):
            raise ValueError("Loader overlaps another loader or a partition table/filesystem")
        ranges.append((start, end))
        gap[start:end] = data
    if hashlib.sha256(gap).hexdigest() != spec["sha256"]:
        raise ValueError("Combined boot gap does not match the known-good reference")
    return bytes(gap)


def graft(image: Path, output: Path, loader_dir: Path, manifest_path: Path = DEFAULT_MANIFEST) -> dict:
    regular(image)
    if output.exists() or output.is_symlink():
        raise ValueError("Output exists; refusing to overwrite")
    manifest = json.loads(manifest_path.read_text())
    partitions = partition_layout(image)
    gap = make_gap(manifest, loader_dir)
    before = digest(image, outside_gap=True)
    created = False
    try:
        # Exclusive creation also refuses pre-existing device nodes and symlinks.
        with output.open("xb") as target, image.open("rb") as source:
            created = True
            shutil.copyfileobj(source, target, CHUNK)
            target.seek(GAP_START)
            target.write(gap)
            target.flush()
            os.fsync(target.fileno())
        after = digest(output, outside_gap=True)
        if before != after or partition_layout(output) != partitions:
            raise ValueError("Protected bytes changed: partition tables or filesystems differ")
        with output.open("rb") as f:
            f.seek(GAP_START)
            if f.read(len(gap)) != gap:
                raise ValueError("Boot gap read-back mismatch")
        return {
            "status": "offline-validated-candidate",
            "hardware_boot_tested": False,
            "npu_vpu_runtime_tested": False,
            "source_image": image.name,
            "output_image": output.name,
            "source_sha256": digest(image),
            "output_sha256": digest(output),
            "image_size": output.stat().st_size,
            "changed_region": {"start": GAP_START, "end_exclusive": GAP_END},
            "boot_gap_sha256": manifest["boot_gap"]["sha256"],
            "protected_bytes_sha256": after,
            "protected_bytes_unchanged": True,
            "partitions": partitions,
            "bootloader_commit": manifest["bootloader_commit"],
            "loaders": [{k: p[k] for k in ("name", "offset", "size", "sha256")} for p in manifest["loaders"]],
            "notes": "GPT/MBR and every byte from the first partition to EOF are unchanged, including BSP kernel, DTB, modules, rootfs and backup GPT. This does not establish a DDR fault or successful boot. Old bootloader packages remain in rootfs: do not reinstall/update U-Boot before validation.",
        }
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--loader-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        report = graft(args.image, args.output, args.loader_dir, args.manifest)
    except (OSError, ValueError, KeyError, struct.error) as error:
        print(f"Refused: {error}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
