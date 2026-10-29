# MIPI DSI

　　MIPI DSI 屏 (初始化序列+触摸+在位检测) 与 LT9211D 桥转 LVDS 屏。参考板 AIO-3588SG。

## 1. RK3588 DSI 架构

| 控制器 | 地址 | PHY | VOP 数据源 |
|---|---|---|---|
| dsi0 | fde20000 | mipi_dcphy0 | vp2/vp3 |
| dsi1 | fde30000 | mipi_dcphy1 | vp2/vp3 |

　　说明:
- RK3588 DSI 是 DW MIPI DSI2 控制器, 用 mipi_dcphy (Samsung CPHY/DPHY) 做 PHY
- **dsi0 必须使能 mipi_dcphy0, dsi1 必须使能 mipi_dcphy1**, 漏掉必黑屏
- 数据源选 vp2 或 vp3 (默认 vp2 已挂 HDMI, 一般 DSI 走 vp3, 并把
  dsiN_in_vp2 显式 disabled)
- MIPI 屏无 EDID: 时序 + 初始化命令序列必须完整写在设备树里,
  这也是本模块内容多的原因 (一块屏的 init sequence 上百行是正常水平)
- 典型板级做法: 屏配置放独立 dtsi (如 rk3588-firefly-aio-3588sg-mipi-dsi1.dtsi),
  主 dts include 它, 换屏只换 dtsi

　　内核配置 (defconfig 已开):

```
CONFIG_DRM_ROCKCHIP=y
CONFIG_ROCKCHIP_DW_MIPI_DSI=y      # DW MIPI DSI2 控制器
CONFIG_PHY_ROCKCHIP_SAMSUNG_DCPHY=y  # mipi_dcphy
CONFIG_DRM_PANEL_SIMPLE=y          # simple-panel-dsi 面板
CONFIG_BACKLIGHT_PWM=y             # PWM 背光
CONFIG_DRM_PWM_MUX=y               # PWM 多路复用 (背光与 PWM 复用引脚时)
```

## 2. 方式一: DSI1 接 MIPI 屏 + 触摸

　　参考板: AIO-3588SG。

　　源文件: rk3588-firefly-aio-3588sg-mipi-dsi1.dtsi (800x1280 屏, 完整复制版)

### 2.1 硬件连接

```
MIPI 屏 (800x1280, 4 lane):
  MIPI 差分对  ====> mipi_dcphy1 (dsi1, 4 lane)
  屏电源 3.3V   ====> PCA9555 IO0_6 (vcc3v3_mipi)
  屏使能 EN     ====> PCA9555 IO0_5 (高有效)
  屏复位 RST    ====> PCA9555 IO0_4 (低有效)
  背光 PWM      ====> PWM3_M3 (pwms = <&pwm3 0 50000 1>) = GPIO1_A7
  背光使能      ====> GPIO4_B7 (高有效)
  I2C 触摸      ====> I2C6_M3: SCL GPIO4_B1 / SDA GPIO4_B0 (goodix @0x14)
  触摸 INT      ====> GPIO1_B5 (低有效)
  触摸 RST      ====> PCA9555 IO0_7
```

### 2.2 设备树配置 (完整, 直接复制后按屏改)

　　第一部分: 电源 + 背光 + PWM:

