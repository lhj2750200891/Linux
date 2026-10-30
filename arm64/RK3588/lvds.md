# LVDS 屏

　　LT9211D 桥接 LVDS 屏 (MIPI DSI→LVDS), 含 6.12 内核驱动移植实录 (API 差异/编译错误全解)。参考板 AIO-3588SG lvds101。

　　RK3588 没有原生 LVDS 输出, LVDS 屏必须经 Lontium LT9211D 桥片
(MIPI DSI RX -> LVDS TX) 转接。显示链路:

```
VOP (vp3) ==> dsi0 (DW MIPI DSI2 + mipi_dcphy0)
          ==> LT9211D (MIPI RX, I2C 0x2d 配置桥)
          ==> LVDS TX ==> LVDS 屏 (800x1280 lvds101 / 1920x1080 lvds215)
背光独立: PWM3_M1 + PCA9554 IO0_0, 不经桥
```

　　屏配置的设备树部分在 [mipi-dsi.md](mipi-dsi.md) 方式二/三也有收录;
本文件聚焦 **LVDS 专属内容: LT9211D 驱动在 6.12 内核的移植**,
特别是 6.12 与 5.10 旧内核的 API 差异和编译失败原因。

　　源文件:
- 设备树: kernel-6.12/arch/arm64/boot/dts/rockchip/rk3588-firefly-aio-3588sg-mipi-dsi0-lvds101.dtsi
- 桥驱动: kernel-6.12/drivers/video/firefly/lt9211c/ (lt9211c.c 730 行
  + mipirx-lvdstx.c + ModPattern.c, 5.10 的 drivers/video/lt9211c/ 原样拷贝,
  **已修复构建链 + 6.12 API 适配, 编译验证通过**, 见第 4 节)
- 挂接点: kernel-6.12/drivers/gpu/drm/rockchip/dw-mipi-dsi2-rockchip.c

　　参考 (旧内核完整工程):
rk3588_5.10.198_sdk 的 kernel/drivers/video/lt9211c/ 与
kernel/drivers/gpu/drm/rockchip/dw-mipi-dsi2-rockchip.c

## 1. 硬件连接

```
LVDS 屏 (800x1280 lvds101, 经 LT9211D 桥):
  DSI 差分对  ====> mipi_dcphy0 (dsi0, 4 lane) ====> LT9211D MIPI RX
  LT9211D I2C ====> I2C0_M2: SCL GPIO0_D1 / SDA GPIO0_D2 (地址 0x2d, 100kHz)
                  (i2c0m2_xfer: <0 RK_PD1 3> / <0 RK_PD2 3>)
  LT9211D 电源 ====> GPIO3_C1 (power-gpio, 高有效) — 同时要 disabled can2
  LT9211D 复位 ====> GPIO3_B7 (reset-gpio, 高有效)
  桥 LVDS TX  ====> LVDS 屏排座
  背光使能    ====> PCA9554 IO0_0 (高有效)
  背光 PWM    ====> PWM3_M1 (pwms = <&pwm3 0 50000 1>) = GPIO3_B2, 20kHz
```

　　I2C0_M2 这条总线上还挂着别的设备 (调试时 i2cdetect -y 0 会全部看到):

| 地址 | 设备 | 定义处 |
|---|---|---|
| 0x42 | rk8602 (CPU big0 核供电) | rk3588-firefly-rk806-single.dtsi |
| 0x43 | rk8603 (CPU big1 核供电) | 同上 |
| 0x20 | PCA9554 (背光使能) | rk3588-firefly-aio-3588sg-bp.dtsi |
| 0x2d | LT9211D 桥 | rk3588-firefly-aio-3588sg-mipi-dsi0-lvds101.dtsi |

　　注意 RK806 PMIC 本体走 SPI2 (spi2m2_cs0), 不占 i2c0; 但 CPU 核供电
rk8602/8603 挂在 i2c0 上 --- 动 i2c0 的 pinctrl/上拉配置时先想到这层
(核供电 I2C 失联会影响 CPU 调压)。

## 2. 设备树配置

### 2.1 include 链 (换屏时知道改哪)

　　主 dts (rk3588-firefly-aio-3588sg.dts) 只定义宏, 具体屏 dtsi 由
"-bp.dtsi" 按宏选出 (bp = 背光扩展板, 上面有 PCA9554):

```
rk3588-firefly-aio-3588sg.dts:
    #define FF_BP                   // 背光扩展板
    #define FF_DSI0_LVDS101_VP3     // 屏二选一: lvds101 / lvds215
    //#define FF_DSI0_LVDS215_VP3
    #include "rk3588-firefly-aio-3588sg.dtsi"   // 主 dtsi (内含 -bp.dtsi)

rk3588-firefly-aio-3588sg-bp.dtsi:
    #if defined(FF_DSI0_LVDS101_VP3) && !defined(FF_DSI0_LVDS215_VP3) && !defined(FF_DSI1_VP3)
    #include "rk3588-firefly-aio-3588sg-mipi-dsi0-lvds101.dtsi"
    #endif
    ... (pca9554 挂 i2c0)
```

　　注意主 dts 里还有一段本模块相关的死代码 (条件永假, 走不到):

```
#if defined(FF_DSI1_VP3) && !defined(FF_DSI0_LVDS101_VP3) && !defined(FF_DSI0_LVDS215_VP3)
#include "rk3588-firefly-aio-3588sg-mipi-dsi0-lvds101.dtsi"
#endif
```

　　lvds101 与 lvds215 互斥; 若定义了 FF_DSI1_VP3 (MIPI 直连屏) 则 LVDS
不生效 (GPIO 复用冲突)。

### 2.2 背光 + 面板 + 桥 (完整, 摘自 lvds101 dtsi)

