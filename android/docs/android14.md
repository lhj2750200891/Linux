# Android 开发

## 1. SDK 获取与编译

```
# 下载源码包,我是从ftp中下载下来的
# 如果下载下来的是7z.001-011,则直接使用md5sum -c MD5.txt进行校验
# 如果下载下来的是一个zip压缩包,解压后校验: unzip firefly_rk3588_android14_git_240822.zip
cd firefly_rk3588_android14_git_240822/
md5sum -c MD5.txt    # 每个包都是ok即可
7z x ./firefly_rk3588_android14_git_240822.7z.001 -oRK3588_Android14.0    # 解压
cd ./RK3588_Android14.0
git reset --hard
source build/envsetup.sh
lunch rk3588_firefly_aio_3588q-userdebug
cd u-boot
./make.sh rk3588
cd ..
./build.sh -KAu 

# 如果不采用先编译UBOOT的方式,需要改rk3588下的mk文件
 vim device/rockchip/rk3588/BoardConfig.mk
 /PRODUCT_UBOOT_CONFIG   # 找到这个变量,改为
 rk3588_defconfig   # 原来是rk3588.需要改为 rk3588_defconfig
 ./build.sh -AUCKu -J$(nproc)
```



## 2. 新增板型

### 2.1 itx-3588j

编译阶段不要使用root,一定使用普通用户编译

```
# 前提:当前在 SDK 根目录(服务器 RK3588_Android14.0)

# 1. device 产品目录:拷 aio 改名 
cd device/rockchip/rk3588
cp -r rk3588_firefly_aio_3588q rk3588_firefly_itx_3588j
cd rk3588_firefly_itx_3588j

# 目录内只有 2 个文件内容含 aio_3588q(下划线),先全局替换
sed -i 's/aio_3588q/itx_3588j/g' BoardConfig.mk rk3588_firefly_aio_3588q.mk
# 文件名跟上改
mv rk3588_firefly_aio_3588q.mk rk3588_firefly_itx_3588j.mk
mv init.rk3588_firefly_aio_3588q.rc init.rk3588_firefly_itx_3588j.rc

# BoardConfig.mk:dts 名是连字符 aio-3588q,上面的下划线替换覆盖不到,单独替换
sed -i 's/rk3588-firefly-aio-3588q/rk3588-firefly-itx-3588j/g' BoardConfig.mk

# itx 的 mk:改 model/名称,删 HDMI-IN(ITX 无视频输入)
sed -i 's/AIO-3588Q/ITX-3588J/g' rk3588_firefly_itx_3588j.mk
sed -i 's/PRODUCT_FIREFLY_NAME := HDMI/PRODUCT_FIREFLY_NAME := ITX/' rk3588_firefly_itx_3588j.mk
sed -i '/BOARD_HDMI_IN_SUPPORT := true/d; /CAMERA_SUPPORT_HDMI := true/d; /PRODUCT_PACKAGES += rkCamera2/d' rk3588_firefly_itx_3588j.mk

# 检查无残留(应无输出;有则按上下文改掉)
grep -rni "aio" .

#  2. kernel dts (最好去掉多余的模块,否则会导致无法进入系统)
cd ../../../../kernel-6.1/arch/arm64/boot/dts/rockchip
cp rk3588-firefly-aio-3588q.dts  rk3588-firefly-itx-3588j.dts
cp rk3588-firefly-aio-3588q.dtsi rk3588-firefly-itx-3588j.dtsi
sed -i 's/rk3588-firefly-aio-3588q/rk3588-firefly-itx-3588j/g' rk3588-firefly-itx-3588j.dts rk3588-firefly-itx-3588j.dtsi

# dts:注释掉摄像头 include(ITX 先不带 cam),改 model
sed -i 's|^#include "rk3588-firefly-aio-cam|// #include "rk3588-firefly-aio-cam|' rk3588-firefly-itx-3588j.dts
sed -i 's/Firefly AIO-3588Q HDMI(Android)/Firefly ITX-3588J(Android)/' rk3588-firefly-itx-3588j.dts

#  3. 注册 dtb 
echo 'dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3588-firefly-itx-3588j.dtb' >> kernel-6.1/arch/arm64/boot/dts/rockchip/Makefile
# (本树 aio 未注册也能编,加上保险,防 make dtbs 缺)

# ---------- 4. 注册 lunch ----------
# vim device/rockchip/rk3588/AndroidProducts.mk
#   产品列表(aio_mipi 那行后)加:
#       $(LOCAL_DIR)/rk3588_firefly_itx_3588j/rk3588_firefly_itx_3588j.mk \
#   COMMON_LUNCH_CHOICES(aio_mipi 条目后)加:
#       rk3588_firefly_itx_3588j-userdebug \
#       rk3588_firefly_itx_3588j-user \

# ---------- 5. 编译 ----------
cd /回到/SDK/根目录
rm -rf out    # 换产品必须清 out(见坑3)
source build/envsetup.sh
lunch rk3588_firefly_itx_3588j-userdebug
./build.sh -AUCKu -d rk3588-firefly-itx-3588j -J$(nproc)
make recoveryimage -j$(nproc)     # 改了 dts/内核后 recovery 必须重编
# 产物:rockdev/Image-rk3588_firefly_itx_3588j/

# 烧录
scp rockdev/Image-rk3588_firefly_itx_3588j/update.img lhj@172.16.10.222:/home/lhj
scp rockdev/Image-rk3588_firefly_itx_3588j/boot.img lhj@172.16.10.222:/home/lhj
scp rockdev/Image-rk3588_firefly_itx_3588j/misc.img lhj@172.16.10.222:/home/lhj
scp out/target/product/rk3588_firefly_itx_3588j/recovery.img lhj@172.16.10.222:/home/lhj

# —— 以下 upgrade_tool 在【本机】执行,板子先进 Loader(adb reboot loader 或按 Recovery 复位)——
sudo upgrade_tool uf /home/lhj/update.img   
sudo upgrade_tool di -r /home/lhj/recovery.img   
sudo upgrade_tool di -m /home/lhj/misc.img

/home/lhj/boot.img 单刷 boot 分区(日常改内核用)
```

