#!/usr/bin/env python3
"""Build a generic, matched BSP payload from checksum-pinned ophub rk35xx packages.
Never connects to a board, flashes, reboots or reads /dev/mem.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tarfile
import tempfile
import zlib

REPO = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(8 * 1024 * 1024):
            h.update(b)
    return h.hexdigest()


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def member(archive: Path, name: str) -> bytes:
    with tarfile.open(archive) as t:
        for m in t:
            p = PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError("Unsafe archive path")
            if str(p) == name:
                if not m.isfile():
                    raise ValueError(f"Expected regular archive member: {name}")
                return t.extractfile(m).read()
    raise ValueError(f"Missing archive member: {name}")


def cpio_index(data: bytes) -> tuple[list[str], dict[str, bytes]]:
    """Inspect newc archives without extracting device nodes or following links."""
    names, selected = [], {}
    offset = 0
    while offset < len(data):
        while offset < len(data) and data[offset] == 0:
            offset += 1
        if offset == len(data):
            break
        if data[offset:offset + 6] not in (b"070701", b"070702"):
            raise ValueError("Unsupported/truncated initramfs CPIO")
        header = data[offset:offset + 110]
        if len(header) != 110:
            raise ValueError("Short CPIO header")
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        length, namesize = fields[6], fields[11]
        if not 1 <= namesize <= 4096:
            raise ValueError("Invalid CPIO name")
        start = offset + 110
        rawname = data[start:start + namesize]
        if len(rawname) != namesize or rawname[-1] != 0:
            raise ValueError("Truncated CPIO name")
        name = rawname[:-1].decode()
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("Unsafe initramfs path")
        start = (start + namesize + 3) & ~3
        end = start + length
        if end > len(data):
            raise ValueError("Truncated CPIO data")
        if name != "TRAILER!!!":
            names.append(str(p))
            if str(p) in ("scripts/init-premount/ORDER", "conf/param.conf", "cryptroot/crypttab"):
                selected[str(p)] = data[start:end]
        offset = (end + 3) & ~3
    return names, selected


def legacy_payload(blob: bytes) -> tuple[int, bytes]:
    if len(blob) < 64:
        raise ValueError("Short uImage")
    fields = struct.unpack(">7I4B32s", blob[:64])
    if fields[0] != 0x27051956:
        raise ValueError("Invalid uImage magic")
    hdr = bytearray(blob[:64]); hdr[4:8] = bytes(4)
    data = blob[64:]
    if zlib.crc32(hdr) != fields[1] or len(data) != fields[3] or zlib.crc32(data) != fields[6]:
        raise ValueError("uImage checksum/length mismatch")
    return fields[2], data


def validate_layout(kernel: bytes, initrd_size: int, dtb_size: int, cfg: dict) -> list[dict]:
    if len(kernel) < 64 or kernel[56:60] != b"ARM\x64":
        raise ValueError("Expected uncompressed ARM64 Image")
    offset, size, flags = struct.unpack_from("<QQQ", kernel, 8)
    if offset != 0 or not flags & 8:
        raise ValueError("This profile expects relocatable text_offset=0 ARM64 Image")
    if cfg["kernel_load"] % (2 * 1024 * 1024):
        raise ValueError("Kernel load address is not 2 MiB aligned")
    spans = [
        {"name": "kernel", "start": cfg["kernel_load"], "size": max(len(kernel), size)},
        {"name": "environment", "start": cfg["env_load"], "size": 65536},
        {"name": "dtb", "start": cfg["fdt_load"], "size": dtb_size + 65536},
        {"name": "initrd", "start": cfg["initrd_load"], "size": initrd_size},
    ]
    # Conservative firmware/script reservations; do not use the conventional
    # 0x09000000 environment scratch address inside the optional trust region.
    reserved = [(0, 0x200000), (0xC00000, 0xD00000), (0x8400000, 0xA000000)]
    for a in spans:
        end = a["start"] + a["size"]
        if end > 0x20000000 or any(a["start"] < hi and lo < end for lo, hi in reserved):
            raise ValueError(f"Load region conflicts with conservative firmware reservations: {a['name']}")
        for b in spans:
            if a is not b and a["start"] < b["start"] + b["size"] and b["start"] < end:
                raise ValueError("Boot load regions overlap")
    return spans


def patch_dtb(path: Path, cfg: dict):
    def get(node, prop, kind="s"):
        return subprocess.check_output(["fdtget", "-t", kind, str(path), node, prop], text=True).strip()
    def symbol(name):
        return get("/__symbols__", name)
    for name in cfg["enable_symbols"]:
        run("fdtput", "-t", "s", path, symbol(name), "status", "okay")
    for name in cfg["disable_symbols"]:
        run("fdtput", "-t", "s", path, symbol(name), "status", "disabled")
    for name, prop, supply in (("rknpu", "rknpu-supply", "vdd_npu"),
                               ("rk_rga", "rga-supply", "vdd_logic"),
                               ("rkvdec", "vdec-supply", "vdd_logic"),
                               ("rkvenc", "venc-supply", "vdd_logic")):
        phandle = get(symbol(supply), "phandle", "x")
        run("fdtput", "-t", "x", path, symbol(name), prop, phandle)
    run("fdtput", "-t", "s", path, symbol("rknpu"), "interrupt-names", "npu_irq")
    if get("/dmc", "status") != "disabled":
        raise ValueError("Unexpected enabled DMC; do not silently change DDR policy")
    if get("/", "model") != "Panther X2":
        raise ValueError("Wrong board DTB")


def build(package: Path, out: Path, manifest: Path):
    cfg = json.loads(manifest.read_text())
    if not package.is_file() or package.is_symlink() or sha(package) != cfg["kernel_package"]["sha256"]:
        raise ValueError("Kernel package SHA-256 mismatch")
    if out.exists():
        raise ValueError("Output exists")
    out.mkdir(parents=True)
    ver = cfg["kernel_version"]
    release = ver.split("-")[0]
    with tempfile.TemporaryDirectory(prefix="panther-payload-") as tmp:
        tmp = Path(tmp)
        with tarfile.open(package) as t:
            t.extractall(tmp, filter="data")
        source = tmp / release
        boot = source / f"boot-{ver}.tar.gz"
        dtbs = source / f"dtb-rockchip-{ver}.tar.gz"
        modules = source / f"modules-{ver}.tar.gz"
        config = member(boot, f"config-{ver}")
        for opt in (b"CONFIG_ROCKCHIP_RKNPU=y", b"CONFIG_ROCKCHIP_MPP_SERVICE=y", b"CONFIG_NETPOLL=y", b"CONFIG_RD_GZIP=y"):
            if opt not in config.splitlines():
                raise ValueError(f"Required kernel option missing: {opt.decode()}")
        kernel = member(boot, f"vmlinuz-{ver}")
        (out / "vmlinuz").write_bytes(kernel)
        (out / "config").write_bytes(config)
        (out / "System.map").write_bytes(member(boot, f"System.map-{ver}"))
        dtb = out / "rk3566-panther-x2.dtb"
        dtb.write_bytes(member(dtbs, "rk3566-panther-x2.dtb"))
        patch_dtb(dtb, cfg)
        raw_initrd = member(boot, f"initrd.img-{ver}")
        epoch, wrapped = legacy_payload(member(boot, f"uInitrd-{ver}"))
        if wrapped != raw_initrd:
            raise ValueError("Package initrd/uInitrd mismatch")
        if raw_initrd.startswith(b"\xfd7zXZ\x00"):
            cpio = lzma.decompress(raw_initrd)
        elif raw_initrd.startswith(b"\x1f\x8b"):
            cpio = gzip.decompress(raw_initrd)
        else:
            raise ValueError("Unsupported initrd compression")
        names, selected = cpio_index(cpio)
        if any(n.startswith(("etc/ssh/", "etc/dropbear/", "cryptroot/keyfiles/", "etc/cryptsetup-keys.d/")) or n.endswith("authorized_keys") or n == "etc/shadow" for n in names):
            raise ValueError("Unexpected credentials/private hooks in generic initrd")
        crypttab = selected.get("cryptroot/crypttab", b"")
        if any(line.strip() and not line.lstrip().startswith(b"#") for line in crypttab.splitlines()):
            raise ValueError("Unexpected encrypted-root configuration in generic initrd")
        if not any(n.startswith(f"usr/lib/modules/{ver}/") for n in names):
            raise ValueError("Expected usr-merged initrd module layout")
        dep = member(modules, f"{ver}/modules.dep").decode()
        rows = [line for line in dep.splitlines() if line.startswith("kernel/drivers/net/netconsole.ko:")]
        if len(rows) != 1 or rows[0].split(":", 1)[1].strip():
            raise ValueError("Unexpected netconsole dependencies")
        stage = tmp / "extra"
        script_dir = stage / "scripts/init-premount"; script_dir.mkdir(parents=True)
        script = (REPO / "compat/init-premount-panther-hybrid").read_text().replace("@KERNEL_VERSION@", ver)
        hook = script_dir / "panther-hybrid"; hook.write_text(script); hook.chmod(0o755)
        order = selected.get("scripts/init-premount/ORDER", b"")
        (script_dir / "ORDER").write_bytes(b'/scripts/init-premount/panther-hybrid "$@"\n' + order)
        mod = stage / f"usr/lib/modules/{ver}/kernel/drivers/net/netconsole.ko"
        mod.parent.mkdir(parents=True)
        mod.write_bytes(member(modules, f"{ver}/kernel/drivers/net/netconsole.ko"))
        for p in stage.rglob("*"):
            os.utime(p, (epoch, epoch), follow_symlinks=False)
        os.utime(stage, (epoch, epoch))
        paths = b"\x00".join(str(p.relative_to(stage)).encode() for p in sorted(stage.rglob("*"))) + b"\x00"
        extra = subprocess.check_output(["cpio", "--null", "-o", "-H", "newc", "--owner=0:0", "--reproducible", "--quiet"], cwd=stage, input=paths)
        extra_names, _ = cpio_index(extra)
        if "scripts/init-premount/panther-hybrid" not in extra_names:
            raise ValueError("Initramfs hook missing")
        # Kernel initramfs format permits concatenated, padded newc archives.
        (out / "initrd.img").write_bytes(gzip.compress(cpio + extra, compresslevel=6, mtime=0))
        env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch))
        run("mkimage", "-A", "arm64", "-O", "linux", "-T", "ramdisk", "-C", "gzip", "-n", "Panther hybrid initrd", "-d", out / "initrd.img", out / "uInitrd", env=env)
        shutil.copyfile(REPO / "compat/hybrid-boot.cmd", out / "boot.cmd")
        run("mkimage", "-A", "arm", "-O", "linux", "-T", "script", "-C", "none", "-n", "Panther headless hybrid", "-d", out / "boot.cmd", out / "boot.hybrid.scr", env=env)
        _, ramdisk = legacy_payload((out / "uInitrd").read_bytes())
        if ramdisk != (out / "initrd.img").read_bytes():
            raise ValueError("Generated uInitrd mismatch")
        spans = validate_layout(kernel, (out / "uInitrd").stat().st_size, dtb.stat().st_size, cfg)
        shutil.copyfile(modules, out / "modules.tar.gz")
        (out / "kernel.version").write_text(ver + "\n")
        report = {"profile": cfg["profile"], "kernel_version": ver, "inputs": cfg,
                  "load_regions": spans, "source_date_epoch": epoch,
                  "validation": "offline-built; hardware results belong in separate hardware-validation.json",
                  "private_network_or_trial_configuration_included": False,
                  "initramfs_trial_rollback_limit": "Requires kernel to reach init-premount; earlier hangs still require recovery."}
        (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        (out / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(out.iterdir()) if p.is_file()))
        for p in out.iterdir():
            os.utime(p, (epoch, epoch))
    print(f"Prepared matched payload: {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kernel-package", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--manifest", type=Path, default=REPO / "compat/hybrid-inputs.json")
    args = p.parse_args()
    build(args.kernel_package, args.out, args.manifest)


if __name__ == "__main__":
    main()
