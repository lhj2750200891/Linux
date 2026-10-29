# LED

　　GPIO LED (工作灯/自制灯): gpio-leds 节点配置与 sysfs 亮度控制。参考板 AIO-3588SG。

## 1. 硬件连接

```
DIY_LED   ===> 连接到 PCA9555的 IO_03 引脚
WORK_LED  ===> GPIO1 B3
```

## 2. 设备树配置

```
/ {
	firefly_leds: leds {
		status = "okay";
		compatible = "gpio-leds";
		pinctrl-names = "default";
		pinctrl-0 = <&leds_gpio>;

		power_led: power {
			label = ":power"; //WORK_LED
			linux,default-trigger = "ir-power-click";
			default-state = "on";
			gpios = <&gpio1 RK_PB3 GPIO_ACTIVE_HIGH>;
		};

		user_led: user {
			label = ":user"; //DIY_LED
			linux,default-trigger = "ir-user-click";
			default-state = "off";
			gpios = <&pca9555 PCA_IO0_3 GPIO_ACTIVE_HIGH>;   // 需要先配置PCA9555芯片
		};
	};
};

&pinctrl {
	leds {
		leds_gpio: leds-gpio {
			rockchip,pins = <1 RK_PB3 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};
```

## 3. 验证测试

```
# 通过 echo 能够控制开关即可
cd /sys/class/leds/:power/
echo 1 > brightness
echo 0 > brightness
```
