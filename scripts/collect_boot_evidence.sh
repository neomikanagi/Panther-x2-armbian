#!/usr/bin/env bash
# Run on an explicitly authorized Linux device via SSH stdin. Read-only commands.
# Raw output may contain device/network identifiers: keep it private, never commit it.
set -u
section() { printf '\n===== %s =====\n' "$*"; }
section SYSTEM
date -Is
uname -a
uptime
for f in /etc/os-release /etc/armbian-release /etc/ophub-release /proc/cmdline; do
  if [[ -r "$f" ]]; then printf '\n--- %s ---\n' "$f"; head -c 16384 "$f"; printf '\n'; fi
done
section MEMORY
free -h
head -n 12 /proc/meminfo
section BLOCK_LAYOUT
lsblk -b -o NAME,PATH,TYPE,SIZE,FSTYPE,MOUNTPOINTS,RO
findmnt -no SOURCE,FSTYPE,OPTIONS /
findmnt -no SOURCE,FSTYPE,OPTIONS /boot || true
for f in /sys/class/block/mmcblk*/device/{type,name,manfid,oemid,date,fwrev}; do
  if [[ -r "$f" ]]; then printf '%s: ' "$f"; head -c 128 "$f"; printf '\n'; fi
done
section BOOT_FILES
ls -l /boot
for f in /boot/armbianEnv.txt /boot/extlinux/extlinux.conf; do
  if [[ -r "$f" ]]; then printf '\n--- %s ---\n' "$f"; head -c 8192 "$f"; printf '\n'; fi
done
for f in /boot/Image /boot/dtb/rockchip/rk3566-panther-x2.dtb /usr/lib/u-boot/idbloader.img /usr/lib/u-boot/u-boot.itb; do
  if [[ -r "$f" ]]; then sha256sum "$f"; fi
done
section DT_MEMORY_AND_CHOSEN
for d in /sys/firmware/devicetree/base/chosen /sys/firmware/devicetree/base/memory*; do
  if [[ -d "$d" ]]; then ls -la "$d"; fi
done
for f in /sys/firmware/devicetree/base/model /sys/firmware/devicetree/base/compatible; do
  if [[ -r "$f" ]]; then printf '%s: ' "$f"; tr '\000' '\n' < "$f"; fi
done
section DEVFREQ
for d in /sys/class/devfreq/*; do
  [[ -e "$d" ]] || continue
  printf '\n--- %s ---\n' "$d"
  for key in name governor cur_freq available_frequencies; do
    if [[ -r "$d/$key" ]]; then printf '%s: ' "$key"; head -c 2048 "$d/$key"; printf '\n'; fi
  done
done
section DDR_KERNEL_METADATA
# Use the kernel's existing, bounded regmap view, never /dev/mem or register writes.
for f in /sys/kernel/debug/regmap/*fdc20000*/registers; do
  if [[ -r "$f" ]]; then printf '\n--- %s (bounded prefix) ---\n' "$f"; head -c 2300 "$f"; printf '\n'; fi
done
for f in /sys/kernel/debug/clk/clk_ddr1x/clk_rate /sys/kernel/debug/clk/clk_scmi_ddr/clk_rate /sys/kernel/debug/mmc0/ios; do
  if [[ -r "$f" ]]; then printf '\n--- %s ---\n' "$f"; head -c 4096 "$f"; printf '\n'; fi
done
section ACCELERATOR_DEVICES
for f in /dev/rknpu /dev/mpp_service /dev/rga /dev/video* /dev/dri/*; do
  if [[ -e "$f" ]]; then ls -l "$f"; fi
done
if [[ -r "/boot/config-$(uname -r)" ]]; then
  grep -E 'CONFIG_(ROCKCHIP.*(DMC|DMCFREQ|RKNPU|MPP|RGA)|ARM_ROCKCHIP_DMC_DEVFREQ|MMC_DW|MMC_SDHCI|ROCKCHIP_IODOMAIN|PSTORE|RAMOOPS)' "/boot/config-$(uname -r)" || true
fi
section PSTORE
if [[ -d /sys/fs/pstore ]]; then
  ls -la /sys/fs/pstore
  for f in /sys/fs/pstore/*; do
    if [[ -f "$f" ]]; then printf '\n--- %s ---\n' "$f"; head -c 131072 "$f"; printf '\n'; fi
  done
fi
section KERNEL_LOG
dmesg --color=never
