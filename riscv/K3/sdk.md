# K3 SDK 解读

　　Spacemit Bianbu Linux K3 SDK (Firefly 定制) 全解读: 目录逐项解析、
编译命令体系、以及与本机另一套 SDK (Rockchip RK3588, 见
`/media/lhj/windows/Linux/arm64/RK3588/sdk.md`) 的差异对比。SDK 实际
路径: `/media/lhj/data/t-chip/7.code/riscv/spacemit/k3_6.18.3_sdk`。

## 1. 平台总览

| 项 | 内容 |
|---|---|
| SoC | Spacemit K3 / SPACDA400 (RISC-V 64, RCPU 双核管理核) |
| 内核 | 6.18 (上游 + Spacemit/Firefly 补丁, `bsp-src/linux-6.18`) |
| U-Boot | 2022.10 (`bsp-src/uboot-2022.10`), SPL 兼任 FSBL (DDR init) |
| 引导固件 | OpenSBI + ESOS (`bsp-src/opensbi`, RISC-V M 模式 + RCPU 代理) |
| 根文件系统 | Bianbu Buildroot 2025.02.6 (buildroot + buildroot-ext 外部树), **rootfs.ext4 预构建** (prebuilt_rootfs, 8GiB) |
| 交叉工具链 | Buildroot 生成: `output/<target>/host/bin/riscv64-unknown-linux-gnu-` (SDK 不带 prebuilts) |
| 构建框架 | 顶层 Makefile 泛化目标 (Buildroot-centered) + `./build.sh` 快捷脚本; **构建强制进 docker** (bianbu 镜像) |
| 内核配置 | `arch/riscv/configs/k3_defconfig` 单文件 (无 fragment 合并体系) |
| DTS 规模 | arch/riscv/boot/dts/spacemit/ 数十个 (Firefly 板 + evb/bananapi/deepcomputing) |
| 启动载荷 | UFS bootfs 分区 (ext4): Image + DTB + initrd.img; U-Boot 按 EEPROM TLV product_name 选 DTB |
| 目标板配置 | `make envconfig` 选 (当前 `env.mk`: CONFIG_NAME=firefly-k3) |

## 2. 目录解析

| 目录/文件 | 内容 | 说明 |
|---|---|---|
| `bsp-src/linux-6.18/` | 内核源码树 | **裸树** (非符号链接); 板级 dts 在 arch/riscv/boot/dts/spacemit/, defconfig 在 arch/riscv/configs/k3_defconfig |
| `bsp-src/uboot-2022.10/` | U-Boot 源码 | SPL 即 FSBL (DDR init 在 SPL); configs/ 有 `k3_defconfig` + `k3_sec.config` fragment (安全加固) |
| `bsp-src/opensbi/` | OpenSBI 源码 | RISC-V M 模式固件; ESOS (RCPU 管理代理) 同仓构建 |
| `buildroot/` | Bianbu Buildroot 2025.02.6 | rootfs 构建主力 (Bianbu 官方 fork) |
| `buildroot-ext/` | **Buildroot external 树** | 本 SDK 的定制核心: `configs/spacemit_*_defconfig` (firefly-k3/k3/k3_ci/k3_plt/k3_rt 五个)、`board/spacemit/k3/` (gen_bootfs.sh 等)、package/、patches/; rootfs.ext4 的剪裁/部署也在这 (external.mk 调 prepare_img.sh) |
| `buildroot-ccache/` | 编译缓存 | buildroot ccache 独立目录 |
| `package-src/` | 厂商应用包源码 | k3x-cam、k3x-vpu-firmware/test、img-gpu-powervr、mesa、mpp、glmark2、gpu-test、drm-test、factorytest、esos、rtk_hciattach — 由 buildroot-ext/package/ 引用 |
| `prebuilt_rootfs/` | **预构建根文件系统** | rootfs.ext4 (8GiB, 只读根) + disk_user + userdata; 免编 rootfs 的关键 |
| `Makefile` | **构建总入口** | `make envconfig` 选 target (生成 output/<t>/Makefile + env.mk); 泛化目标 %-config/%-menuconfig/%-build/%-clean/%-linux-menuconfig/%-uboot-menuconfig/%-cleanbuild/%-pkg 透传进 output/<t>/Makefile; distclean/status/vars/docker 系列 |
| `build.sh` | 快捷脚本 (443 行) | 四模式: `linux`(=dtb 快编+在线更新 bootfs)、`linux-rebuild`、`uboot`、`uboot-rebuild`; **内部强制经 docker** (make <t>-shell BATCH_MODE=1, /build 挂载本 SDK) |
| `env.mk` | 当前 target 记录 | CONFIG_NAME=firefly-k3 + MAKEFILE 路径; `make envconfig` 生成, 顶层 Makefile 读它 |
| `scripts/envsetup.sh` | 环境脚本 | source 后得 BIANBU_LINUX_ROOT_DIR 与 `m` 快捷函数 |
| `scripts/bundle_update.sh` | 整包更新脚本 | 与根目录 firefly-update.sh 配合做固件升级 |
| `firefly-release.sh` | 发布脚本 | 打发布包 (对应 RK3588 侧 build.sh release) |
| `repair-linux-rebuild.sh` | 修复脚本 | linux-rebuild 报"Buildroot 输出入口找不到"时跑; 修入口**不删**内核增量目录 (历史 target 名 firefly-k3-aibox-pro 时也会用到) |
| `output/` | 构建产物 (按 target 分目录) | `output/firefly-k3/`: images/ (bootfs.img、u-boot.itb…)、host/ (**工具链+debugfs 工具**)、target/、build/ (内核/U-Boot 增量目录); 当前为空 = 尚未全量构建过 |
| `docker/` 相关 | bianbu docker 镜像构建材料 | make 目标自动带 docker, 无需手工操作 |