### 2.2 lga_3588l_mini

```
cd /home4/lhj/arm64/rockchip/rockchip_android_sdk/RK3588_Android14.0
cd device/rockchip/rk3588
cp -r rk3588_firefly_aio_3588q rk3588_firefly_lga_3588l_mini
cd rk3588_firefly_lga_3588l_mini/
mv rk3588_firefly_aio_3588q.mk rk3588_firefly_lga_3588l_mini.mk 
mv init.rk3588_firefly_aio_3588q.rc init.rk3588_firefly_lga_3588l_mini.rc 
vim BoardConfig.mk # 替换下面的内容
	device/rockchip/rk3588/rk3588_firefly_aio_3588q/recovery.fstab_AB 改为
	device/rockchip/rk3588/rk3588_firefly_lga_3588l_mini/recovery.fstab_AB
	
	PRODUCT_KERNEL_DTS := rk3588-firefly-aio-3588q 改为
	PRODUCT_KERNEL_DTS := rk3588-firefly-lga-3588l-mini
vim rk3588_firefly_lga_3588l_mini.mk  # 替换下面的内容
	device/rockchip/rk3588/rk3588_firefly_aio_3588q/BoardConfig.mk 改为
	device/rockchip/rk3588/rk3588_firefly_lga_3588l_mini/BoardConfig.mk
	
	PRODUCT_NAME := rk3588_firefly_aio_3588q 改为
	PRODUCT_NAME := rk3588_firefly_lga_3588l_mini
	
	PRODUCT_DEVICE := rk3588_firefly_aio_3588q 改为
	PRODUCT_DEVICE := rk3588_firefly_lga_3588l_mini
	
	PRODUCT_MODEL := AIO-3588Q 改为
	PRODUCT_MODEL := LGA-3588L-MINI
	
	PRODUCT_COPY_FILES 中替换目录为lga_3588l_mini
grep -rni "aio" .  # 没有输出即可

cd /home4/lhj/arm64/rockchip/rockchip_android_sdk/RK3588_Android14.0/
cd kernel-6.1/arch/arm64/boot/dts/rockchip/
cp rk3588-firefly-aio-3588q.dts  rk3588-firefly-lga-3588l-mini.dts
cp rk3588-firefly-aio-3588q.dtsi rk3588-firefly-lga-3588l-mini.dtsi
vim rk3588-firefly-lga-3588l-mini.dts # 改为下面的内容
	#include "rk3588-firefly-lga-3588l-mini.dtsi"
	model = "Firefly LGA-3588L-MINI HDMI(Android)";
	compatible = "rockchip,rk3588-firefly-lga-3588l-mini", "rockchip,rk3588";
vim rk3588-firefly-lga-3588l-mini.dtsi   # 删除里面的所有内容,只保留hdmi和电源led即可

cd /home4/lhj/arm64/rockchip/rockchip_android_sdk/RK3588_Android14.0/
vim device/rockchip/rk3588/AndroidProducts.mk
```



## 3. Android 与 Linux 异同对比

