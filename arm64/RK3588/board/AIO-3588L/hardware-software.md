# Firefly AIO-3588L 适配笔记

　　本目录三件套: hardware-software.md (本文), rk3588-firefly-aio-3588l.dts
(顶层, 宏开关), rk3588-firefly-aio-3588l.dtsi (载板全部板级内容展开,
mipi-csi0-imx415/mipi-csi1-imx415/mipi-dsi0/mipi-dsi1 四个模块 dtsi 已
内联, 仅保留 #include "rk3588-firefly-common.dtsi" 基座)。

　　注意: HDMI0/1 / DP0 / GMAC0 / SDCARD 本体 / RECOVERY_KEY / SATA0 与
PCIE2_1L2 互斥逻辑等公共配置位于 rk3588-firefly-common.dtsi, 本文只记载
板差异部分。DSI 双座与文件名-控制器交叉详见根目录 mipi-dsi.md 第 7 节。

## LEDS

### 硬件连接

```
power LED ===> GPIO3 B2 (高有效, 常亮)
user  LED ===> GPIO2 C3 (高有效)
```

### 设备树配置

```
#ifdef FF_LEDS
	firefly_leds: firefly-leds {
		compatible = "gpio-leds";
		pinctrl-0 = <&led_pins>;
		power_led: power-led { label = ":power"; default-state = "on";
			gpios = <&gpio3 RK_PB2 GPIO_ACTIVE_HIGH>; };
		user_led: user-led  { label = ":user";  default-state = "off";
			gpios = <&gpio2 RK_PC3 GPIO_ACTIVE_HIGH>; };
	};
#endif
&pinctrl { leds { led_pins: led-pins {
	rockchip,pins = <3 RK_PB2 RK_FUNC_GPIO &pcfg_pull_none>,
			<2 RK_PC3 RK_FUNC_GPIO &pcfg_pull_none>; }; } }
```

### 测试指令

```
echo 255 > /sys/class/leds/:user/brightness && echo 0 > /sys/class/leds/:user/brightness
```

## FAN

### 硬件连接

```
风扇 PWM ===> PWM15_M2 (pwm15m2_pins 组), 20kHz
无独立供电 regulator, 无转速反馈
```

### 设备树配置

```
#ifdef FF_FAN
	fan: pwm-fan {
		compatible = "pwm-fan";
		#cooling-cells = <2>;
		pwms = <&pwm15 0 50000 0>;
		cooling-levels = <0 50 100 150 200 255>;
		rockchip,temp-trips = <50000 1 55000 2 60000 3 65000 4 70000 5>;
	};
#endif
&pwm15 { status = "okay"; pinctrl-0 = <&pwm15m2_pins>; }
```

### 测试指令

```
cat /sys/class/thermal/thermal_zone*/temp
cat /sys/kernel/debug/pwm            # pwm15 占空比
```

## SDCARD

### 硬件连接

```
SD 电源使能 ===> GPIO4 B0 (高有效, vcc3v3_sd)
SDMMC 本体走 common 公共配置
```

### 设备树配置

```
#ifdef FF_SDCARD
	vcc3v3_sd: vcc3v3-sd {
		compatible = "regulator-fixed";
		regulator-always-on;  regulator-boot-on;
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio4 RK_PB0 GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&vcc3v3_sd_en>;
	};
#endif
```

### 测试指令

```
lsblk
sudo fio --name=real_write --filename=./testfile --rw=write --bs=1M --size=2G --direct=1 --numjobs=1 --time_based=0 --group_reporting
```

## HDMI (HDMI0 + HDMI1)

### 硬件连接

```
HDMI0 (上) enable ===> GPIO4 B1 (高有效)
HDMI1 (下) enable ===> GPIO3 D0 (高有效)
本体 (hdmi0/hdmi1 + 音频) 走 common FF_HDMI0/FF_HDMI1
```

### 设备树配置

```
#ifdef FF_HDMI0
&hdmi0 { status = "okay"; enable-gpios = <&gpio4 RK_PB1 GPIO_ACTIVE_HIGH>; };
#endif
#ifdef FF_HDMI1
&hdmi1 { status = "okay"; enable-gpios = <&gpio3 RK_PD0 GPIO_ACTIVE_HIGH>; };
#endif
```

### 测试指令

```
cat /sys/class/drm/*/status && cat /sys/class/drm/*/modes
xrandr        # 或 modetest -M rockchip -c
```

## HDMI-RX

### 硬件连接

```
HDMI-IN 检测 ===> GPIO1 D5 (低有效, hdmirx-det)
控制器 ===> hdmirx_ctrler (hdmim1_rx 组), HPD 触发电平高
音频 ===> hdmiin-sound (i2s7_8ch <-> hdmirx_ctrler), 带 jack-det
需要预留 256MB CMA (FF_HDMI_RX 段 reserved-memory)
```

### 设备树配置

```
#ifdef FF_HDMI_RX
	reserved-memory { cma { reg = <0x0 (256*0x100000) 0x0 (256*0x100000)>;
		linux,cma-default; reusable; }; };
	hdmiin-sound { compatible = "rockchip,hdmi"; rockchip,cpu = <&i2s7_8ch>;
		rockchip,codec = <&hdmirx_ctrler 0>; rockchip,jack-det; };
#endif
&hdmirx_ctrler { status = "okay"; hpd-trigger-level = <1>;
	hdmirx-det-gpios = <&gpio1 RK_PD5 GPIO_ACTIVE_LOW>;
	pinctrl-0 = <&hdmim1_rx &hdmirx_det>; }
&i2s7_8ch { status = "okay"; }
```

### 测试指令

```
dmesg | grep -i hdmirx
cat /sys/class/video4linux/video*/name | grep -i hdmirx
v4l2-ctl -d /dev/videoXX --set-fmt-video=width=1920,height=1080,pixelformat=NV16 \
	--stream-mmap --stream-count=60 --stream-to=/tmp/hdmiin.yuv
```

## WATCHDOG (PC9202)

### 硬件连接

```
PC9202 (外部看门狗) ===> I2C0 (地址 0x3c)
WD-EN ===> GPIO2 C5 (低有效)    // 注意与 JD4 (GPIO0_C4 高有效) 不同
```

### 设备树配置

```
#ifdef FF_WATCHDOG
&i2c0 {
	status = "okay";
	pc9202: pc9202@3c {
		status = "okay";
		compatible = "firefly,pc9202";
		reg = <0x3c>;
		wd-en-gpio = <&gpio2 RK_PC5 GPIO_ACTIVE_LOW>;
	};
};
#endif
```

### 测试指令

```
ls /dev/watchdog*
wdctl /dev/watchdog1            # 节点号以实际为准
```

## RTC (HYM8563)

### 硬件连接

```
HYM8563 ===> I2C6_M0 (地址 0x51), INT GPIO0 B0 (低有效)
```

### 设备树配置

```
#ifdef FF_RTC
&i2c6 { status = "okay"; pinctrl-0 = <&i2c6m0_xfer>;
	hym8563: hym8563@51 {
		compatible = "haoyu,hym8563";
		reg = <0x51>;
		#clock-cells = <0>;  clock-frequency = <32768>;
		pinctrl-0 = <&hym8563_int>;
		interrupts = <RK_PB0 IRQ_TYPE_LEVEL_LOW>;
		wakeup-source;
	};
}
#endif
&pinctrl { hym8563 { hym8563_int: hym8563-int {
	rockchip,pins = <0 RK_PB0 RK_FUNC_GPIO &pcfg_pull_up>; }; } }
```

### 测试指令

```
hwclock --show && hwclock --systohc
```

## GMAC0

### 硬件连接

```
GMAC0 (千兆网口) ===> reset GPIO3 C7 (低有效), tx_delay = 0x39
```

### 设备树配置

```
#ifdef FF_GMAC0
&gmac0 { status = "okay";
	snps,reset-gpio = <&gpio3 RK_PC7 GPIO_ACTIVE_LOW>;
	tx_delay = <0x39>; };
#endif
```

### 测试指令

```
ip link && ethtool eth0
```

## USB3.0 HOST (上座 + 下座)

### 硬件连接

```
上座 (usbhost3_0) ===> combphy2_psu + u2phy3; 同时把 host1 的 2.0
  (usb_host1_ehci/ohci) 一并打开, 供电 vcc5v0_usb20_host1
下座 (usbdrd3_1) ===> u2phy1_otg + usbdp_phy1, 供电 vcc5v0_usb30_host0
vcc5v0_usb20_host1 覆盖为 ===> GPIO3 A6 (高有效, 定义于 FF_USB30_HOST0 段)
vcc5v0_usb30_host0 / vcc5v0_usb20_host1 无 GPIO (直上电型 regulator)
```

### 设备树配置

```
// 上座 (FF_USB30_HOST0)
&usbhost3_0 { status = "okay"; }
&usbhost_dwc3_0 { status = "okay"; dr_mode = "host"; }
&combphy2_psu { status = "okay"; }
&vcc5v0_usb20_host1 { status = "okay";
	gpio = <&gpio3 RK_PA6 GPIO_ACTIVE_HIGH>;      // 覆盖
	pinctrl-0 = <&vcc5v0_usb20_host1_en>;
	vin-supply = <&vcc5v0_sys>; }
&usb_host1_ehci { status = "okay"; }  &usb_host1_ohci { status = "okay"; }
&u2phy3 { status = "okay"; }
&u2phy3_host { status = "okay"; phy-supply = <&vcc5v0_usb20_host1>; }

// 下座 (FF_USB30_HOST1)
&usbdrd3_1 { status = "okay"; }
&usbdrd_dwc3_1 { status = "okay"; dr_mode = "host"; }
&u2phy1 { status = "okay"; }
&u2phy1_otg { status = "okay"; phy-supply = <&vcc5v0_usb30_host0>; }
&usbdp_phy1 { status = "okay"; }
```

### 测试指令

```
lsusb && lsblk && dmesg | grep -iE "xhci|dwc3"
```

## USB2.0 (HOST0 HUB + HOST1)

### 硬件连接

```
USB2.0 HUB (HOST0) 供电 ===> vcc5v0_usb20_host0, 覆盖为 GPIO0 A0 (高有效)
HOST1 的 2.0 供电见上节 (GPIO3 A6, 与 USB3.0 上座共用 regulator)
```

### 设备树配置

```
#ifdef FF_USB20_HOST0
&vcc5v0_usb20_host0 { status = "okay";
	gpio = <&gpio0 RK_PA0 GPIO_ACTIVE_HIGH>;      // 覆盖
	pinctrl-0 = <&vcc5v0_usb20_host0_en>;
	vin-supply = <&vcc5v0_sys>; };
#endif
```

### 测试指令

```
lsusb -t
```

## TYPEC0 (全功能, DP 复用)

### 硬件连接

```
fusb302 (PD) ===> I2C6_M0 (地址 0x22), INT GPIO0 D3 (低有效)
VBUS 放电使能 ===> GPIO4 A3 (高有效, vbus5v0_typec0)
SBU1/SBU2 (DP) ===> GPIO4 B2 / GPIO4 B3
DP 走 dp0 (vp2, common FF_DP0), USB 走 usbdrd3_0 (otg)
PD sink 仅 5V/1A, source 5V/3A
```

### 设备树配置 (精简)

```
&i2c6 {
	usbc0: fusb302@22 {
		compatible = "fcs,fusb302";
		reg = <0x22>;
		interrupts = <RK_PD3 IRQ_TYPE_LEVEL_LOW>;
		vbus-supply = <&vbus5v0_typec0>;
		usb_con: connector {
			compatible = "usb-c-connector";
			data-role = "dual";  power-role = "dual";
			try-power-role = "sink";
			op-sink-microwatt = <1000000>;
			sink-pdos   = <PDO_FIXED(5000, 1000, PDO_FIXED_USB_COMM)>;
			source-pdos = <PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)>;
			altmodes { altmode@0 { svid = /bits/ 16 <0xff01>;
				vdo = <0xffffffff>; } };
			ports { /* port0 orien_sw / port1 dp_mux -> usbdp_phy0,
				port2 -> dp0 (HPD 边, 2026-11-03 修复, 见 DP0 修复实录) */ };
		};
	};
};

/ { vbus5v0_typec0: vbus5v0-typec0 {
	gpio = <&gpio4 RK_PA3 GPIO_ACTIVE_HIGH>;
	pinctrl-0 = <&vbus5v0_typec0_en>; vin-supply = <&vcc5v0_sys>; }; };

&usbdp_phy0 { status = "okay"; orientation-switch; svid = <0xff01>;
	sbu1-dc-gpios = <&gpio4 RK_PB2 GPIO_ACTIVE_HIGH>;
	sbu2-dc-gpios = <&gpio4 RK_PB3 GPIO_ACTIVE_HIGH>; }
&usbdrd_dwc3_0 { status = "okay"; dr_mode = "otg"; usb-role-switch; }
&u2phy0 { status = "okay"; }
&u2phy0_otg { status = "okay"; rockchip,typec-vbus-det; }
```

### 测试指令

```
ls /sys/class/typec/ && cat /sys/class/typec/port0/power_role
cat /sys/class/drm/*/status                 # 插 DP 后 DP 出现
dmesg | grep -iE "fusb302|typec"
```

## DP0 (经 TypeC 复用)

### 硬件连接

```
DP0 信号经 TypeC0 SBU (GPIO4 B2/B3), 本体 &dp0 / dp0_in_vp2 /
route_dp0 / dp0 音频 (spdif_tx2) 位于 common FF_DP0 段
```

### 设备树配置

```
// 板级修复 (2026-11-03): connector 与 dp0 各加 port@2 互指, 见 DP0 修复实录
// common FF_DP0 段中: &dp0 { mode-switch; status = "okay"; }
//   &usbdp_phy0 { mode-switch; ... }  &dp0_in_vp2 { status = "okay"; }
```

### 测试指令

```
cat /sys/class/drm/*/status
modetest -M rockchip -c        # DP-1 出现即可

# 切换音频默认声卡
runuser -u firefly -- env XDG_RUNTIME_DIR=/run/user/1000 wpctl status    # 找sinks里面的标号
runuser -u firefly -- env XDG_RUNTIME_DIR=/run/user/1000 wpctl set-default 58   # 比如想设置dp的声卡,编号是58


# 播放视频
sudo -u firefly XDG_RUNTIME_DIR=/run/user/1000 gst-play-1.0 4K_H264_bird.mp4
```

## DP0 修复实录 (2026-11-03: connector 图缺 dp0 边 => HPD 恒 unplug)

### 现象与排查

　　6.12.81 内核, TypeC0 经 FL7102 转接器 (billboard) 接 DP 触摸屏
(WingCoolTouch): PD 全程走通 (DFP_TO_UFP_ENTER_MODE ACK), usbdp phy
收到 DP status (0x8a, HPD bit 已置位, lane 配置已下发), 但
card0-DP-1 恒 disconnected, billboard (1d5c:7102) 恒枚举。

```
cat /sys/kernel/debug/usb/tcpm-6-0022/log   # PD 全程回放, Enter Mode ACK
dmesg | grep "received DP status"           # usbdp phy 回调正常 (ddebug)
cat /sys/kernel/debug/dri/0/dw-dp0/dp_status
#   usbdp hpd: yes / hpd status: unplug    <- 断点: dw-dp 的 mux 从未被调
ls /sys/class/typec_mux/                    # fde50000.dp-mux 注册了但没人调
dmesg | grep "hotplug from the usbdp"       # dw-dp mux 回调: 一条不出现
```

### 根因

　　dw-dp 节点带 mode-switch 时, HPD 唯一软件路径 = 它自己注册的
typec mux 回调 (dw_dp_typec_mux_set, 设备 fde50000.dp-mux); 而 typec
core 按 usb-c-connector 的 OF 图收集 mode-switch 设备 (非递归, 上限
3 个), 原图只有 connector<->usbdp_phy0 两条边, dp0 不在图中 =>
无人调用 => hotplug.status 恒 false => HPD unplug。usbdp 写的
vo-grf bits[11:10] 是 PHY 层配置, dw-dp 软件不消费, 替代不了。
引脚移植三方一致 (5.10/6.1/6.12) 无罪; 6.1 官方 dtsi 根本没启用
&dp0, 不存在"以前能亮"的基准。

### 设备树修复

```
// 板级 aio-3588l.dtsi: connector ports 加 port@2, dp0 加 port@2, 互指
				port@2 {
					reg = <2>;
					usbc0_dp0_mux: endpoint {
						remote-endpoint = <&dp0_typec_mux>;
					};
				};
};

&dp0 {
	ports {
		port@2 {
			reg = <2>;
			dp0_typec_mux: endpoint {
				remote-endpoint = <&usbc0_dp0_mux>;
			};
		};
	};
};
```

　　大坑: ① 边不能挂 dp0 的 port@1 (DRM 下游端口,
drm_of_find_panel_or_bridge 对非 panel/bridge 的 remote 返回
-EPROBE_DEFER, 启动报 "failed to attach bridge: -517", dw-dp probe
失败); ② USB-A→C 烧录线插 TypeC0 是 SNK 死循环 (A→C 线 C 端拉 Rp,
板子等不到 PD, HARD_RESET 循环后停 5V, 正常行为勿误判); ③ 补边后
typec_mux_get 要求 fde50000.dp-mux 已注册, fusb302 若早于 dw-dp
probe 则 altmode 注册 defer 不重试 (潜在, 本板未触发)。
详细机制/排查链见 typec.md 第 6 节。

### 测试指令

```
dmesg | grep -E "dw-dp|attach bridge"       # 启动: 无 -517
cat /sys/class/drm/card0-DP-1/status        # 插屏后: connected
dmesg | grep "hotplug from the usbdp"       # dw-dp mux 回调出现
dmesg | grep 1d5c                           # billboard 不再枚举 (DP 成功后撤下)
# 2026-11-03 实测: 显示 + WingCoolTouch 触摸全部正常
```

## M.2 槽 (SATA0 默认开 / PCIE2_1L2 默认关, 复用)

### 硬件连接

```
M.2 槽电源 ===> GPIO4 C6 (高有效): SATA0 用 vcc3v3_sata0,
             PCIE2_1L2 用 vcc3v3_pcie20_1l2, 同一脚
PCIE2_1L2 reset ===> GPIO4 A2 (高有效)
互斥逻辑 ===> common 中 #if defined(FF_SATA0) && !defined(FF_PCIE2_1L2)
```

### 设备树配置

```
// 默认: #define FF_SATA0 (PCIE2_1L2 注释掉)
#ifdef FF_SATA0
&vcc3v3_sata0 { gpio = <&gpio4 RK_PC6 GPIO_ACTIVE_HIGH>; };
#endif
// 切 PCIe 时:
#ifdef FF_PCIE2_1L2
&vcc3v3_pcie20_1l2 { gpio = <&gpio4 RK_PC6 GPIO_ACTIVE_HIGH>; };
&pcie2x1l2 { reset-gpios = <&gpio4 RK_PA2 GPIO_ACTIVE_HIGH>; };
#endif
```

### 测试指令

```
lsblk                        # SATA: 出块设备
lspci && dmesg | grep -i pcie # PCIe: 出设备
```

## WIFI-BT (PCIe, PCIE2_1L0)

### 硬件连接

```
WIFI 模组 (M.2, PCIe 侧) ===> pcie2x1l0
reset ===> GPIO4 A5 (高有效), perst-inactive-ms = <500>
模组供电 ===> vcc3v3_pcie20_1l0 (GPIO0 B2, 高有效, 5ms 延迟)
PHY ===> combphy1_ps
```

### 设备树配置

```
#ifdef FF_PCIE2_1L0_WIFI
	vcc3v3_pcie20_1l0: vcc3v3-pcie20-1l0 {
		enable-active-high;
		gpio = <&gpio0 RK_PB2 GPIO_ACTIVE_HIGH>;
		startup-delay-us = <5000>;
		vin-supply = <&vcc3v3_sys>;
	};
#endif
&combphy1_ps { status = "okay"; }
&pcie2x1l0 { status = "okay";
	reset-gpios = <&gpio4 RK_PA5 GPIO_ACTIVE_HIGH>;
	rockchip,skip-scan-in-resume;
	rockchip,perst-inactive-ms = <500>;
	vpcie3v3-supply = <&vcc3v3_pcie20_1l0>; }
```

### 测试指令

```
lspci
dmesg | grep -iE "pcie|wlan"
ip link          # wlan0
```

## ES8388 音频

### 硬件连接

```
ES8388 (codec) ===> I2C3_M0 (地址 0x11)
MCLK ===> I2S0_MCLK (mclkout_i2s0, 12.288MHz)
耳机检测 hp-det ===> GPIO1 C4 (高有效)
耳机功放控制 hp-con ===> GPIO4 A7
检测走 saradc 3 (keyup 1.8V, playpause 键 2000uV)
```

### 设备树配置

```
#ifdef FF_CODEC_ES8388
	es8388_sound: es8388-sound {
		compatible = "rockchip,multicodecs-card";
		rockchip,card-name = "rockchip-es8388";
		hp-det-gpio = <&gpio1 RK_PC4 GPIO_ACTIVE_HIGH>;
		hp-con-gpio = <&gpio4 RK_PA7 GPIO_ACTIVE_HIGH>;
		io-channels = <&saradc 3>;
		keyup-threshold-microvolt = <1800000>;
		rockchip,mclk-fs = <256>;
		rockchip,cpu = <&i2s0_8ch>;
		rockchip,codec = <&es8388>;
		rockchip,audio-routing =
			"Headphone", "LOUT1", "Headphone", "ROUT1",
			"Speaker", "LOUT2", "Speaker", "ROUT2",
			"LINPUT2", "Main Mic", "RINPUT1", "Headset Mic", ...;
		play-pause-key { linux,code = <KEY_PLAYPAUSE>;
			press-threshold-microvolt = <2000>; };
	};
#endif

&i2c3 { es8388: es8388@11 {
	compatible = "everest,es8388", "everest,es8323";
	reg = <0x11>;
	clocks = <&mclkout_i2s0>;
	assigned-clocks = <&mclkout_i2s0>;
	assigned-clock-rates = <12288000>; }; }
&i2s0_8ch { status = "okay";
	pinctrl-0 = <&i2s0_lrck &i2s0_sclk &i2s0_sdi0 &i2s0_sdo0>; }
```

### 测试指令

```
aplay -l
speaker-test -twav -c2 -t1
arecord -D hw:1,0 -f S16_LE -r 44100 -d 3 /tmp/rec.wav && aplay /tmp/rec.wav
```

## 4G 模块

### 硬件连接

```
4G 模组供电 ===> vcc_4g_pwr, GPIO4 B5 (高有效, 常开)
模组本体走 USB 枚举, 无需额外节点
```

### 设备树配置

```
#ifdef FF_4G_MODULE
	vcc_4g_pwr: vcc-4g-pwr {
		compatible = "regulator-fixed";
		regulator-always-on;  regulator-boot-on;
		enable-active-high;
		gpio = <&gpio4 RK_PB5 GPIO_ACTIVE_HIGH>;
	};
#endif
```

### 测试指令

```
lsusb       # 出现模组 (quectel 等)
dmesg | grep -iE "qmi_wwan|option"
```

## UART / SPI 扩展组

### 硬件连接

```
uart3 ===> UART3_M1     uart6 ===> UART6_M1 (带 cts/rts 流控)
uart7 ===> UART7_M1     uart8 ===> UART8_M1
spi1  ===> SPI1_M2, 50MHz
```

### 设备树配置

```
#ifdef FF_UART3
&uart3 { status = "okay"; pinctrl-0 = <&uart3m1_xfer>; }
#endif
#ifdef FF_UART6
&uart6 { status = "okay"; pinctrl-0 = <&uart6m1_xfer &uart6m1_ctsn &uart6m1_rtsn>; }
#endif
#ifdef FF_UART7
&uart7 { status = "okay"; pinctrl-0 = <&uart7m1_xfer>; }
#endif
#ifdef FF_UART8
&uart8 { status = "okay"; pinctrl-0 = <&uart8m1_xfer>; }
#endif
#ifdef FF_SPI1
&spi1 { status = "okay"; pinctrl-0 = <&spi1m2_cs0 &spi1m2_pins>;
	num-cs = <1>;  max-freq = <50000000>;
	spi_dev: spi-dev@0 { compatible = "rockchip,spidev";
		reg = <0x0>; spi-max-frequency = <50000000>; }; }
#endif
```

### 测试指令

```
ls /dev/ttyS* /dev/spidev*
cat /dev/ttyS7 &          # 对端发数据
echo test > /dev/ttyS7
```

## MIPI DSI (LCD0/LCD1 双座, 宏互斥)

### 硬件连接

```
!! 文件名与控制器交叉: mipi-dsi0.dtsi 内部用 dsi1 控制器 = LCD1 座;
   mipi-dsi1.dtsi 内部用 dsi0 控制器 = LCD0 座。详见 mipi-dsi.md 7.1

LCD0 座 (当前工作配方, FF_MIPI_DSI1_VP3 -> mipi-dsi1.dtsi -> dsi0/dcphy0):
  背光 PWM ===> PWM8_M0 (20kHz), LCD0_BL_EN ===> GPIO1 B1
  LCD0_PWR_EN ===> GPIO3 B7, LCD0_RST ===> GPIO3 B3 (低有效)
  触摸 goodix_ts@0x14 ===> I2C8_M4, TP0_INT GPIO3 B1 / TP0_RST GPIO3 B4
  双 panel: panel0 BSD1218 (70MHz, disabled) / panel1 M101014-BE45-A1
            (72.6MHz, self-init, 当前启用)

LCD1 座 (FF_MIPI_DSI0_VP3 -> mipi-dsi0.dtsi -> dsi1/dcphy1, 默认关):
  背光 PWM ===> PWM9_M0, backlight_1 enable ===> GPIO1 A4
  reset ===> GPIO3 A4 (低有效)
  触摸 goodix_ts1@0x14 ===> I2C6_M0, INT GPIO3 A1 / reset GPIO3 A5
  panel0 (70MHz) / panel1 (72.6MHz) 结构同 LCD0

两座宏互斥: FF_MIPI_DSI0_VP3 XOR FF_MIPI_DSI1_VP3
LCD1 座差分对硬件不通 (见 mipi-dsi.md 第 7 节), 座不可互换使用
```

### 设备树配置 (LCD0 座 / FF_MIPI_DSI1_VP3, 精简)

```
backlight_0: backlight-0 {
	compatible = "pwm-backlight";
	enable-gpios = <&gpio1 RK_PB1 GPIO_ACTIVE_HIGH>;
	pwms = <&pwm8 0 50000 1>;
};
&pwm8 { status = "okay"; pinctrl-0 = <&pwm8m0_pins>; }
&mipi_dcphy0 { status = "okay"; }
&dsi0_in_vp3 { status = "okay"; }  &route_dsi0 { status = "okay"; }
&dsi0 {
	status = "okay";
	dsi0_panel:  panel0@0 { ... status = "disabled";
		enable-gpios = <&gpio3 RK_PB7 GPIO_ACTIVE_HIGH>;
		reset-gpios = <&gpio3 RK_PB3 GPIO_ACTIVE_LOW>;
		display-timings { native-mode = <&timing0>;
			timing0: timing0 { clock-frequency = <70000000>; ... } };
		rockchip,touch-nodes = <&goodix_ts>; };
	dsi0_panel1: panel1@0 { ... status = "okay";   // M101014 self-init
		display-timings { timing0 { clock-frequency = <72600000>; ... } }; };
}
&i2c8 { goodix_ts: goodix_ts@14 {
	compatible = "goodix,gt9xxx";
	reg = <0x14>;
	interrupts = <RK_PB1 IRQ_TYPE_LEVEL_LOW>;
	reset-gpios = <&gpio3 RK_PB4 GPIO_ACTIVE_HIGH>;
	goodix,cfg-group2 = [ ... ]; } }
// 完整 init-sequence / cfg-group2 见 dtsi FF_MIPI_DSI1_VP3 段
// U-Boot 无屏让位 HDMI 的 check-id 修复见 mipi-dsi.md 7.5
```

### 测试指令

```
cat /sys/class/drm/card*-DSI-*/status
cat /sys/class/backlight/*/brightness && echo 100 > /sys/class/backlight/*/brightness
cat /proc/bus/input/devices | grep -A4 goodix
modetest -M rockchip -c       # 无屏时应只见 HDMI (U-Boot fdt_disable_panels)
```

## CAMERA (CSI0/CSI1 双 IMX415)

### 硬件连接

```
CSI0 (FF_MIPI_CSI0_IMX415):
  sensor (IMX415) ===> I2C3_M0 (地址 0x37), reset GPIO2 B5 (低有效)
  链路 ===> csi2_dphy0 -> mipi2_csi2 -> rkcif_mipi_lvds2 -> isp0_vir0
CSI1 (FF_MIPI_CSI1_IMX415):
  sensor (IMX415) ===> I2C8_M4 (地址 0x37), reset GPIO2 C5 (低有效)
  链路 ===> csi2_dphy3 -> mipi4_csi2 -> rkcif_mipi_lvds4 -> isp1_vir0
  注意 I2C8_M4 与 LCD0 座触摸共享总线
```

### 设备树配置 (CSI1 为实测出流座, 精简)

```
&i2c8 { imx415: imx415@37 {
	compatible = "sony,imx415";
	reg = <0x37>;
	reset-gpios = <&gpio2 RK_PC5 GPIO_ACTIVE_LOW>;
	port { imx415_out: endpoint {
		remote-endpoint = <&mipidphy3_in_ucam1>;
		data-lanes = <1 2 3 4>; } }; } }
&csi2_dphy3 { status = "okay"; }
&mipi4_csi2 { status = "okay"; }
&rkcif_mipi_lvds4 { status = "okay"; }
&rkisp1_vir0 { status = "okay"; }
// CSI0 同构: &i2c3 0x37 + GPIO2_B5 + csi2_dphy0/mipi2/lvds2/isp0_vir0
```

### 测试指令

```
dmesg | grep -iE "imx415|dphy.*match"
media-ctl -p -d /dev/media0
grep -H '' /sys/class/video4linux/video*/name    # 找 MAINPATH 节点
v4l2-ctl -d /dev/videoXX --set-fmt-video=width=3840,height=2160,pixelformat=NV12 \
	 --stream-mmap --stream-count=1 --stream-to=/tmp/f.raw
# CSI1 实测: 3864x2192@10bpp RAW 出流正常; CSI0 probe id 000000 = 未插 sensor
```

## PCIE3_X4 (默认关)

### 硬件连接

```
pcie3x4 供电 ===> vcc3v3_pcie30, GPIO1 B3 (高有效)
```

### 设备树配置

```
#ifdef FF_PCIE3_X4
&vcc3v3_pcie30 { status = "okay";
	gpio = <&gpio1 RK_PB3 GPIO_ACTIVE_HIGH>; };
#endif
```

### 测试指令

```
lspci && dmesg | grep -i pcie
```

## RECOVERY_KEY

### 硬件连接

```
Recovery 按键走 common FF_RECOVERY_KEY 公共配置
```

### 设备树配置

```
// common 中 #ifdef FF_RECOVERY_KEY (adc 按键), 板级无差异配置
```

### 测试指令

```
cat /proc/bus/input/devices | grep -i recovery
evtest        # 按键看事件
```
