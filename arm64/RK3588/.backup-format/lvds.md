# LVDS 屏适配笔记 (LT9211D 桥接) — AIO-3588SG lvds101

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

### 4.2 落地的修复清单 (共 5 个文件, 留档可复现)

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