## 3. 编译命令

### 3.1 首次配置

```bash
make envconfig                  # 交互选 target (firefly-k3), 生成 env.mk + output/firefly-k3/Makefile
source scripts/envsetup.sh      # 可选: 获得环境变量与 m() 快捷函数
```

### 3.2 日常命令

**快捷脚本 (build.sh, 自动进 docker):**

| 命令 | 作用 |
|---|---|
| `./build.sh linux` | 只编 DTB (不重编 Image), 同步板级 dts, **用 debugfs 在线更新 output images 里的 bootfs.img** — 换设备树最快路径 |
| `./build.sh linux-rebuild` | 重编内核 + DTB + 更新 bootfs.img |
| `./build.sh uboot` | 增量编 U-Boot, u-boot.itb 装到 images/ |
| `./build.sh uboot-rebuild` | 清理后重编 U-Boot |

**泛化目标 (make, 透传 output/<t>/Makefile):**

| 命令 | 作用 |
|---|---|
| `make linux-config` / `linux-menuconfig` | 内核 defconfig / menuconfig |
| `make linux-build` / `linux-clean` / `linux-cleanbuild` | 内核构建 / 清产物 / 清干净 |
| `make uboot-menuconfig` / `uboot-build` | U-Boot 配置 / 构建 |
| `make busybox-menuconfig` | busybox 配置 |
| `make <pkg>-build` / `<pkg>-clean` / `<pkg>-pkg` | 任意 buildroot 包 (来自 buildroot-ext/package) |
| `make status` / `vars` | 当前 target 状态 / 变量打印 |
| `make distclean` | 全部清理 |

### 3.3 内核板级开发流 (适配笔记常用)

```bash
# 改 dts / defconfig 后:
./build.sh linux                # 快: 只出 DTB 并打进 bootfs.img
# 内核配置变更才需要:
make linux-menuconfig && make linux-build
# U-Boot 变更:
./build.sh uboot
```

　　产物: `output/firefly-k3/images/` (bootfs.img / u-boot.itb);
工具链 `output/firefly-k3/host/bin/riscv64-unknown-linux-gnu-gcc`。
日常换 DTB 也可直接替换设备上 bootfs 分区里的 dtb 文件, 不必整烧。

## 4. 与 RK3588 SDK 差异对比

　　两侧同一张表, 便于对照 (对方侧详见 RK3588 目录 sdk.md):

