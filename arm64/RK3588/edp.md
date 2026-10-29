# eDP

　　eDP 屏: 无 HPD (force-hpd) 与带 HPD (hpd-gpios) 两种方式, 附 GT9xxx 触摸配置。参考板 AIO-3588SG / aio-3588q。

## 1. RK3588 eDP 架构

| 控制器 | 地址 | PHY | 互斥 |
|---|---|---|---|
| edp0 | fdec0000 | hdptxphy0 | 与 HDMI0 共享 PHY, 二选一 |
| edp1 | fded0000 | hdptxphy1 | 与 HDMI1 共享 PHY, 二选一 |

　　特点:
- eDP 屏无标准 EDID, 分辨率时序必须写在设备树 display-timings 中
- 面板用 simple-panel 驱动, 背光用 pwm-backlight
- 热插拔检测两种方式: hpd-gpios (屏有 HPD 线) 或 force-hpd (无 HPD 线强插)

　　内核配置 (defconfig 已开):

```
CONFIG_ROCKCHIP_ANALOGIX_DP=y    # eDP 控制器驱动
CONFIG_DRM_PANEL_SIMPLE=y        # simple-panel 面板驱动
CONFIG_BACKLIGHT_PWM=y           # PWM 背光
```

## 2. 方式一: 无 HPD 检测的屏 (force-hpd)

　　参考板: AIO-3588SG eDP0。

　　参考: rk3588-firefly-aio-3588sg-edp0.dtsi (4K 屏 + 触摸)

### 2.1 硬件连接

```
eDP 屏 (3840x2160):
  屏使能 EN       ====> PCA9555 IO0_3 (高有效)
  背光 BL_EN      ====> PCA9555 IO0_2 (高有效)
  背光 PWM        ====> PWM14_M1 ====> GPIO4_B2
  屏/触摸 3.3V    ====> PCA9554 IO0_1 (vcc3v3_edp0_tp)
  触摸使能        ====> PCA9554 IO0_2 (edp0_tp_en)
  触摸 (GT9xxx)   ====> I2C1_M4, INT ====> GPIO1_B2, RST ====> PCA9554 IO0_3
  HPD             未连接 (用 force-hpd)
```

### 2.2 设备树配置

```
/ {
	/* 屏/触摸电源 */
	vcc3v3_edp0_tp: vcc3v3-edp0-tp {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_edp0_tp";
		regulator-boot-on;
		regulator-always-on;
		enable-active-high;
		gpio = <&pca9554 PCA_IO0_1 GPIO_ACTIVE_HIGH>;
	};

	edp0_tp_en: edp0-tp-en {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "edp0_tp_en";
		regulator-boot-on;
		regulator-always-on;
		enable-active-high;
		gpio = <&pca9554 PCA_IO0_2 GPIO_ACTIVE_HIGH>;
	};

	/* eDP 面板: 时序从屏规格书抄 */
	edp0_panel: edp0-panel {
		status = "okay";
		compatible = "simple-panel";
		backlight = <&backlight_edp0>;
		enable-gpios = <&pca9555 PCA_IO0_3 GPIO_ACTIVE_HIGH>;
		prepare-delay-ms = <200>;

		display-timings {
			native-mode = <&edp_timing0>;
			edp_timing0: timing0 {
				clock-frequency = <533250000>;  // Min 355.52 / Typ 533.25 / Max 586.6 MHz
				hactive = <3840>;
				vactive = <2160>;
				hfront-porch = <48>;
				hsync-len = <32>;
				hback-porch = <100>;
				vfront-porch = <3>;
				vsync-len = <5>;
				vback-porch = <30>;
				hsync-active = <0>;
				vsync-active = <0>;
				de-active = <0>;
				pixelclk-active = <0>;
			};
		};

		port {
			panel_in_edp0: endpoint {
				remote-endpoint = <&edp0_out_panel>;
			};
		};
	};

	/* PWM 背光 */
	backlight_edp0: backlight-edp0 {
		status = "okay";
		compatible = "pwm-backlight";
		enable-gpios = <&pca9555 PCA_IO0_2 GPIO_ACTIVE_HIGH>;  // EDP_BL_EN
		pwms = <&pwm14 0 50000 0>;
		brightness-levels = <0 1 2 ... 255>;   // 256 级亮度表(完整列出)
		default-brightness-level = <200>;
	};
};

&pwm14 {
	status = "okay";
	pinctrl-0 = <&pwm14m1_pins>;       // GPIO4_B2
};

&edp0 {
	status = "okay";
	force-hpd;                          // 屏无 HPD 线, 强制视为已插入
	//hpd-gpios = <&gpio1 RK_PA6 GPIO_ACTIVE_HIGH>;

	ports {
		port@1 {
			reg = <1>;
			edp0_out_panel: endpoint {
				remote-endpoint = <&panel_in_edp0>;
			};
		};
	};
};

&route_edp0 {
	status = "okay";
	connect = <&vp1_out_edp0>;          // VOP VP1 -> eDP0
};

&edp0_in_vp1 {
	status = "okay";
};

&hdptxphy0 {
	status = "okay";                    // eDP0 PHY (与 HDMI0 互斥!)
};
```

