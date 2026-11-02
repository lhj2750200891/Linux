# Firefly AIO-3588JD4 适配笔记

　　本目录三件套: hardware-software.md (本文), rk3588-firefly-aio-3588jd4.dts
(顶层, 宏开关), rk3588-firefly-aio-3588jd4.dtsi (载板全部板级内容展开,
模块 dtsi 已内联, 仅保留 #include "rk3588-firefly-core-3588jd4.dtsi" 核心
板基座)。

　　注意: HDMI0 / GMAC0/1 / RTC / RECOVERY_KEY / USB20_HOST0 本体 / 看门狗
核心 (WDT_CORE) 等核心板公共配置位于 rk3588-firefly-core-3588jd4.dtsi,
本文只记载板差异部分。

## PCA9555 (IO 扩展)

### 硬件连接

```
PCA9555 (IO 扩展, 16 路) ===> I2C3_M2 (地址 0x21)
载板多数外设电源/LED 挂 PCA9555:
  PCA_IO0_2 ===> USB30 vcc5v0_usb30 / USB20_HOST0 电源
  PCA_IO0_3 ===> user LED (黄)
  PCA_IO0_4 ===> vcc3v3_pcie3x2_1 (WIFI 供电)
  PCA_IO0_5 ===> CAM0 reset (低有效)
  PCA_IO0_6 ===> CAM1 reset (低有效)
  PCA_IO1_2 ===> WIFI host_wake_irq
  PCA_IO1_3 ===> 耳机功放控制 (hp-con)
  PCA_IO1_4 ===> vcc3v3_pcie20_1l2 (M.2 供电)
```

### 设备树配置

```
&i2c3 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c3m2_xfer>;

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
gpiodetect                      # 能看到 pca9555 对应的 gpiochip
gpioinfo $(gpiodetect | grep -v gpiochip0 | awk '{print $2}')
echo 200 > /sys/class/gpio/export && cat /sys/class/gpio/gpio200/value
```

## SDCARD

### 硬件连接

```
SD_PWR_EN ===> GPIO1 A7 (vcc_sdcard_pwr_en, 高有效)
SDMMC 本体信号 (CLK/CMD/D0-3/DET) 走核心板公共配置 (core-3588jd4.dtsi)
```

### 设备树配置

```
/ {
#ifdef FF_SDCARD
	vcc_sdcard_pwr_en: vcc-sdcard-pwr-en-regulator {
		compatible = "regulator-fixed";
		regulator-name = "vcc_sdcard_pwr_en";
		regulator-boot-on;
		regulator-always-on;
		enable-active-high;
		gpio = <&gpio1 RK_PA7 GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
#endif
};
```

### 测试指令

```
lsblk   # 能看到sd卡即可
# 可以切换到sd目录中使用下面的指令进行压测
sudo fio --name=real_write --filename=./testfile --rw=write --bs=1M --size=2G --direct=1 --numjobs=1 --time_based=0 --group_reporting
# 读取测试
sudo fio --name=real_read --filename=./testfile --rw=read --bs=1M --size=2G --direct=1 --numjobs=1 --time_based=0 --group_reporting
```

## LED

### 硬件连接

```
user LED (黄) ===> PCA9555 IO0_3 (高有效)
```

### 设备树配置

```
#ifdef FF_LED
	firefly_leds: leds {
		compatible = "gpio-leds";
		status = "okay";
		user_led: user {
			label = ":user";
			gpios = <&pca9555 PCA_IO0_3 GPIO_ACTIVE_HIGH>; //yellow led
			default-state = "off";
		};
	};
#endif
```

### 测试指令

```
echo 255 > /sys/class/leds/:user/brightness    # 亮
echo 0   > /sys/class/leds/:user/brightness    # 灭
cat /sys/class/leds/:user/brightness
```

## FAN (风扇)

### 硬件连接

```
风扇 PWM ===> PWM5_M1 (pwm5m1_pins 组)
风扇供电 ===> vcc5v0_sys
调速曲线 ===> rockchip,temp-trips 50~70 度五档
```

### 设备树配置

```
#ifdef FF_FAN
	fan: pwm-fan {
		compatible = "pwm-fan";
		#cooling-cells = <2>;
		fan-supply = <&vcc5v0_sys>;
		pwms = <&pwm5 0 50000 0>;
		cooling-levels = <50 50 100 150 200 255>;
		rockchip,temp-trips = <
			50000   1
			55000   2
			60000   3
			65000   4
			70000   5
		>;
	};
#endif

#ifdef FF_FAN
&pwm5 {
	pinctrl-0 = <&pwm5m1_pins>;
	status = "okay";
};
#endif
```