```dts
/ {
	backlight_lvds: backlight_lvds {
		status = "okay";
		compatible = "pwm-backlight";
		enable-gpios = <&pca9554 PCA_IO0_0 GPIO_ACTIVE_HIGH>;
		pwms = <&pwm3 0 50000 1>;
		brightness-levels = <0 1 2 ... 255>;   /* 0~255 线性 256 级 */
		default-brightness-level = <200>;
	};
};

&dsi0 {
	status = "okay";
	//rockchip,lane-rate = <1000>;
	dsi0_panel: panel@0 {
		status = "okay";
		compatible = "simple-panel-dsi";
		reg = <0>;
		backlight = <&backlight_lvds>;

		/* 桥后的屏不需 init 命令; EoT 包默认使能 */
		dsi,flags = <(MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST | MIPI_DSI_MODE_LPM)>;
		dsi,format = <MIPI_DSI_FMT_RGB888>;
		dsi,lanes  = <4>;

		display-timings {
			native-mode = <&timing0>;
			timing0: timing0 {
				clock-frequency = <72000000>;
				hactive = <800>;
				vactive = <1280>;
				hfront-porch = <50>;
				hsync-len = <10>;
				hback-porch = <50>;
				vfront-porch = <10>;
				vsync-len = <18>;
				vback-porch = <10>;
				hsync-active = <0>;
				vsync-active = <0>;
				de-active = <0>;
				pixelclk-active = <0>;
			};
		};

		ports { /* panel_in_dsi0 <-> dsi0_out_panel, 常规 graph */ };
	};

	ports { /* port@1: dsi0_out_panel */ };
};

&dsi0_in_vp2 {
	status = "disabled";      /* vp2 让给 HDMI */
};

&dsi0_in_vp3 {
	status = "okay";          /* DSI0 数据源走 vp3 */
};

&route_dsi0 {
	status = "okay";
	connect = <&vp3_out_dsi0>;
};

&mipi_dcphy0 {
	status = "okay";          /* dsi0 必须配 dcphy0, 漏了必黑屏 */
};

&pwm3 {
	pinctrl-0 = <&pwm3m1_pins>;   /* PWM3_M1 = GPIO3_B2 */
	status = "okay";
};

/* LT9211D 桥, 挂 I2C0_M2 */
&i2c0 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c0m2_xfer>;
	clock-frequency = <100000>;

	LT9211D: LT9211D@2d {
		status = "okay";
		compatible = "loutium, LT9211C";    /* 原样! 空格也不能改, 见下 */
		reg = <0x2d>;

		power-gpio = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;
		reset-gpio = <&gpio3 RK_PB7 GPIO_ACTIVE_HIGH>;

		mod = "mipi_in_lvds_out";           /* pattern_out / mipi_in_lvds_out */
		lvdstx_port_swap = "disabled";      /* enabled / disabled */
		lvdstx_port_sel = "porta";          /* porta / portb / dou_port */

		/* 桥端时序, 必须与 panel display-timings 一致 */
		clock-frequency = <72000000>;
		hactive = <800>;
		vactive = <1280>;
		hfront-porch = <50>;
		hsync-len = <10>;
		hback-porch = <50>;
		vfront-porch = <10>;
		vsync-len = <18>;
		vback-porch = <10>;
		frameRate = <60>;
	};
};

&can2 {
	status = "disabled";      /* GPIO3_C1 被 LT9211D 电源占用 */
};
```

　　要点:
- `compatible = "loutium, LT9211C"` — 厂商驱动就这么写的 (loutium 拼错 +
  逗号后带空格), dts 与驱动 of_match_table 两边一致才能匹配, **任何一边
  都不要"顺手修正"**, 改一边就 probe 不上
- 桥不是 DRM bridge 挂在 DSI graph 里的, 而是**独立 i2c 驱动**, 靠
  dsi0 面板使能时手工调用其 resume/suspend (见第 4 节)
- lvds215 (1080P): clock 150MHz, 1920x1080, porches 按屏调, 其余同构

## 3. LT9211C/D 驱动原理 (5.10 原始设计)

　　厂商驱动不是标准 DRM bridge, 是"哑"配置驱动, 全部逻辑:

```
probe (i2c 匹配 "loutium, LT9211C"):
    解析 dts 的 power/reset-gpio、mod、时序
    配置 GPIO, 不初始化芯片

DSI 上电路径 (dw-mipi-dsi2 encoder enable):
    drm_panel_enable(panel) 之后 ==> LT9211C_resume()
        lt9211c_config():
            拉电源/复位时序 (power 高 100ms -> reset 低 100ms -> 高)
            读 ChipID 验证 I2C
            Mod_SystemRx/Tx_PowerOnInit      (MIPI RX / LVDS TX 初始化)
            循环调 Mod_MipiRx_Handler + Mod_LvdsTx_Handler 直到
            Rx/Tx 都 PLAY_BACK (最多 30 次, 超时打印 "No video source access!")

DSI 断电路径 (encoder disable):
    drm_panel_unprepare() 之后 ==> LT9211C_suspend()
        拉低电源脚
```

　　即: **MIPI 主机先发视频流, 桥再对流做 MIPI->LVDS 转换**。所以 DSI 侧
`card?-DSI-1 connected` 且有 modes 不代表屏会亮 — 桥没被 config, LVDS
侧照样黑屏 (这正是本次调试的现象: 只有背光亮)。

## 4. 6.12 内核移植

### 4.1 现状: 构建链断点已全部修复 (编译/开机验证通过)

　　6.12 SDK 里 `drivers/video/firefly/lt9211c/` 目录原样带来了完整驱动
源码 (与 5.10 逐文件 diff 一致), 但**构建链是断的** (下面左列原始
状态), 内核里根本没有这个模块, 导致"背光亮屏不亮"。现已全部修复
并编进内核 (built-in.a + .config CONFIG_LT9211C_DRIVER=y):

| 环节 | 修复前 (6.12 SDK 原始状态) | 修复后 (当前树) |
|---|---|---|
| 目录位置 | drivers/video/lt9211c/ | drivers/video/firefly/lt9211c/ (含 .o/built-in.a 编译产物) |
| 进目录编译 | drivers/video/Makefile 已有 `obj-y += firefly/`, 但 firefly/Makefile 一行都没有 | firefly/Makefile: `obj-$(CONFIG_LT9211C_DRIVER) += lt9211c/` |
| Kconfig | firefly/Kconfig 存在却没人 source, 选项不存在 | drivers/video/Kconfig L54 已 source; firefly/Kconfig source lt9211c/Kconfig |
| lt9211c 自身 Kconfig | 带一段无关的 menuconfig GPIOLIB 且缺 endmenu | 已替换为干净的 4 行版本 |
| config fragment | — | firefly-linux.config L164 `CONFIG_LT9211C_DRIVER=y` |
| DSI 挂接钩子 | dw-mipi-dsi2-rockchip.c 没有桥钩子 | L41 include + L1104 resume + L550 suspend |
| U-Boot 配置时序 | `lt9211c_probe()` 过早执行完整配置 | probe 只解析设备；DSI video stream 启动后由 `dw_mipi_dsi2_connector_enable()` 调用 `lt9211c_resume()` |
| 内核初始化 | `subsys_initcall()` 与 `module_init()` 重复注册 | 只保留一个初始化入口，避免 `Driver 'LT9211C' is already registered` |

### 4.2 落地的修复清单（内核与 U-Boot 共同修改，留档可复现）

**(1) drivers/video/Kconfig** — 把 firefly 的 Kconfig 挂进菜单
(已加在 L54):

```
menu "Rockchip Misc Video driver"
source "drivers/video/rockchip/Kconfig"
source "drivers/video/firefly/Kconfig"     ← 加这行
endmenu
```

**(2) drivers/video/firefly/lt9211c/Kconfig** — 整个文件替换
(原始文件开头是一段与内核重复的 `menuconfig GPIOLIB` 定义, 缺
endmenu, 不替换会破坏配置菜单; 已替换):

```
config LT9211C_DRIVER
	tristate "Loutium LT9211C"
	default y
	help
	  Lontium LT9211C/D MIPI-DSI to LVDS bridge driver (Firefly).
```

**(3) drivers/video/firefly/Makefile** — 补进目录条目 (本树只有
lt9211c 一个子目录, 5.10 firefly 的 rga/mpp 等都在别处; 已补):

