#!/usr/bin/env bash
# Explicit boot selection only. Never reboots, writes U-Boot, or changes DDR settings.
set -euo pipefail
mode=${1:-}
[[ "$mode" == --trial || "$mode" == --promote || "$mode" == --normal ]] || {
  echo 'Usage: select_hybrid_boot.sh --trial|--promote|--normal (NO reboot)' >&2; exit 2;
}
[[ "$(id -u)" == 0 && "$(uname -m)" == aarch64 ]] || exit 1
tr '\000' '\n' </proc/device-tree/model | grep -qx 'Panther X2'
base=/boot/hybrid
read -r version < "$base/kernel.version"
[[ "$version" == 6.1.174-rk35xx-ophub ]] || exit 1
(cd "$base"; sha256sum -c SHA256SUMS)
case "$mode" in
  --trial)
    [[ "$(uname -r)" == 6.18.57-ophub && ! -e "$base/trial-requested.txt" ]] || exit 1
    [[ -r /boot/hybrid-debug.env ]] && grep -q 'hybrid_trial=1' /boot/hybrid-debug.env
    read -r backup < /root/panther-hybrid-backup.path
    sha256sum -c "$backup/original-boot-files.sha256"
    date -u -Is > "$base/trial-requested.txt"
    selected="$base/boot.hybrid.scr"
    ;;
  --promote)
    [[ "$(uname -r)" == "$version" && -s "$base/hardware-validation.json" ]] || exit 1
    grep -q '"all_tests_passed": true' "$base/hardware-validation.json"
    if [[ -f /boot/hybrid-debug.env ]]; then
      read -r backup < /root/panther-hybrid-backup.path
      mv /boot/hybrid-debug.env "$backup/hybrid-debug.env"
    fi
    selected="$base/boot.hybrid.scr"
    ;;
  --normal)
    selected="$base/boot.mainline.scr"
    ;;
esac
cp "$selected" /boot/boot.scr.selection-new
mv /boot/boot.scr.selection-new /boot/boot.scr
sync
printf 'Boot selection %s installed. NO reboot issued.\n' "$mode"
