# Panther X2 BSP 启动排查

**目标设备的 eMMC 启动问题尚未解决。`bootchain-candidate-1` 不能视为已验证可用的固件。** 用户反馈 eMMC 线刷不启动，已恢复可启动的 ophub 6.18.57 供只读检查；不再用“静态打包通过”代替启动通过，也不要求必须先用 TF 卡。

## 实机核实结果

- 正常系统是 Debian 13 / `6.18.57-ophub`，从 eMMC 的 ext4 分区启动。
- 内存初始化元数据是 **LPDDR4X、32 位总线、单通道、单 Rank**；内核识别约 4GB（可用总量约 3.8GiB）。这不能确定颗粒厂商或生产批次，也不是内存稳定性测试。
- eMMC 容量标称 32GB，设备名 `DF4032`、厂商 ID `0x45`；当前 HS200 / 200MHz，寿命及 Pre-EOL 字段均为正常初始等级。**eMMC 型号不是 RAM 颗粒型号。**
- 实际 eMMC 内的 `idbloader.img`、`u-boot.itb` 与候选使用的两份 ophub 文件 SHA-256 完全相同。引导空隙有少量 Rockchip vendor-storage 元数据变化，不能把它误判成另一套 DDR/SPL。
- BSP 镜像的根分区 UUID 与 `armbianEnv.txt` 相符，eMMC 驱动内建；BSP DTB 的 `/dmc` 本来就是 `disabled`。因此不能靠重复换同一引导或再关一次 DMC 来认定修复。

目前只能把问题继续缩小到 BSP 内核、设备树及启动流程；**仍不能确诊内存批次或具体驱动。** 当前可启动系统未被替换内核、改写引导或重启；原始日志、DTB 和引导区快照保存在本地 git 忽略的 `artifacts/`，含设备标识的原始数据不公开。

## 下一项必需证据

需要失败镜像从上电开始的串口日志，区分 DDR/SPL、U-Boot、Linux 初始化、根分区挂载和仅网络未起来。已经刷回正常系统后，SSH 只能提供正常内核的日志；本次 pstore 为空，无法追溯之前的失败现场。

调试串口必须是 **3.3V USB-TTL**，不是普通刷机 USB 线；连接前核对板上引脚，不接 VCC。没有串口时，任何可能失联的诊断启动，都要先取得重启及人工恢复确认，而不是直接覆盖这套正常系统。

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