```
/ {
	vcc3v3_mipi: vcc3v3-mipi {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_mipi";
		regulator-boot-on;
		regulator-always-on;
		enable-active-high;
		gpio = <&pca9555 PCA_IO0_6 GPIO_ACTIVE_HIGH>;
	};

	backlight_1: backlight-1 {
		status = "okay";
		compatible = "pwm-backlight";
		enable-gpios = <&gpio4 RK_PB7 GPIO_ACTIVE_HIGH>;
		pwms = <&pwm3 0 50000 1>;      // 周期 20ms, 极性 1 (反相)
		brightness-levels = <
			 60  60  60  61  61  61  62  62
			 62  63  63  63  64  64  64  65
			 65  65  66  66  66  67  67  67
			 68  68  68  69  69  69  70  70
			 70  71  71  71  72  72  72  73
			 73  73  74  74  74  75  75  75
			 76  76  76  77  77  77  78  78
			 78  79  79  79  80  80  80  81
			 81  81  82  82  82  83  83  83
			 84  84  84  85  85  85  86  86
			 86  87  87  87  88  88  88  89
			 89  89  90  91  92  93  94  95
			 96  97  98  99 100 101 102 103
			104 105 106 107 108 109 110 111
			112 113 114 115 116 117 118 119
			120 121 122 123 124 125 126 127
			128 129 130 131 132 133 134 135
			136 137 138 139 140 141 142 143
			144 145 146 147 148 149 150 151
			152 153 154 155 156 157 158 159
			160 161 162 163 164 165 166 167
			168 169 170 171 172 173 174 175
			176 177 178 179 180 181 182 183
			184 185 186 187 188 189 190 191
			192 193 194 195 196 197 198 199
			200 201 202 203 204 205 206 207
			208 209 210 211 212 213 214 215
			216 217 218 219 220 221 222 223
			224 225 226 227 228 229 230 231
			232 233 234 235 236 237 238 239
			240 241 242 243 244 245 246 247
			248 249 250 251 252 253 254 255 >;
		default-brightness-level = <200>;
	};
};

&pwm3 {
	pinctrl-0 = <&pwm3m3_pins>;
	status = "okay";
};
```

　　(brightness-levels 是 256 项亮度曲线, 前 88 项压低防低端闪; 直接整段复制)

　　第二部分: 显示通路 (dcphy + vp 路由):

```
/* dsi1 使能必须带 mipi_dcphy1 */
&mipi_dcphy1 {
	status = "okay";
};

&dsi1_in_vp2 {
	status = "disabled";          // vp2 让给 HDMI
};

&dsi1_in_vp3 {
	status = "okay";              // DSI 走 vp3
};

&route_dsi1 {
	status = "okay";
	connect = <&vp3_out_dsi1>;
};
```

　　第三部分: 面板节点 (内容大头):

