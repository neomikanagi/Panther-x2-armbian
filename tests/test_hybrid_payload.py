import importlib.util
import json
from pathlib import Path
import struct
import unittest
import zlib

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hybrid", REPO / "scripts/prepare_hybrid_payload.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def record(name, data=b"", mode=0o100644):
    name = name.encode() + b"\0"
    fields = [1, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name), 0]
    out = b"070701" + b"".join(f"{n:08x}".encode() for n in fields) + name
    out += b"\0" * (-len(out) % 4)
    out += data
    out += b"\0" * (-len(out) % 4)
    return out


class HybridPayloadTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((REPO / "compat/hybrid-inputs.json").read_text())
        self.kernel = bytearray(64)
        self.kernel[56:60] = b"ARM\x64"
        struct.pack_into("<QQQ", self.kernel, 8, 0, 45 * 1024 * 1024, 10)

    def test_safe_profile_load_layout(self):
        spans = h.validate_layout(self.kernel, 30 * 1024 * 1024, 200000, self.cfg)
        self.assertEqual(len(spans), 4)

    def test_rejects_kernel_overlap(self):
        struct.pack_into("<Q", self.kernel, 16, 130 * 1024 * 1024)
        with self.assertRaises(ValueError):
            h.validate_layout(self.kernel, 1000000, 200000, self.cfg)

    def test_rejects_unaligned_kernel(self):
        self.cfg["kernel_load"] += 0x80000
        with self.assertRaises(ValueError):
            h.validate_layout(self.kernel, 1000000, 200000, self.cfg)

    def test_rejects_overlapping_fdt(self):
        with self.assertRaises(ValueError):
            h.validate_layout(self.kernel, 1000000, 2000000, self.cfg)

    def test_script_addresses_match_profile(self):
        text = (REPO / "compat/hybrid-boot.cmd").read_text()
        for key in ("kernel_load", "env_load", "fdt_load", "initrd_load"):
            self.assertIn(f"0x{self.cfg[key]:08x}", text)
        self.assertIn("boot.mainline.scr", text)
        self.assertIn("panic=0", text)
        self.assertNotIn("saveenv", text)

    def test_cpio_concatenation_and_latest_order(self):
        a = record("scripts/init-premount/ORDER", b"old\n") + record("TRAILER!!!") + b"\0" * 128
        b = record("scripts/init-premount/ORDER", b"new\n") + record("TRAILER!!!")
        names, selected = h.cpio_index(a + b)
        self.assertEqual(len(names), 2)
        self.assertEqual(selected["scripts/init-premount/ORDER"], b"new\n")

    def test_cpio_rejects_traversal_and_absolute_names(self):
        for name in ("../escape", "/absolute", "usr/../../escape"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                h.cpio_index(record(name))

    def test_cpio_rejects_truncation(self):
        with self.assertRaises(ValueError):
            h.cpio_index(record("conf/param.conf", b"12345")[:-8])

    def test_legacy_image_crc(self):
        data = b"compressed ramdisk fixture"
        fields = [0x27051956, 0, 123, len(data), 0, 0, zlib.crc32(data), 5, 22, 3, 1, b"test"]
        header = struct.pack(">7I4B32s", *fields)
        fields[1] = zlib.crc32(header)
        good = struct.pack(">7I4B32s", *fields) + data
        self.assertEqual(h.legacy_payload(good), (123, data))
        with self.assertRaises(ValueError):
            h.legacy_payload(good[:-1] + b"X")

    def test_no_private_trial_configuration_in_sources(self):
        for file in ("compat/hybrid-boot.cmd", "compat/init-premount-panther-hybrid"):
            text = (REPO / file).read_text()
            self.assertNotIn("10.10.10.", text)
            self.assertNotIn("SSHPASS", text)
            self.assertNotIn("/dev/mem", text)


if __name__ == "__main__":
    unittest.main()
