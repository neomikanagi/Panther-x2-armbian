import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/decode_ddr_os_regs.py"
spec = importlib.util.spec_from_file_location("ddr_decode", SCRIPT)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DDRDecodeTests(unittest.TestCase):
    def test_lpddr4x_v3_is_not_ddr4(self):
        value = d.decode(0x10000201, 0x30001021)
        self.assertEqual(value["dram_type"], "LPDDR4X")
        self.assertEqual(value["dram_type_code"], 8)
        self.assertEqual(value["channels"], [{"channel": 0, "bus_width_bits": 32, "ranks": 1}])
        self.assertIsNone(value["manufacturer"])
        self.assertIsNone(value["manufacturing_batch"])

    def test_ddr4_v2_ignores_v3_extension(self):
        value = d.decode(0, 0x20001000)
        self.assertEqual(value["dram_type"], "DDR4")

    def test_ddr3_v2(self):
        self.assertEqual(d.decode(3 << 13, 0x20000000)["dram_type"], "DDR3")

    def test_two_channels_and_bus_widths(self):
        value = d.decode((1 << 12) | (1 << 2) | (2 << 18) | (1 << 27), 0x20000000)
        self.assertEqual(value["channels"], [{"channel": 0, "bus_width_bits": 16, "ranks": 1},
                                            {"channel": 1, "bus_width_bits": 8, "ranks": 2}])

    def test_v3_four_ranks(self):
        self.assertEqual(d.decode(0, 0x30004000)["channels"][0]["ranks"], 4)

    def test_unknown_type_is_not_guessed(self):
        self.assertEqual(d.decode(7 << 13, 0x30003000)["dram_type"], "unknown-31")

    def test_invalid_input(self):
        for a, b in [(-1, 0x30000000), (0, 0x100000000), (0, 0), (0, 0x40000000)]:
            with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                d.decode(a, b)


if __name__ == "__main__":
    unittest.main()
