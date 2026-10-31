# Panther X2 BSP 启动排查

**目标设备的 BSP/eMMC 启动问题尚未解决，尚无可宣称修复成功的新固件。** 用户授权的 6.1.174 杂交诊断重启后，原 IP 的 SSH/ping 未恢复，netconsole 未收到数据；这不能确定卡在引导、内核还是网络阶段。

当前等待给设备断电再通电一次，先不要重刷，以检查是否回到保留的 6.18 正常启动。按 eMMC 线刷方式排查，不要求 TF 卡。

## 实机核实结果

- 试启动前已核实的正常基线是 Debian 13 / `6.18.57-ophub`，从 eMMC 的 ext4 分区启动。
- 内存初始化元数据是 **LPDDR4X、32 位总线、单通道、单 Rank**；内核识别约 4GB（可用总量约 3.8GiB）。这不能确定颗粒厂商或生产批次，也不是内存稳定性测试。
- eMMC 容量标称 32GB，设备名 `DF4032`、厂商 ID `0x45`；当前 HS200 / 200MHz，寿命及 Pre-EOL 字段均为正常初始等级。**eMMC 型号不是 RAM 颗粒型号。**
- 实际 eMMC 内的 `idbloader.img`、`u-boot.itb` 与候选使用的两份 ophub 文件 SHA-256 完全相同。引导空隙有少量 Rockchip vendor-storage 元数据变化，不能把它误判成另一套 DDR/SPL。
- BSP 镜像的根分区 UUID 与 `armbianEnv.txt` 相符，eMMC 驱动内建；BSP DTB 的 `/dmc` 本来就是 `disabled`。因此不能靠重复换同一引导或再关一次 DMC 来认定修复。

**仍不能确诊内存批次或具体驱动。** 本轮已按授权改变启动选择并执行一次诊断重启；原主线 Image/uInitrd/DTB 和引导程序未被覆盖，新 BSP 组件另置 `/boot/hybrid/`。私有备份、日志、DTB 和引导区快照仅保存在被 git 忽略的 `artifacts/`，不公开设备与网络标识。

## 恢复与下一项必需证据

先断电再上电，检查能否回到主线并读取 `/boot/hybrid/trial-status.txt`。试启动 initramfs 会先恢复正常 boot.scr，再继续 BSP 启动；**挂在 init-premount 之前时，这个回退尚未生效，不能保证恢复。** 设备、服务器和 MBA 均有已校验的原 `/boot` 分区与引导区备份；分区备份不是可从地址 0 刷入的整盘固件。

需要失败现场的上电串口日志，区分 DDR/SPL、U-Boot、Linux 初始化、根分区和网络故障。正常基线的 pstore 原为空，本次因失联尚不能读取。调试串口用 **3.3V USB-TTL**，核对引脚，不接 VCC；普通刷机 USB 线不能替代它。新的可能失联启动必须另行确认，不能在本轮授权后盲目循环重启。

## 匹配 BSP 杂交工具

[`compat/hybrid-inputs.json`](compat/hybrid-inputs.json) 固定 ophub `6.1.174-rk35xx-ophub` 整套内核、模块、DTB、initrd。构建器基于同包 Panther DTB 启用 NPU/MPP/RGA/MMU，解析同包电源 phandle，补 NPU IRQ 名；不改 DDR 电压/时序。GPU/display 禁用，定位为 headless NPU/VPU 使用。

- `scripts/prepare_hybrid_payload.py`：校验固定输入、DTB 变换、initrd/ORDER 注入、uImage CRC 和不重叠加载地址；仅生成普通文件，不访问实机。
- `scripts/backup_target_boot.sh`：只读窗口备份 `/boot`、引导区和布局，不刷写、不重启。
- `scripts/install_hybrid_payload.sh`：默认只暂存；显式 `--activate` 才选择新启动。保留原主线组件。
- `scripts/select_hybrid_boot.sh`：显式试启动/验收后启用/恢复正常启动；均不自行重启。
- `scripts/rknn_smoke.c`：调用 RKNN 的真实本机推理测试，零输入不代表模型精度测试。