```
&dsi1 {
	status = "okay";
	/*
	 * firefly-check 是 Firefly 6.1 BSP 私有特性, 6.12 未移植, 保持注释
	 */
	//firefly-check;

	dsi1_panel: panel1@0 {
		status = "okay";
		compatible = "simple-panel-dsi";
		reg = <0>;
		backlight = <&backlight_1>;

		enable-gpios = <&pca9555 PCA_IO0_5 GPIO_ACTIVE_HIGH>;
		reset-gpios = <&pca9555 PCA_IO0_4 GPIO_ACTIVE_LOW>;

		/* 上电/初始化时序延时 (毫秒) */
		enable-delay-ms = <50>;
		prepare-delay-ms = <200>;
		reset-delay-ms = <50>;
		init-delay-ms = <55>;
		unprepare-delay-ms = <50>;
		disable-delay-ms = <20>;
		mipi-data-delay-ms = <200>;
		size,width = <120>;
		size,height = <170>;
		dsi,flags = <(MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST |
		              MIPI_DSI_MODE_LPM | MIPI_DSI_MODE_NO_EOT_PACKET)>;
		dsi,format = <MIPI_DSI_FMT_RGB888>;
		dsi,lanes = <4>;

		/*
		 * 在位检测 (U-Boot 执行): 选 page 后读 0x00 期望 0x98;
		 * 无屏时 U-Boot 把 panel/dsi1/route_dsi1/触摸节点在传给内核的
		 * FDT 里关掉, 防止死 connector 阻塞整个 DRM (HDMI 也出不来)
		 */
		panel-read-id-sequence = [
			39 00 04 FF 98 81 01
		];
		id-reg = <0x00>;
		id = [98];
		rockchip,touch-nodes = <&goodix_ts_dsi1>;

		/*
		 * 屏初始化命令: [类型 延时ms 长度 数据...]
		 * 39=长写(LCS) 15=短写(SCS) 05=延时; 从屏规格书/FAE 代码抄
		 */
		panel-init-sequence = [
			39 00 04 FF 98 81 01
			39 00 04 FF 98 81 03
			15 00 02 01 00
			15 00 02 02 00
			15 00 02 03 55
			15 00 02 04 55
			15 00 02 05 03
			15 00 02 06 06
			15 00 02 07 00
			15 00 02 08 07
			15 00 02 09 00
			15 00 02 0a 00
			15 00 02 0b 00
			15 00 02 0c 00
			15 00 02 0d 00
			15 00 02 0e 00
			15 00 02 0f 00
			15 00 02 10 00
			15 00 02 11 00
			15 00 02 12 00
			15 00 02 13 00
			15 00 02 14 00
			15 00 02 15 00
			15 00 02 16 00
			15 00 02 17 00
			15 00 02 18 00
			15 00 02 19 00
			15 00 02 1a 00
			15 00 02 1b 00
			15 00 02 1c 00
			15 00 02 1d 00
			15 00 02 1e C0
			15 00 02 1f 80
			15 00 02 20 04
			15 00 02 21 03
			15 00 02 22 00
			15 00 02 23 00
			15 00 02 24 00
			15 00 02 25 00
			15 00 02 26 00
			15 00 02 27 00
			15 00 02 28 33
			15 00 02 29 33
			15 00 02 2a 00
			15 00 02 2b 00
			15 00 02 2c 00
			15 00 02 2d 00
			15 00 02 2e 00
			15 00 02 2f 00
			15 00 02 30 00
			15 00 02 31 00
			15 00 02 32 00
			15 00 02 33 00
			15 00 02 34 04
			15 00 02 35 00
			15 00 02 36 00
			15 00 02 37 00
			15 00 02 38 3C
			15 00 02 39 00
			15 00 02 3a 00
			15 00 02 3b 00
			15 00 02 3c 00
			15 00 02 3d 00
			15 00 02 3e 00
			15 00 02 3f 00
			15 00 02 40 00
			15 00 02 41 00
			15 00 02 42 00
			15 00 02 43 00
			15 00 02 44 00
			15 00 02 50 00
			15 00 02 51 11
			15 00 02 52 44
			15 00 02 53 55
			15 00 02 54 88
			15 00 02 55 AB
			15 00 02 56 00
			15 00 02 57 11
			15 00 02 58 22
			15 00 02 59 33
			15 00 02 5a 44
			15 00 02 5b 55
			15 00 02 5c 66
			15 00 02 5d 77
			15 00 02 5e 00
			15 00 02 5f 02
			15 00 02 60 02
			15 00 02 61 0A
			15 00 02 62 09
			15 00 02 63 08
			15 00 02 64 13
			15 00 02 65 12
			15 00 02 66 11
			15 00 02 67 10
			15 00 02 68 0F
			15 00 02 69 0E
			15 00 02 6a 0D
			15 00 02 6b 0C
			15 00 02 6c 06
			15 00 02 6d 07
			15 00 02 6e 02
			15 00 02 6f 02
			15 00 02 70 02
			15 00 02 71 02
			15 00 02 72 02
			15 00 02 73 02
			15 00 02 74 02
			15 00 02 75 02
			15 00 02 76 02
			15 00 02 77 0A
			15 00 02 78 06
			15 00 02 79 07
			15 00 02 7a 10
			15 00 02 7b 11
			15 00 02 7c 12
			15 00 02 7d 13
			15 00 02 7e 0C
			15 00 02 7f 0D
			15 00 02 80 0E
			15 00 02 81 0F
			15 00 02 82 09
			15 00 02 83 08
			15 00 02 84 02
			15 00 02 85 02
			15 00 02 86 02
			15 00 02 87 02
			15 00 02 88 02
			15 00 02 89 02
			15 00 02 8A 02
			39 00 04 FF 98 81 04
			15 00 02 6E 2A
			15 00 02 6F 37
			15 00 02 3A 24
			15 00 02 8D 19
			15 00 02 87 BA
			15 00 02 B2 D1
			15 00 02 88 0B
			15 00 02 38 01
			15 00 02 39 00
			15 00 02 B5 02
			15 00 02 31 25
			15 00 02 3B 98
			39 00 04 FF 98 81 01
			15 00 02 22 0A
			15 00 02 31 0C
			15 00 02 53 40
			15 00 02 55 45
			15 00 02 50 B7
			15 00 02 51 B2
			15 00 02 60 07
			15 00 02 A0 22
			15 00 02 A1 3F
			15 00 02 A2 4E
			15 00 02 A3 17
			15 00 02 A4 1A
			15 00 02 A5 2D
			15 00 02 A6 21
			15 00 02 A7 22
			15 00 02 A8 C4
			15 00 02 A9 1B
			15 00 02 AA 25
			15 00 02 AB A7
			15 00 02 AC 1A
			15 00 02 AD 19
			15 00 02 AE 4B
			15 00 02 AF 1F
			15 00 02 B0 2A
			15 00 02 B1 59
			15 00 02 B2 64
			15 00 02 B3 3F
			15 00 02 C0 22
			15 00 02 C1 48
			15 00 02 C2 59
			15 00 02 C3 15
			15 00 02 C4 15
			15 00 02 C5 28
			15 00 02 C6 1C
			15 00 02 C7 1E
			15 00 02 C8 C4
			15 00 02 C9 1C
			15 00 02 CA 2B
			15 00 02 CB A3
			15 00 02 CC 1F
			15 00 02 CD 1E
			15 00 02 CE 52
			15 00 02 CF 24
			15 00 02 D0 2A
			15 00 02 D1 58
			15 00 02 D2 68
			15 00 02 D3 3F
			39 00 04 FF 98 81 00
			05 78 01 11              // Sleep Out, 延时 120ms
			05 14 01 29              // Display On, 延时 20ms
		];

		panel-exit-sequence = [
			39 00 04 FF 98 81 00     // page0
			05 14 01 28              // Display Off, 延时 20ms
			05 78 01 10              // Sleep In, 延时 120ms
		];

		/* 时序从屏规格书抄 */
		disp_timings: display-timings {
			native-mode = <&dsi_timing>;
			dsi_timing: timing {
				clock-frequency = <70000000>;
				hactive = <800>;
				vactive = <1280>;
				hsync-len = <20>;
				hback-porch = <20>;
				hfront-porch = <40>;
				vsync-len = <4>;
				vback-porch = <20>;
				vfront-porch = <20>;
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
				panel_in_dsi1: endpoint {
					remote-endpoint = <&dsi1_out_panel>;
				};
			};
		};
	};

	ports {
		#address-cells = <1>;
		#size-cells = <0>;
		port@1 {
			reg = <1>;
			dsi1_out_panel: endpoint {
				remote-endpoint = <&panel_in_dsi1>;
			};
		};
	};
};
```