### 测试指令

```
cat /sys/class/thermal/thermal_zone*/temp     # 看温度
cat /sys/class/hwmon/*/pwm1                   # 看风扇档位 (随温度自动)
echo 0 > /sys/class/hwmon/*/pwm1_enable       # 手动模式 (按需)
cat /sys/kernel/debug/pwm                     # 看 pwm5 占空比
```

## USB3.0 (HOST0/HOST1)

### 硬件连接

```
HOST0: TypeC0 转 TypeA (上) ===> usbdrd3_0 + u2phy0_otg (vbus5v0_typec0 GPIO1 A3)
HOST1: TypeC1 转 TypeA (下) + USB2.0 HUB ===> usbdrd3_1 + u2phy1_otg
两路 5V 供电 ===> vcc5v0_usb30 (PCA9555 IO0_2)
```

### 设备树配置

```
#ifdef FF_USB30_HOST0
&usbdrd3_0 { status = "okay"; };
&usbdrd_dwc3_0 { dr_mode = "host"; status = "okay"; };
&u2phy0 { status = "okay"; };
&u2phy0_otg { phy-supply = <&vcc5v0_usb30>; status = "okay"; };
&usbdp_phy0 { status = "okay"; };
#endif

#ifdef FF_USB30_HOST1
&usbdrd3_1 { status = "okay"; };
&usbdrd_dwc3_1 { dr_mode = "host"; status = "okay"; };
&u2phy1 { status = "okay"; };
&u2phy1_otg { phy-supply = <&vcc5v0_usb30>; status = "okay"; };
&usbdp_phy1 { status = "okay"; };
#endif
```

### 测试指令

```
lsusb                       # 插 U 盘可见设备
lsblk                       # U 盘出块设备
dmesg | grep -iE "dwc3|usb" # 枚举日志
```

## USB2.0 (HOST0)

### 硬件连接

```
USB2.0 HOST0 供电 ===> vcc5v0_usb20_host0, GPIO 覆盖为 PCA9555 IO0_2
USB2.0 HOST0 本体 (ehci/ohci) 走核心板公共配置
```

### 设备树配置

```
#ifdef FF_USB20_HOST0
&vcc5v0_usb20_host0 {
	status = "okay";
	gpio = <&pca9555 PCA_IO0_2 GPIO_ACTIVE_HIGH>;
};
#endif
```

### 测试指令

```
lsusb
dmesg | grep -iE "ehci|ohci"
```

## WIFI-BT (RTL8852BE)

### 硬件连接

```
WIFI 模组 (RTL8852BE, M.2/PCIe) ===> pcie3x4
WIFI 供电 ===> vcc3v3_pcie3x2_1 (PCA9555 IO0_4)
host_wake_irq ===> PCA9555 IO1_2
W_DISABLE ===> GPIO0 D3 (gpio-hog 拉低使能)
注意: WIFI 占用 pcie3x4, 载板把 pcie3x2 disabled
```

### 设备树配置

```
#ifdef FF_WIFI_RTL8852BE
	wireless_wlan: wireless-wlan {
		compatible = "wlan-platdata";
		wifi_chip_type = "rtl8852be";
		WIFI,host_wake_irq = <&pca9555 PCA_IO1_2 GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
#endif

&gpio0 {
	wifi_wdisable_gpio: wifi-wdisable-gpio {
		gpio-hog;
		gpios = <RK_PD3 GPIO_ACTIVE_HIGH>;
		output-low;
		line-name = "wifi-wdisable";
	};
};

#ifdef FF_WIFI_RTL8852BE
&vcc3v3_pcie3x2_0 { status = "disabled"; };
&pcie3x2 { status = "disabled"; };
&pcie3x4 { status = "okay"; };
&vcc3v3_pcie3x2_1 {
	gpio = <&pca9555 PCA_IO0_4 GPIO_ACTIVE_HIGH>;
	startup-delay-us = <5000>;
	status = "okay";
};
#endif
```

### 测试指令

```
dmesg | grep -iE "8852|rtw|wifi"
ip link set wlan0 up && iw dev wlan0 scan | grep SSID | head
nmcli dev wifi connect <SSID> password <pwd>
hciconfig -a          # 蓝牙
```

## PCIE (M.2, PCIE2_1L2)

### 硬件连接