```make
obj-$(CONFIG_LT9211C_DRIVER) += lt9211c/
```

**(4) arch/arm64/configs/firefly-linux.config** — 加配置 (L162-164):

```
# lvds: LT9211C
CONFIG_LT9211C_DRIVER=y
```

　　(SDK 走 config fragment 机制: firefly.config 里
`RK_KERNEL_CFG_FRAGMENTS="firefly-linux.config"`, 加在 .config 里
下次重配会被冲掉, 必须写 fragment)

**(5) drivers/gpu/drm/rockchip/dw-mipi-dsi2-rockchip.c** — 恢复 5.10 的
上下电钩子, 三处 (已加: L41 / L1104 / L550):

　　文件头部 include 区:

```c
#include "../../../video/firefly/lt9211c/include.h"
```

　　`dw_mipi_dsi2_encoder_atomic_enable()` 结尾 (drm_panel_enable 之后):

```c
	if (!(old_crtc_state && old_crtc_state->self_refresh_active)) {
		if (dsi2->panel) {
			drm_panel_enable(dsi2->panel);
			LT9211C_resume();
		}
	}
```

　　`dw_mipi_dsi2_encoder_atomic_disable()` 中 (drm_panel_unprepare 之后):

```c
	if (!new_crtc_state || !new_crtc_state->self_refresh_active) {
		if (dsi2->panel) {
			drm_panel_unprepare(dsi2->panel);
			LT9211C_suspend();
		}
	}
```

**大括号坑**: 这两个 if 千万注意, 6.12 原代码是不带大括号的

```c
		if (dsi2->panel)
			drm_panel_enable(dsi2->panel);
			LT9211C_resume();   /* ← 编译能过, 但这句在 if 外,
			                        panel 为空也执行 */
```

　　缩进有迷惑性, 悬空语句必须用大括号包住才对。(LT9211C_resume 内部
有 lt9211c_client==NULL 保护所以不会崩, 但条件语义错了。)

**(6) U-Boot 的初始化时序修复** — 这是 `route_dsi0=okay` 时能否显示的关键。
U-Boot 的 LT9211C 节点是 I2C 子设备，但 LT9211C 私有状态机必须在收到
DSI 视频后才能锁定 MIPI RX/PCR。不能在 U-Boot 的 I2C `probe()` 中直接执行：

```c
/* 错误：此时 DSI 尚未输出视频 */
lt9211c_config(dev, priv);
```

正确做法是让 `lt9211c_probe()` 只解析 GPIO、时序和地址，并在
`dw_mipi_dsi2_connector_enable()` 中先启动 DSI，再调用 `lt9211c_resume()`：

```c
/* DSI video stream 已经启动 */
dw_mipi_dsi2_enable(dsi2);
lt9211c_resume();
```

如果在 probe 阶段提前配置，典型结果是没有 Chip ID/PLL 锁定日志，或者打印
`No video source access!`。U-Boot 仍可能打开 route 并留下“软件上已启用”的
状态，Linux 接管后又跳过完整 modeset，于是出现背光亮、LVDS 屏黑屏。

**(7) 内核驱动重复注册修复** — 内核驱动不能同时使用两个初始化入口：

```c
subsys_initcall(LT9211C_init);
module_init(LT9211C_init);
```

两者会导致同一 I2C driver 注册两次，日志表现为：

```text
Lontium LT9211C driver installing....
Lontium LT9211C driver installing....
Error: Driver 'LT9211C' is already registered
```

当前版本删除 `subsys_initcall(LT9211C_init)`，只保留 `module_init()`。

### 4.3 驱动源码本身的 6.12 适配 (6 个编译错误, 均已修复)

　　驱动源码虽是从 5.10 原样拷来的, 但 6.12 的内核 API 和编译策略变了,
直译编译会**连环报 6 个错误**, 每个 error 都是一个内核版本差异
(以下全部已改, 留档作为老驱动移植到 6.12 的通用参考):

**(1) of_get_named_gpio_flags() 已删除** — lt9211c.c 的 parse_dt:

```c
/* 5.10 原码 (6.12 的 include/linux/of_gpio.h 里已无此函数) */
lt9211c_pdata->reset_gpio = of_get_named_gpio_flags(np, "reset-gpio", 0, &flag_reset);

/* 6.12 改法: 只剩不带 flags 的版本; flag 变量本来就没用, 连声明一起删 */
lt9211c_pdata->reset_gpio = of_get_named_gpio(np, "reset-gpio", 0);
```

　　背景: 内核 6.x 起持续清退 legacy GPIO API, 带 flags 的解析函数从
include/linux/of_gpio.h 移除 (gpiolib-of.c 里只剩内部实现, 只导出
of_get_named_gpio)。

**(2) i2c_driver.probe 签名变化** — probe 去掉了第二个参数:

```c
/* 5.10: */  static int LT9211C_probe(struct i2c_client *client, const struct i2c_device_id *id)
/* 6.12: */  static int LT9211C_probe(struct i2c_client *client)
```

　　背景: 内核 6.3 起 probe_new 改名为 probe 且统一无 id 参数 (probe
与 device 驱动模型对齐, id_table 仍用于 i2c 匹配但不再传入回调)。

**(3) i2c_driver.remove 签名变化** — 返回值从 int 改 void:

```c
/* 5.10: */  static int LT9211C_remove(struct i2c_client *client) { ... return 0; }
/* 6.12: */  static void LT9211C_remove(struct i2c_client *client) { ... }
```

　　背景: 内核 6.9 起 remove 回调不再允许失败, 返回值被移除。

**(4) -Werror=uninitialized** — mipirx-lvdstx.c 的 Drv_LvdsTxPll_Cali:

```c
u8 ucloopx;      /* 5.10 编译器没告警, GCC 12+/6.12 -Werror 下必炸 */
    do { ...; ucloopx++; } while ((ucloopx < 3) && ...);
/* 改: */ u8 ucloopx = 0;
```

**(5) -Werror=implicit-fallthrough** — lt9211c.c 的
Drv_System_VidChk_SrcSel, switch 里 case LVDSDEBUG 缺 break,
gcc 认为是无意穿透。补 `break;` (调试模式分支, 正常
mipi_in_lvds_out 模式不走, 无行为影响):

```c
        case LVDSDEBUG:
            LT9211C_write(0x3f,LVDSDEBUG);
        break;               /* ← 补 */
        case MIPIDEBUG:
```

**(6) -Wmissing-prototypes / -Wmissing-declarations + CONFIG_WERROR=y**
— 厂商代码大量非 static 全局函数没在头文件声明, 5.10 内核默认不开
这两个警告所以能过, 6.12 (Makefile.extrawarn) 默认开且 WERROR 把警告
全变错误。这类是**代码风格问题而非真 bug**, 局部豁免:

```make
# drivers/video/firefly/lt9211c/Makefile
ccflags-y += -Wno-missing-prototypes -Wno-missing-declarations
obj-$(CONFIG_LT9211C_DRIVER) += ModPattern.o mipirx-lvdstx.o lt9211c.o
```