　　需要 #include <dt-bindings/display/drm_mipi_dsi.h> (dsi,flags/format 宏)。

　　第四部分: 触摸 (完整, 含 cfg-group2 固件参数):

```
&i2c6 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c6m3_xfer>;

	goodix_ts_dsi1: goodix-ts-dsi1@14 {
		status = "okay";
		compatible = "goodix,gt9xxx";
		reg = <0x14>;
		interrupt-parent = <&gpio1>;
		interrupts = <RK_PB5 IRQ_TYPE_LEVEL_LOW>;
		reset-gpios = <&pca9555 PCA_IO0_7 GPIO_ACTIVE_HIGH>;
		irq-gpios = <&gpio1 RK_PB5 IRQ_TYPE_LEVEL_LOW>;
		irq-flags = <2>;                    // 1 上升沿, 2 下降沿
		pinctrl-names = "default";
		pinctrl-0 = <&touch_int1>;
		touchscreen-size-x = <800>;
		touchscreen-size-y = <1280>;
		goodix,slide-wakeup = <0>;
		goodix,type-a-report = <1>;
		goodix,driver-send-cfg = <1>;
		goodix,resume-in-workqueue = <0>;
		goodix,int-sync = <1>;
		goodix,esd-protect = <1>;
		goodix,auto-update-cfg = <1>;
		goodix,auto-update = <0>;
		goodix,power-off-sleep = <0>;
		goodix,pen-suppress-finger = <0>;
		goodix,has-pen = <0>;

		/* 触摸参数固件 (坐标/灵敏度/按键映射), 从屏厂/参考 dtsi 抄 */
		goodix,cfg-group2 = [
			62 20 03 00 05 0A 35 00 01
			0A 28 0F 50 3C 03 05 00 00
			00 00 00 00 06 18 1A 1E 14
			90 30 AA 37 39 12 0C 00 00
			00 1A 02 2D 00 00 00 00 00
			00 00 00 07 00 00 28 4B 94
			D5 02 07 00 00 04 9A 2A 00
			8C 30 00 81 36 00 76 3E 00
			6E 46 00 6E 00 00 00 00 00
			00 00 00 00 00 00 00 00 00
			00 00 00 00 00 00 00 00 00
			00 00 00 00 00 02 00 00 00
			00 00 00 00 19 18 17 16 15
			14 11 10 0F 0E 0D 0C 09 08
			07 06 05 04 01 00 00 00 00
			00 00 00 00 00 00 00 14 13
			12 11 10 0F 0E 0D 0C 0A 08
			07 06 04 02 00 19 1B 1C 1E
			1F 20 21 22 23 24 25 26 27
			28 29 2A 00 00 00 00 00 00
			00 00 00 00 D8 01];
	};
};

&pinctrl {
	touch {
		touch_int1: touch-int1 {
			rockchip,pins = <1 RK_PB5 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

### 2.3 面板在位检测说明

　　panel-read-id-sequence / id-reg / id / rockchip,touch-nodes 四件套由
**U-Boot** 执行 (不是内核): 无屏时 U-Boot 把 panel/dsi1/route_dsi1 和
触摸节点在传给内核的 FDT 里关掉, 避免内核建死 connector 把 DRM
component master 卡死、HDMI 也不亮。自研板建议保留这套 (U-Boot 侧需
支持, 对应 SG 板已验证的实现)。

　　firefly-check / 0x99 ID-check 是 Firefly 6.1 BSP 私有特性, 6.12 未移植,
保持注释关闭。

## 3. 方式二: DSI0 + LT9211D 桥接 LVDS 屏

　　参考板: AIO-3588SG (lvds101)。

　　源文件: rk3588-firefly-aio-3588sg-mipi-dsi0-lvds101.dtsi

**注意: LVDS 屏是经 Lontium LT9211D 桥片 (MIPI 转 LVDS, I2C 挂 i2c0)
实现的, 不是屏内自带转换。**

### 3.1 硬件连接

```
LVDS 屏 (800x1280, 经 LT9211D 桥):
  DSI 差分对  ====> mipi_dcphy0 (dsi0, 4 lane) ====> LT9211D MIPI RX
  LT9211D I2C ====> I2C0_M2 (地址 0x2d)
  LT9211D 电源 ====> GPIO3_C1 (power-gpio, 高有效)
  LT9211D 复位 ====> GPIO3_B7 (reset-gpio, 高有效)
  桥输出 LVDS  ====> LVDS 屏
  背光使能    ====> PCA9554 IO0_0 (高有效)
  背光 PWM    ====> PWM3_M1 (pwms = <&pwm3 0 50000 1>) = GPIO3_B2
