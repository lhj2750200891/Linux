# Android 开发

## 1. SDK 获取与编译

```
# 我这里是firefly的android 16
git clone ssh://git@git.t-firefly.com:8022/rockchip-android/android16/rk3572-android16.git

# 编译
source build/envsetup.sh
grep -rh -A 8 COMMON_LUNCH_CHOICES device/rockchip/rk3572/*/AndroidProducts.mk # 查看板型
lunch rk3572_firefly_r3572a-bp4a-userdebug
./build.sh -AUCKu
```

### 1.1 板型(lunch 目标)全集

| lunch 目标 | 板型 | 默认 dts |
|---|---|---|
| `rk3572_firefly_r3572a-bp4a-userdebug` | Firefly R3572A(我的板) | rk3572-firefly-r3572a |
| `rk3572_firefly_r5a-bp4a-userdebug` | Firefly R5A | rk3572-firefly-r5a |
| `rk3572_a16-bp4a-userdebug` | RK3572 EVB1 | rk3572-evb1-v10 |
| `rk3572s_a16-bp4a-userdebug` | RK3572S EVB1 | rk3572s-evb1-v10 |
| `rk3572_ebook-bp4a-userdebug` | 电子书方案 | rk3572-ebook-a3-v10 |

- 每个产品都有 `-userdebug`(调试,可 root)和 `-user`(量产)两个版本。
- release 段固定 `bp4a`;不要用两段式 `lunch xxx`,否则 release 默认成 `trunk_staging`、variant 默认 `eng`。
- `print_lunch_menu` 虽然存在,但它底层要跑 soong_ui 冷启动(几分钟),失败会报 "Cannot display lunch menu",不必纠结,用上面的 grep 查板型即可。
- `lunch` 第一次执行同样要跑 soong_ui 分析,几分钟没输出是正常的,**别 ^C**。

### 1.2 一键编译参数

```
./build.sh -AUCKu [-J 32] [-v user|userdebug] [-d <dts名>]
```
`-A`ndroid + `-U`boot + `-C`/`-K`ernel(Clang) + `-u`pdate.img 打包。
共享服务器建议: `nice -n 10 ./build.sh -AUCKu -J 32`(机器 192 核 251G,别把负载打满)。

### 1.3 编译产物

首次全量约 1~3 小时,`out/` 会额外占 250~350G(源码本身 137G,`/home4/lhj` 独立盘剩 846G,够用)。

```
rockdev/Image-rk3572_firefly_r3572a/
├── update.img        # 整包固件,烧写工具直接烧这一个
├── parameter.txt     # 分区表,烧写前必须加载
├── MiniLoaderAll.bin # 一级 loader
├── uboot.img         # uboot
├── trust.img         # BL31/BL32(ATF)
├── boot.img          # kernel + dtb + ramdisk(AVB 校验对象)
├── boot-debug.img    # user 版可烧它获得 root 调试能力
├── dtbo.img          # device tree overlay
├── recovery.img
├── super.img         # 动态分区: system+vendor+product+odm+system_ext
├── vbmeta.img        # AVB 校验信息
├── misc.img          # recovery/pcba 开机标识
└── config.cfg        # 导入烧写工具可直接显示要烧的选项
```

默认**不开 GKI**(`BOARD_BUILD_GKI := false`),所以上面这条一键编译直接可用。

## 2. Android 与 Linux(嵌入式 BSP)开发差异对比