### 4.4 差异总结表 (6.12 vs 5.10)

| 差异点 | 5.10 | 6.12 | 影响 |
|---|---|---|---|
| GPIO 解析 | of_get_named_gpio_flags() | 已删, 用 of_get_named_gpio() | lt9211c.c parse_dt |
| i2c probe | (client, id) 两参数 | (client) 单参数 | 签名不匹配编译错 |
| i2c remove | 返回 int | 返回 void | 签名不匹配编译错 |
| 警告策略 | -Wall, 原型缺失不报 | -Wmissing-prototypes 等默认开 + WERROR | Makefile 豁免 |
| 未初始化/fallthrough | 只是警告 | -Werror= 升级为错误 | ucloopx 初始化、补 break |
| 驱动目录 | drivers/video/lt9211c/ | drivers/video/firefly/lt9211c/ | include 路径 ../../../video/firefly/lt9211c/include.h |

　　另外 6.12 里还有一个**主线** LT9211 驱动
(drivers/gpu/drm/bridge/lontium-lt9211.c, CONFIG_DRM_LONTIUM_LT9211=y
默认开), 但它是标准 DRM bridge, compatible 是 `lontium,lt9211`, 走
DSI graph 挂接, 且 ChipID 校验按 LT9211 (0x18 0x01) — 与本板的
LT9211**D** + Firefly 私有 dts 写法完全不兼容, 两者互不相干, 不要
混淆。若自研板想走主线化路线, 需重写 dts 桥节点为 graph 端点结构并
验证 D 版 ChipID, 工作量大于直接移植厂商驱动。

## 5. 验证测试

```
# 1. 确认模块编进内核 (编译期)
grep CONFIG_LT9211C_DRIVER .config                 # =y
# 产物: drivers/video/firefly/lt9211c/built-in.a

# 2. 开机后桥驱动日志 (按顺序应全部出现)
dmesg | grep -i -E "lontium|lt9211"
#   Lontium LT9211C driver installing....
#   Lontium I2C address is 0x2d
# 点亮显示屏后:
#   LT9211C i2c test success chipid: 0x...     ← I2C 通了
#   Tx Pll Lock                                 ← LVDS TX 锁相成功

# 3. DRM 侧
cat /sys/class/drm/card0-DSI-1/status     # connected
cat /sys/class/drm/card0-DSI-1/modes      # 800x1280
cat /sys/class/drm/card0-DSI-1/enabled    # 1

# 4. 背光
cat /sys/class/backlight/*/brightness
echo 100 > /sys/class/backlight/*/brightness

# 5. I2C 在位检查 (桥没起来时)
i2cdetect -y 0        # 0x2d 处应出现设备 (UU 或 2d)
```

### 5.1 故障排查实录: "只有背光亮, 屏不亮"

　　本次 (2026-10-29) 实际踩到的坑, 现象与判据 (**修复前**的现场记录,
根因就是第 4 节的构建链断裂, 修复后此现象消失):

| 现象 | 结论 |
|---|---|
| card0-DSI-1 connected, modes=800x1280 | dts 面板节点生效, VOP->DSI 流水线在跑, MIPI 信号已在发 |
| 背光亮 | PWM3 + PCA9554 背光通路正常 (独立于显示链路) |
| 屏不亮 | **LT9211D 从未被初始化** — compatible "loutium, LT9211C" 在 6.12 里无驱动匹配, power/reset GPIO 没人拉, 桥不工作, LVDS 侧无输出 |

　　教训: DSI connector 状态正常 != 屏会亮。桥接 LVDS 方案必须同时验证
"DSI side 正常" 和 "桥 dmesg 日志正常" 两条链。

　　常见问题:
1. `i2c test failed time N` — I2C 通路问题: 量 i2c0 波形, 确认
   pinctrl i2c0m2_xfer、地址 0x2d、power GPIO3_C1 先拉高
2. `No video source access!` — 桥在收流但 MIPI RX 没锁定: 查
   dsi,lanes 与桥端一致 (4 lane)、时序两端一致、dsi0 是否真开了
   (cat .../card0-DSI-1/enabled)
3. `Tx Pll Unlocked` — LVDS TX 锁不住: 查 frameRate/时钟与屏规格
4. 黑屏但日志全 OK — 转到屏侧: LVDS 线序 (JEIDA/VESA 映射,
   lvdstx_port_swap/lvdstx_port_sel)、屏供电
5. 桥日志出现但背光不亮 — PWM3_M1 引脚复用组选错 (pwm3m1 vs
   pwm3m3), 或 PCA9554 (bp 扩展板) 没 probe

## 6. 本次移植的最终落地清单

本节按“内核、U-Boot、设备树、启动时序”重新汇总当前 6.12 SDK 的最终状态，便于把改动复制到另一块 RK3588 板卡。以下路径均相对于 SDK 根目录；如果使用不同产品 DTS，只需要替换对应的 DTS 文件，驱动和配置接入方式不变。

### 6.1 内核驱动与配置

内核侧驱动是一个 Firefly 私有 I2C 驱动，不是主线 DRM bridge。最终文件如下：

```text
kernel-6.12/drivers/video/firefly/Kconfig
kernel-6.12/drivers/video/firefly/Makefile
kernel-6.12/drivers/video/firefly/lt9211c/
├── Kconfig
├── Makefile
├── include.h
├── lt9211c.c
├── lt9211c.h
├── ModPattern.c
├── ModPattern.h
├── mipirx-lvdstx.c
├── mipirx-lvdstx.h
└── type.h
```

接入关系是：

```text
drivers/video/Kconfig
        └── source "drivers/video/firefly/Kconfig"
                └── source "drivers/video/firefly/lt9211c/Kconfig"

drivers/video/Makefile
        └── obj-y += firefly/

drivers/video/firefly/Makefile
        └── obj-$(CONFIG_LT9211C_DRIVER) += lt9211c/

drivers/video/firefly/lt9211c/Makefile
        └── obj-$(CONFIG_LT9211C_DRIVER) += ModPattern.o mipirx-lvdstx.o lt9211c.o
```

内核配置至少需要：

```text
CONFIG_I2C=y
CONFIG_GPIO_SYSFS=y                 # 若需要用户态 GPIO 调试，可选
CONFIG_ROCKCHIP_DW_MIPI_DSI2=y
CONFIG_LT9211C_DRIVER=y
CONFIG_GPIO_PCA953X=y               # 背光使能通过 PCA9554/PCA9555 时需要
```

Firefly 产品配置片段位于 `kernel-6.12/arch/arm64/configs/firefly-linux.config`。驱动使用 `default y`，但仍建议在产品 fragment 中显式写 `CONFIG_LT9211C_DRIVER=y`，这样换基线、执行 `olddefconfig` 或重新合并配置时不会意外关闭。

驱动的职责边界：

