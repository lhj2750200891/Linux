# LGA-3588L-MINI 适配笔记

　　本目录三件套: hardware-software.md (本文),
rk3588-firefly-lga-3588l-mini-duo-rk182x.dts (顶层, 宏开关),
rk3588-firefly-lga-3588l-mini-duo-rk182x.dtsi (载板全部板级内容展开,
仅保留 #include "rk3588-firefly-common.dtsi" 基座)。

## 12V_DCIN (直流输入)

### 硬件连接

```
DC12V 使能  ===> GPIO0 C0 (高有效, vcc12v_ac, 上游 vcc12v_dcin)
```

### 设备树配置

```
#ifdef FF_12V_DCIN
	vcc12v_ac: vcc12v-ac {
		compatible = "regulator-fixed";
		regulator-name = "vcc12v_ac";
		regulator-always-on;
		regulator-boot-on;
		regulator-min-microvolt = <12000000>;
		regulator-max-microvolt = <12000000>;
		enable-active-high;
		gpio = <&gpio0 RK_PC0 GPIO_ACTIVE_HIGH>;
		pinctrl-names = "default";
		pinctrl-0 = <&vcc12v_ac_en>;
		vin-supply = <&vcc12v_dcin>;
	};
#endif

&pinctrl {
#ifdef FF_12V_DCIN
	vcc12v_ac {
		vcc12v_ac_en: vcc12v-ac-en {
			rockchip,pins = <0 RK_PC0 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
#endif
};
```

### 测试指令

```
grep -H '' /sys/class/regulator/*/name | grep -i 12v
cat /sys/class/regulator/*/status | head -30
```

## LEDS

### 硬件连接

```
3.3V 系统电源保持 ===> GPIO0 C2 (vcc3v3_sys_ctrl, default on,
                      retain-state-suspended, 睡眠不掉电)
power LED ===> GPIO0 C4 (高有效, 常亮)
user  LED ===> GPIO1 C0 (高有效)
user1 LED ===> GPIO1 C1 (高有效)
```

### 设备树配置

```
/ {
	vcc3v3_sys_ctrl: vcc3v3-sys-ctrl {
		compatible = "gpio-leds";
		pinctrl-0 = <&vcc3v3_sys_ctrl_pin>;
		vcc3v3_sys_user: vcc3v3-sys-user {
			label = "vcc3v3_sys";
			gpios = <&gpio0 RK_PC2 GPIO_ACTIVE_HIGH>;
			default-state = "on";
			retain-state-suspended;
		};
	};

#ifdef FF_LEDS
	firefly_leds: firefly-leds {
		compatible = "gpio-leds";
		pinctrl-0 = <&led_pins>;
		power_led: power  { label = ":power"; default-state = "on";
			gpios = <&gpio0 RK_PC4 GPIO_ACTIVE_HIGH>; };
		user_led: user    { label = ":user";  default-state = "off";
			gpios = <&gpio1 RK_PC0 GPIO_ACTIVE_HIGH>; };
		user1_led: user1  { label = ":user1"; default-state = "off";
			gpios = <&gpio1 RK_PC1 GPIO_ACTIVE_HIGH>; };
	};
#endif
};

&pinctrl {
	vcc3v3_sys_ctrl {
		vcc3v3_sys_ctrl_pin: vcc3v3-sys-ctrl-pin {
			rockchip,pins = <0 RK_PC2 RK_FUNC_GPIO &pcfg_output_high>;
		};
	};
#ifdef FF_LEDS
	leds {
		led_pins: led-pins {
			rockchip,pins = <0 RK_PC4 RK_FUNC_GPIO &pcfg_pull_none>,
					<1 RK_PC0 RK_FUNC_GPIO &pcfg_pull_none>,
					<1 RK_PC1 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
#endif
};
```

### 测试指令

```
echo 255 > /sys/class/leds/:user/brightness && echo 0 > /sys/class/leds/:user/brightness
ls /sys/class/leds/        # :power :user :user1 vcc3v3_sys
```

## SDCARD

### 硬件连接

```
SDIO_PWR_EM  ===> GPIO0 B2
SDMMC0_D0    ===> SDMMC_D0  ===> GPIO4 D0
SDMMC0_D1    ===> SDMMC_D1  ===> GPIO4 D1
SDMMC_D2     ===> SDMMC_D2  ===> GPIO4 D2 
SDMMC_D3     ===> SDMMC_D3  ===> GPIO4 D3 
SDMMC_CMD    ===> SDMMC_CMD ===> GPIO4 D4
SDMMC_CLK    ===> SDMMC_CLK ===> GPIO4 D5
SDMMC_DET_L  ===> SDMMC_DET ===> GPIO0 A4
```



### 设备树配置

```
/ {
#ifdef FF_SDCARD
	vcc3v3_sd: vcc3v3-sd {
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_sd";
		regulator-always-on;
		regulator-boot-on;
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio0 RK_PB2 GPIO_ACTIVE_HIGH>;
		pinctrl-names = "default";
		pinctrl-0 = <&vcc3v3_sd_en>;
	};
#endif
};

#ifdef FF_SDCARD
&sdmmc {
	status = "okay";
	max-frequency = <150000000>;
	no-sdio;
	no-mmc;
	bus-width = <4>;
	cap-mmc-highspeed;
	cap-sd-highspeed;
	disable-wp;
	sd-uhs-sdr104;
	vqmmc-supply = <&vccio_sd_s0>;
	cd-gpios = <&gpio0 RK_PA4 GPIO_ACTIVE_LOW>;
	pinctrl-0 = <&sdmmc_clk &sdmmc_cmd &sdmmc_bus4>;
};
#endif

&pinctrl {
#ifdef FF_SDCARD
	sd_card {
		vcc3v3_sd_en: vcc3v3-sd-en {
			rockchip,pins = <0 RK_PB2 RK_FUNC_GPIO &pcfg_pull_none>;
		};
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

## GMAC0 / GMAC1 (双千兆网口)

### 硬件连接

```
GMAC0 reset ===> GPIO4 B0 (低有效)
GMAC1 reset ===> GPIO4 A4 (低有效)
```

### 设备树配置

```
#ifdef FF_GMAC0
&gmac0 {
	snps,reset-gpio = <&gpio4 RK_PB0 GPIO_ACTIVE_LOW>;
};
#endif

#ifdef FF_GMAC1
&gmac1 {
	snps,reset-gpio = <&gpio4 RK_PA4 GPIO_ACTIVE_LOW>;
};
#endif
```

### 测试指令

```
ip link                    # eth0/eth1
ethtool eth0 && ethtool eth1
```

## USB3.0 HOST

### 硬件连接

```
USB3.0 供电使能 ===> GPIO4 B4 (高有效, vcc5v0_usb30_host)
host0 ===> usbhost3_0 + usb_host0_ehci/ohci + u2phy2_host + combphy2_psu
host1 ===> usbdrd3_1 + usbdrd_dwc3_1(host) + u2phy1_otg + usbdp_phy1
```

### 设备树配置

```
#ifdef FF_USB30_HOST
	vcc5v0_usb30_host: vcc5v0-usb30-host {
		compatible = "regulator-fixed";
		enable-active-high;
		gpio = <&gpio4 RK_PB4 GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&usb30_host_en>;
		vin-supply = <&vcc5v0_sys>;
	};
#endif

// host1 (usbdrd)
&usbdrd3_1 { status = "okay"; }
&usbdrd_dwc3_1 { status = "okay"; dr_mode = "host"; }
&u2phy1 { status = "okay"; }
&u2phy1_otg { status = "okay"; phy-supply = <&vcc5v0_usb30_host>; }
&usbdp_phy1 { status = "okay"; }

// host0 (usbhost, 带 2.0 共路)
&usbhost3_0 { status = "okay"; vbus-supply = <&vcc5v0_usb30_host>; }
&usbhost_dwc3_0 { status = "okay"; dr_mode = "host"; }
&usb_host0_ehci { status = "okay"; }
&usb_host0_ohci { status = "okay"; }
&u2phy2 { status = "okay"; }
&u2phy2_host { status = "okay"; phy-supply = <&vcc5v0_usb30_host>; }
&combphy2_psu { status = "okay"; }
```

### 测试指令

```
lsusb && lsblk
dmesg | grep -iE "xhci|dwc3"
```

## HDMI0

### 硬件连接

```
HDMI0 enable ===> GPIO4 B1 (高有效)
音频 ===> hdmi0_sound (i2s5_8ch <-> hdmi0)
注意: FF_HDMI0 打开时 rk806single 的 pinctrl 换成 pmic_pins_lga
      (PMIC 引脚组随载板变化, LGA 专属)
```

### 设备树配置

```
#ifdef FF_HDMI0
&rk806single {
	pinctrl-0 = <&pmic_pins_lga>;
};

&hdmi0 { enable-gpios = <&gpio4 RK_PB1 GPIO_ACTIVE_HIGH>; status = "okay"; }
&hdmi0_in_vp0 { status = "okay"; }
&i2s5_8ch { status = "okay"; }
&hdptxphy0 { status = "okay"; }
&route_hdmi0 { status = "okay"; }
#endif

// pinctrl 段:
#ifdef FF_HDMI0
	pmic {
		pmic_pins_lga: pmic-pins-lga {
			rockchip,pins =
				<0 RK_PA7 0 &pcfg_pull_up>,
				<0 RK_PA2 1 &pcfg_pull_none>,
				<0 RK_PA3 1 &pcfg_pull_none>,
				<0 RK_PC1 1 &pcfg_pull_none>,
				<0 RK_PC3 1 &pcfg_pull_none>,
				<0 RK_PD6 1 &pcfg_pull_none>;
		};
	};
#endif
```

### 测试指令

```
cat /sys/class/drm/*/status && cat /sys/class/drm/*/modes
aplay -l | grep hdmi0
modetest -M rockchip -c
```

## M.2 SSD0 / SSD1 (双 PCIe 槽)

### 硬件连接

```
共用资源 (SSD0/SSD1 任一打开):
  PCIe 参考时钟使能 ===> GPIO4 B6 (pcie_refclk_en)
  槽供电 vcc3v3_ac1 ===> GPIO4 B5 (高有效, 5ms 延迟, 上游 12V)
SSD0 ===> pcie3x4 (num-lanes=2), reset GPIO1 B2 (高有效), wake GPIO1 B1
SSD1 ===> pcie3x2 (num-lanes=2), reset GPIO1 B7 (高有效), wake GPIO1 B6
PHY ===> pcie30phy (NANBNB 模式)
```

### 设备树配置

```
#if defined(FF_M2_SSD0) || defined(FF_M2_SSD1)
	pcie_refclk_en: pcie-refclk-en {   // 参考时钟
		enable-active-high;
		gpio = <&gpio4 RK_PB6 GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&pcie_refclk_en_pin>;
	};
	vcc3v3_ac1: vcc3v3-ac1 {           // 槽供电
		enable-active-high;
		gpio = <&gpio4 RK_PB5 GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&pcie_m2_power_en>;
		vin-supply = <&vcc12v_dcin>;
		startup-delay-us = <5000>;
	};
#endif

#ifdef FF_M2_SSD0
	pcie_ssd0_wake_keys: pcie-ssd0-wake-keys {   // 远程唤醒按键
		compatible = "gpio-keys";
		pcie_ssd0_wake: pcie-ssd0-wake {
			gpios = <&gpio1 RK_PB1 GPIO_ACTIVE_LOW>;
			linux,code = <KEY_WAKEUP>;  wakeup-source;
		};
	};
#endif
#ifdef FF_M2_SSD1
	pcie_ssd1_wake_keys: pcie-ssd1-wake-keys { ... GPIO1_B6 同构 ... }
#endif

#if defined(FF_M2_SSD0) || defined(FF_M2_SSD1)
&pcie30phy { rockchip,pcie30-phymode = <PHY_MODE_PCIE_NANBNB>; status = "okay"; }
#endif
#ifdef FF_M2_SSD0
&pcie3x4 { num-lanes = <2>;
	reset-gpios = <&gpio1 RK_PB2 GPIO_ACTIVE_HIGH>;
	vpcie3v3-supply = <&vcc3v3_ac1>;
	pinctrl-0 = <&pcie30x4m3_pins &pcie_ssd0_wake_pin>; status = "okay"; }
#endif
#ifdef FF_M2_SSD1
&pcie3x2 { num-lanes = <2>;
	reset-gpios = <&gpio1 RK_PB7 GPIO_ACTIVE_HIGH>;
	vpcie3v3-supply = <&vcc3v3_ac1>;
	pinctrl-0 = <&pcie30x2m3_pins &pcie_ssd1_wake_pin>; status = "okay"; }
#endif
```

### 测试指令

```
lspci && lsblk             # NVME 出块设备
dmesg | grep -i pcie
```

## FAN0 / FAN1 (双风扇, 带转速反馈)

### 硬件连接

```
FAN0: PWM ===> PWM3_M2, 转速 TACH ===> GPIO1 C3 (下降沿中断, 上拉)
FAN1: PWM ===> PWM11_M2, 转速 TACH ===> GPIO1 C6 (下降沿中断, 上拉)
两风扇 2 脉冲/转, 供电 12V (vcc12v_dcin)
```

### 设备树配置

```
#ifdef FF_FAN0
	fan0: pwm-fan0 {
		compatible = "pwm-fan";
		label = "fan0";
		#cooling-cells = <2>;
		pwms = <&pwm3 0 50000 0>;
		cooling-levels = <0 64 128 192 255>;
		fan-supply = <&vcc12v_dcin>;
		interrupts-extended = <&gpio1 RK_PC3 IRQ_TYPE_EDGE_FALLING>;
		pulses-per-revolution = <2>;
		status = "okay";
	};
#endif
#ifdef FF_FAN1
	fan1: pwm-fan1 { ... pwms = <&pwm11 0 50000 0>; GPIO1_C6 同构 ... }
#endif

#ifdef FF_FAN0
&pwm3 { pinctrl-0 = <&pwm3m2_pins &fan0_tach_gpio>; status = "okay"; }
#endif
#ifdef FF_FAN1
&pwm11 { pinctrl-0 = <&pwm11m2_pins &fan1_tach_gpio>; status = "okay"; }
#endif
```

### 测试指令

```
cat /sys/class/hwmon/*/fan*_input      # 转速 RPM
cat /sys/kernel/debug/pwm              # pwm3/pwm11 占空比
cat /sys/class/thermal/thermal_zone*/temp
```

## RTC (HYM8563)

### 硬件连接

```
HYM8563 ===> I2C6_M0 (地址 0x51), INT GPIO0 B0 (低有效)
```

### 设备树配置

```
#if defined(FF_RTC) || defined(FF_TYPEC_FULL)
&i2c6 { status = "okay"; pinctrl-0 = <&i2c6m0_xfer>;
#ifdef FF_RTC
	hym8563: hym8563@51 {
		compatible = "haoyu,hym8563";
		reg = <0x51>;
		#clock-cells = <0>;  clock-frequency = <32768>;
		pinctrl-0 = <&hym8563_int>;
		interrupts = <RK_PB0 IRQ_TYPE_LEVEL_LOW>;
		wakeup-source;
	};
#endif
#endif
&pinctrl { rtc { hym8563_int: hym8563-int {
	rockchip,pins = <0 RK_PB0 RK_FUNC_GPIO &pcfg_pull_up>; }; } }
```

### 测试指令

```
hwclock --show && hwclock --systohc
```

## TYPEC_FULL (全功能 TypeC + DP0)

### 硬件连接

```
fusb302 (PD) ===> I2C6_M0 (地址 0x22), INT GPIO0 D3 (低有效)
VBUS 放电使能 ===> GPIO4 A3 (高有效, vbus5v0_typec0)
SBU1/SBU2 (DP) ===> GPIO4 B2 / GPIO4 B3
DP 走 dp0 (vp2) + dp0_sound (spdif_tx2, mclk-fs 512)
USB 走 usbdrd3_0 (otg, role-switch)
PD sink 5V/1A, source 5V/3A, svid 0xff01
注意: I2C6 与 RTC 共享总线 (FF_RTC 与 FF_TYPEC_FULL 任一打开即开 i2c6)
```

### 设备树配置 (精简)

```
#ifdef FF_TYPEC_FULL
	vbus5v0_typec0: vbus5v0-typec0 {
		enable-active-high;
		gpio = <&gpio4 RK_PA3 GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&vbus5v0_typec0_en>;
		vin-supply = <&vcc5v0_sys>;
	};
	dp0_sound: dp0-sound {
		compatible = "rockchip,hdmi";
		rockchip,card-name = "rockchip-dp0";
		rockchip,mclk-fs = <512>;
		rockchip,cpu = <&spdif_tx2>;
		rockchip,codec = <&dp0 1>;
	};
#endif

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
			sink-pdos   = <PDO_FIXED(5000,1000, DATA_SWAP|USB_COMM|EXTPOWER|DUAL_ROLE)>;
			source-pdos = <PDO_FIXED(5000,3000, DATA_SWAP|USB_COMM|EXTPOWER|DUAL_ROLE)>;
			mode-switch = <&dp0>;
			altmodes { altmode@0 { svid = /bits/ 16 <0xff01>; vdo = <0x00001c46>; } };
			ports { /* orien_sw / dp_altmode_mux -> usbdp_phy0 */ };
		};
	};
};

