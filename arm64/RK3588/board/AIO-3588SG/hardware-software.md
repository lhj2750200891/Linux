# Firefly AIO-3588SG 适配笔记

　　本目录三件套: hardware-software.md (本文), rk3588-firefly-aio-3588sg.dts
(顶层, 宏开关), rk3588-firefly-aio-3588sg.dtsi (载板全部板级内容展开, edp0/
mipi-dsi1/mipi-csi2/bp 模块 dtsi 已内联, 仅保留 #include
"rk3588-firefly-common.dtsi" 基座)。

　　注意: 本板无 #define rk3588 (走 rk3588s 资源子集); HDMI / USB20 本体 /
sdmmc 本体等公共配置位于 rk3588-firefly-common.dtsi。edp0 段引用的 pca9554
label 在当前 SDK 源中未定义 (官方源自带问题), 编译报 phandle_references
错误时先排查此点。

## PCA9555 (IO 扩展)

### 硬件连接

```
PCA9555 (IO 扩展, 16 路) ===> I2C4_M3 (地址 0x21)
  PCA_IO0_2 ===> EDP_BL_EN (EDP 屏背光使能)
  PCA_IO0_3 ===> EDP 屏 EN
  PCA_IO0_6 ===> MIPI 屏背光 EN
  PCA_IO0_7 ===> MIPI 屏触摸 goodix reset
  PCA_IO1_4 ===> USB2.0 HUB reset
  PCA_IO1_5 ===> user1 LED
  PCA_IO1_6 ===> user LED
  PCA_IO1_7 ===> power LED
```

### 设备树配置

```
&i2c4 {
	status = "okay";
	pinctrl-0 = <&i2c4m3_xfer>;
#ifdef FF_PCA9555
	pca9555: gpio@21 {
		status = "okay";
		compatible = "nxp,pca9555";
		reg = <0x21>;
		gpio-controller;
		#gpio-cells = <2>;
		gpio-group-num = <200>;    // 引出为 gpio 200~215
	};
#endif
};
```

### 测试指令

```
gpiodetect                                  # 能看到 pca9555 对应 gpiochip
echo 200 > /sys/class/gpio/export && cat /sys/class/gpio/gpio200/value
```

## LEDS

### 硬件连接

```
power LED ===> PCA9555 IO1_7 (常亮)
user  LED ===> PCA9555 IO1_6
user1 LED ===> PCA9555 IO1_5
```

### 设备树配置

```
#ifdef FF_LEDS
	firefly_leds: leds {
		compatible = "gpio-leds";
		status = "okay";
		power_led: power  { label = ":power";  default-state = "on";
			gpios = <&pca9555 PCA_IO1_7 GPIO_ACTIVE_HIGH>; };
		user_led: user   { label = ":user";   default-state = "off";
			gpios = <&pca9555 PCA_IO1_6 GPIO_ACTIVE_HIGH>; };
		user_led1: user1 { label = ":user1";  default-state = "off";
			gpios = <&pca9555 PCA_IO1_5 GPIO_ACTIVE_HIGH>; };
	};
#endif
```

### 测试指令

```
echo 255 > /sys/class/leds/:user/brightness && echo 0 > /sys/class/leds/:user/brightness
```

## FAN

### 硬件连接

```
风扇 PWM ===> PWM15_M2 (pwm15m2_pins 组), 20kHz
风扇供电 ===> 12V (vcc12v_dcin)
```

### 设备树配置

```
#ifdef FF_FAN
	fan: pwm-fan {
		status = "okay";
		compatible = "pwm-fan";
		fan-supply = <&vcc12v_dcin>;
		pwms = <&pwm15 0 50000 0>;
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
SD_PWR_EN ===> GPIO3 C6 (高有效, vcc3v3_sd_s0)
SDMMC 本体走 common 公共配置
```

### 设备树配置

```
#ifdef FF_SDCARD
	vcc3v3_sd_s0: vcc3v3-sd-s0 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio3 RK_PC6 GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&sd_pwr_en>;
		vin-supply = <&vcc_3v3_s3>;
		regulator-state-mem { regulator-off-in-suspend; };
	};
#endif
&sdmmc { status = "okay"; vmmc-supply = <&vcc3v3_sd_s0>; }
```

### 测试指令

```
lsblk
sudo fio --name=real_write --filename=./testfile --rw=write --bs=1M --size=2G --direct=1 --numjobs=1 --time_based=0 --group_reporting
```

