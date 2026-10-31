# 多 AI 交接

## 2026-10-31 — pi → 实机验证

- **状态：** 兼容候选已完成本地离线生成，尚未上电验证；NPU/VPU 运行未验收。18 项合成 GPT 测试、ShellCheck、YAML 解析通过。完整源码编译路径已接入相同重打包步骤，但没有执行数小时全编译。
- **改了：** `compat/inputs.json` 固定失败镜像及 Panther X2 引导文件；`scripts/graft_bootchain.py` 检查 GPT/校验值且只生成普通文件，拒绝设备、符号链接和覆盖；`scripts/build_bootchain_candidate.sh` 下载校验、打包与压缩；新增手动 Actions，原全编译也改为手动并应用同一引导替换；README 只写现状与实机边界。
- **为什么·思路：** 用户确认 wlxxyw build 13 不启动，ophub `6.18.57_server_2026.10.17` 能启动。两份完整下载的压缩镜像 SHA-256 均与 GitHub release digest 一致。成功参照 `[32768,16777216)` 的全部字节等于固定 ophub/u-boot 提交的两份文件加零填充，整个区间 SHA-256 为 `2d61b73387e90d97e4401b48e5efe886b3d46702072878033d5d18680fb88c1e`。故先替换整段引导空隙，消除原引导与陈旧环境，保留 GPT/MBR 和全部文件系统字节不变，避免混用另一内核 DTB/模块。不能据此断定 DDR 批次问题，也不能保证旧 BL31 与 BSP DMC 的兼容性。
- **证据：** 本地候选原始镜像 SHA-256 `4e7e4df5c44943eb88ece4339132bdfd4079abe098d445dd80f162546e06ac6b`，3015704576 字节；保护区前后 SHA-256 一致，报告明确 `hardware_boot_tested=false`、`npu_vpu_runtime_tested=false`。机器生成报告与大镜像不进 git，由 Actions artifact / prerelease 交付。
- **请你：** 下一步仅需空闲 TF 实机验证。确认根分区确实来自候选 TF，再做 RKNN 推理及 MPP 编解码。若失败收集从上电开始的串口日志；不要先擦 eMMC。rootfs 中保留了原 Radxa U-Boot 包，实测前不要升级/重装 U-Boot 或运行安装器覆盖兼容引导。不要把静态构建报告当作实机通过；不要为降低变量把 BSP DTB 换成 mainline DTB。