1. `probe()` 只解析 I2C 地址、GPIO 和时序，申请 GPIO，并保存 `i2c_client`；不会在 probe 阶段直接配置 LT9211C。
2. `LT9211C_resume()` 执行复位、电源打开、Chip ID 读取、MIPI RX 初始化、PCR/PLL 校准和 LVDS TX 配置。
3. `LT9211C_suspend()` 拉低 `power-gpio`，让桥芯片退出工作状态。
4. `include.h` 对外导出 `LT9211C_resume()`/`LT9211C_suspend()`，供 DSI encoder 调用。

### 6.2 U-Boot 驱动与配置

U-Boot 侧也必须配置 LT9211C。原因是 U-Boot 先于 Linux 打开显示 route 并显示 logo；如果 U-Boot 没有初始化桥，Linux 可能接管一个“软件状态已打开、硬件实际未 modeset”的显示链路，随后 DRM atomic enable 不一定再次执行，最终表现为背光亮但 LVDS 屏黑屏。

最终 U-Boot 文件如下：

```text
u-boot/drivers/video/Kconfig
u-boot/drivers/video/Makefile
u-boot/drivers/video/firefly/Kconfig
u-boot/drivers/video/firefly/Makefile
u-boot/drivers/video/firefly/lt9211c/
├── Kconfig
├── Makefile
├── lt9211c.c
├── lt9211c.h
├── mipirx-lvdstx.c
├── mipirx-lvdstx.h
└── type.h
```

关键配置和编译关系：

```text
u-boot/drivers/video/Kconfig
        └── source "drivers/video/firefly/Kconfig"

u-boot/drivers/video/Makefile
        └── obj-y += firefly/

u-boot/drivers/video/firefly/Makefile
        └── obj-$(CONFIG_LT9211C_DRIVER) += lt9211c/
```

`u-boot/drivers/video/firefly/lt9211c/Kconfig` 中的配置符号必须和两个 Makefile 完全一致：

```text
config LT9211C_DRIVER
        bool "Lontium LT9211C"
        depends on VIDEO
        depends on DM_I2C
        depends on DM_GPIO
        default y
```

Firefly U-Boot 配置片段 `u-boot/configs/firefly-linux.config` 中加入：

```text
CONFIG_VIDEO=y
CONFIG_DM_I2C=y
CONFIG_DM_GPIO=y
CONFIG_DM_PCA953X=y
CONFIG_LT9211C_DRIVER=y
```

注意：曾经出现过外层 Makefile 使用 `CONFIG_FIREFLY_LT9211C`、Kconfig 定义 `CONFIG_LT9211C_DRIVER` 的符号不一致问题。这种情况下菜单里看得到选项，但 `lt9211c.o` 不会进入 `drivers/video/firefly/built-in.o`。检查时应同时确认：

```bash
grep CONFIG_LT9211C_DRIVER u-boot/.config
nm u-boot/drivers/video/firefly/lt9211c/built-in.o | grep lt9211c
```

U-Boot 侧使用 Driver Model I2C API，6.12 U-Boot API 适配点包括：

```text
dev_get_platdata()         -> dev_get_plat()
dev_get_parent_platdata()  -> dev_get_parent_plat()
dev->node                  -> dev_ofnode(dev)
priv_auto_alloc_size       -> priv_auto
platdata_auto_alloc_size   -> plat_auto
```

U-Boot 只负责在启动阶段完成一次桥的硬件初始化，Linux 驱动仍然负责后续 suspend/resume 和显示状态切换；两边共享的是同一组 I2C 地址、GPIO 和显示时序。

需要特别注意 U-Boot 的时序：U-Boot LT9211C `probe()` 不能直接运行完整
`lt9211c_config()`，因为此时 DSI 尚未输出视频。当前实现由
`dw_mipi_dsi2_connector_enable()` 在 `dw_mipi_dsi2_enable()` 之后调用
`lt9211c_resume()`，从而保证桥芯片在有 MIPI 输入后才执行 RX/PCR/PLL/LVDS
配置。

### 6.3 设备树：必须保持四组参数一致

设备树需要同时描述 DSI 面板、DSI 输入路由、LT9211C I2C 节点和背光。以 `rk3588-firefly-aio-3588sg-mipi-dsi0-lvds101.dtsi` 为例：

```dts
/ {
        backlight_lvds: backlight_lvds {
                status = "okay";
                compatible = "pwm-backlight";
                enable-gpios = <&pca9554 PCA_IO0_0 GPIO_ACTIVE_HIGH>;
                pwms = <&pwm3 0 50000 1>;
                brightness-levels = <0 1 2 /* ... */ 254 255>;
                default-brightness-level = <200>;
        };
};

&dsi0 {
        status = "okay";

        dsi0_panel: panel@0 {
                status = "okay";
                compatible = "simple-panel-dsi";
                reg = <0>;
                backlight = <&backlight_lvds>;
                dsi,flags = <(MIPI_DSI_MODE_VIDEO |
                             MIPI_DSI_MODE_VIDEO_BURST |
                             MIPI_DSI_MODE_LPM)>;
                dsi,format = <MIPI_DSI_FMT_RGB888>;
                dsi,lanes = <4>;

                display-timings {
                        native-mode = <&timing0>;
                        timing0: timing0 {
                                clock-frequency = <72000000>;
                                hactive = <800>;
                                vactive = <1280>;
                                hfront-porch = <50>;
                                hsync-len = <10>;
                                hback-porch = <50>;
                                vfront-porch = <10>;
                                vsync-len = <18>;
                                vback-porch = <10>;
                                hsync-active = <0>;
                                vsync-active = <0>;
                                de-active = <0>;
                                pixelclk-active = <0>;
                        };
                };

                ports {
                        #address-cells = <1>;
                        #size-cells = <0>;
                        port@0 {
                                reg = <0>;
                                panel_in_dsi0: endpoint {
                                        remote-endpoint = <&dsi0_out_panel>;
                                };
                        };
                };
        };

        ports {
                #address-cells = <1>;
                #size-cells = <0>;
                port@1 {
                        reg = <1>;
                        dsi0_out_panel: endpoint {
                                remote-endpoint = <&panel_in_dsi0>;
                        };
                };
        };
};

&dsi0_in_vp2 {
        status = "disabled";
};

&dsi0_in_vp3 {
        status = "okay";
};

&route_dsi0 {
        status = "okay";
        connect = <&vp3_out_dsi0>;
};

&mipi_dcphy0 {
        status = "okay";
};

&pwm3 {
        pinctrl-0 = <&pwm3m1_pins>;
        status = "okay";
};

&i2c0 {
        status = "okay";
        pinctrl-names = "default";
        pinctrl-0 = <&i2c0m2_xfer>;
        clock-frequency = <100000>;

        LT9211D: LT9211D@2d {
                status = "okay";
                compatible = "loutium, LT9211C";
                reg = <0x2d>;

                power-gpio = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;
                reset-gpio = <&gpio3 RK_PB7 GPIO_ACTIVE_HIGH>;
                mod = "mipi_in_lvds_out";
                lvdstx_port_swap = "disabled";
                lvdstx_port_sel = "porta";

                clock-frequency = <72000000>;
                hactive = <800>;
                vactive = <1280>;
                hfront-porch = <50>;
                hsync-len = <10>;
                hback-porch = <50>;
                vfront-porch = <10>;
                vsync-len = <18>;
                vback-porch = <10>;
                frameRate = <60>;
        };
};

&can2 {
        status = "disabled";
};
```