## USB (USB2.0 HOST0 + USB3.0 HOST)

### 硬件连接

```
USB2.0 HUB reset ===> PCA9555 IO1_4
5V 供电 ===> vcc5v0_usb_host (GPIO4 B5, 高有效)
USB2.0 ===> u2phy2_host
USB3.0 ===> usbhost3_0 + usbhost_dwc3_0 + u2phy3_host + combphy2_psu
```

### 设备树配置

```
&u2phy2_host { status = "okay"; phy-supply = <&vcc5v0_usb_host>; }
&u2phy3     { status = "okay"; }
&u2phy3_host{ status = "okay"; phy-supply = <&vcc5v0_usb_host>; }
&combphy2_psu { status = "okay"; }
&usbhost3_0 { status = "okay"; }
&usbhost_dwc3_0 { status = "okay"; dr_mode = "host"; }
```

### 测试指令

```
lsusb && lsblk
dmesg | grep -iE "xhci|ehci|hub"
```

## TYPEC0 (全功能 + 电池充电)

### 硬件连接

```
fusb302 (PD) ===> I2C2_M0 (地址 0x22), INT GPIO0 C4 (低有效)
充电 IC sc8886 (兼容 bq25703) ===> I2C4_M3 (地址 0x6b), INT GPIO4 C1
OTG 模式使能 ===> GPIO4 C0
TypeC 放电使能 ===> GPIO1 A5
电量计 cw2017 ===> I2C4_M3 (地址 0x63), 双电池串联 (8.4V max)
DP 走 dp0 (vp2), USB 走 usbdrd3_0 (otg)
SBU1/SBU2 ===> GPIO1 B0 / GPIO1 A0
DP 音频 ===> dp0_sound (spdif_tx2 -> dp0)
```

### 设备树配置 (精简)

```
&i2c2 {
	usbc0: fusb302@22 {
		compatible = "fcs,fusb302";
		reg = <0x22>;
		interrupts = <RK_PC4 IRQ_TYPE_LEVEL_LOW>;
		vbus-supply = <&vbus5v0_typec_charge>;
		charge-dev = <&sc8886>;
		usb_con: connector {
			compatible = "usb-c-connector";
			data-role = "dual";  power-role = "dual";
			try-power-role = "sink";
			sink-pdos = <PDO_FIXED(5000,3000,...) PDO_FIXED(9000,3000,...)
			             PDO_FIXED(12000,2000,...)>;
			mode-switch = <&dp0>;
			ports { /* orientation_switch / dp_altmode_mux */ };
		};
	};
};

&i2c4 {
	cw2017: cw2017@63 {          // 电量计, 双电池
		compatible = "cellwise,cw2017";
		reg = <0x63>;
		cellwise,dual-cell;
		cellwise,design-capacity-amh = <5000>;
		firefly,battery-max-voltage = <8400>;
		power-supplies = <&sc8886>;
	};
	sc8886: sc8886@6b {          // 充电 IC
		compatible = "ti,bq25703";
		reg = <0x6b>;
		ti,usb-charger-detection = <&usbc0>;
		ti,charge-current = <2000000>;
		ti,max-charge-voltage = <8400000>;
		interrupts = <RK_PC1 IRQ_TYPE_LEVEL_LOW>;
		otg-mode-en-gpios = <&gpio4 RK_PC0 GPIO_ACTIVE_HIGH>;
		typec0-discharge-gpios = <&gpio1 RK_PA5 GPIO_ACTIVE_HIGH>;
		regulators { vbus5v0_typec_charge: vbus5v0-typec-charge { ... }; };
	};
};

&usbdp_phy0 { orientation-switch; mode-switch; svid = <0xff01>;
	sbu1-dc-gpios = <&gpio1 RK_PB0 GPIO_ACTIVE_HIGH>;
	sbu2-dc-gpios = <&gpio1 RK_PA0 GPIO_ACTIVE_HIGH>; }
&dp0 { status = "okay"; } &dp0_in_vp2 { status = "okay"; }
&route_dp0 { status = "okay"; connect = <&vp2_out_dp0>; }
&spdif_tx2 { status = "okay"; } &dp0_sound { status = "okay"; }
&usbdrd_dwc3_0 { dr_mode = "otg"; usb-role-switch; }

/* U-Boot 充电动画 (关机充电) */
charge_animation: charge-animation {
	compatible = "rockchip,uboot-charge";
	rockchip,uboot-charge-on = <1>;
	rockchip,uboot-exit-charge-level = <2>;
	rockchip,screen-on-voltage = <6144>;
};
```