```

### 3.2 设备树配置 (完整)

```
/ {
	backlight_lvds: backlight_lvds {
		status = "okay";
		compatible = "pwm-backlight";
		enable-gpios = <&pca9554 PCA_IO0_0 GPIO_ACTIVE_HIGH>;
		pwms = <&pwm3 0 50000 1>;
		brightness-levels = <
			0   1   2   3   4   5   6   7
			8   9  10  11  12  13  14  15
			16  17  18  19  20  21  22  23
			24  25  26  27  28  29  30  31
			32  33  34  35  36  37  38  39
			40  41  42  43  44  45  46  47
			48  49  50  51  52  53  54  55
			56  57  58  59  60  61  62  63
			64  65  66  67  68  69  70  71
			72  73  74  75  76  77  78  79
			80  81  82  83  84  85  86  87
			88  89  90  91  92  93  94  95
			96  97  98  99 100 101 102 103
			104 105 106 107 108 109 110 111
			112 113 114 115 116 117 118 119
			120 121 122 123 124 125 126 127
			128 129 130 131 132 133 134 135
			136 137 138 139 140 141 142 143
			144 145 146 147 148 149 150 151
			152 153 154 155 156 157 158 159
			160 161 162 163 164 165 166 167
			168 169 170 171 172 173 174 175
			176 177 178 179 180 181 182 183
			184 185 186 187 188 189 190 191
			192 193 194 195 196 197 198 199
			200 201 202 203 204 205 206 207
			208 209 210 211 212 213 214 215
			216 217 218 219 220 221 222 223
			224 225 226 227 228 229 230 231
			232 233 234 235 236 237 238 239
			240 241 242 243 244 245 246 247
			248 249 250 251 252 253 254 255>;
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

		/* 桥后的屏不需 init 命令; EoT 包默认使能, 无 NO_EOT flag */
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

/* LT9211D MIPI->LVDS 桥 (挂 I2C0_M2, 100kHz) */
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

		mod = "mipi_in_lvds_out";           // pattern_out / mipi_in_lvds_out
		lvdstx_port_swap = "disabled";      // enabled / disabled
		lvdstx_port_sel = "porta";          // porta / portb / dou_port

		/* 桥端时序 (与屏一致) */
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
	status = "disabled";        // GPIO3_C1 被 LT9211D 电源占用时关掉
};
```

　　要点:
- compatible 写 "loutium, LT9211C" (复用 LT9211C 驱动, 注意厂商拼写
  就是 dtsi 原样 loutium)
- 桥的时序与 panel display-timings 必须一致
- can2 若占用了桥的电源脚 (GPIO3_C1) 需 disabled

## 4. 方式三: DSI0 + LT9211D 接 1080P LVDS 屏 (lvds215)

　　与方式二同构, 换屏参数即可:

| 参数 | lvds101 (800x1280) | lvds215 (1920x1080) |
|---|---|---|
| clock-frequency | 72000000 | 150000000 (166M@50Hz) |
| hactive/vactive | 800/1280 | 1920/1080 |
| hsync-len | 10 | 10 |
| hback-porch | 50 | 10 |
| hfront-porch | 50 | 282 |
| vsync-len | 18 | 10 |
| vback-porch | 10 | 25 |
| vfront-porch | 10 | (按屏) |
| default-brightness | 200 | 0 |

　　lt9211d 节点里 frameRate 按屏 50/60 调整。

## 5. PWM 背光引脚注意

　　同一块板 PWM3 有多个复用组, 按背光走线选:

| 复用组 | 引脚 | 用途 |
|---|---|---|
| pwm3m1 | GPIO3_B2 | LVDS 屏背光 (方式二/三) |
| pwm3m3 | GPIO1_A7 | MIPI 屏背光 (方式一) |

　　pinctrl-0 引用的组要与硬件一致, 背光引脚还在 PWM_MUX 框架管理下
(drm-pwm-mux, 见 debug/pwm 相关文档)。

## 6. 验证测试

```
# 查看连接器
ls /sys/class/drm/
# 应看到 card?-DSI-1 (dsi1) / card0-DSI-2 (dsi0)

cat /sys/class/drm/card*-DSI-1/status    # enabled
cat /sys/class/drm/card*-DSI-1/modes     # 应列出设备树 timing 的分辨率

# DSI 日志
dmesg | grep -i -E "dsi|mipi|panel"
# 正常: dsi host 初始化, 面板 attached
# LT9211D 桥: 额外看 lt9211 相关打印

# 背光
cat /sys/class/backlight/*/brightness
echo 100 > /sys/class/backlight/*/brightness

# 触摸
cat /proc/bus/input/devices | grep -A4 goodix
# 应看到触摸设备; evtest 测触摸事件

# 常见问题:
# 1. 黑屏无输出: mipi_dcphyN 未使能 (dsi0 配 dcphy0, dsi1 配 dcphy1);
#    或 dsiN_in_vp2/vp3 路由没配对
# 2. panel attached 后无图: panel-init-sequence 与屏不符, 逐条对照
#    屏规格书/FAE 参考代码
# 3. 花屏: timing 错或 lane 数错, 核对 display-timings 和 dsi,lanes
# 4. 挂死整个 DRM (HDMI 也不亮): 没做面板在位检测, 参考 2.3;
#    或 panel enable/reset 时序错导致 probe 卡住
# 5. LVDS 屏无图: 先量 LT9211D 电源/复位脚, i2cdetect 看 0x2d 在不在,
#    桥没起来 MIPI 侧自然无输出
# 6. 触摸无反应: cfg-group2 与屏不匹配或 INT 极性错
```
