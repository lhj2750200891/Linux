# RK2118G EVB 板快速上手实操

> 目标: 拿到板子 → 看到串口日志 → 自己编译烧写 → 修改代码快速迭代
> 依据: `Rockchip_RK2118_Quick_Start_RT-Thread_CN.pdf` (V1.0.7) + `RK2118G_EVB_V20_User_Guide_V1.0_20240807_CN.pdf`
> 笔记时间: 2026-11-27

---

## 0. 先分清你的板子是 V1.0 还是 V2.0

| | EVB V1.0 | EVB V2.0 |
|---|---|---|
| 板级标识 | RK_EVB1_RK2118G_V10_20240219 | **RK_EVB1_RK2118G_V20_20240424**(丝印/贴纸可查) |
| 对应 BSP 目录 | `board/evb` | `board/evb1_v20` |
| 存储 | **SPI NOR** | **SPI NAND 128MB**(eMMC 8GB 可选) |
| 编译命令 | `./build.sh board/evb/package-file` | `./build.sh board/evb1_v20/package-file` |
| 用户指南 | `Rockchip_RK2118G_EVB_User_Guide_V1.0_CN_20240523.pdf` | `RK2118G_EVB_V20_User_Guide_V1.0_20240807_CN.pdf` |

看不准就数喇叭接线端子/看实物图(用户指南 2.1 实物图): V20 正面右侧一列是 SPK×3+DC12V+SPDIF RX/TX+AUX IN+Headphone,背面有 Audio Debug 和 SD 卡。

### EVB V20 板上关键接口(正对板子)

```
左侧: System Debug(TypeC,看日志) / USB2 Device(TypeC,烧写) / USB2 HOST / RJ45 网口 / IR
中上: Display 连接器 / MCU JTAG / DSP JTAG / 3×SPK 喇叭端子(绿色)
右侧: DC12V 电源口 / Power Switch 电源开关 / SPDIF RX/TX / AUX IN / Headphone / Audio Connector
下侧: MIC 阵列 / Keys 按键组(MASKROM、RESET、V+、V-、PRE、NEXT、MODE、PLAY/MUTE)
背面: Audio Debug(TypeC)/ SD 卡槽 / Power Test 座
```

供电: DC 12V 适配器(包装自带,12V 3A),打开 Power Switch。

## 1. 第一步:上电看日志(先体验,不用烧写)

板子出厂一般已烧录固件,先直接开机体验:

1. Type-C 线连 **System Debug** 口到 PC(Windows 设备管理器看 COM 号;需要先装串口驱动 `bsp/rockchip/tools/CDM212364_Setup.zip`)
2. 串口终端(PuTTy/mobaxterm/minicom):**1500000 波特率,8 数据位,1 停止位,无校验,无流控**(流控必须设 None,否则没输出)
3. DC12V 供电,打开电源开关

正常应看到:

```
Booting TF-M 20240303
clk_init: PLL_GPLL = 800000000
clk_init: PLL_VPLL0 = 1179648000
... (一大串 clk_init)
    \ | /
   - RT -     Thread Operating System
    / | \     4.1.1 build Mar 15 2024
 2006 - 2022 Copyright by rt-thread team
[I/I2C] I2C bus [i2c2] registered
[Dsp0 INFO] Hello RK2118 dsp0. build ...
[Dsp1 INFO] Hello RK2118 dsp1. ...
[Dsp2 INFO] Hello RK2118 dsp2. ...
msh >                       ← FinSH shell 就绪
```

看到 `msh >` 就说明 CPU0 + 三个 DSP 全部起来了。**注意**: debug 串口与烧写共用场景见第 4 步红字提醒。

## 2. 第二步:搭建编译环境(Linux 主机)

```bash
# 依赖(Ubuntu 20.04/18.04)
sudo apt-get update
sudo apt-get install scons clang-format astyle build-essential \
                     dosfstools fusefat python3 python3-pip lzma

# 工具链:必须 arm-gnu-toolchain-13.2.Rel1(build.sh 会校验)
wget https://developer.arm.com/--media/Files/downloads/gnu/13.2.rel1/binrel/\
arm-gnu-toolchain-13.2.rel1-x86_64-arm-none-eabi.tar.xz
tar xvf arm-gnu-toolchain-13.2.rel1-x86_64-arm-none-eabi.tar.xz
export RTT_EXEC_PATH=/path/to/arm-gnu-toolchain-13.2.rel1-x86_64-arm-none-eabi/bin
echo $RTT_EXEC_PATH     # 确认
```

## 3. 第三步:一键编译(EVB 全流程,含 DSP 固件打包)

```bash
cd <SDK>/bsp/rockchip/rk2118

# EVB V2.0(SPI NAND):
./build.sh board/evb1_v20/package-file
# EVB V1.0(SPI NOR):
./build.sh board/evb/package-file
```

