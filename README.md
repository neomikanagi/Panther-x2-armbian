# Panther X2：BSP NPU/VPU + 已知能启动的 ophub 引导链

这是 **待实机验证的兼容候选**：保留 wlxxyw Debian 13 / Rockchip BSP 6.1.115 的内核、设备树、模块与系统分区，只把分区前的引导区换成 ophub 的 Panther X2 专用版本。**还没有证明能启动，也没有证明故障来自内存批次。**

## 下载与试机

优先下载本 fork 的 `bootchain-candidate-*` **预发布**，或 Actions 中的 `Panther-X2-BSP61-ophub-bootchain-candidate` artifact：

- `Armbian_Panther-X2_trixie_BSP6.1.115_ophub-bootchain_candidate.img.xz`
- 同名 `.sha256`
- `bootchain-validation.json`：改动范围、完整镜像校验值、分区保持不变的证据。
- `inputs.json`：下载地址、固定提交、输入校验值。

1. 校验下载文件后，用 Etcher 等将 `.img.xz` 写入**空闲 TF 卡**。不要覆盖 eMMC，也不要把外接备份盘当成 TF 卡。
2. 断电插卡再开机，检查路由器 DHCP 与 SSH，而不只看灯。现有 eMMC 可能影响启动来源；没有确认来源前，不能把“有/无 IP”当成候选镜像成功/失败的充分证据。
3. 能登录后先核对 `uname -r` 为 `6.1.115-vendor-rk35xx`、根分区来自 TF，再检查 `/dev/rknpu`、`/dev/mpp_service`、`/dev/rga` 与内核日志。最终须跑 RKNN 推理和 MPP 硬件编解码，不能只看驱动节点。
4. 失败时保留现象和上电串口日志；拔卡回到原系统。**TF 启动本身不完全隔离 eMMC 引导链，勿为此擦除 eMMC。**

本候选仍保留原 rootfs 中的 Rock-3C U-Boot 软件包及配置；实机验证前不要重装/升级 U-Boot、执行写入 eMMC 的安装器，否则可能把兼容引导覆盖回去。复用现成系统的账号初始化方式；本项目不增加默认密码或远程登录密钥。

## 为什么先改引导

失败基线使用 `rock-3c-rk3566_defconfig`，成功基线使用 ophub 的 Panther X2 专用引导文件。两者仍可能在内核设备树、DMC、供电或初始化方面存在其他差异，因此第一步只控制一个变量：

```text
ophub Panther X2 idbloader（DDR 初始化/SPL）+ u-boot.itb（U-Boot/固件）
  → 原样保留的 BSP 6.1.115 内核 + Panther X2 DTB + 模块 + Debian 13
```

固定输入见 [`compat/inputs.json`](compat/inputs.json)：

- 失败基线：wlxxyw `pantherx2-trixie-13`，SHA-256 `2703abaf…c8d08278`。
- 用户报告能启动的参照：ophub `6.18.57_server_2026.10.17`。参照镜像本身不进入构建。
- 引导文件：`ophub/u-boot` 提交 `ce8e3d9d6c70a74a17d9b01cf80b44c6ec08f146`。

检查范围是 `[32768, 16777216)` 字节，即 LBA 64 到第一分区之前：清除原引导与陈旧环境，写入固定的 `idbloader.img`（LBA 64）及 `u-boot.itb`（LBA 16384）。生成区间的 SHA-256 与成功参照的完整引导空隙一致。主/备 GPT、MBR、FAT 启动分区和根分区逐字节不变；不会混用另一内核的 DTB 或模块。

## GitHub Actions

两个工作流都只手动触发，避免普通文档提交启动数小时编译：

- **Panther X2 bootchain compatibility candidate**：下载校验固定基线与两份引导文件，快速重打包。`publish_release=true` 会发布明确标为候选的 prerelease。
- **Build Panther X2 Trixie BSP 6.1**：保留上游完整源码编译；编译和 BSP 静态校验后，同样执行引导替换再压缩。这个全编译路径的修改尚未实际跑完，不能等同于快速重打包路径的验收。

构建器只接受普通镜像文件，拒绝设备、符号链接、已有输出、损坏 GPT、不符的分区偏移或引导校验值；不包含刷盘动作。测试使用合成 GPT 文件，不碰硬件：

```bash
python3 -m unittest discover -s tests -v
bash scripts/build_bootchain_candidate.sh
# 对新的源码编译产物应用相同引导：
bash scripts/build_bootchain_candidate.sh --input /path/to/new.img --out ./candidate
```

自动化校验仅证明内容与改动边界，不代替上电测试。

## NPU / VPU 用户态

保留了上游 `examples/` 的 RKNN 示例、模型与运行库；它们尚未在目标机器上重新验收。RKNN Lite2 版本需与内核驱动、模型及 `librknnrt.so` 匹配；上游示例使用 Python 3.11。MPP/RGA 用户态与适配的 FFmpeg 仍需另行安装并实测，镜像能启动不代表加速已可用。

## 上游

- [wlxxyw/Panther-x2-armbian](https://github.com/wlxxyw/Panther-x2-armbian)
- [clfang666/Panther-x2-NPU-VPU](https://github.com/clfang666/Panther-x2-NPU-VPU)
- [ophub/u-boot](https://github.com/ophub/u-boot)
- [ophub/amlogic-s9xxx-armbian](https://github.com/ophub/amlogic-s9xxx-armbian)
- [Armbian build](https://github.com/armbian/build)、[Rockchip kernel](https://github.com/armbian/linux-rockchip)、[Radxa U-Boot](https://github.com/radxa/u-boot)

上游补丁、模型、固件及衍生源码继续遵循各自上游许可；本 fork 不重新声明上游资产的许可。
