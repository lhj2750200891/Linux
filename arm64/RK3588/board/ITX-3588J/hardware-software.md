# Firefly ITX-3588J 适配笔记

　　本目录三件套: hardware-software.md (本文), rk3588-firefly-itx-3588j.dts
(顶层, 宏开关), rk3588-firefly-itx-3588j.dtsi (载板全部板级内容展开, 模块
dtsi 已内联, 仅保留 #include "rk3588-firefly-common.dtsi" 基座)。

　　注意: HDMI0/HDMI1 / USB20 本体 / sdmmc 本体 / GMAC 本体等公共配置位于
rk3588-firefly-common.dtsi, 本文只记载板差异部分。

## PCA953X (IO 扩展)

### 硬件连接

```
PCA9555 (IO 扩展, 16 路) ===> I2C6_M0 (地址 0x21, 总线 400kHz)
  PCA_IO0_0 ===> 4G_PWR_EN
  PCA_IO0_3 ===> user LED
  PCA_IO0_4 ===> USB2.0 HUB reset
  PCA_IO0_5 ===> USB2.0 HOST 供电
  PCA_IO0_6 ===> USB3.0 HUB reset
  PCA_IO0_7 ===> USB3.0 供电
  PCA_IO1_2 ===> SATA0 供电
  PCA_IO1_4 ===> TypeC VBUS 5V 使能
  PCA_IO1_5 ===> SD 卡供电
```

### 设备树配置

```
&i2c6 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c6m0_xfer>;
	clock-frequency = <400000>;
#ifdef FF_PCA953X
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
power LED (WORK_LED) ===> GPIO1 B3 (高有效, 常亮)
user  LED (DIY_LED)  ===> PCA9555 IO0_3 (高有效)
```

### 设备树配置

```
#ifdef FF_LEDS
	firefly_leds: leds {
		status = "okay";
		compatible = "gpio-leds";
		pinctrl-0 = <&leds_gpio>;
		power_led: power {
			label = ":power";
			linux,default-trigger = "ir-power-click";
			default-state = "on";
			gpios = <&gpio1 RK_PB3 GPIO_ACTIVE_HIGH>;
		};
		user_led: user {
			label = ":user";
			linux,default-trigger = "ir-user-click";
			default-state = "off";
			gpios = <&pca9555 PCA_IO0_3 GPIO_ACTIVE_HIGH>;
		};
	};
#endif
```

### 测试指令

```
cat /sys/class/leds/:power/brightness
echo 255 > /sys/class/leds/:user/brightness && echo 0 > /sys/class/leds/:user/brightness
```

## SDCARD

### 硬件连接

```
SD_PWR_EN ===> PCA9555 IO1_5 (高有效)
SDMMC 本体信号走 common 公共配置
```

### 设备树配置

```
/ {
#ifdef FF_SDCARD
	vcc_sdcard_pwr_en: vcc-sdcard-pwr-en-regulator {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc_sdcard_pwr_en";
		regulator-boot-on;
		regulator-always-on;
		enable-active-high;
		gpio = <&pca9555 PCA_IO1_5 GPIO_ACTIVE_HIGH>;
	};
#endif
};
```

### 测试指令

```
lsblk
sudo fio --name=real_write --filename=./testfile --rw=write --bs=1M --size=2G --direct=1 --numjobs=1 --time_based=0 --group_reporting
sudo fio --name=real_read  --filename=./testfile --rw=read  --bs=1M --size=2G --direct=1 --numjobs=1 --time_based=0 --group_reporting
```

## RECOVERY-KEY

### 硬件连接

```
Recovery 按键 ===> ADC 通道 (saradc), 按下阈值 10mV, 键值 F12
```

### 设备树配置

```
#ifdef FF_RECOVERY_KEY
&adc_keys {
	recovery-key {
		label = "F12";
		linux,code = <KEY_F12>;
		press-threshold-microvolt = <10000>;
	};
};
#endif
```

### 测试指令

```
evtest                     # 选 adc-keys 设备, 按键可见 KEY_F12
cat /proc/bus/input/devices | grep -A4 adc-keys
```

## RTC (HYM8563)

### 硬件连接

```
HYM8563 ===> I2C6_M0 (地址 0x51)
RTC_INT ===> GPIO0 B0 (低有效)
32.768k 输出 ===> 同时供蓝牙时钟 (wireless-bluetooth clocks)
```

### 设备树配置

```
#ifdef FF_RTC
	hym8563: hym8563@51 {
		status = "okay";
		compatible = "haoyu,hym8563";
		reg = <0x51>;
		#clock-cells = <0>;
		clock-frequency = <32768>;
		clock-output-names = "hym8563";
		pinctrl-0 = <&hym8563_int>;
		interrupt-parent = <&gpio0>;
		interrupts = <RK_PB0 IRQ_TYPE_LEVEL_LOW>;
		wakeup-source;
	};
#endif
```

### 测试指令

```
hwclock --show             # 读取
hwclock --systohc          # 系统时间写入 RTC
dmesg | grep -i hym8563
```

## GMAC (GMAC0/GMAC1)

### 硬件连接

```
GMAC0/1 本体 (phy/时钟) 走 common 公共配置
板级差异: TX/RX 引脚驱动强度调为 level_6 (长走线增强驱动)
  gmac0: txd0/1 = GPIO2 B6/B7, rxd2/3 = GPIO2 A6/A7, txd2/3 = GPIO2 B1/B2
  gmac1: txd0/1 = GPIO3 B3/B4, rxd2/3 = GPIO3 A2/A3, txd2/3 = GPIO3 A0/A1
```

### 设备树配置

```
#ifdef FF_GMAC0
&gmac0_tx_bus2 {
	rockchip,pins =
		<2 RK_PB6 1 &pcfg_pull_up_drv_level_6>,   // gmac0_txd0
		<2 RK_PB7 1 &pcfg_pull_up_drv_level_6>,   // gmac0_txd1
		<2 RK_PC0 1 &pcfg_pull_none>;             // gmac0_txen
};
&gmac0_rgmii_bus { /* rxd2/3, txd2/3 同理 level_6 */ };
#endif
```

### 测试指令

```
ip link                    # eth0/eth1
ethtool eth0               # 协商速率 (插线应 1000M)
ping -I eth0 <网关>
```

## USB3.0 (USB30)

### 硬件连接

```
USB3.0 (usbdrd3_1, host 模式) ===> usbdp_phy1 + u2phy1_otg
5V 供电 ===> vcc5v0_usb30 (PCA9555 IO0_7)
USB3 HUB reset ===> vcc_hub3_reset (PCA9555 IO0_6)
```

### 设备树配置

```
#ifdef FF_USB30
&usbdrd3_1 { status = "okay"; };
&usbdrd_dwc3_1 { status = "okay"; dr_mode = "host"; };
&u2phy1 { status = "okay"; };
&u2phy1_otg { status = "okay"; phy-supply = <&vcc5v0_usb30>; };
&usbdp_phy1 { status = "okay"; };
#endif
```

### 测试指令

```
lsusb && lsblk
dmesg | grep -iE "dwc3|xhci"
```

## USB2.0 (HOST0/HOST1)

### 硬件连接

```
USB2.0 HUB reset ===> vcc_hub_reset (PCA9555 IO0_4)
USB2.0 HOST 供电 ===> vcc5v0_usb20_host0, GPIO 覆盖为 PCA9555 IO0_5
本体 (ehci/ohci) 走 common 公共配置
```

### 设备树配置

```
#ifdef FF_USB20_HOST1
	vcc_hub_reset: vcc-hub-reset-regulator {
		compatible = "regulator-fixed";
		regulator-always-on;
		enable-active-high;
		gpio = <&pca9555 PCA_IO0_4 GPIO_ACTIVE_HIGH>;
	};
#endif

#if defined(FF_USB20_HOST0) || defined(FF_USB20_HOST1)
&vcc5v0_usb20_host0 {
	gpio = <&pca9555 PCA_IO0_5 GPIO_ACTIVE_HIGH>;
};
#endif
```

### 测试指令

```
lsusb
dmesg | grep -iE "ehci|ohci|hub"
```

## TYPEC (全功能, DP altmode)

### 硬件连接

```
fusb302 (PD 控制器) ===> I2C6_M0 (地址 0x22)
INT ===> GPIO0 D3 (低有效)
VBUS 5V 使能 ===> PCA9555 IO1_4
SBU1/SBU2 (DP aux 切换) ===> GPIO4 A6 / GPIO4 A7
DP 走 dp0 (vp2), USB 走 usbdrd3_0 (otg + role switch)
```

### 设备树配置

```
&i2c6 {
	usbc0: fusb302@22 {
		status = "okay";
		compatible = "fcs,fusb302";
		reg = <0x22>;
		interrupts = <RK_PD3 IRQ_TYPE_LEVEL_LOW>;
		vbus-supply = <&vbus5v0_typec_pwr_en>;
		usb_con: connector {
			compatible = "usb-c-connector";
			data-role = "dual";
			power-role = "dual";
			try-power-role = "sink";
			sink-pdos = <PDO_FIXED(5000, 1000, PDO_FIXED_USB_COMM)>;
			source-pdos = <PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)>;
			altmodes { /* svid 0xff01 DP */ };
			ports { /* orientation_switch / dp_altmode_mux */ };
		};
	};
};

&usbdp_phy0 { orientation-switch; mode-switch; svid = <0xff01>;
	sbu1-dc-gpios = <&gpio4 RK_PA6 GPIO_ACTIVE_HIGH>;
	sbu2-dc-gpios = <&gpio4 RK_PA7 GPIO_ACTIVE_HIGH>; };
&dp0 { status = "okay"; }  &dp0_in_vp2 { status = "okay"; }
&usbdrd_dwc3_0 { dr_mode = "otg"; usb-role-switch; }
```

### 测试指令

```
ls /sys/class/typec/                       # port0, 看当前 data_role/power_role
cat /sys/class/drm/*/status                # 插 DP 转接后 DP 出现
dmesg | grep -iE "fusb302|typec|pd"
lsusb && ip addr                           # host/device 角色切换验证
```

## ES8388 音频

### 硬件连接

```
ES8388 (codec) ===> I2C3 (地址 0x11)
MCLK ===> I2S0_MCLK (12.288MHz)
耳机检测 HP_DET_L ===> GPIO1 C4 (低有效)
功放控制 SPK_CTL_H (XA9221) ===> GPIO3 B2
耳机功放 PHONE_CTL ===> GPIO4 B0
```

### 设备树配置

```
#ifdef FF_ES8388
	es8388_sound: es8388-sound {
		status = "okay";
		compatible = "rockchip,multicodecs-card";
		rockchip,card-name = "rockchip-es8388";
		hp-det-gpio = <&gpio1 RK_PC4 GPIO_ACTIVE_LOW>;
		spk-con-gpio = <&gpio3 RK_PB2 GPIO_ACTIVE_HIGH>;
		hp-con-gpio = <&gpio4 RK_PB0 GPIO_ACTIVE_HIGH>;
		rockchip,mclk-fs = <256>;
		rockchip,cpu = <&i2s0_8ch>;
		rockchip,codec = <&es8388>;
		ff-separate-headphone-jack;
		pinctrl-0 = <&hp_det>;
	};
#endif

&i2c3 {
	es8388: es8388@11 {
		compatible = "everest,es8388", "everest,es8323";
		reg = <0x11>;
		assigned-clocks = <&mclkout_i2s0>;
		assigned-clock-rates = <12288000>;
	};
}
```

### 测试指令

```
aplay -l                       # rockchip-es8388 声卡
speaker-test -twav -c2 -t1     # 喇叭+耳机
arecord -f S16_LE -r 44100 -d 3 /tmp/rec.wav && aplay /tmp/rec.wav
```

## WIFI-BT (AP6275P)

### 硬件连接

```
WIFI (AP6275P) ===> pcie2x1l0, WIFI_PERST GPIO1 B4 (高有效)
WIFI_REG_ON ===> GPIO0 C4
BT 走 UART6_M1: BT_REG_ON GPIO0 C6 / BT_WAKE GPIO0 C5 / BT_HOST_WAKE GPIO0 A0
BT 32.768k 时钟 ===> hym8563 输出
BT RTS ===> GPIO1 A2 (rts_gpio 态切换)
```

### 设备树配置

```
&uart6 { status = "okay"; pinctrl-0 = <&uart6m1_xfer &uart6m1_ctsn>; }
&combphy1_ps { status = "okay"; }
&pcie2x1l0 { status = "okay";
	reset-gpios = <&gpio1 RK_PB4 GPIO_ACTIVE_HIGH>;
	rockchip,skip-scan-in-resume; }

wireless_wlan: wireless-wlan {
	compatible = "wlan-platdata";
	wifi_chip_type = "ap6275p";
	WIFI,poweren-gpios = <&gpio0 RK_PC4 GPIO_ACTIVE_HIGH>;
};
wireless_bluetooth: wireless-bluetooth {
	compatible = "bluetooth-platdata";
	clocks = <&hym8563>;
	BT,power-gpios     = <&gpio0 RK_PC6 GPIO_ACTIVE_HIGH>;
	BT,wake-gpios      = <&gpio0 RK_PC5 GPIO_ACTIVE_HIGH>;
	BT,wake_host-gpios = <&gpio0 RK_PA0 GPIO_ACTIVE_HIGH>;
};
```

### 测试指令

```
dmesg | grep -iE "ap6275|wifi|pcie2x1l0"
ip link set wlan0 up && iw dev wlan0 scan | grep SSID | head
hciconfig -a && hcitool scan
```

## 4G/5G 模组

### 硬件连接

```
模组供电 3.8V ===> vcc3v8_4g (PCA9555 IO0_0, 12V 输入)
模组走 PCIe ===> pcie2x1l1 + combphy2_psu
BT SCO 通话音频 ===> i2s1_8ch (i2s1m0 组) + bt_sco 虚拟声卡 (dsp_a)
```

### 设备树配置

```
/ {
	vcc3v8_4g: vcc3v8-4g {
		compatible = "regulator-fixed";
		regulator-min-microvolt = <3800000>;
		regulator-max-microvolt = <3800000>;
		enable-active-high;
		gpio = <&pca9555 PCA_IO0_0 GPIO_ACTIVE_HIGH>;
		vin-supply = <&vcc12v_dcin>;
	};
	bt_sco: bt-sco { compatible = "delta,dfbmcs320"; #sound-dai-cells = <1>; };
	bt_sound: bt-sound { /* simple-audio-card dsp_a, cpu i2s1_8ch */ };
};

&i2s1_8ch { status = "okay"; pinctrl-0 = <&i2s1m0_lrck &i2s1m0_sclk &i2s1m0_sdi0 &i2s1m0_sdo0>; }
&combphy2_psu { status = "okay"; }
&pcie2x1l1 { status = "okay"; }
```

### 测试指令

```
lspci                        # 4G/5G 模组可见
ls /dev/mhi* /dev/wwan* 2>/dev/null; dmesg | grep -i mhi
aplay -l                     # rockchip,bt 声卡 (SCO)
```

## FAN

### 硬件连接

```
风扇 PWM ===> PWM15_M2 (pwm15m2_pins 组), 20kHz
风扇供电 ===> 12V (vcc12v_dcin)
调速曲线 ===> 50~70 度五档
```

### 设备树配置

```
#ifdef FF_FAN
	fan: pwm-fan {
		status = "okay";
		compatible = "pwm-fan";
		fan-supply = <&vcc12v_dcin>;
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
cat /sys/class/hwmon/*/pwm1
cat /sys/kernel/debug/pwm     # pwm15 占空比
```

## RS232 / RS485

### 硬件连接

```
RS232 ===> UART0_M2 (uart0m2_xfer)
RS485 ===> UART1 (复用组走 common 默认)
```

### 设备树配置

```
#ifdef FF_RS232
&uart0 { pinctrl-0 = <&uart0m2_xfer>; status = "okay"; };
#endif
#ifdef FF_RS485
&uart1 { status = "okay"; };
#endif
```

### 测试指令

```
cat /dev/ttyS0 &      # RS232 对端发数据
echo hello > /dev/ttyS0
cat /dev/ttyS1 &      # RS485
echo test  > /dev/ttyS1
```

## CAN1

### 硬件连接

```
CAN1 ===> CAN1_M1 (can1m1_pins), 时钟 200MHz
```

### 设备树配置

```
#ifdef FF_CAN1
&can1 {
	status = "okay";
	assigned-clocks = <&cru CLK_CAN1>;
	assigned-clock-rates = <200000000>;
	pinctrl-0 = <&can1m1_pins>;
};
#endif
```

### 测试指令

```
ip link set can1 type can bitrate 500000 && ip link set can1 up
candump can1 &
cansend can1 123#DEADBEEF
```

## VGA (DP1 + IT6516)

### 硬件连接

```
VGA 经 IT6516 桥 (DP1 -> VGA)
HPD ===> GPIO1 A4 (VGA_HPDIN_L)
usbdp_phy1 lane 复用: lane2/3 给 DP1, lane0/1 保持 USB3 (rockchip,dp-lane-mux = <2 3>)
VGA 音频 ===> dp1_sound (spdif_tx5 -> dp1)
```

### 设备树配置

```
&dp1_in_vp2 { status = "okay"; }
&dp1 {
	status = "okay";
	hpd-gpios = <&gpio1 RK_PA4 GPIO_ACTIVE_HIGH>;
	pinctrl-0 = <&dp1_hpd>;
}
&usbdp_phy1 { status = "okay"; rockchip,dp-lane-mux = <2 3>; }
&spdif_tx5 { status = "okay"; }
```

### 测试指令

```
cat /sys/class/drm/*/status      # 插 VGA 转 DP 线后 DP 出现
xrandr                           # 列出输出
aplay -l | grep dp1              # rockchip-dp1 声卡
```

## HDMI-RX (HDMIIN)

### 硬件连接

```
HDMIIN 检测 HDMIIRX_DET_L ===> GPIO1 D5 (低有效)
音频 ===> i2s7_8ch (hdmirx 作 bitclock/frame master)
预留 256MB CMA (reserved-memory cma, 供 hdmirx-controller@fdee0000)
```

### 设备树配置

```
#ifdef FF_HDMIRX
reserved-memory {
	cma {
		compatible = "shared-dma-pool";
		reusable;
		reg = <0x0 (256 * 0x100000) 0x0 (256 * 0x100000)>;
		linux,cma-default;
	};
};
&hdmirx_ctrler {
	status = "okay";
	hpd-trigger-level = <1>;
	hdmirx-det-gpios = <&gpio1 RK_PD5 GPIO_ACTIVE_LOW>;
	pinctrl-0 = <&hdmim1_rx &hdmirx_det>;
}
&i2s7_8ch { status = "okay"; }
#endif
```

### 测试指令

```
ls /dev/video* | head            # hdmirx 节点
v4l2-ctl -d /dev/videoXX --all   # 看输入时序 (插 HDMI 源)
dmesg | grep -i hdmirx
```

## SW3203

### 硬件连接

```
SW3203 (ismartware) ===> I2C6_M0 (地址 0x3c), 启动延时 2.5s
```

### 设备树配置

```
#ifdef FF_SW3203
	sw3203@3c {
		status = "okay";
		compatible = "ismartware,sw3203";
		reg = <0x3c>;
		startup-delay-ms = <2500>;
		reg-0x20 = <0x05>;
	};
#endif
```

### 测试指令

```
dmesg | grep -i sw3203
i2cdetect -y 6                   # 0x3c 应被内核占用 (UU)
```

## SATA0 (默认关)

### 硬件连接

```
SATA0 供电 ===> vcc3v3_sata0 (PCA9555 IO1_2)
与 FF_PCIE2_1L2 复用, 默认 //#define FF_SATA0
```

### 设备树配置

```
#ifdef FF_SATA0
&vcc3v3_sata0 {
	gpio = <&pca9555 PCA_IO1_2 GPIO_ACTIVE_HIGH>;
};
#endif
```

### 测试指令

```
lsblk                       # SATA 盘可见
dmesg | grep -i ata
```

## CAMERA (CSI0 IMX415)

### 硬件连接

```
I2C (i2c3m0) ===> I2C3_SCL_M0_MIPI GPIO1 C0 / I2C3_SDA_M0_MIPI GPIO1 C1
sensor (IMX415) 地址 0x37
MCLK ===> MIPI_CAM3_CLKOUT = GPIO1 D6 (mipim0_camera3_clk)
PDN ===> MIPI_CAM3_PDN_L = GPIO1 A7
RESET ===> RESET0_CAM = GPIO1 B0
PWREN ===> CAM3 GPIO1 B2 / CAM4 GPIO1 B1
差分对 ===> MIPI_CSI0_RX_D0~D3/CLK0~CLK1
链路 ===> csi2_dphy0 -> mipi2_csi2 -> rkcif_mipi_lvds2 -> rkcif_mipi_lvds2_sditf -> isp0_vir0
```

### 设备树配置 (精简)

```
&i2c3 {
	status = "okay";
	IMX415: imx415@37 {
		compatible = "sony,imx415";
		reg = <0x37>;
		clocks = <&cru CLK_MIPI_CAMARAOUT_M3>;
		pinctrl-0 = <&mipim0_camera3_clk>;
		port {
			imx415_out: endpoint {
				remote-endpoint = <&mipidphy0_in_ucam1>;
				data-lanes = <1 2 3 4>;
			};
		};
	};
};
&csi2_dphy0_hw { status = "okay"; }
&csi2_dphy0 { status = "okay"; }
&mipi2_csi2 { status = "okay"; }
&rkcif_mipi_lvds2 { status = "okay"; }
&rkisp0 { status = "okay"; } &isp0_mmu { status = "okay"; }
&rkisp0_vir0 { status = "okay"; }
&rkcif { status = "okay"; } &rkcif_mmu { status = "okay"; }
```

### 测试指令

```
dmesg | grep -iE "imx415|dphy.*match"
media-ctl -p -d /dev/media0
v4l2-ctl -d /dev/videoXX --set-fmt-video=width=3840,height=2160,pixelformat=NV12 \
	 --stream-mmap --stream-count=1 --stream-to=/tmp/f.raw
```

## DSI 屏 (FF_DSI1_V3 默认 / FF_DSI0_V3 备选)

### 硬件连接

```
两座互斥宏选择 (FF_DSI0_V3 XOR FF_DSI1_V3):

DSI0 座 (FF_DSI0_V3):
  背光 PWM ===> PWM12_M1 + BL EN GPIO2 C4 (高有效)
  PHY/路由 ===> mipi_dcphy0, dsi0_in_vp3, route_dsi0 (vp3)
  触摸 ===> I2C1_M2: goodix@0x14 (GT9xxx) / hxchipset@0x48
           (himax RST GPIO3 C1 / INT GPIO3 C0)

DSI1 座 (FF_DSI1_V3, 默认):
  背光 PWM ===> PWM11 + BL EN GPIO4 C6 (高有效)
  PHY/路由 ===> mipi_dcphy1, dsi1_in_vp3, route_dsi1 (vp3)
  触摸 ===> I2C6: goodix_ts1@0x14 / hxchipset1@0x48
           (himax RST GPIO2 B5 / INT GPIO3 A6)

屏 (双 panel 结构, 同 AIO-3588L):
  panel0 = BSD1218 (70MHz, FF 98 81 init 序列)
  panel1 = M101014 (72.6MHz, hs14/hbp26/hfp32/vs8/vbp20/vfp80,
           init 仅 11/29 Sleep Out/Display On)
```

### 设备树配置 (结构)

```
&dsi1 {
	status = "okay";
	//firefly-check;
	dsi1_panel: panel1@0 {
		status = "okay";
		compatible = "simple-panel-dsi";
		backlight = <&backlight_1>;
		dsi,flags = <(MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST |
		              MIPI_DSI_MODE_LPM | MIPI_DSI_MODE_NO_EOT_PACKET)>;
		dsi,format = <MIPI_DSI_FMT_RGB888>;
		dsi,lanes = <4>;
		panel-init-sequence = [ ... ];        // 完整序列见 dtsi
		rockchip,touch-nodes = <&goodix_ts1>;
	};
};

&i2c6 {
	goodix_ts1: goodix_ts@14 { compatible = "goodix,gt9xxx"; reg = <0x14>; ... };
	hxchipset1: hxchipset@48 { compatible = "himax,hxcommon"; reg = <0x48>; ... };
};
// 完整内容 (init 序列/cfg-group2/时序) 见 rk3588-firefly-itx-3588j.dtsi 对应宏段
```

### 测试指令

```
cat /sys/class/drm/card*-DSI-*/status && cat /sys/class/drm/card*-DSI-*/modes
cat /sys/class/backlight/*/brightness
cat /proc/bus/input/devices | grep -A4 -iE "goodix|himax"
dmesg | grep -iE "dsi|panel|goodix|himax"
```