- 弹出 menuconfig 时:**直接选底部的 <Exit>,再选 <Yes> 保存退出**(用默认配置)
- 脚本自动完成: 编 cpu1(rtt1) → recovery → cpu0(rtt0) → 打 root.img → 打包
- 产物: `Image/update.img`(完整固件包,分 GPT 分区升级);BSP 根下有 `rtt0.bin/elf`、`rtt1.bin/elf`、`recovery.bin`
- DSP 固件不用自己编: 打包自动用 SDK 预编译的 `components/hifi4/rtt/dsp_fw/evb_soundbar_demo/`(对应 `evb_partybox_demo` 工程)
- 清理: `scons -c`,顽固时 `rm -rf build`

## 4. 第四步:烧写 update.img

### 进入烧写模式(MaskRom)三选一

1. 板子从未烧过固件 → 上电自动进 MaskRom
2. **按住 MASKROM 按键,再按 RESET(或重新上电)** → 进 MaskRom
3. 系统正常跑着时,串口输入 `reboot loader` → 进 MaskRom

### 方式 A: Windows + SocToolKit(推荐,最省事)

工具: `bsp/rockchip/tools/SocToolKit_v2.51_20250728_01_win.zip`,驱动: `DriverAssitant_v5.13.zip`(USB)、`CDM212364_Setup.zip`(串口)

1. 打开 SocToolKit → 选择芯片 **RK2118**
2. USB 烧写(优先): USB Device 口连 PC,工具 USB设备栏出现 `Maskrom ...` 标识 → 切到"固件升级"页 → 选择 `Image/update.img` → 点"升级"(可勾"重启设备")
3. 串口烧写(没有 USB 线时): 串口设备栏选 COM 口 + 波特率 **1500000** → 固件下载页勾 Loader(`rkbin/rk2118_db_loader.bin`)+ Firmware(`Image/Firmware.img`,地址 0x0)→ 下载

> ⚠️ 红字注意(Quick Start 原文):
> - 串口打印和串口烧写是同一个口,**烧写前必须断开串口终端**;串口烧写时不能插 USB
> - **USB DEVICE 和 SYS UART 同时接入时,只能 USB 烧写(USB 优先级最高)**
> - 分区烧写(改了 rtt0 不用整包重烧): USB 模式下选 loader(rk2118_db_loader.bin)+ 单个 rtt0.bin,地址按 setting.ini 的 PartOffset×512 填

### 方式 B: Linux + upgrade_tool(USB)

```bash
cd <SDK>/bsp/rockchip/rk2118
# EVB 烧 update.img 包: uf 自动解析分区表、自动下 loader,板子只需在 MaskRom
sudo ../tools/upgrade/upgrade_tool uf ./Image/update.img
# 若 uf 失败再手动两步(loader 在 rkbin/ 下,不在 Image/)
sudo ../tools/upgrade/upgrade_tool db ./rkbin/rk2118_db_loader.bin
sudo ../tools/upgrade/upgrade_tool uf ./Image/update.img
# 开发期单分区快烧(EVB V20: cpu0_os_a@0x2200;烧 Image/ 下带 RESC 头的 .img,不是裸 bin)
sudo ../tools/upgrade/upgrade_tool db ./rkbin/rk2118_db_loader.bin
sudo ../tools/upgrade/upgrade_tool wl 0x2200 ./Image/rtt0.img
# 其余分区偏移查 board/evb1_v20/parameter.txt(dsp1_a@0xb200、root_a@0x15a00 等)
```

排查 `Open loader failed`: ①loader 路径(在 `rkbin/`,Image/ 里只有 MiniLoaderAll*);②板子确实进了 MaskRom(按住 MASKROM 再按 RESET);③线插在 **USB2 Device** 口(不是 HOST/调试口),`lsusb` 应能看到 `2207:xxxx` Rockchip 设备;④加 `sudo`(无 udev 规则时普通用户无 USB 权限)。

### EVB V20 固件↔分区速查(单位=512B sector,来源 parameter.txt)

| 分区 | a / b 偏移 | 内容 | 备注 |
|---|---|---|---|
| loader | 0x0 | IDB(MiniLoaderAll) | uf/db 自动处理,不单独烧 |
| vnvm | 0x600 | vendor storage | RKDevInfoWriteTool 写 |
| cpu0_secure_a/b | 0xa00 / 0xe00 | Image/tfm_s.img | 预编译,基本不烧 |
| recovery | 0x1200 | Image/recovery.img | 改升级逻辑才烧 |
| misc | 0x1a00 | Image/misc.img | 全零占位 |
| **cpu0_os_a/b** | **0x2200** / 0x4200 | **Image/rtt0.img** | **日常开发最常烧** |
| cpu1_os_a/b | 0x3200 / 0x5200 | Image/rtt1.img | 改 CPU1 才烧 |
| dsp0_a/b | 0x6200 / 0x8a00 | Image/dsp0.img | 预编译 partybox 固件 |
| dsp1_a/b | 0xb200 / 0xda00 | Image/dsp1.img | |
| dsp2_a/b | 0x10200 / 0x12a00 | Image/dsp2.img | |
| rkstudio_a/b | 0x15200 / 0x15600 | 音效参数 bin | |
| root_a/b | 0x15a00 / 0x19a00 | Image/root.img | 资源文件 |
| userdata | 0x1da00 grow | 不打包 | 首启自动格式化 |