设备树检查重点：

| 项目 | 要求 | 作用 |
|---|---|---|
| `compatible` | 必须是 `"loutium, LT9211C"` | 与内核/U-Boot 两侧 `of_match_table` 精确匹配；拼写和空格都不能单独修改 |
| `reg` | `0x2d` | LT9211D 的 7-bit I2C 地址 |
| `power-gpio` | GPIO3_C1，高有效 | 桥芯片主电源/使能 |
| `reset-gpio` | GPIO3_B7，高有效 | 桥芯片复位 |
| `dsi,lanes` | 4 | DSI0 到 LT9211D 的 lane 数 |
| `route_dsi0` | `vp3_out_dsi0` | VOP VP3 作为 DSI0 视频源 |
| `mipi_dcphy0` | `okay` | DSI0 D-PHY 必须启用 |
| 桥端时序 | 与 `display-timings` 相同 | LT9211D PCR/PLL 和 LVDS TX 计算使用 |
| `can2` | `disabled` | GPIO3_C1 与 CAN2 复用冲突时必须关闭 |

`lvds215` 只替换分辨率、像素时钟和 porch；`compatible`、I2C 地址、GPIO、`mod` 和 DSI lane 配置仍应按硬件保持一致。

## 7. 为什么要修改 `dw-mipi-dsi2-rockchip.c`

需要理解三个不同层次：

1. `route_dsi0` 是 Rockchip 显示路由的硬件/软件连接关系。
2. `drm_panel_prepare/enable` 是 DRM 面板生命周期回调，只能保证 panel 对象进入相应状态。
3. LT9211D 是一个独立 I2C 配置芯片；它不是当前实现中的标准 DRM bridge，因此 `drm_panel_enable()` 不会自动向 LT9211D 写寄存器。

所以，仅仅把 `route_dsi0` 设为 `okay`，并不等于 LT9211D 已完成 MIPI RX、PCR、LVDS PLL 和 LVDS TX 配置。尤其在 U-Boot 已经打开 route、Linux 继承 framebuffer/显示状态的情况下，Linux 可能跳过一次完整的 modeset，导致桥没有机会执行初始化，现象就是：

```text
DSI connector: connected
DSI modes:     正常
背光:          正常
LVDS 屏:       黑屏
```

### 7.1 头文件 include 的原因

```diff
 #include "rockchip_drm_drv.h"
 #include "rockchip_drm_vop.h"
 
+#include "../../../video/firefly/lt9211c/include.h"
```

`include.h` 是 Firefly LT9211C 驱动的公共入口，包含 `lt9211c.h`、时序结构体和 `LT9211C_resume()`/`LT9211C_suspend()` 的声明。DSI2 encoder 位于 `drivers/gpu/drm/rockchip/`，相对路径回到 `drivers/video/firefly/lt9211c/` 正好是三级 `../../../`。

这里采用显式函数调用，是因为当前 LT9211C 驱动不是挂在 DRM bridge graph 上的标准桥；如果改成主线 DRM bridge，应当重新设计设备树 graph、bridge attach 和 atomic callbacks，不能只替换 include 路径。

### 7.2 disable 路径为什么放在 `drm_panel_unprepare()` 后面

```diff
 if (!new_crtc_state || !new_crtc_state->self_refresh_active) {
-       if (dsi2->panel)
+       if (dsi2->panel) {
                drm_panel_unprepare(dsi2->panel);
+               LT9211C_suspend();
+       }
 }
```

执行顺序是：

```text
停止 DSI 输出
  -> panel unprepare
  -> LT9211C_suspend() 拉低 power-gpio
```

这样可以先停止上游 MIPI 视频流，再关掉桥芯片电源，避免 LT9211D 在仍有输入时被突然断电。`self_refresh_active` 分支必须保留：PSR/自刷新切换不是完整的物理断电，不应每次都复位桥。

### 7.3 enable 路径为什么放在 `drm_panel_enable()` 后面

```diff
 if (!(old_crtc_state && old_crtc_state->self_refresh_active)) {
-       if (dsi2->panel)
+       if (dsi2->panel) {
                drm_panel_enable(dsi2->panel);
+               LT9211C_resume();
+       }
 }
```

执行顺序是：

```text
panel enable
  -> LT9211C_resume()
       -> power/reset 时序
       -> I2C Chip ID 检查
       -> MIPI RX / PCR / PLL 配置
       -> LVDS TX 配置
  -> 上游持续输出 MIPI 视频
```

`LT9211C_resume()` 内部会执行 `lt9211c_config()`。配置函数先打开电源并产生复位脉冲，然后读取 Chip ID，最后循环执行 MIPI RX 和 LVDS TX 状态机，直到 RX/TX 都进入 `PLAY_BACK`，或者达到超时次数。

### 7.4 大括号不是格式问题，而是功能正确性

原始代码没有大括号时，下面的写法会让 `LT9211C_resume()` 无条件执行：

```c
if (dsi2->panel)
        drm_panel_enable(dsi2->panel);
        LT9211C_resume();       /* 实际已脱离 if */
```

正确写法必须把两个动作放入同一个 `if` 代码块：

```c
if (dsi2->panel) {
        drm_panel_enable(dsi2->panel);
        LT9211C_resume();
}
```

这样既保证 panel 存在时桥与 panel 同步，也避免某些没有 panel 的 DSI 使用场景误触发 LT9211C 全局配置函数。

### 7.5 为什么这个修改能解决 route/logo 黑屏

完整启动时序如下：

```text
U-Boot:
  读取同一份设备树
  -> LT9211C U-Boot driver probe（只解析设备树和 GPIO）
  -> DSI connector enable，启动 MIPI video stream
  -> lt9211c_resume() 配置 LT9211D
  -> route_dsi0 输出 logo

Linux DRM:
  dsi2 encoder atomic_enable
  -> panel prepare/enable
  -> LT9211C_resume() 再确认桥处于工作态
  -> DSI 视频稳定输出到 LVDS

Linux 关闭/重启显示:
  dsi2 encoder atomic_disable
  -> 停止 DSI
  -> panel unprepare
  -> LT9211C_suspend() 关闭桥电源
```

因此，该补丁不是“为了让 panel 回调多执行一次”，而是补上了当前私有 LT9211C 驱动与 Rockchip DSI2 DRM 生命周期之间缺失的控制连接。它解决的是桥芯片状态机没有被调用的问题，而不是修复 DSI lane、时序或背光本身。

## 8. 编译、启动和故障定位清单

### 8.1 编译前检查

