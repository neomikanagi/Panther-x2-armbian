#!/usr/bin/env bash
# Stage only by default. --activate changes boot.scr, never reboots or writes U-Boot.
set -euo pipefail
payload=""
root=""
live=false
activate=false
while (($#)); do
  case "$1" in
    --payload) payload="$2"; shift 2 ;;
    --root) root="$2"; shift 2 ;;
    --live) live=true; root=/; shift ;;
    --activate) activate=true; shift ;;
    *) echo 'Usage: install_hybrid_payload.sh --payload DIR (--live|--root IMAGE_MOUNT) [--activate]' >&2; exit 2 ;;
  esac
done
[[ -n "$payload" && -n "$root" && -d "$root" ]] || exit 2
payload=$(cd "$payload" && pwd)
root=$(cd "$root" && pwd)
prefix=${root%/}
boot="${prefix}/boot"
[[ -f "$payload/SHA256SUMS" && -d "$boot" && ! -L "$boot" ]] || exit 1
(cd "$payload"; sha256sum -c SHA256SUMS)
read -r version < "$payload/kernel.version"
[[ "$version" == 6.1.174-rk35xx-ophub ]] || { echo 'Unexpected kernel version' >&2; exit 1; }
if [[ "$root" == / ]]; then
  $live || { echo 'Root filesystem requires explicit --live' >&2; exit 1; }
  [[ "$(id -u)" == 0 && "$(uname -m)" == aarch64 ]] || exit 1
  tr '\000' '\n' </proc/device-tree/model | grep -qx 'Panther X2'
  [[ "$(uname -r)" == 6.18.57-ophub ]] || { echo 'Only stage from verified mainline baseline' >&2; exit 1; }
  [[ "$(findmnt -no SOURCE /boot)" == /dev/mmcblk0p1 ]] || exit 1
  read -r backup < /root/panther-hybrid-backup.path
  [[ "$backup" == /root/panther-hybrid-backup-* && -s "$backup/boot-partition.img.gz" ]] || exit 1
  (cd "$backup"; sha256sum -c SHA256SUMS)
fi
[[ -f "$boot/boot.scr" && -f "$boot/armbianEnv.txt" && -d "$prefix/usr/lib/modules" ]] || exit 1
(( $(df -PB1 "$boot" | awk 'NR==2 {print $4}') > 100000000 )) || { echo 'Insufficient boot space' >&2; exit 1; }
(( $(df -PB1 "$root" | awk 'NR==2 {print $4}') > 600000000 )) || { echo 'Insufficient root space' >&2; exit 1; }
[[ ! -e "$boot/hybrid" && ! -e "$prefix/usr/lib/modules/$version" ]] || { echo 'Hybrid output already exists' >&2; exit 1; }
# Verify all module archive members stay under the expected ABI directory.
while IFS= read -r path; do
  [[ "$path" == "$version" || "$path" == "$version/"* ]] || exit 1
  [[ "/$path/" != *'/../'* && "$path" != /* ]] || exit 1
done < <(tar -tzf "$payload/modules.tar.gz")
mkdir "$boot/hybrid"
cp -a "$boot/boot.scr" "$boot/hybrid/boot.mainline.scr"
cp -a "$boot/armbianEnv.txt" "$boot/hybrid/armbianEnv.mainline.txt"
for f in vmlinuz initrd.img uInitrd config System.map rk3566-panther-x2.dtb kernel.version boot.cmd boot.hybrid.scr manifest.json; do
  install -m 644 "$payload/$f" "$boot/hybrid/$f"
done
tar -xzf "$payload/modules.tar.gz" -C "$prefix/usr/lib/modules"
# Keep original Image, uInitrd, dtb and boot.cmd unchanged for recovery.
install -m 644 "$payload/config" "$boot/config-$version"
install -m 644 "$payload/System.map" "$boot/System.map-$version"
printf 'profile=panther-x2-headless-npu-vpu\nkernel=%s\n' "$version" > "$prefix/etc/panther-hybrid-release"
(
  cd "$boot/hybrid"
  sha256sum vmlinuz initrd.img uInitrd config System.map rk3566-panther-x2.dtb kernel.version boot.cmd boot.hybrid.scr manifest.json boot.mainline.scr armbianEnv.mainline.txt > SHA256SUMS
  sha256sum -c SHA256SUMS
)
if $activate; then
  cp "$boot/hybrid/boot.hybrid.scr" "$boot/boot.scr.hybrid-new"
  mv "$boot/boot.scr.hybrid-new" "$boot/boot.scr"
  echo 'Hybrid boot script activated. NO reboot issued.'
else
  echo 'Hybrid staged; original boot selection unchanged. NO reboot issued.'
fi
sync
