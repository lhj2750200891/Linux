# Android 开发

## 1. SDK 获取与编译

```
# 我这里是firefly的android 14,在百度网盘下载的
cd /media/lhj/windows/code/arm64/rockchip/rockchip_android_sdk
ls # 输出如下:
android_sdk_delivery.tar.gz.part00  android_sdk_delivery.tar.gz.part05
android_sdk_delivery.tar.gz.part01  android_sdk_delivery.tar.gz.part06
android_sdk_delivery.tar.gz.part02  android_sdk_delivery.tar.gz.part07
android_sdk_delivery.tar.gz.part03  android_sdk_delivery.tar.gz.part08
android_sdk_delivery.tar.gz.part04

# 先合并压缩包并检验
cat android_sdk_delivery.tar.gz.part* &gt; android_sdk_delivery.tar.gz
或者
nohup sh -c 'cat android_sdk_delivery.tar.gz.part* > android_sdk_delivery.tar.gz' > merge.log 2>&1 &
watch -n 5 'ls -lh android_sdk_delivery.tar.gz merge.log'   # 用于监控是否在变化
md5sum android_sdk_delivery.tar.gz   # 检验值应该为: 14e23c298e79ed8b83ac82bd76ada530

# 解压
tar -vxf android_sdk_delivery.tar.gz  

# 编译aic ()
cd android_sdk
source build/envsetup.sh
cat device/rockchip/rk3588/AndroidProducts.mk 
source build/envsetup.sh && lunch rk3588_aic-userdebug
env ALLOW_MISSING_DEPENDENCIES=true ./build_aic.sh -K   # ① 先编内核（必须，生成 kernel Image）
env ALLOW_MISSING_DEPENDENCIES=true ./build_aic.sh -A   # ② 再编 android 容器固件
# 产物：IMAGE/RK3588_AIC_ANDROID14_USERDEBUG_&lt;时间戳&gt;/IMAGES/container/

# 编译 itx-3588j
cd android_sdk
source build/envsetup.sh
lunch rk3588_firefly_itx_3588j-userdebug
cd u-boot
./make.sh rk3588
cd ..
./build.sh -KAu    # 编译出的update.img 可以直接烧录,产物在android_sdk/rockdev/Image-rk3588_firefly_itx_3588j中

# 烧录
reboot loader
fastboot flash super /home/lhj/super.img
sudo upgrade_tool uf /home/lhj/update.img

# 编译
./FFTools/make.sh -d rk3588-firefly-itx-3588j -j$(nproc) -l rk3588_firefly_itx_3588j-userdebug
./FFTools/mkupdate/mkupdate.sh -l rk3588_firefly_itx_3588j-userdebug   # 打包update.img
```



## 2. Android 与 Linux 异同对比

> 对照样本（均为只读分析结论，路径以实际机器为准）：
> - Android14 SDK：`/media/lhj/windows/code/arm64/rockchip/rockchip_android_sdk/android_sdk`（Rockchip Android14，内核 `kernel-6.1` = **6.1.141**，目标板 `rk3588_firefly_itx_3588j`）
> - Linux BSP SDK：`/media/lhj/data/t-chip/7.code/arm64/rockchip/rk3588_6.1.118_sdk`（Firefly Linux SDK，内核 **6.1.118**，同一板子有 `firefly_rk3588_itx-3588j_{buildroot,debian,ubuntu,openeuler}_defconfig`）

### 2.1 总体定位对比

| 维度 | Android14 SDK | Linux BSP SDK |
|---|---|---|
| 用户态世界 | AOSP 14（system_server/HAL/binder） | Ubuntu / Debian / Buildroot / OpenEuler（`prebuilt_rootfs/` 预置镜像或源码编译） |
| 内核 | 6.1.141（`kernel-6.1/`） | 6.1.118（`kernel/`） |
| 板级配置抽象 | `device/rockchip/rk3588/rk3588_firefly_itx_3588j/` 下 `*.mk` + BoardConfig | `device/rockchip/rk3588/firefly_rk3588_<board>_<rootfs>_defconfig` + `firefly.config` |
| 构建入口 | `source build/envsetup.sh && lunch <product>-userdebug && ./build.sh -UKAu` | `make <板级defconfig>`（SDK 级 Kconfig）→ `./build.sh` |
| 产物 | `rockdev/Image-*/`：boot.img、dtbo.img、super.img（动态分区）、recovery、vbmeta、parameter.txt、update.img | `output/firmware/`：update.img（FIT 形态 boot、整只 rootfs） |
| 镜像形态 | Android boot.img（非 GKI 时 kernel+resource 合入 boot）+ 动态分区 super | FIT 镜像（`RK_USE_FIT_IMG=y`，`bootramdisk.its`）+ 独立 rootfs 分区（`parameter-buildroot-fit.txt`） |
| 调试通道 | adb、logcat、fastboot | ssh/串口 shell、dmesg/journalctl、`rkflash.sh` |
| 软件升级 | recovery OTA / AB OTA（`build.sh -o`） | 整包 update.img、`bundle_update.sh` |