```bash
# 内核
grep -E 'CONFIG_(ROCKCHIP_DW_MIPI_DSI2|LT9211C_DRIVER)=' \
        kernel-6.12/.config

# U-Boot
grep -E 'CONFIG_(VIDEO|DM_I2C|DM_GPIO|LT9211C_DRIVER)=' \
        u-boot/.config

# 设备树宏
grep -n 'FF_DSI0_LVDS\|FF_BP' \
        kernel-6.12/arch/arm64/boot/dts/rockchip/rk3588-firefly-aio-3588sg.dts
```

### 8.2 日志判据

```bash
dmesg | grep -i -E 'lontium|lt9211'
```

正常情况下至少应看到：

```text
Lontium LT9211C driver installing....
Lontium I2C address is 0x2d
LT9211C i2c test success chipid: ...
```

如果看到 `No video source access!`，说明桥已被调用，但 MIPI 输入或时序没有锁定；如果连 `Lontium I2C address` 都没有，优先检查 Kconfig、`compatible` 和 I2C 总线；如果 Chip ID 为全 0，检查电源 GPIO、复位 GPIO、I2C pinctrl 和 0x2d 地址。

### 8.3 三条链路必须分别验证

```text
I2C/电源链：i2cdetect -y 0 能看到 0x2d，GPIO 电平正确
DSI/DRM 链：card*-DSI-* 为 connected，modes 与屏一致
LVDS/背光链：Tx PLL lock，背光 PWM/PCA9554 正常，屏供电和线序正确
```

只有三条链路同时正常，才可以判定 LVDS 屏适配完成。`connected` 只说明 DRM graph 和 connector 状态正常，不能代替 LT9211D 的 Chip ID、PCR、PLL 和 LVDS TX 验证。

## 9. 从零复现：完整移植与编译步骤

下面步骤以当前 SDK 和 AIO-3588SG LVDS101 为例。换成其他 RK3588 板卡时，保留驱动接入方式，只替换产品 DTS、GPIO、I2C 控制器和屏时序。

### 9.1 准备源代码目录

```bash
export SDK=/path/to/rk3588_6.12.69_sdk
cd "$SDK"

find kernel-6.12/drivers/video/firefly/lt9211c -maxdepth 1 -type f
find u-boot/drivers/video/firefly/lt9211c -maxdepth 1 -type f
```

内核目录必须包含 `lt9211c.c`、`lt9211c.h`、`include.h`、`ModPattern.c/.h`、
`mipirx-lvdstx.c/.h` 和 `type.h`；U-Boot 目录包含 `lt9211c.c/.h`、
`mipirx-lvdstx.c/.h` 和 `type.h`。

### 9.2 接入内核 Kconfig/Makefile

```make
# kernel-6.12/drivers/video/Makefile
obj-y += firefly/

# kernel-6.12/drivers/video/firefly/Makefile
obj-$(CONFIG_LT9211C_DRIVER) += lt9211c/

# kernel-6.12/drivers/video/firefly/lt9211c/Makefile
ccflags-y += -Wno-missing-prototypes -Wno-missing-declarations
obj-$(CONFIG_LT9211C_DRIVER) += ModPattern.o mipirx-lvdstx.o lt9211c.o
```

在 `kernel-6.12/arch/arm64/configs/firefly-linux.config` 中加入：

```text
CONFIG_ROCKCHIP_DW_MIPI_DSI2=y
CONFIG_LT9211C_DRIVER=y
CONFIG_GPIO_PCA953X=y
```

必须修改 fragment，而不是只修改生成后的 `.config`。

### 9.3 接入内核 DSI 生命周期

在 `kernel-6.12/drivers/gpu/drm/rockchip/dw-mipi-dsi2-rockchip.c` 加入：

```c
#include "../../../video/firefly/lt9211c/include.h"
```

在 enable/disable 的 panel 分支中分别加入：

```c
if (dsi2->panel) {
        drm_panel_enable(dsi2->panel);
        LT9211C_resume();
}

if (dsi2->panel) {
        drm_panel_unprepare(dsi2->panel);
        LT9211C_suspend();
}
```

内核驱动只保留一个初始化入口：

```c
module_init(LT9211C_init);
```

删除重复的 `subsys_initcall(LT9211C_init)`，否则同一 I2C driver 会注册两次。

### 9.4 接入 U-Boot Kconfig/Makefile

```make
# u-boot/drivers/video/Makefile
obj-y += firefly/

# u-boot/drivers/video/firefly/Makefile
obj-$(CONFIG_LT9211C_DRIVER) += lt9211c/

# u-boot/drivers/video/firefly/lt9211c/Makefile
ccflags-y += -Wno-missing-prototypes -Wno-missing-declarations
obj-$(CONFIG_LT9211C_DRIVER) += mipirx-lvdstx.o lt9211c.o
```

在 `u-boot/configs/firefly-linux.config` 中加入：

```text
CONFIG_VIDEO=y
CONFIG_DM_I2C=y
CONFIG_DM_GPIO=y
CONFIG_DM_PCA953X=y
CONFIG_LT9211C_DRIVER=y
```

### 9.5 修正 U-Boot 初始化时序

这是 `route_dsi0=okay` 场景最关键的一步。U-Boot `lt9211c_probe()` 中不能直接调用：

```c
lt9211c_config(dev, priv);
```

probe 阶段只保存设备、GPIO 和时序；在 `u-boot/drivers/video/drm/dw_mipi_dsi2.c`
的 connector enable 中，先启动 DSI 视频，再调用：

```c
dw_mipi_dsi2_enable(dsi2);
lt9211c_resume();
```

LT9211C 的 MIPI RX/PCR 状态机只有在收到 DSI 视频后才能锁定。提前配置会导致
`No video source access!`，Linux 接管 route 后又可能跳过完整 modeset。

### 9.6 配置设备树

产品 DTS 中定义：

```dts
#define FF_BP
#define FF_DSI0_LVDS101_VP3
#include "rk3588-firefly-aio-3588sg.dtsi"
```

LVDS dtsi 必须同时打开 `dsi0`、`dsi0_in_vp3`、`route_dsi0`、`mipi_dcphy0`
和 `i2c0`。LT9211C 节点至少包含：

```dts
compatible = "loutium, LT9211C";
reg = <0x2d>;
power-gpio = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;
reset-gpio = <&gpio3 RK_PB7 GPIO_ACTIVE_HIGH>;
mod = "mipi_in_lvds_out";
```

`display-timings` 与 LT9211C 节点中的像素时钟、分辨率、porch 和 `frameRate`
必须一致。

### 9.7 配置并编译

```bash
cd "$SDK/u-boot"
make rk3588_defconfig
make firefly-linux.config
make olddefconfig
grep CONFIG_LT9211C_DRIVER .config
make CROSS_COMPILE=aarch64-linux-gnu- -j"$(nproc)" u-boot-nodtb.bin

cd "$SDK/kernel-6.12"
# 按 SDK 方式合并 firefly-linux.config 后执行：
make ARCH=arm64 olddefconfig
grep -E 'CONFIG_(ROCKCHIP_DW_MIPI_DSI2|LT9211C_DRIVER)=' .config
make ARCH=arm64 CROSS_COMPILE=aarch64-none-linux-gnu- -j"$(nproc)" Image dtbs modules
```