构建载荷需要 Python 3.12+、dtc/fdtput、cpio、u-boot-tools。36 项单测和相关 ShellCheck 已通过，但这只是离线检查；**本次 RKNN 推理与 MPP 编解码尚未运行，新整盘固件没有合成或发布。** 网络地址、接收端 MAC 和试启动参数仅放私有调试文件，不进入通用载荷。

## 只读取证工具

`scripts/collect_boot_evidence.sh` 通过已授权的 SSH stdin 执行，只读取系统、分区、设备树、现有内核 debugfs 和日志；不刷盘、不重启、不装目标机软件。输出可能含设备与网络标识，必须私下保存，不能提交或上传。

`scripts/decode_ddr_os_regs.py` 只离线解析数值，不访问硬件。位域依据固定版本 Radxa U-Boot 的 `sdram_common.h`、`sdram.h` 与 `grf_rk3568.h`：

```bash
python3 scripts/decode_ddr_os_regs.py --os-reg2 0x10000201 --os-reg3 0x30001021
```

这是编码版本 3；DDR 类型的高位在 OS_REG3，不能只看 OS_REG2 的低三位，否则会把 LPDDR4X 错认成 DDR4。

## 保留的候选构建流程

候选保留 wlxxyw Debian 13 / Rockchip BSP 6.1.115 的内核、DTB、模块和系统分区，只替换分区前引导区；不是重新编译内核。输入、提交、大小及 SHA-256 固定在 [`compat/inputs.json`](compat/inputs.json)。

替换范围是 `[32768,16777216)` 字节，写入 ophub Panther X2 `idbloader.img`（LBA 64）、`u-boot.itb`（LBA 16384），其余空隙按发布参照填零。MBR、主/备 GPT 和所有文件系统字节保持不变。**这是通用发布镜像重打包，不是保存实机 vendor-storage 数据的克隆工具，检测到非空 vendor-storage 的源镜像会被拒绝，避免擦掉设备信息，不能对实机备份直接套用。**

本地与 Actions 的压缩产物均为 624997688 字节，SHA-256：

```text
a09748b7f544de5d62b3b56cc6f6cfbe9ed103126c1dced6a6a93f946ec2c529
```

这些校验只证明来源与改动范围，不证明能启动或 NPU/VPU 可用。预发布保留用于复现，不推荐反复盲刷。原 rootfs 中仍有 Radxa U-Boot 软件包；安装器或升级可能再次覆盖引导。

两个 Actions 均仅手动触发：

- **Panther X2 bootchain compatibility candidate**：固定输入快速重打包；可发布明确标为候选的 prerelease。
- **Build Panther X2 Trixie BSP 6.1**：上游源码全编译后应用相同重打包步骤；该完整路径尚未执行，不能视为已验收。

```bash
python3 -m unittest discover -s tests -v
bash scripts/build_bootchain_candidate.sh
```

构建器仅接受普通镜像文件，拒绝设备、符号链接、已有输出、坏 GPT、不符的布局或输入校验值，不包含刷盘动作。NPU/VPU 的最终验收必须包含 RKNN 推理与 MPP 硬件编解码，不能只看驱动配置或节点。

## 上游

[wlxxyw/Panther-x2-armbian](https://github.com/wlxxyw/Panther-x2-armbian) · [clfang666/Panther-x2-NPU-VPU](https://github.com/clfang666/Panther-x2-NPU-VPU) · [ophub/u-boot](https://github.com/ophub/u-boot) · [ophub/amlogic-s9xxx-armbian](https://github.com/ophub/amlogic-s9xxx-armbian) · [Armbian build](https://github.com/armbian/build) · [Rockchip kernel](https://github.com/armbian/linux-rockchip) · [Radxa U-Boot](https://github.com/radxa/u-boot)

上游源码、模型及固件继续遵循各自许可；本 fork 不重新声明上游资产的许可。
