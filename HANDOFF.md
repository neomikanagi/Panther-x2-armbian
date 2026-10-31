# 多 AI 交接

## 2026-11-01 — pi（gpt-6.1-sol）→ 等待实物断电再通电

- **状态：pending。** 已执行用户授权 B 的一次诊断重启；重启后原 IP 的 SSH 和两端 ping 均无回复。MBA 的 UDP 接收器预检通过、重启前已清空连接状态，事后仍在监听，但 netconsole 为 0 字节；mDNS 的 armbian.local/panther-x2.local 亦未解析。不能据此断定内核停在 initramfs 之前，也没有排除网络未起来或地址变化，不能宣称修复/确诊 RAM 批次。
- **已做：** `d3ff2da` 提交了固定 SHA 的 6.1.174 匹配载荷、headless DTB 修正、initrd 试启动回退与受控启动选择工具；36 项离线单测、Bash 脚本 ShellCheck 通过。原 Image/uInitrd/DTB 哈希在激活前通过；boot.scr 已改为已校验的 hybrid 脚本后才重启。新模块和本机 RKNN/MPP 测试程序已暂存，但因未能回连，**没有运行 NPU/VPU 硬件验收，也没有合成/发布新整盘固件。**
- **为什么停：** 失败现场没有串口日志，网络日志也没到达；继续换内核/DTB盲试会丢失当前现场，且本轮只安排一次风险启动。已向用户请求先断电再通电一次、先不要重刷，并用 Signal AGENT `--force` 喊人。若 init-premount 曾运行，下一次应尝试保留的主线 boot.scr；若更早挂住，回退可能未生效。
- **请你：** 等用户确认重新通电，再只读检查连通性、uname、`/boot/hybrid/trial-status.txt`、`trial-kernel.txt`、boot.scr 校验值、journal/pstore。读私有 `artifacts/hybrid-20261101/` 中的 reboot-trial、post-trial、receiver 和备份记录接续；地址/凭据不写公开文档。仍不能恢复时再协调原可启动镜像线刷或 3.3V UART，不要求 TF 卡，不自动安排第二次可能失联的启动。
- **恢复材料：** 目标 `/root/panther-hybrid-backup-20261031T180303Z/`；服务器 `artifacts/hybrid-20261101/recovery/`；MBA `Downloads/Panther-X2-Hybrid-Recovery-20261101/`。MBA 的 boot 分区镜像和 eMMC 前缀 SHA 已核对；`README.md` 明确这是分区备份，禁止当整盘从地址 0 乱刷。保留原引导程序、正常系统组件和 private vendor-storage；不要撤销这些保护或把实机快照发 GitHub。

## 2026-11-01 — pi（gpt-6.1-sol）→ 授权 B 诊断启动检查点

- **状态：** 用户已明确回复「b！最好能一次性为我做出杂交固件」，授权一次可能失联、需线刷恢复的诊断启动。已完成备份、源码/载荷校验和文件暂存；写本条时仍是正常 6.18.57，尚未执行本轮重启。36 项单测、相关 ShellCheck 通过。
- **方案：** 不再复用失败的 6.1.115 rootfs，也不混用主线 DTB。保留当前可启动 ophub 用户空间与原有 Image/uInitrd/DTB，采用固定 SHA-256 的 ophub `kernel_rk35xx/6.1.174.tar.gz` 整套内核、模块、DTB、initrd；基于同包 Panther DTB 按符号启用 NPU/MPP/RGA/MMU，并解析同包 vdd_npu/vdd_logic phandle，不动 DDR 电压/时序。GPU/display 禁用，定位为 headless NPU/VPU 工位。
- **启动与恢复：** 内核显式加载到 2MiB 对齐的 32MiB，环境暂存 128MiB，DTB/ramdisk 161/162MiB，离线检查区域不重叠。`select_hybrid_boot.sh --trial` 只选启动项、绝不自行重启。试启动 init-premount 会先把 boot.scr 恢复为保留的主线脚本，再继续这次 BSP 启动；若后续 panic 则可重启回主线。挂在更早阶段仍可能失联，不能承诺自动恢复。只安排本轮授权的一次诊断启动，不盲目循环重启。
- **备份：** 目标 `/root/panther-hybrid-backup-20261031T180303Z/` 有干净只读 /boot 分区镜像、原始 boot 文件归档、eMMC 前 16MiB、分区表与显式恢复脚本；已复制到本地 `artifacts/hybrid-20261101/recovery/` 和 MBA 的 `Downloads/Panther-X2-Hybrid-Recovery-20261101/` 并核对 SHA。这些是私有恢复材料，不是可从地址 0 刷入的整盘镜像，绝不发布 GitHub。
- **取证：** 私有 `hybrid-debug.env` 仅本次试启动使用；MBA 临时 UDP netconsole 接收器已做路径测试，再重启为空白监听，避免 BSD nc 绑定到预检随机源端口。地址/MAC/密码不进源码或公共载荷。目标 `/boot/hybrid/` 是匹配载荷，模块目录已加入；原始启动选择在检查点尚未改变。
- **下一步：** 激活试启动、核对原启动文件及载荷哈希后执行唯一一次诊断重启；若能 SSH 返回，运行 `/opt/panther-hybrid/` 的真实 RKNN 推理以及 MPP H.264 解码/编码，不能用设备节点代替验收。成功后写硬件验收报告并 promote，再以干净的原始 ophub 发布镜像合成可刷 eMMC 的通用固件，不能克隆实机私有数据。若失败，保留 netconsole 和试启动标记，恢复正常系统，不把候选叫修复成功。