## 3. eDP 触摸屏配置 (有触摸时增加)

　　eDP 触摸 (GT9xxx 电容屏) 与显示链路独立, 挂在 I2C 上,
需增加 I2C 设备节点 + 中断 pinctrl 两部分配置。

### 3.1 硬件连接 (AIO-3588SG 为例)

```
触摸 (GT9xxx):
  SCL/SDA  ====> I2C1_M4
  INT      ====> GPIO1_B2 (低有效, 下降沿触发)
  RST      ====> PCA9554 IO0_3 (低有效复位)
```

### 3.2 设备树配置

```
&i2c1 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c1m4_xfer>;

	goodix_ts_edp0: goodix-ts-edp0@5d {
		status = "okay";
		compatible = "goodix,gt9xxx";               // 驱动: CONFIG_TOUCHSCREEN_GT9XXX
		reg = <0x5d>;                               // GT9xxx I2C 地址 0x5d/0x14 视屏而定
		interrupt-parent = <&gpio1>;
		interrupts = <RK_PB2 IRQ_TYPE_LEVEL_LOW>;   // INT 引脚
		reset-gpios = <&pca9554 PCA_IO0_3 GPIO_ACTIVE_LOW>;
		irq-gpios = <&gpio1 RK_PB2 IRQ_TYPE_EDGE_FALLING>;
		irq-flags = <2>;                            // 1 rising, 2 falling
		pinctrl-names = "default";
		pinctrl-0 = <&touch_int_edp0>;
		touchscreen-size-x = <3840>;                // 与屏分辨率一致
		touchscreen-size-y = <2160>;
		goodix,slide-wakeup = <0>;
		goodix,type-a-report = <1>;
		goodix,driver-send-cfg = <1>;
		goodix,resume-in-workqueue = <0>;
		goodix,int-sync = <0>;
		goodix,esd-protect = <0>;
		goodix,auto-update-cfg = <1>;
		goodix,auto-update = <0>;
		goodix,power-off-sleep = <0>;
		goodix,pen-suppress-finger = <0>;
		goodix,has-pen = <0>;

		goodix,cfg-group2 = [ ... ];   // 触摸固件配置参数, 从屏厂家/参考 dtsi 获取
	};
};

&pinctrl {
	touch {
		touch_int_edp0: touch-int-edp0 {
			rockchip,pins = <1 RK_PB2 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

　　内核配置 (firefly-linux.config 片段):

```
CONFIG_TOUCHSCREEN_GT9XXX=y
```

　　注意:
- goodix,cfg-group2 是触摸参数固件块(十进制字节数组), 内容与具体屏绑定,
  从屏规格书/厂家资料或参考 dtsi 中复制
- aio-3588q 的触摸用不同接法 (irq 走 GPIO2_C3, pwr/rst 走 PCA9555_1),
  属性名也略不同 (goodix,pwr-gpio / goodix,rst-gpio / read-tp-thread),
  以实际屏的触摸规格为准
- 触摸电源如需独立控制, 参考方式一中的 vcc3v3_edp0_tp / edp0_tp_en

## 4. 方式二: 带 HPD 检测的屏 (hpd-gpios)

　　参考板: aio-3588q eDP1。

　　参考: rk3588-firefly-aio-3588q-edp_NV156FHM-T06.dtsi (1080p 屏)

### 4.1 硬件连接

```
eDP 屏 (NV156FHM-T06, 1920x1080):
  屏电源 PWR      ====> PCA9555_1 IO0_1 (pwr-gpios)
  背光使能 EN     ====> PCA9555_1 IO0_2 (enable-gpios)
  背光 PWM        ====> PWM8_M2 ====> GPIO3_D0
  HPD             ====> GPIO3_D5 (hpd-gpios, 高有效)
  触摸 (GT9xxx)   ====> I2C1, IRQ ====> GPIO2_C3