原则: 全新/半砖 → `uf` 整包;日常开发 → 只烧改的那份(a/b 烧同一份最稳);开机 slot 由 OTA 机制决定。`wl` 烧带 RESC 头的 `Image/*.img`,不用裸 bin。

烧完自动重启(或按 RESET),串口重新接上看日志。

## 5. 第五步:串口体验 msh(验证开发流程闭环)

```text
msh > help             # 全部命令
msh > version          # RT-Thread 版本
msh > ps / list_thread # 线程
msh > free             # 内存
msh > list_device      # 已注册设备(uart/i2c/pin/mtd...)
msh > mount            # 文件系统挂载(root→/, userdata→/data)
msh > ls /             # 资源文件
msh > get_temp         # TSADC 温度
msh > opp_dump         # 调频档位
msh > cpu_stress       # CPU 压测
msh > mem_bw_test      # 内存带宽
msh > dsp_cmd          # DSP 命令
msh > vendor_test r 1  # 读 vendor storage(SN/MAC)
msh > io 0x40460000    # 直接读写寄存器
msh > reboot loader    # 重启进烧写模式
```

EVB 板出厂固件 = **partybox 演示**(音箱场景): 板上按键切歌/调音量、喇叭出声、PDM 麦克风阵列、数码管显示状态,可以整体体验一次。

## 6. 第六步:改代码 → 快速迭代(核心开发循环)

```bash
# 1. 改应用代码(入口在 BSP 的 applications/main.c)
vim <SDK>/bsp/rockchip/rk2118/applications/main.c
#    例: rt_kprintf("my first build\n"); 或用 INIT_APP_EXPORT / MSH_CMD_EXPORT 加命令

# 2. 重编(增量,scons 按 MD5 判断;若改动"没生效"先 scons -c 清理)
cd <SDK>/bsp/rockchip/rk2118
scons -j32                      # 只得到 rtt0.bin(不动打包)

# 3. 单分区烧写 cpu0(不用整包升级,快)
#    Windows: SocToolKit → loader + rtt0.bin,地址 = board/evb1_v20/setting.ini
#             里 cpu0_os_a 的 PartOffset × 512
#    Linux:   ../tools/upgrade/upgrade_tool wl 0x<PartOffset> ./rtt0.bin

# 4. 复位看串口新日志
```

改动较大(defconfig/分区/DSP)时才走 `./build.sh board/evb1_v20/package-file` 整包流程。

## 7. 踩坑提示(Quick Start + EVB 指南原文提炼)

1. menuconfig 退出时如果没弹保存提示且 `.config` 与 rtconfig.h 不一致 → `scons --useconfig=.config` 强制重新生成 rtconfig.h
2. 调过 menuconfig 后把配置存回板级目录: `cp .config board/evb1_v20/defconfig`,不要提交 `.config`
3. rtt0.img 超过分区大小 → 打包报 `Packing Error:file length is larger than part size` → 增大 setting.ini 里 cpu0_os_a 的 PartSize,并顺移后续分区偏移
4. 分区规则: userdata 必须最后;nor 64KB / nand 256KB 对齐;nand 分区留坏块余量(小分区 +1 block,大分区 +1MB)
5. 串口乱码/无输出 → 先检查波特率是不是 1500000、流控是否关了
6. 烧写无反应 → 确认真进了 MaskRom(按住 MASKROM 再按 RESET),工具里出现 Maskrom 标识
7. 想体验自己的 DSP 程序 → 参考 `RK211X_HiFi4_Quick_Start_CN.pdf`,装 Xtensa 工具链后 `./mkdsp.sh evb_partybox_demo_dsp0 build`

## 8. 下一步进阶路线

| 方向 | 资料 |
|---|---|
| 音频应用开发 | `Rockchip-docs/develop/rk211x/RK2118_DSP_Audio_Application_Developer_Guide_CN.pdf`、`RK2118_Audio_Subsystem_CN.pdf` |
| RKStudio 调音 | Quick Start 第 5 章(FTP: ftp://www.rockchip.com.cn, 用户 rkwifi,目录 14-RK2118/RkStudioTool,内含 soundbar demo) |
| DSP 固件开发 | `RK211X_HiFi4_Quick_Start_CN.pdf` + `RK211X_Xtensa_Development_Tools_Installation_Guide_CN.pdf` |
| OTA 升级 | `RT-Thread_OTA_Upgrade_CN.pdf`(EVB V20 是 A/B 分区板) |
| 外设驱动 | `Rockchip-docs/develop/common/` 每个外设一份 PDF |
| 通用开发指南 | `Rockchip_Developer_Guide_RK2118_CN.pdf` |