## 2026-11-01 — pi（gpt-6.1-sol）→ 等待诊断启动条件

- **状态：** 用户反馈 eMMC 线刷仍不启动，已恢复 ophub `6.18.57` 供检查；启动问题未修复。本轮 SSH 只读检查，未装目标机软件、未改引导或内核、未重启；结束时启动文件哈希与取证开始相同。不要把前条离线生成通过当成实机成功，也不要再把 TF 卡当作唯一排查方式。
- **改了：** 新增 `scripts/collect_boot_evidence.sh`、离线 DDR 编码解析器及 7 项测试；补充重打包器对非空 Rockchip vendor-storage 的拒绝保护，避免对实机克隆误填零。26 项单测及两个 ShellCheck 通过。README / prerelease 的结论改为 eMMC 启动未解决，旧镜像仅保留复现，不另发未经验证的“修复版”。
- **为什么·证据：** 实机 eMMC 中两份引导文件与固定 ophub 文件 SHA-256 一致；全 gap 仅在 vendor-storage 三个扇区不同，不能把整个 gap 哈希不同当成另一套 DDR 引导。4GB RAM 初始化元数据按编码 v3 解析为 LPDDR4X、32bit、单通道单 Rank：OS_REG2=`0x10000201`，OS_REG3=`0x30001021`。类型高位在 REG3，忽略会错判 DDR4；总线宽度是 `8 * 2^bw_shift`，不能直接把 shift 当字节数。制造商/批次无法从这里得到；eMMC DF4032 不是内存颗粒型号。
- **排除与边界：** 原 BSP 根 UUID 与 ext4 超级块匹配，eMMC 驱动内建，DMC DT 节点本来已 disabled。正常和失败内核 Image 的 text_offset 不同，但 Radxa booti 会按 flags/对齐重定位，不能仅凭这个差异就修改 Image 头宣称修复。DDR 频率、供电、内核和 DTB 兼容仍需失败启动证据，不能据正常内核推断根因。
- **取证位置：** 本地 `artifacts/live-20261031/`（git 忽略）含日志、实机引导区、静态/运行中 DTB、内存寄存器解码、存储健康及最终只读复核。含网络/设备标识的原始材料不提交、不放 GitHub。直接 `/dev/mem` 读取被内核拒绝，未继续 raw MMIO；通过现有内核 regmap 的有界只读视图取得 OS_REG2/3。dtc 仅装在自己的 Pi 工人，不在目标设备安装。
- **请你：** 当前正常内核的 pstore 为空，无法追溯上一次失败。等用户确认 A：先接 3.3V USB-TTL，核对连接及恢复条件后安排失败启动取证（优先，不预先改写正常系统）；或 B：明确授权一次可能失联、需人工线刷恢复的诊断启动，再备份并保留正常启动文件做受控测试。MBA 当前未发现 USB 串口设备；未获授权前不切内核、不重启目标。

## 2026-10-31 — pi → 实机验证

- **状态：** 兼容候选已完成本地与 GitHub Actions 两次独立离线生成，压缩镜像 SHA-256 完全一致（`a09748b7f544de5d62b3b56cc6f6cfbe9ed103126c1dced6a6a93f946ec2c529`，624997688 字节）。Actions `41206370109` 全部成功，已发布 `bootchain-candidate-1` prerelease，并已转存至用户 MBA 下载目录、完整 SHA-256 复核通过。当前缺 TF 卡实物与覆盖确认；现有外接盘未操作。尚未上电验证；NPU/VPU 运行未验收。18 项合成 GPT 测试、ShellCheck、YAML 解析通过。完整源码编译路径已接入相同重打包步骤，但没有执行数小时全编译。
- **改了：** `compat/inputs.json` 固定失败镜像及 Panther X2 引导文件；`scripts/graft_bootchain.py` 检查 GPT/校验值且只生成普通文件，拒绝设备、符号链接和覆盖；`scripts/build_bootchain_candidate.sh` 下载校验、打包与压缩；新增手动 Actions，原全编译也改为手动并应用同一引导替换；README 只写现状与实机边界。
- **为什么·思路：** 用户确认 wlxxyw build 13 不启动，ophub `6.18.57_server_2026.10.17` 能启动。两份完整下载的压缩镜像 SHA-256 均与 GitHub release digest 一致。成功参照 `[32768,16777216)` 的全部字节等于固定 ophub/u-boot 提交的两份文件加零填充，整个区间 SHA-256 为 `2d61b73387e90d97e4401b48e5efe886b3d46702072878033d5d18680fb88c1e`。故先替换整段引导空隙，消除原引导与陈旧环境，保留 GPT/MBR 和全部文件系统字节不变，避免混用另一内核 DTB/模块。不能据此断定 DDR 批次问题，也不能保证旧 BL31 与 BSP DMC 的兼容性。
- **证据：** 本地候选原始镜像 SHA-256 `4e7e4df5c44943eb88ece4339132bdfd4079abe098d445dd80f162546e06ac6b`，3015704576 字节；保护区前后 SHA-256 一致，报告明确 `hardware_boot_tested=false`、`npu_vpu_runtime_tested=false`。机器生成报告与大镜像不进 git，由 Actions artifact / prerelease 交付。
- **请你：** 下一步仅需空闲 TF 实机验证。确认根分区确实来自候选 TF，再做 RKNN 推理及 MPP 编解码。若失败收集从上电开始的串口日志；不要先擦 eMMC。rootfs 中保留了原 Radxa U-Boot 包，实测前不要升级/重装 U-Boot 或运行安装器覆盖兼容引导。不要把静态构建报告当作实机通过；不要为降低变量把 BSP DTB 换成 mainline DTB。