&u2phy0 { status = "okay"; }
&u2phy0_otg { status = "okay"; rockchip,typec-vbus-det; }
&usbdp_phy0 { status = "okay"; orientation-switch; mode-switch; svid = <0xff01>;
	sbu1-dc-gpios = <&gpio4 RK_PB2 GPIO_ACTIVE_HIGH>;
	sbu2-dc-gpios = <&gpio4 RK_PB3 GPIO_ACTIVE_HIGH>; }
&dp0 { status = "okay"; mode-switch; }
&dp0_in_vp2 { status = "okay"; }
&spdif_tx2 { status = "okay"; }
&usbdrd3_0 { status = "okay"; }
&usbdrd_dwc3_0 { status = "okay"; dr_mode = "otg"; usb-role-switch; }
```

### 测试指令

```
ls /sys/class/typec/ && cat /sys/class/typec/port0/power_role
cat /sys/class/drm/*/status                  # 插 DP 后 DP-1 出现
aplay -l | grep dp0
dmesg | grep -i fusb302
```

## RECOVERY_KEY

### 硬件连接

```
Recovery 按键 ===> ADC 通道 0 (saradc), 按下 ~17mV, 松开阈值 1.8V
```

### 设备树配置

```
#ifdef FF_RECOVERY_KEY
	adc_keys_recovery: adc-keys-recovery {
		status = "okay";
		compatible = "adc-keys";
		io-channels = <&saradc 0>;
		io-channel-names = "buttons";
		keyup-threshold-microvolt = <1800000>;
		poll-interval = <100>;
		recovery-key {
			label = "recovery";
			linux,code = <KEY_F11>;
			press-threshold-microvolt = <17000>;
		};
	};
#endif
```

### 测试指令

```
cat /proc/bus/input/devices | grep -i recovery
evtest           # 按 recovery 键看 KEY_F11 事件
```

## 备注: 默认关闭的宏

```
顶层 dts 中注释掉的宏 (需要时手动打开):
// FF_WATCHDOG         外部看门狗
// FF_CURRENT_MONITOR  电流监测
```
