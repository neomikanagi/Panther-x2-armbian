# Panther X2 headless BSP profile. Original Image/uInitrd/DTB remain untouched.
# The kernel has text_offset=0: use a 2 MiB-aligned address, above scriptaddr.
setenv hybrid_saved_kernel ${kernel_addr_r}
setenv hybrid_saved_fdt ${fdt_addr_r}
setenv hybrid_saved_ramdisk ${ramdisk_addr_r}
setenv kernel_addr_r 0x02000000
setenv fdt_addr_r 0x0a100000
setenv ramdisk_addr_r 0x0a200000
setenv load_addr 0x08000000
setenv rootdev /dev/mmcblk0p2
setenv rootfstype ext4
setenv rootflags rw,errors=remount-ro
setenv extraargs
setenv extraboardargs
setenv hybrid_extraargs
if test -z "${distro_bootpart}"; then setenv distro_bootpart 1; fi
setenv hybrid_devpart ${devnum}:${distro_bootpart}
echo "Panther hybrid: ${devtype} ${hybrid_devpart} ${prefix}"
if load ${devtype} ${hybrid_devpart} ${load_addr} ${prefix}armbianEnv.txt; then
    env import -t ${load_addr} ${filesize}
fi
# Optional private diagnostic settings are NOT included in generic firmware.
if test -e ${devtype} ${hybrid_devpart} ${prefix}hybrid-debug.env; then
    if load ${devtype} ${hybrid_devpart} ${load_addr} ${prefix}hybrid-debug.env; then
        env import -t ${load_addr} ${filesize}
    fi
fi
part uuid ${devtype} ${hybrid_devpart} partuuid
setenv bootargs "root=${rootdev} rootwait rootfstype=${rootfstype} rootflags=${rootflags} earlycon=uart8250,mmio32,0xfe660000 console=ttyS2,1500000n8 console=tty0 loglevel=7 log_buf_len=4M noresume cma=256M panic=0 net.ifnames=0 ${extraargs} ${extraboardargs} cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory ubootpart=${partuuid} ${hybrid_extraargs}"
if load ${devtype} ${hybrid_devpart} ${ramdisk_addr_r} ${prefix}hybrid/uInitrd; then
    if load ${devtype} ${hybrid_devpart} ${kernel_addr_r} ${prefix}hybrid/vmlinuz; then
        if load ${devtype} ${hybrid_devpart} ${fdt_addr_r} ${prefix}hybrid/rk3566-panther-x2.dtb; then
            fdt addr ${fdt_addr_r}
            fdt resize 65536
            echo "Starting matched Panther X2 BSP kernel/DTB/initrd"
            booti ${kernel_addr_r} ${ramdisk_addr_r} ${fdt_addr_r}
        fi
    fi
fi
# This handles load/booti errors only, NOT hangs inside the kernel.
echo "Hybrid boot returned: falling back to unchanged mainline boot script"
setenv kernel_addr_r ${hybrid_saved_kernel}
setenv fdt_addr_r ${hybrid_saved_fdt}
setenv ramdisk_addr_r ${hybrid_saved_ramdisk}
if load ${devtype} ${hybrid_devpart} ${scriptaddr} ${prefix}hybrid/boot.mainline.scr; then
    source ${scriptaddr}
fi