| 维度 | 嵌入式 Linux(RK3588 那套) | Android(RK3572 这套) |
|---|---|---|
| 构建系统 | Kconfig/defconfig + make;一条 `make xxx_defconfig && make` | Soong/Blaze(Android.bp)+ Make 残留(.mk);`envsetup.sh` + `lunch` 选目标,`build.sh` 封装 |
| 内核 config | 一个 defconfig 说清一切 | 三层组合: `rockchip_defconfig` + `android-16.config`(通用安卓配置)+ `rk3572.config`(芯片配置),改配置要落到对应 config 文件,menuconfig 手改会被 `make distclean` 冲掉 |
| 内核工具链 | SDK 自带 gcc/clang,make 直接用 | SDK prebuilts 自带 clang-r574158 + **rust 1.88**(kernel-6.12 强依赖 rust)+ bindgen,环境变量由 build.sh/mkboot.sh 注入 |
| 启动链 | spl → uboot → boot.img(kernel+dtb) → rootfs | loader → uboot → boot.img(含 Android ramdisk,dts 编译进 dtb 内嵌)→ super 动态分区挂载 system/vendor/product/odm;全程 AVB 校验(vbmeta.img) |
| 分区/根文件系统 | 整个 rootfs 一个 ext4 分区,ssh 上去随便改 | system/vendor/product/odm 在 super.img 里(动态分区),只读;userdebug 下 `adb remount` 后才能改,量产改不了;改系统内容要重新编译 |
| init | systemd / busybox init,/etc/rc*.d、unit 文件 | Android init,`.rc` 语言(device/rockchip/common/init/*.rc 等),服务靠 `service` 节点声明;属性系统 `getprop/setprop` 代替 sysconf |
| 权限模型 | 真 root,rootfs 里就是天王老子 | userdebug 才有 `adb root`;且 SELinux enforcing,程序行为被策略限制,违规看 `logcat | grep avc` |
| 用户态 C 库 | glibc / musl | **bionic**,二进制不通用;交叉编译要用 NDK 或 SDK prebuilts 工具链 |
| 调试入口 | ssh + 串口,dmesg/journalctl | adb(usb/网络)+ 串口;logcat(应用+native)、dmesg 仍可用、dumpsys/bugreport 是安卓特有 |
| 显示/输入 | 直接写 drm/fb/evdev | 应用层走 SurfaceFlinger,硬件层是 HAL(hwcomposer/gralloc);改显示行为要么改 HAL 要么改 dts+overlay |
| 烧写 | dd / RKDevTool 烧 rootfs | RKDevTool(≥3.41)/ upgrade_tool(≥2.55)烧整包或分区;动态分区走 fastbootd |
| 应用生态 | 自己写 C/Qt/服务 | APK + JNI;平台开发常改 framework(java/kotlin)+ native(C++)两层 |

一句话:**kernel/dts/u-boot 这层两端几乎一样,我的 Linux 经验直接复用;从 boot.img 往上(rootfs、init、权限、调试入口)全是安卓自己的世界,要按安卓的规则来。**

## 3. 与 Linux 不同之处:逐项详细教程

> 每节结构:差异本质 → 这套 SDK 里的落地位置 → 完整实操。例子统一用一个 aarch64 C 程序 `mydaemon` 贯穿(编进系统 → 开机自启 → SELinux 放行 → 打日志)。

### 3.1 构建系统:从 make/Kconfig 到 Soong/lunch

| Linux 习惯 | Android 等价物 |
|---|---|
| `make xxx_defconfig` | `source build/envsetup.sh && lunch <target>`(选的是"产品+variant") |
| `make -j` | `m -j`(全量);内核仍是老 make |
| `make 目标` | `m <模块名>`(模块名 = Android.bp 里的 `name:`) |
| Kconfig+defconfig | 内核侧不变;**系统组件**由 `PRODUCT_*` 变量在 device.mk 里拼装 |
| Makefile | 编译产物用 Android.bp;板子配置(分区/dts/预装)仍用 .mk |

Android.bp 最小骨架(后面几节的例子都基于它):

```
// 文件: device/rockchip/rk3572/rk3572_firefly_r3572a/mydaemon/Android.bp
cc_binary {
    name: "mydaemon",
    srcs: ["mydaemon.c"],
    shared_libs: ["liblog"],      // 用安卓日志接口(见 3.7);纯 libc 可删这行
    init_rc: ["mydaemon.rc"],     // 自动安装到 /system/etc/init/,见 3.2
}

// 同目录 device.mk 里加一行,让它进 super.img:
// PRODUCT_PACKAGES += mydaemon
```

要点:
- Soong 会索引整棵树所有 Android.bp,放板级目录下即可被发现,不用手动 include;
- 编出来的位置:`out/target/product/rk3572_firefly_r3572a/system/bin/mydaemon`;
- 记忆口诀:**编什么程序用 bp,板子长什么样用 mk**(BoardConfig.mk/device.mk)。

### 3.2 init 与开机服务:.rc 代替 systemd

| systemd | Android init(.rc) |
|---|---|
| [Service] ExecStart= | `service 名字 /system/bin/xxx` 块 |
| WantedBy=multi-user.target | `class main` / `class late_start` |
| Restart=always | 默认行为:崩溃后自动重启;`oneshot` = 只跑一次 |
| systemctl start/stop | `adb shell start xxx` / `stop xxx` |
| 用户/组 User=, Group= | `user root` / `group root` 等 |

`mydaemon.rc` 完整例子(与 3.1 的 cc_binary 放同一目录,init_rc 会装到 /system/etc/init/):

```
service mydaemon /system/bin/mydaemon
    user root
    group root
    class late_start
    seclabel u:r:su:s0        # userdebug 临时通行证;量产必须按 3.4 走正规 domain

on property:sys.boot_completed=1
    start mydaemon
```

实操链路(改完 `./build.sh -A`,烧 super):
1. `adb shell ps -A | grep mydaemon` 确认被拉起;
2. `adb shell start mydaemon` / `stop mydaemon` 手动控制;
3. 服务崩溃 init 会自动重启,日志看 `adb logcat | grep -i init`。

### 3.3 属性系统 getprop/setprop(Linux 没有)

全局 key-value,由 init 维护,所有进程可见,常用来做配置开关和进程间通知。

- 前缀规则:`ro.` 只读;`persist.` 重启保留(存 /data);`ctl.start/xxx` 控制类;`vendor.` 只有 vendor 进程可写;
- 板级定义位置:device.mk 里 `PRODUCT_VENDOR_PROPERTIES += ro.vendor.my.flag=1`(编进 vendor/build.prop);
- 与 .rc 联动:

```
on property:persist.vendor.my.flag=1
    start mydaemon
```

```bash
adb shell getprop | grep -i my          # 全量查
adb shell setprop persist.vendor.my.flag 1
```

### 3.4 SELinux:Linux 工程师最大的坑

Linux 上 root 即无敌;安卓上 SELinux enforcing,进程行为被策略白名单限制。三板斧:

```bash
adb shell getenforce                                  # Enforcing?
adb shell setenforce 0                                # userdebug 可临时关,先确认"是不是 selinux 拦的"
adb shell setenforce 1
adb shell dmesg | grep -i denied                      # 回看拒绝记录
```

读懂一条 avc:

```
avc: denied { read } for comm="mydaemon" name="xxx" dev="sysfs"
scontext=u:r:mydaemon:s0 tcontext=u:object_r:sysfs:s0 tclass=file permissive=0
```
含义:`mydaemon` 域(进程)对 `sysfs` 类型(文件)做 `read` 被拒 → 策略里补 `allow mydaemon sysfs:file read;` 即可。

量产正规做法(替代 3.2 的 su 通行证),在 `device/rockchip/rk3572/rk3572_firefly_r3572a/sepolicy_vendor/` 新增:

```
# mydaemon.te
type mydaemon, domain;
type mydaemon_exec, exec_type, file_type;

init_daemon_domain(mydaemon)               # init 拉起时自动切到本 domain
allow mydaemon sysfs:file r_file_perms;    # 按 avc 逐条补,不求一步到位
```

再在同目录加/改 `file_contexts`,给可执行文件打标签(标签决定 tcontext):

```
/system/bin/mydaemon  u:object_r:mydaemon_exec:s0
```

原则:
- 策略编进 super,`./build.sh -A` 重编生效;
- **neverallow 是编译期检查**,别对抗全局策略,按 avc 一条条补;
- 参考现有写法:`grep -rh "^allow " device/rockchip/*/sepolicy*/ | head -30`。

### 3.5 文件系统布局:大部分"系统目录"是只读的

| 路径 | 可写? | Linux 对应 |
|---|---|---|
| /system /vendor /product /odm | ❌ 只读(super 动态分区) | 相当于把 /usr 拆成四个只读分区 |
| /data | ✅ | /var + /home 合体,应用数据、persist 属性在这 |
| /data/local/tmp | ✅ | adb 推文件的"家",shell 可执行 |
| /dev /proc /sys | ✅(临时态) | 与 Linux 完全一样 |
| /system/etc | ❌ | /etc |

持久修改系统文件只有两条路:改源码重编(正规);userdebug 下 `adb root && adb disable-verity`(重启)后 `adb remount` 做 overlay(重启即失效,只适合当场试效果)。量产镜像别碰 verity。

### 3.6 bionic 与交叉编译:glibc 习惯全要换

- 系统 libc 是 **bionic**,PC 上编的 aarch64 动态二进制推上去直接 "not found"(没有匹配的 glibc/ld.so);
- 动态库有命名空间隔离:/system 进程只能链 /system/lib64,/vendor 只能链 /vendor/lib64,"推个 so 上去 dlopen" 经常被 linker 直接拒;
- 没有 /etc(resolv.conf、nsswitch 都没有),DNS 由 netd 代理;没有 systemd,守护逻辑按 init 规则来。

姿势 A——临时跑个工具,静态编译绕开一切:

```bash
# NDK 工具链在 SDK 树里,r 版本以 prebuilts/ndk/ 实际为准
TC=prebuilts/ndk/r*/toolchains/llvm/prebuilt/linux-x86_64/bin
$TC/aarch64-linux-android34-clang -static hello.c -o hello
adb push hello /data/local/tmp/ && adb shell /data/local/tmp/hello
```

姿势 B——要进系统的组件,必须走 3.1 的 Android.bp 编进镜像,PC 工具链编的别直接塞。

### 3.7 日志体系:printf 去哪了、logcat 怎么用

- Linux 的 journald/stdout 三件套换成 **logcat**(应用+native+system)+ dmesg(内核,不变);
- C 里 printf 在后台服务里**没人看**(没有 journald 收集),native 打日志用 liblog:

```c
#include <android/log.h>
__android_log_print(ANDROID_LOG_INFO, "mydaemon", "hello %d", 42);
```

```bash
adb logcat -c && adb logcat -v time | grep -i mydaemon   # 清空+时间戳+过滤
adb logcat -b crash                                       # 单看崩溃缓冲
adb logcat --pid=$(adb shell pidof mydaemon)              # 只看某进程
adb shell dumpsys activity | head -50                     # 各系统服务状态快照(dumpsys <服务名>)
adb bugreport bug.zip                                     # 疑难杂症全家桶
```

- 内核日志还是老朋友 `adb shell dmesg`;串口同样可用(RK 平台 debug 串口一般 1500000 8N1,连不上就查 dts 的 stdout-path)。

### 3.8 显示/硬件栈:你的 dts 经验还在,上面多一层 HAL

- 内核侧(drm/encoder/HPD/时序)与 Linux 完全同一套——RK3588 上调过的 route/force-output 那套 dtsi 手法在安卓原样适用,照旧 mkboot.sh 烧 boot;
- 区别在用户态:应用 → SurfaceFlinger → **HWC HAL** → 内核 drm。排查分流:画面内容/合成问题看 SurfaceFlinger(`dumpsys SurfaceFlinger`),时序/点屏/掉线问题仍回 dts+驱动;
- RK 的 HAL 源码在树里 `hardware/rockchip/`(hwcomposer/audio/sensors/camera),改 HAL 走 `./build.sh -A` 烧 super。

## 4. 详细开发流程

### 4.1 每次登录后的环境初始化(必做)

```bash
cd /home4/lhj/arm64/rockchip/rockchip_android_sdk/rk3572-android16
source build/envsetup.sh
lunch rk3572_firefly_r3572a-bp4a-userdebug   # 第一次会跑几分钟 soong_ui,别打断
```

### 4.2 全量编译(首次/大改动后)

```bash
nice -n 10 ./build.sh -AUCKu -J 32
# 产物: rockdev/Image-rk3572_firefly_r3572a/update.img 及各分区镜像
```

### 4.3 只改内核(驱动/dts/config)——最快路径

SDK 自带 `kernel-6.12/mkboot.sh`(原理: 把新编的 Image/dtb 替换进旧 boot.img,**不会**重编 Android):

```bash
cd kernel-6.12
./mkboot.sh rk3572-firefly-r3572a ../rockdev/Image-rk3572_firefly_r3572a/boot.img rk3572.config
# 输出: kernel-6.12/boot.img → 烧到板子的 boot 分区即可
```

注意:
- dts 文件在 `kernel-6.12/arch/arm64/boot/dts/rockchip/`,板级 dts 名与 `device/rockchip/rk3572/rk3572_firefly_r3572a/BoardConfig.mk` 里的 `PRODUCT_KERNEL_DTS` 一致。
- 内核 config 是三层组合 `rockchip_defconfig + android-16.config + rk3572.config`;想永久改配置,改这些文件(或加 fragment),menuconfig 手改的会丢(`build.sh -K` 每次都 `make distclean`)。
- `./build.sh -K` 编完内核但**不会**自动刷新 rockdev 的 boot.img;要走 rockdev 就得 `-AK`(连带重编 Android,慢),所以日常用 mkboot.sh。

### 4.4 只改 u-boot

```bash
./build.sh -U     # 产物 rockdev/Image-*/uboot.img(和 trust/MiniLoaderAll 视改动而定)
```

### 4.5 改 Android 上层(framework / 预装应用 / sepolicy / 设备配置)

```bash
./build.sh -A     # 增量编译 Android,产物更新到 rockdev(重打包 super.img 需 -p)
```

常改的位置:
- 板级配置/dts 选择/预装: `device/rockchip/rk3572/rk3572_firefly_r3572a/`(device.mk、BoardConfig.mk)
- SELinux 板级策略: 同目录 `sepolicy_vendor/`;被拒先看 `logcat | grep avc`,再补规则
- framework/系统服务: `frameworks/`,单模块调试用 `m <模块名>`(envsetup 提供)

### 4.6 烧写

- 整包: RKDevTool ≥3.41(Windows, `RKTools/windows/AndroidTool/`)或 upgrade_tool ≥2.55(Linux, `RKTools/linux/Linux_Upgrade_Tool/`),切换到"升级固件"页,导入 `update.img`。
- 单分区: "下载镜像"页加载 `parameter.txt`(或导入 `config.cfg`),勾选要烧的分区镜像。
- 动态分区(system/vendor 等)也可 fastbootd:
  ```
  adb reboot fastboot
  fastboot flash super super.img   # 或单独 flash vendor/system
  fastboot reboot
  ```

### 4.7 板子上调试

```bash
adb devices; adb root; adb remount        # userdebug 才可用
adb push xxx /data/; adb shell
logcat | grep -i xxx                      # 应用/native 日志
adb shell dmesg                           # 内核日志,和 Linux 一样
adb shell getprop / setprop               # 属性系统
```

### 4.8 典型场景速查

| 需求 | 改哪里 | 编译方式 |
|---|---|---|
| 加/改驱动 | kernel-6.12/drivers/... | mkboot.sh → 烧 boot |
| 改 dts(外设/显示/HPD 等) | kernel-6.12 dts | mkboot.sh → 烧 boot |
| 内核配置项 | configs 三层文件 | mkboot.sh → 烧 boot |
| uboot/开机 logo | u-boot/ | build.sh -U → 烧 uboot |
| 开机自启服务 | .rc 文件(device 树下) | build.sh -A → 烧 super |
| 预装 APK | device.mk / PRODUCT_PACKAGES | build.sh -A → 烧 super |
| SELinux 放行 | sepolicy_vendor/ | build.sh -A → 烧 super |
| 显示/多媒体 HAL | hardware/rockchip/ | build.sh -A → 烧 super |

## 5. 参考资料(SDK 内,服务器上)

- `RKDocs/android/Rockchip_RK3572_Developer_Guide_Android16_SDK_CN.pdf` — 总指南(编译 2.5、固件 2.8、fastboot 2.9、dtbo 3、fstab 4、parameter 5、新产 6、dts 7)
- `RKDocs/android/Rockchip_Developer_Guide_Android14_GKI_CN.pdf` — 开 GKI 时再看
- 烧写失败排查: `Rockchip_Firmware_Upgrade_Failed_Analyze_Method_CN.pdf`

## 6. 能不能在虚拟机里跑?

### 6.1 RK3572 固件本身 —— 不能

- `MiniLoaderAll.bin` 是 RK3572 专用 DDR init blob,QEMU 没有 RK3572 机器模型;
- 内核按 `rockchip_defconfig` + rk3572 dts 编译,期望真 SoC 外设,在 QEMU `-M virt` 上早期就挂;
- QEMU 纯软件模拟 aarch64(无 KVM)慢 10~50 倍,不可用。

**结论:驱动/dts/uboot/HAL 的验证只能烧真板,VM 不参与 BSP 开发流程。**

### 6.2 Cuttlefish —— 树里自带,可跑通用 Android

适合 framework/Java 应用层调试;跑的是通用镜像,**没有 RK 的 dts/驱动/HAL,对 BSP 无验证意义**。

```bash
# 服务器上编译(注意:cuttlefish 目标不能用 build.sh,直接用 m)
source build/envsetup.sh
lunch aosp_cf_x86_64_phone-trunk_staging-userdebug
m -j32
# 产物在 out/dist/(boot.img/super.img/cvd 主机包),打包拷回本机

# 本机运行要求: x86_64 + KVM + 空闲内存 ≥16G
# launch_cvd 起虚拟机,带 WebRTC 浏览器窗口,可 adb 连接
```

可选目标(树内 `device/google/cuttlefish/`):`aosp_cf_x86_64_phone` / `aosp_cf_arm64_phone` / `aosp_cf_arm64_auto` / `aosp_cf_riscv64_phone` 等。

### 6.3 其他方案

- Android Emulator(goldfish,prebuilts 里有)—— 应用层用,与 RK 固件无关;
- Waydroid/Anbox —— 通用 Android 容器,不是这份固件;
- chroot + qemu-user 跑 super.img 里的 system —— 玩具级,init/binder 全缺,跑不起来。