### 2.2 相同点：底层 BSP 是同一套

1. **三件套同源**：u-boot、kernel、`rkbin/`（DDR loader、boot_merger 等）两边结构一致。RK3588 启动链都是 BootROM → MiniLoaderAll（DDR 初始化）→ uboot.img（内含 BL31/ATF）→ boot；`BOARD_ROCKCHIP_TRUST_MERGE_TO_UBOOT` 两侧等价（trust 并入 uboot，无独立 trust 镜像）。
2. **内核开发流程完全一致**：改 `arch/arm64/boot/dts/rockchip/*.dts(i)`、menuconfig/defconfig 片段合并、驱动 `.ko`、打补丁——方法和工具链（clang/LLVM）两边通用。
3. **设备树同源同形**：两边都有 `rk3588-firefly-itx-3588j.dts/.dtsi`，且都是“板级 dts → `rk3588-firefly-core.dtsi`/`rk3588-firefly-port.dtsi` → 平台差异 dtsi”的分层结构。差异只在尾巴：Android 版挂 `rk3588-android.dtsi`（reboot-to-bootloader、android fstab 等软件策略节点），Linux 版挂 `rk3588-linux.dtsi`。**外设使能节点（GPIO/UART/I2C/SPI/摄像头/网卡）两边基本可互抄**，软件策略节点不能。
4. **分区与烧录一致**：parameter.txt、update.img、RKDevTool/upgrade_tool、MaskRom/Loader 进入方式、调试串口 UART2 1500000 波特率，两边相同。
5. **交叉编译环境**：都是 x86_64 主机出 arm64 产物，工具链均来自 SDK 内置（Android 在 `prebuilts/clang`，Linux 在 `prebuilts/`）。

> ⚠️ 注意：两棵树内核基线不同（**6.1.141 vs 6.1.118**），驱动补丁和 dts 片段**不能整文件互拷**，只能当参考，合入前需确认上下文冲突。

### 2.3 关键差异

| 方面 | Android14 | Linux BSP |
|---|---|---|
| 配置体系 | Soong/Kati：PRODUCT_*/BOARD_* `.mk`、`lunch` 选产品、resource overlay | SDK 级 Kconfig：`common/configs/Config.in.*`（kernel/loader/rootfs/firmware/recovery/security/update 各一节），板级 defconfig 选型 |
| 内核 config 组成 | `firefly_defconfig android-14.config rk3588.config pcie_wifi.config`（由 `device/rockchip/common/modules/kernel_config.mk` 拼装） | `RK_KERNEL_CFG_FRAGMENTS="firefly-linux.config rockchip_linux_docker.config firefly-net.config"`（`firefly.config`）——同为“基线 defconfig + 片段合并”机制，片段名不同 |
| 构建模块化 | 一个 make 大锅炖（boot/vendor/super 一次出） | `common/scripts/mk-*.sh` 按模块钩子（mk-kernel/mk-loader/mk-rootfs/mk-updateimg），可单模块重跑 |
| 显示/图形栈 | SurfaceFlinger + HWC + mali DDK + gralloc | 直接 DRM/KMS + mesa/panfork，无需 HAL |
| 摄像头 | 内核 ISP 驱动相同，但需 rkisp/rkaiq HAL + CameraProvider 才能出图 | v4l2 直接用 |
| 权限与安全 | SELinux **enforcing**（改代码常需同步改 sepolicy）、动态权限、APEX | 无 SELinux 约束、root 直用 |
| 系统分区 | 动态分区 super（system/vendor/product/odm/…），改系统要重出 super.img | rootfs.img 整分区，chroot 即可定制 |
| 开机图形 | bootanimation、logo 打包进 resource | 内核 logo、plymouth（视 rootfs） |
| OTA | `build.sh -o` 出 OTA 包，recovery/AB 升级 | update.img 整刷或 swupdate 类方案 |

**一句话总结**：内核/驱动/设备树这一层，Android BSP 和 Linux BSP 是同一份工作；Android 额外的成本全在用户态——HAL、SEPolicy、动态分区与 OTA 体系、Soong 构建规则；Linux BSP 额外的成本在 rootfs（Buildroot/Debian 定制）。

## 3. Android14 开发步骤

### 3.1 环境准备

- 编译主机：x86_64 Ubuntu（本机实测 Ubuntu 22.04 可用），磁盘 ≥ 250G（out/ 一套约 100G+，kernel/android 双份产物另计），内存越大越好（`-J96` 是按 96 线程跑的）。
- 源码见第 1 节（分卷合并 → md5 校验 → 解压）。
- Android 与 Linux 两个 SDK **不要共用 out 目录混编**（见第 4 节坑 3）。