```
PCIE2_1L2 (M.2 槽) ===> pcie2x1l2, reset GPIO4 A3 (高有效)
槽供电 ===> vcc3v3_pcie20_1l2 (PCA9555 IO1_4)
与 SATA0 复用 (FF_SATA0 互斥)
```

### 设备树配置

```
#if defined(FF_PCIE2_1L2) && !defined(FF_SATA0)
&vcc3v3_pcie20_1l2 {
	gpio = <&pca9555 PCA_IO1_4 GPIO_ACTIVE_HIGH>;
};
&pcie2x1l2 {
	reset-gpios = <&gpio4 RK_PA3 GPIO_ACTIVE_HIGH>;
};
#endif
```

### 测试指令

```
lspci                          # 插 NVME 可见
lsblk                          # NVME 出块设备
dmesg | grep -i pcie
```

## CAN (CAN1)

### 硬件连接

```
CAN1 ===> CAN1_M1 (can1m1_pins 组), 时钟 200MHz
```

### 设备树配置

```
#ifdef FF_CAN
&can1 {
	status = "okay";
	assigned-clocks = <&cru CLK_CAN1>;
	assigned-clock-rates = <200000000>;
	pinctrl-names = "default";
	pinctrl-0 = <&can1m1_pins>;
};
#endif
```

### 测试指令

```
ip link set can1 down
ip link set can1 type can bitrate 500000
ip link set can1 up
candump can1 &                 # 另一终端
cansend can1 123#DEADBEEF
```

## RS485 (UART6)

### 硬件连接

```
RS485 ===> UART6_M1 (uart6m1_xfer 组)
```

### 设备树配置

```
#ifdef FF_RS485
&uart6 {
	pinctrl-0 = <&uart6m1_xfer>;
	status = "okay";
};
#endif
```

### 测试指令

```
stty -F /dev/ttyFIQ0 raw speed 115200   # 设备名以 /dev/tty* 实际为准
cat /dev/ttyS6 &                        # 另一端发数据
echo test > /dev/ttyS6
```

## RS232 (UART1)

### 硬件连接

```
RS232 ===> UART1_M1 (uart1m1_xfer 组)
```

### 设备树配置

```
#ifdef FF_RS232
&uart1 {
	pinctrl-0 = <&uart1m1_xfer>;
	status = "okay";
};
#endif
```

### 测试指令

```
cat /dev/ttyS1 &                 # 对端发数据可见
echo hello > /dev/ttyS1
```

## WATCHDOG (PC9202 基座)

### 硬件连接

```
PC9202 (外部看门狗) ===> I2C4_M1 (地址 0x3c)
WD-EN ===> GPIO0 C4 (高有效)
```

### 设备树配置

```
#ifdef FF_WDT_BASE
&i2c4 {
	status = "okay";
	pinctrl-0 = <&i2c4m1_xfer>;
	pc9202@3c {
		status = "okay";
		compatible = "firefly,pc9202";
		reg = <0x3c>;
		index = <1>;
		pinctrl-names = "default";
		pinctrl-0 = <&wdt_en_base>;
		wd-en-gpio = <&gpio0 RK_PC4 GPIO_ACTIVE_HIGH>;
		driver-names = "wdt_base";
	};
};
#endif
```

### 测试指令

```
ls /dev/watchdog*
wdctl /dev/watchdog1            # 看驱动信息 (节点号以实际为准)
# 喂狗测试: 写入后停喂等复位
```

## ES8388 音频

### 硬件连接

```
ES8388 (codec) ===> I2C6 (地址 0x11)
MCLK ===> I2S0_MCLK (mclkout_i2s0, 12.288MHz)
I2S ===> I2S0 (LRCK/SCLK/SDI0/SDO0)
耳机检测 ===> GPIO2 C3 (hp-det, 高有效)
耳机功放控制 ===> PCA9555 IO1_3
```

### 设备树配置