> 对照样本（均为只读分析结论，路径以实际机器为准）：
> - Android14 SDK：`/media/lhj/windows/code/arm64/rockchip/rockchip_android_sdk/android_sdk`（Rockchip Android14，内核 `kernel-6.1` = **6.1.141**，目标板 `rk3588_firefly_itx_3588j`）
> - Linux BSP SDK：`/media/lhj/data/t-chip/7.code/arm64/rockchip/rk3588_6.1.118_sdk`（Firefly Linux SDK，内核 **6.1.118**，同一板子有 `firefly_rk3588_itx-3588j_{buildroot,debian,ubuntu,openeuler}_defconfig`）

### 3.1 总体定位对比

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

### 3.2 相同点：底层 BSP 是同一套

1. **三件套同源**：u-boot、kernel、`rkbin/`（DDR loader、boot_merger 等）两边结构一致。RK3588 启动链都是 BootROM → MiniLoaderAll（DDR 初始化）→ uboot.img（内含 BL31/ATF）→ boot；`BOARD_ROCKCHIP_TRUST_MERGE_TO_UBOOT` 两侧等价（trust 并入 uboot，无独立 trust 镜像）。
2. **内核开发流程完全一致**：改 `arch/arm64/boot/dts/rockchip/*.dts(i)`、menuconfig/defconfig 片段合并、驱动 `.ko`、打补丁——方法和工具链（clang/LLVM）两边通用。
3. **设备树同源同形**：两边都有 `rk3588-firefly-itx-3588j.dts/.dtsi`，且都是“板级 dts → `rk3588-firefly-core.dtsi`/`rk3588-firefly-port.dtsi` → 平台差异 dtsi”的分层结构。差异只在尾巴：Android 版挂 `rk3588-android.dtsi`（reboot-to-bootloader、android fstab 等软件策略节点），Linux 版挂 `rk3588-linux.dtsi`。**外设使能节点（GPIO/UART/I2C/SPI/摄像头/网卡）两边基本可互抄**，软件策略节点不能。
4. **分区与烧录一致**：parameter.txt、update.img、RKDevTool/upgrade_tool、MaskRom/Loader 进入方式、调试串口 UART2 1500000 波特率，两边相同。
5. **交叉编译环境**：都是 x86_64 主机出 arm64 产物，工具链均来自 SDK 内置（Android 在 `prebuilts/clang`，Linux 在 `prebuilts/`）。

> ⚠️ 注意：两棵树内核基线不同（**6.1.141 vs 6.1.118**），驱动补丁和 dts 片段**不能整文件互拷**，只能当参考，合入前需确认上下文冲突。

### 3.3 关键差异

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

## 4. Android14 开发步骤

### 4.1 环境准备

- 编译主机：x86_64 Ubuntu（本机实测 Ubuntu 22.04 可用），磁盘 ≥ 250G（out/ 一套约 100G+，kernel/android 双份产物另计），内存越大越好（`-J96` 是按 96 线程跑的）。
- 源码见第 1 节（分卷合并 → md5 校验 → 解压）。
- Android 与 Linux 两个 SDK **不要共用 out 目录混编**（见第 4 节坑 3）。

### 4.2 编译流程详解

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

### 4.3 产物与烧录

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

### 4.4 调试手段

```text
adb devices / adb root / adb remount          # userdebug 可直接 root、可写 /
adb shell dmesg -w                            # 内核日志（与 Linux 完全相同）
adb shell cat /proc/kmsg                      # 同上
logcat                                        # 用户态日志
adb shell getprop / setprop                   # 系统属性
adb reboot bootloader                         # 进 fastboot
```

底层问题仍然是串口第一优先：UART2、1500000 波特率。烧卡死/黑屏先看串口，再 `logcat | grep -E "avc|ServiceManager"` 查 SELinux/服务问题。

### 4.5 典型开发任务 SOP

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

### 4.6 同一任务的 Linux ↔ Android 对照表

| 任务 | Linux BSP SDK | Android14 SDK |
|---|---|---|
| 换内核配置 | 改 `RK_KERNEL_CFG_FRAGMENTS` / menuconfig | 改 defconfig 片段集（`kernel_config.mk` 拼装） |
| 使能一个 I2C 外设 | 板级 dts + 驱动，重出 boot FIT | **完全相同**（dts + 驱动），重出 boot.img |
| 换系统内容 | 换 rootfs defconfig 或 `build.sh post-rootfs` 脚本 | 改 PRODUCT_PACKAGES/overlay，重出 super.img |
| 看外设是否工作 | ssh + `dmesg`/`i2cdetect` | `adb shell` + 同样的 dmesg/i2cdetect |
| 开机自启程序 | systemd unit / rcS | init.rc（`device/rockchip/.../*.rc`）或系统服务 |
| 升级到新版本 | 重烧 update.img | OTA 包或整刷 |