### 3.2 编译流程详解

```text
# uboot 单独入口（原因见第 4 节坑 1）
cd u-boot && ./make.sh rk3588 && cd -

# 内核 + Android + 打包
source build/envsetup.sh
lunch rk3588_firefly_itx_3588j-userdebug
./build.sh -KAu -J96
```

`build.sh` 各参数实际动作：

| 参数 | 动作 |
|---|---|
| `-U` | 编 uboot（本 SDK 的 build.sh 用 `make rk3588` 会失败，见坑 1，平时不用它） |
| `-K` | 编内核：`make firefly_defconfig android-14.config rk3588.config pcie_wifi.config` + `make rk3588-firefly-itx-3588j.img`，之后 `u-boot/scripts/pack_resource.sh` 把 charger logo 打进 resource.img |
| `-A` | Android：`make installclean && make -j`，35 分钟量级（96 线程、全量） |
| `-u` | mkimage.sh 收集镜像到 `rockdev/Image-<product>/` + RKTools 打 update.img |
| `-o` | 出 OTA 包（本板非 AB，走 recovery OTA） |
| `-p` | 版本留档：打包到 `Image/` + repo patches（与 AIC 交付同款动作） |

关键板级文件（改配置先看这里）：

```
device/rockchip/rk3588/rk3588_firefly_itx_3588j/rk3588_firefly_itx_3588j.mk   # 产品定义（HDMI 口顺序、分辨率、lcd_density、gps 等）
device/rockchip/rk3588/rk3588_firefly_itx_3588j/BoardConfig.mk               # 板级（非 AB、非 GKI、dtbo 模板、内核 dts）
device/rockchip/rk3588/rk3588_firefly_itx_3588j/dt-overlay.in                # dtbo overlay（v1_1/v1_2 两版硬件）
kernel-6.1/arch/arm64/boot/dts/rockchip/rk3588-firefly-itx-3588j.dts         # 设备树入口
```

### 3.3 产物与烧录

产物目录 `rockdev/Image-rk3588_firefly_itx_3588j/`：

```
MiniLoaderAll.bin  uboot.img  boot.img  resource.img  dtbo.img
recovery.img  super.img  vbmeta.img  misc.img  oem.img
parameter.txt  config.cfg  baseparameter.img  update.img（整包）
```

烧录：

```text
# Windows: RKDevTool「升级固件」页 → 固件选 update.img → 板子进 Loader（按住 Recovery 复位）→ 升级
# Linux:
upgrade_tool uf update.img
```

- 整包带 MiniLoaderAll.bin + parameter.txt，烧录会**整盘重分区**，板上原系统（含 AIC）被完整覆盖。
- 包里没有 data.img 是正常的：parameter 末尾自动生成 `userdata:grow`（吃满剩余 eMMC，见 `parameter_generator.py`），`/data` 首次开机格式化。
- 包里没有 trust.img 也是正常的：RK3588 的 BL31 已合入 uboot.img（`BOARD_ROCKCHIP_TRUST_MERGE_TO_UBOOT := true`）。
- 首次开机较慢（data 格式化、SELinux relabel、dexopt），默认 HDMI 输出 1920x1080。

### 3.4 调试手段

```text
adb devices / adb root / adb remount          # userdebug 可直接 root、可写 /
adb shell dmesg -w                            # 内核日志（与 Linux 完全相同）
adb shell cat /proc/kmsg                      # 同上
logcat                                        # 用户态日志
adb shell getprop / setprop                   # 系统属性
adb reboot bootloader                         # 进 fastboot
```

底层问题仍然是串口第一优先：UART2、1500000 波特率。烧卡死/黑屏先看串口，再 `logcat | grep -E "avc|ServiceManager"` 查 SELinux/服务问题。

### 3.5 典型开发任务 SOP

**A. 内核层（与 Linux BSP 完全同法）**

```text
1. 改 kernel-6.1 下的 dts/dtsi/驱动
2. 已 lunch 环境下重编内核：
   cd kernel-6.1
   make ARCH=arm64 firefly_defconfig android-14.config rk3588.config pcie_wifi.config
   make ARCH=arm64 rk3588-firefly-itx-3588j.img -j96
   cd -
3. make bootimage        # 非 GKI：内核+resource 已合入 boot.img
4. 只烧 boot 分区验证（RKDevTool「下载镜像」模式，秒级迭代），稳定后再并入整包
```

**B. 板级配置（等效 Linux SDK 的 defconfig/dts 改动）**

