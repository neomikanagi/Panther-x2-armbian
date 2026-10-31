"""Synthetic GPT tests; no disks, root, mounts or hardware required."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/graft_bootchain.py"
spec = importlib.util.spec_from_file_location("graft", SCRIPT)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def image(path, first=32768):
    sectors = 34816
    entries = bytearray(128 * 128)
    entries[:16] = b"t" * 16
    entries[16:32] = b"u" * 16
    struct.pack_into("<QQ", entries, 32, first, sectors - 34)
    crc = zlib.crc32(entries)

    def header(current, other, entry_lba):
        data = bytearray(512)
        struct.pack_into("<8sIIIIQQQQ16sQIII", data, 0, b"EFI PART", 0x10000, 92, 0, 0,
                         current, other, 34, sectors - 34, b"d" * 16, entry_lba, 128, 128, crc)
        struct.pack_into("<I", data, 16, zlib.crc32(data[:92]))
        return data

    with path.open("wb") as f:
        f.truncate(sectors * 512)
        mbr = bytearray(512)
        mbr[450] = 0xEE
        mbr[510:512] = b"\x55\xaa"
        f.write(mbr)
        f.write(header(1, sectors - 1, 2))
        f.write(entries)
        f.seek(g.GAP_START)
        f.write(b"old loader and stale environment")
        f.seek(first * 512)
        f.write(b"kernel, DTB, modules, root filesystem must not change")
        f.seek((sectors - 33) * 512)
        f.write(entries)
        f.write(header(sectors - 1, 1, sectors - 33))


class GraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.img"
        self.out = self.root / "candidate.img"
        self.loaders = self.root / "loaders"
        self.loaders.mkdir()
        image(self.source)
        gap = bytearray(g.GAP_END - g.GAP_START)
        items = []
        for name, offset, data in [("idbloader.img", g.GAP_START, b"new DDR loader"),
                                   ("u-boot.itb", 8388608, b"new U-Boot and BL31")]:
            (self.loaders / name).write_bytes(data)
            items.append(dict(name=name, offset=offset, size=len(data), sha256=hashlib.sha256(data).hexdigest()))
            gap[offset - g.GAP_START:offset - g.GAP_START + len(data)] = data
        self.manifest = self.root / "inputs.json"
        self.data = dict(bootloader_commit="test", loaders=items,
                         boot_gap=dict(start=g.GAP_START, end=g.GAP_END, sha256=hashlib.sha256(gap).hexdigest()))
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.data))

    def run_graft(self):
        return g.graft(self.source, self.out, self.loaders, self.manifest)

    def refused(self):
        with self.assertRaises((ValueError, OSError)):
            self.run_graft()
        self.assertFalse(self.out.exists())

    def test_changes_only_gap_and_keeps_original(self):
        original = self.source.read_bytes()
        report = self.run_graft()
        candidate = self.out.read_bytes()
        self.assertEqual(original, self.source.read_bytes())
        self.assertEqual(candidate[:g.GAP_START], original[:g.GAP_START])
        self.assertEqual(candidate[g.GAP_END:], original[g.GAP_END:])
        self.assertNotEqual(candidate[g.GAP_START:g.GAP_END], original[g.GAP_START:g.GAP_END])
        self.assertNotIn(b"stale environment", candidate[g.GAP_START:g.GAP_END])
        self.assertTrue(report["protected_bytes_unchanged"])
        self.assertFalse(report["hardware_boot_tested"])
        self.assertFalse(report["npu_vpu_runtime_tested"])

    def test_refuses_existing_output(self):
        self.out.write_bytes(b"valuable file")
        with self.assertRaises(ValueError):
            self.run_graft()
        self.assertEqual(self.out.read_bytes(), b"valuable file")

    def test_refuses_output_symlink(self):
        self.out.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            self.run_graft()
        self.assertTrue(self.out.is_symlink())

    def test_refuses_input_symlink(self):
        link = self.root / "link.img"
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            g.graft(link, self.out, self.loaders, self.manifest)

    def test_refuses_same_input_output(self):
        with self.assertRaises(ValueError):
            g.graft(self.source, self.source, self.loaders, self.manifest)

    def test_refuses_block_or_character_device(self):
        with self.assertRaises(ValueError):
            g.graft(Path("/dev/null"), self.out, self.loaders, self.manifest)

    def test_refuses_nonempty_vendor_storage(self):
        for offset in (g.VENDOR_START, g.VENDOR_START + 65536, g.VENDOR_END - 1):
            with self.subTest(offset=offset):
                image(self.source)
                with self.source.open("r+b") as f:
                    f.seek(offset)
                    f.write(b"X")
                self.refused()

    def test_refuses_altered_loader(self):
        path = self.loaders / "idbloader.img"
        path.write_bytes(b"x" * path.stat().st_size)
        self.refused()

    def test_refuses_short_loader(self):
        (self.loaders / "idbloader.img").write_bytes(b"short")
        self.refused()

    def test_refuses_wrong_gap_checksum(self):
        self.data["boot_gap"]["sha256"] = "0" * 64
        self.save()
        self.refused()

    def test_refuses_loader_overlap(self):
        self.data["loaders"][1]["offset"] = g.GAP_START
        self.save()
        self.refused()

    def test_refuses_loader_crossing_filesystem(self):
        self.data["loaders"][1]["offset"] = g.GAP_END - 1
        self.save()
        self.refused()

    def test_refuses_wrong_layout(self):
        image(self.source, first=16384)
        self.refused()

    def test_refuses_corrupt_primary_gpt(self):
        with self.source.open("r+b") as f:
            f.seek(520)
            f.write(b"broken")
        self.refused()

    def test_refuses_corrupt_partition_entries(self):
        with self.source.open("r+b") as f:
            f.seek(1024)
            f.write(b"broken")
        self.refused()

    def test_refuses_corrupt_backup_gpt(self):
        with self.source.open("r+b") as f:
            f.seek(self.source.stat().st_size - 512)
            f.write(b"broken")
        self.refused()

    def test_refuses_corrupt_backup_entries(self):
        with self.source.open("r+b") as f:
            f.seek(self.source.stat().st_size - 33 * 512)
            f.write(b"broken")
        self.refused()

    def test_refuses_truncated_image(self):
        with self.source.open("r+b") as f:
            f.truncate(g.GAP_END)
        self.refused()

    def test_cleans_up_on_failed_validation(self):
        # First protected digest succeeds; read-back validation then detects a mismatch.
        with patch.object(g, "digest", side_effect=["before", "different"]):
            self.refused()


if __name__ == "__main__":
    unittest.main()