```
#ifdef FF_CODEC_ES8388
	es8388_sound: es8388-sound {
		status = "okay";
		compatible = "rockchip,multicodecs-card";
		rockchip,card-name = "rockchip-es8388";
		hp-det-gpio = <&gpio2 RK_PC3 GPIO_ACTIVE_HIGH>;
		hp-con-gpio = <&pca9555 PCA_IO1_3 GPIO_ACTIVE_HIGH>;
		io-channels = <&saradc 6>;
		rockchip,format = "i2s";
		rockchip,mclk-fs = <256>;
		rockchip,cpu = <&i2s0_8ch>;
		rockchip,codec = <&es8388>;
		rockchip,audio-routing =
			"Headphone", "LOUT1",
			"Headphone", "ROUT1",
			"Speaker", "LOUT2",
			"Speaker", "ROUT2",
			...;
		pinctrl-0 = <&hp_det>;
	};
#endif

&i2c6 {
	es8388: es8388@11 {
		compatible = "everest,es8388", "everest,es8323";
		reg = <0x11>;
		clocks = <&mclkout_i2s0>;
		assigned-clocks = <&mclkout_i2s0>;
		assigned-clock-rates = <12288000>;
		pinctrl-0 = <&i2s0_mclk>;
	};
}

&i2s0_8ch {
	status = "okay";
	pinctrl-0 = <&i2s0_lrck &i2s0_sclk &i2s0_sdi0 &i2s0_sdo0>;
};
```

### 测试指令

```
aplay -l                        # 应见 rockchip-es8388 声卡
speaker-test -twav -c2 -t1      # 唱调
arecord -D hw:1,0 -f S16_LE -r 44100 -d 3 /tmp/rec.wav && aplay /tmp/rec.wav
```

## CAMERA (IMX415, CAM0/CAM1 二选一)

### 硬件连接

```
载板 CAM0/CAM1 二选一 (dtsi 宏 CAM0_OR_CAM1, 默认 1 = CAM0):
CAM 选择切换 ===> GPIO3 C1 (cam0_cam1_switch)

CAM0 (默认):
  sensor (IMX415) ===> I2C6 (地址 0x37)
  MCLK ===> CLK_MIPI_CAMARAOUT_M1 (mipim1_camera1_clk = GPIO3_A6)
  power ===> GPIO3 D5
  reset ===> PCA9555 IO0_5 (低有效)
  链路 ===> csi2_dphy0 -> mipi2_csi2 -> rkcif_mipi_lvds2 -> isp0_vir2

CAM1:
  sensor (IMX415) ===> I2C6 (地址 0x37)
  MCLK ===> CLK_MIPI_CAMARAOUT_M0 (mipim0_camera0_clk = GPIO4_B1)
  power ===> GPIO1 D5
  reset ===> PCA9555 IO0_6 (低有效)
  链路 ===> csi2_dphy3 -> mipi4_csi2 -> rkcif_mipi_lvds4 -> isp0_vir2
```

### 设备树配置 (CAM0 分支精简)

```
#define CAM0_OR_CAM1 1          // 1=CAM0, 0=CAM1

/ {
	cam0_cam1_switch: cam0-cam1-switch {
		compatible = "regulator-fixed";
		regulator-name = "cam0_cam1_switch";
		enable-active-high;
		gpio = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;
	};
};

&i2c6 {
	imx415: imx415@37 {
		compatible = "sony,imx415";
		reg = <0x37>;
		clocks = <&cru CLK_MIPI_CAMARAOUT_M1>;
		pinctrl-0 = <&mipim1_camera1_clk>;
		power-gpios = <&gpio3 RK_PD5 GPIO_ACTIVE_HIGH>;
		reset-gpios = <&pca9555 PCA_IO0_5 GPIO_ACTIVE_LOW>;
		port {
			imx415_out0: endpoint {
				remote-endpoint = <&mipidphy0_in_ucam1>;
				data-lanes = <1 2 3 4>;
			};
		};
	};
};

&csi2_dphy0 { status = "okay"; }        // -> mipi2_csi2 -> rkcif_mipi_lvds2
&csi2_dphy0_hw { status = "okay"; }
&mipi2_csi2 { status = "okay"; }
&rkcif_mipi_lvds2 { status = "okay"; }
&rkcif { status = "okay"; }  &rkcif_mmu { status = "okay"; }
&rkisp0 { status = "okay"; } &isp0_mmu { status = "okay"; }
&rkisp0_vir2 { status = "okay"; }       // sditf -> isp0_vir2
```

### 测试指令

```
dmesg | grep -iE "imx415|dphy.*match"   # Detected imx415 id 0000e0
ls /dev/media*
media-ctl -p -d /dev/media0              # 链路 imx415 -> dphy -> mipi2 -> cif -> isp
grep -H '' /sys/class/video4linux/video*/name   # 找 MAINPATH 节点
v4l2-ctl -d /dev/videoXX --set-fmt-video=width=3840,height=2160,pixelformat=NV12 \
	 --stream-mmap --stream-count=1 --stream-to=/tmp/f.raw
```
