# RK3588 SDK 解读

　　Firefly RK3588 / RK3576 Linux SDK 全解读: 目录逐项解析、编译命令
体系、以及与本机另一套 SDK (Spacemit K3, 见
`/media/lhj/windows/Linux/riscv/K3/sdk.md`) 的差异对比。SDK 实际路径:
`/media/lhj/data/t-chip/7.code/arm64/rockchip/rk3588_6.12.69_sdk`。

## 1. 平台总览

| 项 | 内容 |
|---|---|
| SoC | Rockchip RK3588/RK3576 (ARM64) |
| 内核 | 6.12 (Rockchip fork, manifest `common_linux6.12_next.xml`, kernel → kernel-6.12 符号链接) |
| U-Boot | 2025.04 (TPL+SPL 全在上游 U-Boot 树内) |
| 固件 blob | rkbin (DDR init / miniloader / bl32) |
| 根文件系统 | buildroot (fork 2026.02.2) / debian / yocto 三选 |
| 交叉工具链 | prebuilts/gcc/linux-x86/{aarch64, arm} (SDK 自带) |
| 构建框架 | Rockchip 新版 `build.sh` 子命令体系 + Firefly `firefly-build.sh` 封装 (可选 docker) |
| 烧录工具 | tools/{linux,mac,windows} + rkflash.sh |
| DTS 规模 | arch/arm64/boot/dts/rockchip/ 下 695 个 dts |

## 2. 目录解析

| 目录/文件 | 内容 | 说明 |
|---|---|---|
| `kernel` → `kernel-6.12` | 内核源码树 | **符号链接**, 切版本时换链接即可; 板级 dts/defconfig 改这里 |
| `u-boot/` | U-Boot 2025.04 源码 | 含 TPL/SPL; `configs/` 有 `firefly-linux.config` fragment 与各家板 defconfig |
| `rkbin/` | Rockchip 闭源固件 blob | DDR init bin、miniloader、bl32 (TEE) — 打包 loader 时按芯片取用 |
| `buildroot/` | Buildroot fork (2026.02.2) | buildroot 类 rootfs 主力; `board/` 支持众多上游板 |
| `debian/` `yocto/` | 另两类 rootfs 支持 | 与 buildroot 三选一, `./build.sh rootfs` 按配置走 |
| `app/` | Rockchip 应用层 demo | rkipc、rkadk、rkai、lvgl_demo、ipcweb-backend 等 |
| `external/` | 厂商中间件/库 | linux-rga、mpp (编解码)、libmali (GPU userland)、camera_engine_rkaiq、gstreamer-rockchip、ethercat_igh、chromium 等 |
| `device/rockchip/common/` | 构建公共仓库 | 实体在顶层 `common/` (device 下是链接): build-hooks、configs (Config.in.* Kconfig 体系)、kconfig、linux-kbuild、device-scripts、extra-parts |
| `build.sh` | **SDK 总入口** | 新版子命令式: chip/defconfig 选择 + 各阶段构建 (见 3.2) |
| `firefly-build.sh` | Firefly 封装 | init (装环境/docker) + config (选产品) + all/kernel/uboot/rootfs |
| `rkflash.sh` | 烧录入口 | 调 tools/ 下工具烧 update.img 或分区镜像 |
| `Makefile` | 顶层 make 桥 | 少量透传目标, 主入口还是 build.sh |
| `prebuilts/` | 交叉工具链 | gcc/linux-x86/{aarch64, arm} — 内核/U-Boot 直接用 |
| `output/` | 产物与状态 | `firmware/` (分区 img)、`sessions/` (构建会话日志, initial.env/log 是链接)、`.make_usage` |
| `tools/` | 烧录器 | linux/mac/windows 三平台 (RKDevTool 命令行底座) |
| `docs/` | SDK 文档 | Rockchip 官方说明 |
| `Dockerfile.firefly`、`docker-compose.yml` | docker 构建环境 | firefly-build.sh -d 用, ubuntu:24.04 底座 |

## 3. 编译命令

### 3.1 首次环境

```bash
# 宿主机直接装依赖 (二选一):
./firefly-build.sh init -a          # apt 装构建依赖
./firefly-build.sh init -d          # 或走 docker compose (ubuntu:24.04)

# 选 Firefly 产品与 rootfs 系统 (交互):
./firefly-build.sh config           # 写入 BoardConfig/配置
```

### 3.2 日常命令 (build.sh 子命令体系)

| 命令 | 作用 |
|---|---|
| `./build.sh chip:rk3588[:<config>]` | 选芯片与板级配置 |
| `./build.sh defconfig:<name>` / `<name>_defconfig` | 切换内核 defconfig |
| `./build.sh` (= `all`) | 全量出镜像 |
| `./build.sh kernel` / `kernel[:dry-run]` | 只编内核 (extboot 类型用 `extboot`) |
| `./build.sh uboot` (= `loader`) | 编 U-Boot + 打包 loader |
| `./build.sh kernel-config` (别名 `kconfig`) | 内核 defconfig 交互 |
| `./build.sh kernel-make:<args>` (kmake) | 内核 make 透传 (如 `kmake:dtbs`) |
| `./build.sh buildroot` / `debian` / `yocto` / `rootfs` | 根文件系统三选 |
| `./build.sh buildroot-config` (bconfig) / `bmake` | buildroot defconfig 与 make 透传 |
| `./build.sh firmware` | 汇总打包各分区镜像到 output/firmware |
| `./build.sh updateimg` / `sd-updateimg` / `ota-updateimg` | 合成整烧/SD/OTA 升级镜像 |
| `./build.sh recovery` | recovery 镜像 |
| `./build.sh clean-kernel` 等 `clean-*` | 分阶段清理 |
| `./build.sh shell` / `bshell` | 进入构建环境 shell (SDK/buildroot) |
| `./build.sh release` / `all-release` | 发布产物与构建信息 |