- 显示参数、HDMI 口顺序、主次网口：`rk3588_firefly_itx_3588j.mk` 里的 `PRODUCT_PROPERTY_OVERRIDES`（如 `vendor.hwc.device.primary=HDMI-A-1,DP-1,...`）
- 预置文件：`PRODUCT_COPY_FILES`；预置 APK：`PRODUCT_PACKAGES` + 模块 `Android.bp/Android.mk`
- 硬件版本差异 overlay：`PRODUCT_DTBO_TEMPLATE`（`*.in`），编进 dtbo.img
- MIPI 屏：默认 dts 是 HDMI 为主显，接 MIPI 屏需要换 mipi 变体 dts 重编内核（`rk3588-firefly-itx-3588j-mipi*.dts`，并先在 `kernel-6.1/arch/arm64/boot/dts/rockchip/Makefile` 注册对应 dtb）

**C. Android 用户态**

```text
1. 单模块增量编译：source build/envsetup.sh && lunch ... 后
   m <模块名>
   产物 adb push 或重打 super
2. framework/system_service：改 frameworks/ 后需整编 make -j96
3. HAL/系统服务：AIDL 接口声明 + vendor 进程实现，
   同步在 device/rockchip/common/sepolicy_vendor/（或产品目录）补 SELinux 规则
   权限违例先 logcat | grep avc，用 audit2allow 生成初版 allow 规则再收敛
4. 系统属性：PRODUCT_PROPERTY_OVERRIDES 进 *.mk，
   运行期 adb shell setprop/getprop 验证
```

**D. 出固件**

```text
./build.sh -KAu    # 整包 update.img（日常）
./build.sh -KAo    # OTA 包（recovery 升级）
./build.sh -p      # 版本留档：打包到 Image/ + 生成 patches
```

### 3.6 同一任务的 Linux ↔ Android 对照表

| 任务 | Linux BSP SDK | Android14 SDK |
|---|---|---|
| 换内核配置 | 改 `RK_KERNEL_CFG_FRAGMENTS` / menuconfig | 改 defconfig 片段集（`kernel_config.mk` 拼装） |
| 使能一个 I2C 外设 | 板级 dts + 驱动，重出 boot FIT | **完全相同**（dts + 驱动），重出 boot.img |
| 换系统内容 | 换 rootfs defconfig 或 `build.sh post-rootfs` 脚本 | 改 PRODUCT_PACKAGES/overlay，重出 super.img |
| 看外设是否工作 | ssh + `dmesg`/`i2cdetect` | `adb shell` + 同样的 dmesg/i2cdetect |
| 开机自启程序 | systemd unit / rcS | init.rc（`device/rockchip/.../*.rc`）或系统服务 |
| 升级到新版本 | 重烧 update.img | OTA 包或整刷 |

## 4. 常见问题与坑（实测记录）

1. **`./build.sh -U` 编 uboot 报 `No rule to make target 'rk3588'`**：build.sh 内部执行 `make $UBOOT_CONFIG`（`rk3588`，无 `_defconfig` 后缀），这份 u-boot 没有该目标。绕过：先 `cd u-boot && ./make.sh rk3588 && cd -`，再 `./build.sh -KAu`（不带 -U）。改 `build.sh` 里为 `make ${UBOOT_DEFCONFIG}_defconfig` 也可。
2. **mkimage 时提示 `u-boot/trust.img not fount!`**：预期行为。RK3588 方案是 BL31 合入 uboot.img，无独立 trust 镜像；parameter 里的 4M trust 分区烧后保持旧内容即可。
3. **AIC（rk3588_aic）与标准产品（rk3588_firefly_itx_3588j）混编**：两者共用 `kernel-6.1`，内核 `.config`/boot 产物会互相覆盖；切换产品建议 `rm -rf out` 后再编，否则 soong 可能报诡异错误。需要同时维护两种固件就复制两棵树。
4. **Android 编译日志里的 `Invalid sparse file format at header magic` ×8**：无害噪音，是组 super.img 时读取各分区 ext4 镜像的 sparse 头探测提示，后面紧跟 build completed 即正常。
5. **选 itx 编内核报 `No rule to make target 'rockchip/rk3588-firefly-itx-3588j.dtb'`**：本交付包（AIC 版）把 firefly 系 dtb 从 `kernel-6.1/arch/arm64/boot/dts/rockchip/Makefile` 删掉了，需补回：
   `dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3588-firefly-itx-3588j.dtb`（MIPI 屏变体按需再加 `rk3588-firefly-itx-3588j-mipi*.dtb`）。
6. **烧完黑屏排查顺序**：串口有没有 DDR init/uboot log → 有 uboot 没 kernel 看 boot 分区和 dts → 有内核没安卓看 logcat/SELinux avc。工具与升级失败分析见 SDK 内 `RKDocs/Rockchip_Firmware_Upgrade_Failed_Analyze_Method_CN.pdf`。