### 测试指令

```
cat /sys/class/power_supply/*/capacity      # 电量
cat /sys/class/power_supply/*/status        # Charging/Discharging
ls /sys/class/typec/
cat /sys/class/drm/*/status                 # 插 DP 后 DP 出现
dmesg | grep -iE "fusb302|cw2017|bq25703|sc8886"
```

## GMAC1

### 硬件连接

```
GMAC1 (千兆网口) ===> reset GPIO1 A1 (低有效), tx_delay = 0x37
```

### 设备树配置

```
#ifdef FF_GMAC1
&gmac1 {
	snps,reset-gpio = <&gpio1 RK_PA1 GPIO_ACTIVE_LOW>;
	tx_delay = <0x37>;
	status = "okay";
};
#endif
```

### 测试指令

```
ip link                       # eth?
ethtool eth0
```

## PCIE2_1L2 (M.2)

### 硬件连接

```
pcie2x1l2 ===> reset GPIO3 D1 (高有效), skip-scan-in-resume
与 SATA0 复用
```

### 设备树配置

```
#if defined(FF_PCIE2_1L2) && !defined(FF_SATA0)
&pcie2x1l2 {
	reset-gpios = <&gpio3 RK_PD1 GPIO_ACTIVE_HIGH>;
	rockchip,skip-scan-in-resume;
	status = "okay";
};
#endif
```

### 测试指令

```
lspci && lsblk
dmesg | grep -i pcie
```

## WIFI-BT (AP6275P)

### 硬件连接

```
WL_REG_ON ===> GPIO0 C7
WIFI_HOST_WAKE ===> GPIO0 A0
BT 走 UART9_M2: BT_REG_ON GPIO0 D0 / BT_WAKE GPIO0 C6 / BT_HOST_WAKE GPIO0 C5
BT RTS ===> GPIO3 D2 (rts_gpio 态切换)
BT 32.768k 时钟 ===> hym8563
BT SCO 音频 ===> i2s1_8ch (sdi2/sdo3, dsp_a, rockchip,bt 声卡)
```

### 设备树配置

```
&uart9 { status = "okay"; pinctrl-0 = <&uart9m2_xfer &uart9m2_ctsn>; }
&i2s1_8ch { status = "okay"; pinctrl-0 = <&i2s1m0_lrck &i2s1m0_sclk
             &i2s1m0_sdi2 &i2s1m0_sdo3>; rockchip,bclk-fs = <32>; }
wireless_wlan: wireless-wlan {
	compatible = "wlan-platdata";
	wifi_chip_type = "ap6275p";
	WIFI,host_wake-gpios = <&gpio0 RK_PA0 GPIO_ACTIVE_HIGH>;
	WIFI,poweren-gpios   = <&gpio0 RK_PC7 GPIO_ACTIVE_HIGH>;
};
wireless_bluetooth: wireless-bluetooth {
	compatible = "bluetooth-platdata";
	clocks = <&hym8563>;
	BT,reset-gpios     = <&gpio0 RK_PD0 GPIO_ACTIVE_HIGH>;
	BT,wake-gpios      = <&gpio0 RK_PC6 GPIO_ACTIVE_HIGH>;
	BT,wake_host-gpios = <&gpio0 RK_PC5 GPIO_ACTIVE_HIGH>;
};
```

### 测试指令

```
dmesg | grep -iE "ap6275|wifi"
iw dev wlan0 scan | grep SSID | head
hciconfig -a
```

## RTC (HYM8563)

### 硬件连接

```
HYM8563 ===> I2C2_M0 (地址 0x51), INT GPIO0 B0 (低有效)
32.768k 输出 ===> 供蓝牙
```

### 设备树配置

```
#ifdef FF_RTC
	hym8563: hym8563@51 {
		compatible = "haoyu,hym8563";
		reg = <0x51>;
		#clock-cells = <0>;
		clock-frequency = <32768>;
		interrupt-parent = <&gpio0>;
		interrupts = <RK_PB0 IRQ_TYPE_LEVEL_LOW>;
		wakeup-source;
		status = "okay";
	};
#endif
```

### 测试指令

```
hwclock --show && hwclock --systohc
```

## EDP0 屏 (FF_EDP0_VP1)

### 硬件连接