只验证内核驱动时可执行：

```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-none-linux-gnu- \
     M=drivers/video/firefly/lt9211c modules
```

### 9.8 产物与启动验证

```bash
strings "$SDK/u-boot/u-boot" | grep -E 'lt9211c|loutium, LT9211C'
nm "$SDK/u-boot/u-boot" | grep lt9211c_probe
dmesg | grep -i -E 'lontium|lt9211|video source|pll'
i2cdetect -y 0
cat /sys/class/drm/card0-DSI-1/status
cat /sys/class/drm/card0-DSI-1/modes
cat /sys/class/drm/card0-DSI-1/enabled
```

预期结果是：U-Boot DSI enable 后完成 LT9211C 配置；Linux 日志出现 Chip ID，
I2C 0x2d 显示 `UU`，DSI 状态为 `connected`，模式包含 `800x1280`，并且
`route_dsi0=okay` 时仍能显示 U-Boot logo 和 Linux 桌面。

### 9.9 失败现象定位

| 现象 | 优先检查 |
|---|---|
| 没有 `Lontium I2C address` | 内核配置、compatible、最终 DTB |
| U-Boot 有地址但无 Chip ID | U-Boot I2C、power/reset GPIO、实际加载 DTB |
| `No video source access!` | 是否仍在 probe 阶段配置；必须 DSI enable 后调用 resume |
| `Driver 'LT9211C' is already registered` | 删除内核重复 `subsys_initcall()` |
| route 关闭正常、route 打开黑屏 | U-Boot 镜像未更新或初始化时序错误 |
| DSI connected 但 LVDS 黑屏 | Chip ID、PCR/PLL、LVDS 映射、屏供电和背光 |

## 10. 最终摄像头适配与实机验证（2026-10-30）

本节记录当前 6.12 DTS 的最终摄像头资源映射和已经在 AIO-3588SG 实机上验证的配置。

### 10.1 最终可用映射

```text
CAMERA1:
    I2C1-M4 -> XC7160 @ 0x1b
      -> csi2_dcphy0 / MIPI_DPHY0_RX
      -> mipi0_csi2 -> rkcif_mipi_lvds

CAMERA2:
    I2C0-M2 -> XC7160 @ 0x1b
      -> csi2_dcphy1 / MIPI_DPHY1_RX
      -> mipi1_csi2 -> rkcif_mipi_lvds1
```

这是根据 5.10 SDK 和 6.12 实机 CSI 中断结果确定的最终映射，不能只根据 `mipi0`/`mipi1` 名称猜测物理接口。

### 10.2 只修改 DTS 宏切换配置

DSI1 VP3 屏幕 + CAMERA1：

```dts
#define FF_DSI1_VP3
#define FF_MIPI_CSI2_CAMERA1_XC7160

//#define FF_MIPI_CSI2_CAMERA2_XC7160
//#define FF_MIPI_CSI2_IMX415
```

CAMERA2 单摄：

```dts
#define FF_MIPI_CSI2_CAMERA2_XC7160

//#define FF_DSI1_VP3
//#define FF_MIPI_CSI2_CAMERA1_XC7160
//#define FF_MIPI_CSI2_IMX415
```

双摄：

```dts
#define FF_MIPI_CSI2_CAMERA1_XC7160
#define FF_MIPI_CSI2_CAMERA2_XC7160

//#define FF_DSI1_VP3
//#define FF_MIPI_CSI2_IMX415
```

IMX415：

```dts
#define FF_MIPI_CSI2_IMX415

//#define FF_MIPI_CSI2_CAMERA1_XC7160
//#define FF_MIPI_CSI2_CAMERA2_XC7160
```

### 10.3 `bp.dtsi` 自动互斥处理

当前 `rk3588-firefly-aio-3588sg-bp.dtsi` 会根据摄像头宏自动关闭冲突外设，不再要求手工修改多个节点：

| 启用宏 | 自动关闭资源 |
|---|---|
| `FF_MIPI_CSI2_CAMERA1_XC7160` | DSI0/route、UART4、PCIe2 1-lane、Wi-Fi/蓝牙复用 |
| `FF_MIPI_CSI2_CAMERA2_XC7160` | DSI1/route |
| 双摄 | DSI0/route、DSI1/route，以及 CAMERA1 的 UART4/PCIe/Wi-Fi 冲突资源 |
| XC7160 + IMX415 | IMX415 的 CSI/ISP 链路 |

CAMERA1 使用 I2C1-M4，而 UART4-M0 也使用 GPIO1_PD2/PD3；CAMERA1 的 camera clock 还使用 GPIO1_PD7，而 PCIe2 1-lane/Wi-Fi 电源也可能使用该引脚。因此 CAMERA1 模式下自动关闭 UART4、PCIe2 和 Wi-Fi 是必要的。

### 10.4 实机验证

先检查驱动和媒体链路：

```bash
dmesg | grep -i -E 'xc7160|csi2|dphy|rkcif'
```

列出视频节点：

```bash
for x in /sys/class/video4linux/video*; do
	[ -e "$x" ] || continue
	echo -n "$(basename "$x"): "
	cat "$x/name"
done
```

正常采集节点通常名为 `stream_cif_mipi_id*`；`rkcif_tools_id*` 和 `rkcif_scale_ch*` 不应作为第一选择。

以 CAMERA1 的 `/dev/video0` 为例，显示到 DSI/LVDS 桌面：

```bash
sudo -u firefly env \
XDG_RUNTIME_DIR=/run/user/1000 \
WAYLAND_DISPLAY=wayland-0 \
gst-launch-1.0 -e \
v4l2src device=/dev/video0 io-mode=2 \
! video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 \
! videoconvert \
! waylandsink fullscreen=true sync=false
```

确认确实收到帧：

```bash
sudo -u firefly env \
XDG_RUNTIME_DIR=/run/user/1000 \
WAYLAND_DISPLAY=wayland-0 \
gst-launch-1.0 -e \
v4l2src device=/dev/video0 io-mode=2 \
! video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 \
! fpsdisplaysink video-sink=waylandsink text-overlay=false sync=false
```

### 10.5 故障判据

| 现象 | 结论 |
|---|---|
| `/dev/i2c-1` 不存在 | I2C1-M4 没有成功申请，优先检查 UART4 是否关闭 |
| `pin gpio1-26 already requested by feb70000.serial` | UART4 与 I2C1-M4 冲突 |
| 有 XC7160 I2C 节点但没有 `/dev/video*` | 传感器没有完成 probe 或 CIF 没有绑定 sensor |
| 只有 `stream ON`、没有帧率 | MIPI 没有收到有效视频包，检查 DPHY、lane、排线和电源 |
| 使用 `/dev/video10` 无图像 | 通常是 `rkcif_tools_id*`，不是正常采集节点 |
| IMX415 的 `/dev/video11` 正常、XC7160 不正常 | 两者媒体链路和节点编号不同，必须按 video 节点名称选择 |
