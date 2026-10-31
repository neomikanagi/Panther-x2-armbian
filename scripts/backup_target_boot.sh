#!/usr/bin/env bash
# Run only on the explicitly authorized Panther X2. No reboot or bootloader writes.
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'root required' >&2; exit 1; }
[[ "$(uname -r)" == 6.18.57-ophub ]] || { echo 'Unexpected running kernel' >&2; exit 1; }
[[ "$(findmnt -no SOURCE /boot)" == /dev/mmcblk0p1 ]] || { echo 'Unexpected boot device' >&2; exit 1; }
[[ "$(findmnt -no FSTYPE /boot)" == ext4 ]] || exit 1
(( $(df -PB1 / | awk 'NR==2 {print $4}') > 1073741824 )) || exit 1
backup="/root/panther-hybrid-backup-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$backup"
printf '%s\n' "$backup" > /root/panther-hybrid-backup.path
uname -a > "$backup/kernel.txt"
findmnt > "$backup/mounts.txt"
sfdisk --dump /dev/mmcblk0 > "$backup/partition-table.sfdisk"
sha256sum /boot/Image /boot/uInitrd /boot/boot.scr /boot/armbianEnv.txt \
  /boot/dtb/rockchip/rk3566-panther-x2.dtb > "$backup/original-boot-files.sha256"
sync
# A clean, read-only boot filesystem gives a consistent raw partition backup.
mount -o remount,ro /boot
trap 'mount -o remount,rw /boot' EXIT
dd if=/dev/mmcblk0p1 bs=4M iflag=fullblock status=none | gzip -1 > "$backup/boot-partition.img.gz"
tar --numeric-owner --xattrs --acls -C / -czf "$backup/boot-files.tar.gz" boot \
  etc/armbian-release etc/ophub-release etc/fstab etc/initramfs-tools etc/modprobe.d
dd if=/dev/mmcblk0 bs=1M count=16 iflag=fullblock status=none > "$backup/emmc-prefix-16MiB.bin"
mount -o remount,rw /boot
trap - EXIT
(cd "$backup"; sha256sum boot-partition.img.gz boot-files.tar.gz emmc-prefix-16MiB.bin > SHA256SUMS; sha256sum -c SHA256SUMS)
cat > "$backup/restore-boot-files.sh" <<'RESTORE'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == --restore-boot-files ]] || { echo 'Explicit --restore-boot-files required; does not reboot.' >&2; exit 2; }
cd "$(dirname "$0")"
sha256sum -c SHA256SUMS
tar --same-owner --numeric-owner --xattrs --acls -C / -xzf boot-files.tar.gz
sync
echo 'Original boot files restored. Added hybrid files/modules are left unused. No reboot issued.'
RESTORE
chmod 700 "$backup/restore-boot-files.sh"
printf 'BACKUP_COMPLETE=%s\n' "$backup"
ls -lh "$backup"
