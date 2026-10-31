#!/usr/bin/env python3
"""Offline Rockchip DDR OS_REG2/3 decoder. Does not access hardware or /dev/mem.

Bit fields: Radxa U-Boot c55987146f4f9b20f7cb2f917ca88300419afe8d,
arch/arm/include/asm/arch-rockchip/{sdram_common.h,sdram.h,grf_rk3568.h}.
RK3568 PMUGRF OS_REG2/3 are at offsets 0x208/0x20c. On RK3566 the
existing kernel regmap debugfs view can expose them without raw MMIO.
Encoding v3 extends DDR type into OS_REG3 bits 13:12: ignoring those bits
misidentifies LPDDR4X (8) as DDR4 (0). Registers do NOT identify RAM batches.
"""
import argparse
import json

TYPES = {0: "DDR4", 2: "DDR2", 3: "DDR3", 5: "LPDDR2", 6: "LPDDR3",
         7: "LPDDR4", 8: "LPDDR4X", 9: "LPDDR5", 10: "DDR5"}


def decode(reg2: int, reg3: int) -> dict:
    if not all(isinstance(x, int) and 0 <= x <= 0xFFFFFFFF for x in (reg2, reg3)):
        raise ValueError("Registers must be unsigned 32-bit integers")
    version = (reg3 >> 28) & 15
    if version not in (2, 3):
        raise ValueError(f"Unsupported DDR register encoding version: {version}")
    dram_type = (reg2 >> 13) & 7
    if version == 3:
        dram_type |= ((reg3 >> 12) & 3) << 3
    channels = 1 + ((reg2 >> 12) & 1)
    info = []
    for ch in range(channels):
        bw_shift = 2 >> ((reg2 >> (2 + 16 * ch)) & 3)
        if version == 3 and ch == 0:
            ranks = 1 << (((reg2 >> 11) & 1) | (((reg3 >> 14) & 1) << 1))
        else:
            ranks = 1 + ((reg2 >> (11 + 16 * ch)) & 1)
        info.append({"channel": ch, "bus_width_bits": 8 * (1 << bw_shift), "ranks": ranks})
    return {
        "os_reg2": f"0x{reg2:08x}", "os_reg3": f"0x{reg3:08x}",
        "encoding_version": version, "dram_type_code": dram_type,
        "dram_type": TYPES.get(dram_type, f"unknown-{dram_type}"),
        "channels": info,
        "manufacturer": None, "part_number": None, "manufacturing_batch": None,
        "note": "Boot-firmware metadata, not a memory stress test or proof of BSP compatibility. RAM capacity must be independently checked. Manufacturer/batch is not encoded here.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--os-reg2", required=True, type=lambda s: int(s, 0))
    parser.add_argument("--os-reg3", required=True, type=lambda s: int(s, 0))
    args = parser.parse_args()
    try:
        result = decode(args.os_reg2, args.os_reg3)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