| 维度 | K3 (本 SDK) | RK3588 (Rockchip) |
|---|---|---|
| 架构/工具链 | RISC-V 64; 工具链由 buildroot 生成在 output/<t>/host/bin (riscv64-unknown-linux-gnu-) | ARM64; prebuilts 自带 aarch64-gcc |
| 内核 | 6.18.3, 在 `bsp-src/linux-6.18` | 6.12 fork, 顶层 `kernel`→`kernel-6.12` 链接 |
| 内核配置 | 单文件 arch/riscv/configs/k3_defconfig (无 fragment 体系) | rockchip_linux_defconfig + 多 fragment 合并 |
| DTS | arch/riscv/boot/dts/spacemit (数十个, Firefly 板 + evb/com260) | arch/arm64/boot/dts/rockchip (695 个) |
| U-Boot | 2022.10, SPL 即 FSBL (DDR init), bsp-src/uboot-2022.10 | 2025.04, TPL/SPL 同树 |
| 引导中间层 | **OpenSBI + ESOS** (RISC-V M 模式固件 + RCPU 管理代理, bsp-src/opensbi) | rkbin blob (DDR bin/miniloader/bl32) |
| 启动载荷 | bootfs 分区 (ext4: Image+DTB+initrd.img), U-Boot 按 EEPROM TLV 型号选 dtb | boot 分区 (boot.img/extboot), recovery/OTA 体系 |
| 根文件系统 | buildroot (bianbu 2025.02.6) + **prebuilt_rootfs/rootfs.ext4 预构建** (8GiB, 只读 + userdata OverlayFS) | buildroot/debian/yocto 三选一 |
| 构建框架 | Buildroot 为中心: `make envconfig` 生成 output/<t>/Makefile, `make` 泛化目标透传 | `build.sh` 子命令式 (Rockchip 新 SDK) |
| 快捷入口 | `./build.sh` (dtb 快编并 debugfs 更新 bootfs.img) / linux-rebuild / uboot-rebuild | build.sh kernel/uboot/... |
| 配置交互 | `make envconfig` (选 target) + `make linux-menuconfig` 等 | `./build.sh config` (Kconfig, device/rockchip/common/configs/Config.in.*) |
| docker | **必经** (bianbu docker 镜像, make 目标自动带) | 可选 (firefly-build.sh -d) |
| 构建日志 | output/<t>/ 常规 make 日志 | output/sessions 会话制 |
| ccache | buildroot-ccache/ 独立目录 | 无专门顶层目录 |
| 应用/厂商包 | package-src/ (gpu-test、k3x-cam、k3x-vpu-*, img-gpu-powervr, mesa, mpp) 喂给 buildroot-ext | app/ (rkipc 等) + external/ (rga/mpp/libmali...) |
| 扩展树 | buildroot-ext/ (Buildroot external: configs/board/package/patches) | device/rockchip/common (构建 hooks/脚本) |
| 烧录/升级 | firefly-update.sh + scripts/bundle_update.sh; 日常换 dtb 直接替换 bootfs.img 里的文件 | rkflash.sh + tools/ (RKDevTool 体系), update.img |
| 特有机制 | 单仓 + bsp-src; docker 强制; repair-linux-rebuild.sh 修复入口; EEPROM TLV 选 dtb | manifest 多仓 (repo), extboot, AMP, security 签名 |

## 5. 板级适配工作面对照

| 适配动作 | 本 SDK 位置 |
|---|---|
| 板级 DTS / pinctrl | `bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit/` (各 md 已给展开配置) |
| 内核配置 | `bsp-src/linux-6.18/arch/riscv/configs/k3_defconfig` (单文件, 直接改) |
| U-Boot | `bsp-src/uboot-2022.10/` (configs/k3_defconfig + k3_sec.config) |
| bootfs 内容 | buildroot-ext/board/spacemit/k3/gen_bootfs.sh (Image+DTB+initrd 装箱) |
| rootfs 剪裁 | buildroot-ext/configs/spacemit_firefly-k3_defconfig + prebuilt_rootfs |
| 固件更新 | firefly-update.sh + scripts/bundle_update.sh |

　　各模块适配方法见本目录其余 22 份 md (README.md 有总索引);
SDK 结构性问题 (docker、target 机制、bootfs 打包) 以本篇为准。