　　Firefly 快捷等价: `./firefly-build.sh all` ≈ `./build.sh`、
`./firefly-build.sh kernel` ≈ `./build.sh kernel` (按已配置产品)。

### 3.3 内核板级开发流 (适配笔记常用)

```bash
./build.sh kernel-config            # 或直接改 arch/arm64/configs/ + fragment
./build.sh kernel                   # 出 Image/dtb
./build.sh firmware && ./build.sh updateimg     # 打包烧录镜像
```

　　defconfig 体系: 基座 `arch/arm64/configs/rockchip_linux_defconfig`
+ fragment (`firefly-linux.config`、`rockchip_rt.config`、
`firefly-rk182x.config` 等) 由构建系统合并。

## 4. 与 K3 SDK 差异对比

　　两侧同一张表, 便于对照 (对方侧详见 K3 目录 sdk.md):

| 维度 | RK3588 (本 SDK) | K3 (Spacemit) |
|---|---|---|
| 架构/工具链 | ARM64; prebuilts 自带 aarch64-gcc | RISC-V 64; 工具链由 buildroot 生成在 output/<t>/host/bin (riscv64-unknown-linux-gnu-) |
| 内核 | 6.12 fork, 顶层 `kernel`→`kernel-6.12` 链接 | 6.18.3, 在 `bsp-src/linux-6.18` |
| 内核配置 | rockchip_linux_defconfig + 多 fragment 合并 | 单文件 arch/riscv/configs/k3_defconfig (无 fragment 体系) |
| DTS | arch/arm64/boot/dts/rockchip (695 个) | arch/riscv/boot/dts/spacemit (数十个, Firefly 板 + evb/com260) |
| U-Boot | 2025.04, TPL/SPL 同树 | 2022.10, SPL 即 FSBL (DDR init), bsp-src/uboot-2022.10 |
| 引导中间层 | rkbin blob (DDR bin/miniloader/bl32) | **OpenSBI + ESOS** (RISC-V M 模式固件 + RCPU 管理代理, bsp-src/opensbi) |
| 启动载荷 | boot 分区 (boot.img/extboot), recovery/OTA 体系 | bootfs 分区 (ext4: Image+DTB+initrd.img), U-Boot 按 EEPROM TLV 型号选 dtb |
| 根文件系统 | buildroot/debian/yocto 三选一 | buildroot (bianbu 2025.02.6) + **prebuilt_rootfs/rootfs.ext4 预构建** (8GiB, 只读 + userdata OverlayFS) |
| 构建框架 | `build.sh` 子命令式 (Rockchip 新 SDK) | Buildroot 为中心: `make envconfig` 生成 output/<t>/Makefile, `make` 泛化目标透传 |
| 快捷入口 | build.sh kernel/uboot/... | `./build.sh` (dtb 快编并 debugfs 更新 bootfs.img) / linux-rebuild / uboot-rebuild |
| 配置交互 | `./build.sh config` (Kconfig, device/rockchip/common/configs/Config.in.*) | `make envconfig` (选 target) + `make linux-menuconfig` 等 |
| docker | 可选 (firefly-build.sh -d) | **必经** (bianbu docker 镜像, make 目标自动带) |
| 构建日志 | output/sessions 会话制 | output/<t>/ 常规 make 日志 |
| ccache | 无专门顶层目录 | buildroot-ccache/ 独立目录 |
| 应用/厂商包 | app/ (rkipc 等) + external/ (rga/mpp/libmali...) | package-src/ (gpu-test、k3x-cam、k3x-vpu-*, img-gpu-powervr, mesa, mpp) 喂给 buildroot-ext |
| 扩展树 | device/rockchip/common (构建 hooks/脚本) | buildroot-ext/ (Buildroot external: configs/board/package/patches) |
| 烧录/升级 | rkflash.sh + tools/ (RKDevTool 体系), update.img | firefly-update.sh / bundle_update.sh; 日常换 dtb 直接替换 bootfs.img 里的文件 |
| 特有机制 | manifest 多仓 (repo), extboot, AMP, security 签名 | 单仓 + bsp-src; docker 强制; repair-linux-rebuild.sh 修复入口; EEPROM TLV 选 dtb |

## 5. 板级适配工作面对照

| 适配动作 | 本 SDK 位置 |
|---|---|
| 板级 DTS / pinctrl | `kernel-6.12/arch/arm64/boot/dts/rockchip/` (各 md 已给展开配置) |
| 内核配置 | `kernel-6.12/arch/arm64/configs/` (defconfig + firefly-linux.config) |
| U-Boot / 引脚 | `u-boot/` (configs/ firefly-linux.config) |
| 分区表 | `./build.sh print-parts` / `edit-parts` (device/rockchip/common/configs) |
| 开机 logo / 资源 | device/rockchip/common (build-hooks) |

　　各模块适配方法见本目录其余 md (led/key/gmac/usb/pcie/显示系列);
SDK 结构性问题 (工具链、打包、烧录) 以本篇为准。
