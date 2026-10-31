# 多 AI 交接

## 2026-11-01 — pi（gpt-6.1-sol）→ 等待诊断启动条件

- **状态：** 用户反馈 eMMC 线刷仍不启动，已恢复 ophub `6.18.57` 供检查；启动问题未修复。本轮 SSH 只读检查，未装目标机软件、未改引导或内核、未重启；结束时启动文件哈希与取证开始相同。不要把前条离线生成通过当成实机成功，也不要再把 TF 卡当作唯一排查方式。
- **改了：** 新增 `scripts/collect_boot_evidence.sh`、离线 DDR 编码解析器及 7 项测试；补充重打包器对非空 Rockchip vendor-storage 的拒绝保护，避免对实机克隆误填零。26 项单测及两个 ShellCheck 通过。README / prerelease 的结论改为 eMMC 启动未解决，旧镜像仅保留复现，不另发未经验证的“修复版”。
- **为什么·证据：** 实机 eMMC 中两份引导文件与固定 ophub 文件 SHA-256 一致；全 gap 仅在 vendor-storage 三个扇区不同，不能把整个 gap 哈希不同当成另一套 DDR 引导。4GB RAM 初始化元数据按编码 v3 解析为 LPDDR4X、32bit、单通道单 Rank：OS_REG2=`0x10000201`，OS_REG3=`0x30001021`。类型高位在 REG3，忽略会错判 DDR4；总线宽度是 `8 * 2^bw_shift`，不能直接把 shift 当字节数。制造商/批次无法从这里得到；eMMC DF4032 不是内存颗粒型号。
- **排除与边界：** 原 BSP 根 UUID 与 ext4 超级块匹配，eMMC 驱动内建，DMC DT 节点本来已 disabled。正常和失败内核 Image 的 text_offset 不同，但 Radxa booti 会按 flags/对齐重定位，不能仅凭这个差异就修改 Image 头宣称修复。DDR 频率、供电、内核和 DTB 兼容仍需失败启动证据，不能据正常内核推断根因。
- **取证位置：** 本地 `artifacts/live-20261031/`（git 忽略）含日志、实机引导区、静态/运行中 DTB、内存寄存器解码、存储健康及最终只读复核。含网络/设备标识的原始材料不提交、不放 GitHub。直接 `/dev/mem` 读取被内核拒绝，未继续 raw MMIO；通过现有内核 regmap 的有界只读视图取得 OS_REG2/3。dtc 仅装在自己的 Pi 工人，不在目标设备安装。
- **请你：** 当前正常内核的 pstore 为空，无法追溯上一次失败。等用户确认 A：接 3.3V USB-TTL 后抓失败镜像的完整上电日志（优先，不改现有系统）；或 B：明确授权一次可能失联、需人工线刷恢复的诊断启动，再备份并保留正常启动文件做受控测试。MBA 当前未发现 USB 串口设备；未获授权前不切内核、不重启目标。

## 2026-10-31 — pi → 实机验证

- **状态：** 兼容候选已完成本地与 GitHub Actions 两次独立离线生成，压缩镜像 SHA-256 完全一致（`a09748b7f544de5d62b3b56cc6f6cfbe9ed103126c1dced6a6a93f946ec2c529`，624997688 字节）。Actions `41206370109` 全部成功，已发布 `bootchain-candidate-1` prerelease，并已转存至用户 MBA 下载目录、完整 SHA-256 复核通过。当前缺 TF 卡实物与覆盖确认；现有外接盘未操作。尚未上电验证；NPU/VPU 运行未验收。18 项合成 GPT 测试、ShellCheck、YAML 解析通过。完整源码编译路径已接入相同重打包步骤，但没有执行数小时全编译。
- **改了：** `compat/inputs.json` 固定失败镜像及 Panther X2 引导文件；`scripts/graft_bootchain.py` 检查 GPT/校验值且只生成普通文件，拒绝设备、符号链接和覆盖；`scripts/build_bootchain_candidate.sh` 下载校验、打包与压缩；新增手动 Actions，原全编译也改为手动并应用同一引导替换；README 只写现状与实机边界。
- **为什么·思路：** 用户确认 wlxxyw build 13 不启动，ophub `6.18.57_server_2026.10.17` 能启动。两份完整下载的压缩镜像 SHA-256 均与 GitHub release digest 一致。成功参照 `[32768,16777216)` 的全部字节等于固定 ophub/u-boot 提交的两份文件加零填充，整个区间 SHA-256 为 `2d61b73387e90d97e4401b48e5efe886b3d46702072878033d5d18680fb88c1e`。故先替换整段引导空隙，消除原引导与陈旧环境，保留 GPT/MBR 和全部文件系统字节不变，避免混用另一内核 DTB/模块。不能据此断定 DDR 批次问题，也不能保证旧 BL31 与 BSP DMC 的兼容性。
- **证据：** 本地候选原始镜像 SHA-256 `4e7e4df5c44943eb88ece4339132bdfd4079abe098d445dd80f162546e06ac6b`，3015704576 字节；保护区前后 SHA-256 一致，报告明确 `hardware_boot_tested=false`、`npu_vpu_runtime_tested=false`。机器生成报告与大镜像不进 git，由 Actions artifact / prerelease 交付。
- **请你：** 下一步仅需空闲 TF 实机验证。确认根分区确实来自候选 TF，再做 RKNN 推理及 MPP 编解码。若失败收集从上电开始的串口日志；不要先擦 eMMC。rootfs 中保留了原 Radxa U-Boot 包，实测前不要升级/重装 U-Boot 或运行安装器覆盖兼容引导。不要把静态构建报告当作实机通过；不要为降低变量把 BSP DTB 换成 mainline DTB。