```
EDP 屏 ===> edp0 (hdptxphy0), edp0_in_vp1, route_edp0
背光 PWM ===> PWM14, 20kHz; EDP_BL_EN ===> PCA9555 IO0_2
屏 EN ===> PCA9555 IO0_3
触摸 (goodix-ts-edp0@5d) ===> I2C1, INT GPIO1 B2 (低有效/下降沿)
触摸供电 ===> vcc3v3_edp0_tp (PCA9554 IO0_1) / 使能 edp0_tp_en (PCA9554 IO0_2)
注意: pca9554 label 当前 SDK 源未定义 (见文首说明)
```

### 设备树配置 (精简)

```
/ {
	backlight_edp0: backlight-edp0 {
		compatible = "pwm-backlight";
		enable-gpios = <&pca9555 PCA_IO0_2 GPIO_ACTIVE_HIGH>;
		pwms = <&pwm14 0 50000 0>;
	};
	edp0_panel: edp0-panel {
		backlight = <&backlight_edp0>;
		enable-gpios = <&pca9555 PCA_IO0_3 GPIO_ACTIVE_HIGH>;
		display-timings { edp_timing0: timing0 { ... } };
	};
};
&pwm14 { status = "okay"; }
&edp0 { status = "okay"; }
&edp0_in_vp1 { status = "okay"; }
&route_edp0 { status = "okay"; }
&hdptxphy0 { status = "okay"; }
&i2c1 { goodix-ts-edp0@5d { ... interrupts = <RK_PB2 IRQ_TYPE_LEVEL_LOW>; } }
```

### 测试指令

```
cat /sys/class/drm/*/status && cat /sys/class/drm/*/modes
cat /sys/class/backlight/*/brightness
dmesg | grep -iE "edp|goodix"
```

## MIPI DSI1 屏 (FF_DSI1_VP3)

### 硬件连接

```
MIPI 屏 ===> dsi1 (mipi_dcphy1), dsi1_in_vp2, route_dsi1
背光 PWM ===> PWM3_M3 (GPIO1 A7), BL EN ===> PCA9555 IO0_6
触摸 goodix ===> I2C6_M3 地址 0x14, INT GPIO1 B5 (低有效), reset PCA9555 IO0_7
双 panel 结构: panel0 BSD1218 (70MHz) / panel1 M101014 (72.6MHz)
```

### 设备树配置 (结构)

```
&pwm3 { pinctrl-0 = <&pwm3m3_pins>; status = "okay"; }
&mipi_dcphy1 { status = "okay"; }
&dsi1_in_vp2 { status = "okay"; }
&route_dsi1 { status = "okay"; }
&dsi1 { status = "okay"; dsi1_panel: panel1@0 { ... } }
&i2c6 { goodix_ts_dsi1: goodix-ts-dsi1@14 { compatible = "goodix,gt9xxx"; ... } }
// panel init 序列 / cfg-group2 完整内容见 dtsi FF_DSI1_VP3 段
```

### 测试指令

```
cat /sys/class/drm/card*-DSI-*/status
cat /sys/class/backlight/*/brightness
cat /proc/bus/input/devices | grep -A4 goodix
```

## CAMERA (CSI2 IMX415)

### 硬件连接

```
sensor (IMX415) ===> I2C (地址 0x37), module CMK-OT2022-PX1
MCLK ===> CLK_MIPI_CAMARAOUT_M1 (mipim1_camera1_clk = GPIO3 A6)
reset ===> GPIO1 D5 (低有效)
链路 ===> csi2_dphy0 -> mipi2_csi2 -> rkcif_mipi_lvds2 -> sditf -> isp0_vir0
```

### 设备树配置 (精简)

```
imx415@37 {
	compatible = "sony,imx415";
	clocks = <&cru CLK_MIPI_CAMARAOUT_M1>;
	pinctrl-0 = <&mipim1_camera1_clk>;
	reset-gpios = <&gpio1 RK_PD5 GPIO_ACTIVE_LOW>;
	port { imx415_out: endpoint {
		remote-endpoint = <&mipidphy0_in_ucam1>;
		data-lanes = <1 2 3 4>; } };
}
&csi2_dphy0 { status = "okay"; } &mipi2_csi2 { status = "okay"; }
&rkcif_mipi_lvds2 { status = "okay"; }
&rkisp0_vir0 { status = "okay"; }
```

### 测试指令

```
dmesg | grep -iE "imx415|dphy.*match"
media-ctl -p -d /dev/media0
v4l2-ctl -d /dev/videoXX --set-fmt-video=width=3840,height=2160,pixelformat=NV12 \
	 --stream-mmap --stream-count=1 --stream-to=/tmp/f.raw
```