```

### 4.2 设备树配置

```
/ {
	edp_panel: edp-panel {
		compatible = "simple-panel";
		status = "okay";
		backlight = <&backlight_edp>;
		pwr-gpios = <&pca9555_1 PCA_IO0_1 GPIO_ACTIVE_HIGH>;
		pwr-delay-ms = <200>;
		enable-gpios = <&pca9555_1 PCA_IO0_2 GPIO_ACTIVE_HIGH>;  // EDP_BL_EN
		display-timings {
			native-mode = <&timing0>;
			timing0: timing0 {
				clock-frequency = <140000000>;
				hactive = <1920>;
				vactive = <1080>;
				hfront-porch = <40>;
				hsync-len = <40>;
				hback-porch = <80>;
				vfront-porch = <16>;
				vsync-len = <8>;
				vback-porch = <16>;
				hsync-active = <0>;
				vsync-active = <0>;
				de-active = <0>;
				pixelclk-active = <0>;
			};
		};

		port {
			panel_in_edp1: endpoint {
				remote-endpoint = <&edp1_out_panel>;
			};
		};
	};

	backlight_edp: backlight-edp {
		status = "okay";
		compatible = "pwm-backlight";
		pwms = <&pwm8 0 500000 0>;
		brightness-levels = <0 1 2 ... 255>;   // 256 级亮度表(完整列出)
		default-brightness-level = <200>;
	};
};

&pwm8 {
	pinctrl-0 = <&pwm8m2_pins>;         // GPIO3_D0
	status = "okay";
};

&edp1 {
	status = "okay";
	hpd-gpios = <&gpio3 RK_PD5 GPIO_ACTIVE_HIGH>;  // 真实 HPD 检测
	//force-hpd;                         // 有 HPD 时不需要

	ports {
		port@1 {
			reg = <1>;
			edp1_out_panel: endpoint {
				remote-endpoint = <&panel_in_edp1>;
			};
		};
	};
};

&route_edp1 {
	status = "okay";
	connect = <&vp2_out_edp1>;          // VOP VP2 -> eDP1
};

&edp1_in_vp2 {
	status = "okay";
};

&hdptxphy1 {
	status = "okay";                    // eDP1 PHY (与 HDMI1 互斥!)
};
```

## 5. 差异速查

| 项目 | 方式一 (SG edp0) | 方式二 (q edp1) ||---|---|---|
| HPD 检测 | force-hpd (无 HPD 线) | hpd-gpios (GPIO3_D5) |
| VOP 数据源 | vp1 | vp2 |
| 背光 PWM | pwm14 m1 (GPIO4_B2) | pwm8 m2 (GPIO3_D0) |
| PHY | hdptxphy0 (互斥 HDMI0) | hdptxphy1 (互斥 HDMI1) |
| 屏分辨率 | 3840x2160@533MHz | 1920x1080@140MHz |

　　注意:
- force-hpd 和 hpd-gpios 二选一: 有 HPD 线优先用 hpd-gpios,
  force-hpd 是调试/无 HPD 屏的兜底方案
- 使用 eDP0 时 HDMI0 不可用 (hdptxphy0 被占), 用 eDP1 则 HDMI1 不可用,
  规划显示接口时先定 PHY 分配
- brightness-levels 完整 256 级表太长, 此处省略, 实际从参考 dtsi 复制

## 6. 验证测试

```
# 查看连接器状态
cat /sys/class/drm/card*-eDP-1/status     # 方式一恒为 connected (force-hpd)
                                          # 方式二随 HPD 变化
cat /sys/class/drm/card*-eDP-1/enabled    # 点亮后为 1

# 查看当前模式
cat /sys/class/drm/card*-eDP-1/modes
# 应列出设备树 timing 对应的分辨率, 如 3840x2160

# 背光控制
ls /sys/class/backlight/
cat /sys/class/backlight/*/brightness
echo 100 > /sys/class/backlight/*/brightness    # 调暗
echo 255 > /sys/class/backlight/*/brightness    # 调亮

# dmesg 排查
dmesg | grep -i -E "edp|analogix"
# 正常应看到 analogix dp controller 初始化和 link training 成功

# 常见问题:
# 1. status 一直是 disconnected: force-hpd 未加或 hpd 引脚/极性错
# 2. 黑屏但 enabled=1: timing 与屏规格书不符, 或屏使能/电源 GPIO 极性错
# 3. link training 失败: 检查 hdptxphy 是否使能、lane 数
# 4. 花屏: 时序参数错误 (对照屏规格书逐项核对)
```