## GSENSOR (MC3230)

### 硬件连接

```
MC3230 (加速度计) ===> I2C4_M3 (地址 0x4c), layout 6, 轮询 30ms
```

### 设备树配置

```
#ifdef FF_GSENSOR
	mc3230: mc3230@4c {
		status = "okay";
		compatible = "gs_mc3230";
		reg = <0x4c>;
		type = <SENSOR_TYPE_ACCEL>;
		irq_enable = <0>;
		poll_delay_ms = <30>;
		layout = <6>;
	};
#endif
```

### 测试指令

```
dmesg | grep -i mc3230
ls /dev/input/                    # sensor 事件节点
```

## ES8388 音频

### 硬件连接

```
ES8388 ===> I2C7_M0 (地址 0x11), MCLK I2S0_MCLK (12.288MHz)
功放控制 SPK_CTL ===> GPIO1 C0 (高有效)
耳机检测走 ADC (saradc 4), hp-det/hp-con 已注释
注意本板 spk-con 曾踩坑: 应为 GPIO1_C0 (旧源误写 GPIO3_B7), 见根目录
mipi-dsi/sound-card 笔记
```

### 设备树配置

```
&i2c7 {
	es8388: es8388@11 {
		compatible = "everest,es8388", "everest,es8323";
		reg = <0x11>;
		assigned-clocks = <&mclkout_i2s0>;
		assigned-clock-rates = <12288000>;
	};
}
&i2s0_8ch { status = "okay"; pinctrl-0 = <&i2s0_sdi0 &i2s0_sdo0>; }

es8388_sound: es8388-sound {
	compatible = "rockchip,multicodecs-card";
	rockchip,card-name = "rockchip-es8388";
	spk-con-gpio = <&gpio1 RK_PC0 GPIO_ACTIVE_HIGH>;
	rockchip,mclk-fs = <256>;
	rockchip,cpu = <&i2s0_8ch>;
	rockchip,codec = <&es8388>;
	io-channels = <&saradc 4>;
};
```

### 测试指令

```
aplay -l
speaker-test -twav -c2 -t1
```

## CAN2

### 硬件连接

```
CAN2 ===> CAN2_M1 (can2m1_pins 组)
注意: 与 LT9211D 桥电源脚冲突时需关 (见根目录 mipi-dsi.md 方式二)
```

### 设备树配置

```
#ifdef FF_CAN2
&can2 { status = "okay"; pinctrl-0 = <&can2m1_pins>; }
#endif
```

### 测试指令

```
ip link set can2 type can bitrate 500000 && ip link set can2 up
candump can2 &
cansend can2 123#DEADBEEF
```

## UART 扩展组

### 硬件连接

```
uart0 ===> UART0_M2    uart3 ===> UART3_M2
uart4 ===> UART4_M0    uart5 ===> UART5_M1
```

### 设备树配置

```
#ifdef FF_UART
&uart0 { status = "okay"; pinctrl-0 = <&uart0m2_xfer>; }
&uart3 { status = "okay"; pinctrl-0 = <&uart3m2_xfer>; }
&uart4 { status = "okay"; pinctrl-0 = <&uart4m0_xfer>; }
&uart5 { status = "okay"; pinctrl-0 = <&uart5m1_xfer>; }
#endif
```

### 测试指令

```
ls /dev/ttyS*
cat /dev/ttyS4 &         # 对端发数据
echo test > /dev/ttyS4
```

## BP 扩展板 (FF_BP, 默认关)

### 硬件连接

```
扩展板载: 第二路 DSI0 屏 / UART4 / PCIE2_1L2 重配 / WIFI-BT 重配 /
摄像头切换 (imx415 重指 dphy0 链)
打开方式: 顶层 dts 打开 #define FF_BP
```

### 设备树配置

```
// rk3588-firefly-aio-3588sg-bp.dtsi 全文已内联于 dtsi 的 FF_BP 段:
&dsi0 { ... }  &route_dsi0 { ... }  &uart4 { ... }
&pcie2x1l2 { ... }  &vcc3v3_pcie20_1l2 { ... }
&wireless_wlan { ... }  &wireless_bluetooth { ... }
&imx415 { ... }  // 重指 csi2_dphy0 链
```

### 测试指令

```
// 打开 FF_BP 后编译烧录, 按 DSI/CAMERA/WIFI 各节指令验证
```
