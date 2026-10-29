# Type-C

　　全功能 Type-C (USB3 OTG + DP altmode + PD 充电) 与非全功能 (无充电管理) 两种方式, 附板间差异速查。

## 1. RK3588 Type-C 架构

　　Type-C 是一整套链路, 不是单个控制器:

```
Type-C 口
  ├── CC 信号 ====> CC/PD 芯片 (fusb302, I2C)         负责插拔/方向/PD 协商
  ├── USB2  ====> u2phy0 (SOC 内置 USB2 PHY)
  ├── USB3  ====> usbdrd3_0 + usbdrd_dwc3_0 (USB3 OTG 控制器)
  └── SSB/DP ====> usbdp_phy0 (USB3/DP 复用 PHY)       DP altmode 时切 lane
```

- RK3588 有 2 路 Type-C capable 通路 (usbdrd3_0/1 + usbdp_phy0/1)
- PD 协议靠 tcpm 框架 + CC 芯片驱动 (fusb302), SOC 内无 PD 硬件
- 板间差异按功能裁剪程度分两档 (见方式一/方式二);

　　内核配置 (defconfig 已开):

```
CONFIG_TYPEC=y
CONFIG_TYPEC_TCPM=y            # TCPM (Type-C 端口管理器)
CONFIG_TYPEC_FUSB302=y         # FUSB302 CC/PD 芯片
CONFIG_TYPEC_DP_ALTMODE=y      # DP altmode (需要 DP 输出时)
CONFIG_TYPEC_MUX_GPIO_SBU=y    # SBU 方向切换
CONFIG_RFKILL=y
CONFIG_RFKILL_RK=y
```

## 2. 板间差异速查 (先看这个再选配置)

| 板 | 宏 | DP altmode | 充电管理 | OTG VBUS 来源 | fusb302 INT |
|---|---|---|---|---|---|
| AIO-3588SG | FF_TYPEC0_FULL | 有 (dp0) | 有 (sc8886+bq25703+cw2017) | 充电芯片 otg-vbus | GPIO0_C4 |
| itx-3588j | FF_TYPEC_FULL | 有 (dp0) | 无 (仅 5V sink) | GPIO OTG 使能 (PCA9555 IO1_4) | GPIO0_D3 |
| roc-rk3588s-pc / aio-3588q | FF_TYPEC0 | 有 (dp0) | 无 (仅 5V sink) | GPIO1_B1 (vbus5v0_typec0) | GPIO0_C4 |

- 全功能口 = DP altmode + PD 双向供电 + 充电芯片 + 电量计
- 非全功能口 = DP altmode + 数据 OTG, 电力上只做 5V sink / 简单 source,
  没有充电芯片和电量计
- 纯数据口 (无 DP): 删掉 dp0/mode-switch 相关部分即可

## 3. 方式一: 全功能 Type-C

　　USB3 OTG + DP altmode + PD 充电, 功能齐备。参考板 AIO-3588SG。

### 3.1 硬件连接

```
Type-C 口:
  CC/PD   ====> FUSB302 (I2C2_M0: SCL GPIO0_B7 / SDA GPIO0_C0, 地址 0x22)
                  INT ====> GPIO0_C4 (低有效)
  USB2    ====> u2phy0
  USB3    ====> usbdrd3_0 / usbdrd_dwc3_0
  DP lane ====> usbdp_phy0 (2 lane USB3 + 2 lane DP)
  SBU1 方向 ====> GPIO1_B0 (sbu1-dc-gpios)
  SBU2 方向 ====> GPIO1_A0 (sbu2-dc-gpios)
  充电芯片 SC8886 (兼容 bq25703, I2C4_M3 地址 0x6b)
                  INT ====> GPIO4_C1 (低有效)
                  OTG 使能 ====> GPIO4_C0 (高有效)
                  OTG 放电 ====> GPIO1_A5 (typec0-discharge-gpios, 高有效)
  电量计 CW2017 (I2C4_M3 地址 0x63)
  OTG VBUS 5V 输出 ====> sc8886 内置 (vbus5v0_typec_charge regulator)
```

### 3.2 设备树配置

　　参考: rk3588-firefly-aio-3588sg.dtsi (FF_TYPEC0_FULL)

```
/* 1. USB2/USB3/PHY 部分 */
&u2phy0 {
	status = "okay";
};

&u2phy0_otg {
	status = "okay";
	rockchip,typec-vbus-det;         // VBUS 检测走 Type-C 供电逻辑
};

&usbdp_phy0 {
	status = "okay";
	orientation-switch;              // 支持正反插方向切换
	mode-switch;                     // 支持 USB3/DP 模式切换
	svid = <0xff01>;                 // DP altmode SVID
	sbu1-dc-gpios = <&gpio1 RK_PB0 GPIO_ACTIVE_HIGH>;
	sbu2-dc-gpios = <&gpio1 RK_PA0 GPIO_ACTIVE_HIGH>;

	port {
		#address-cells = <1>;
		#size-cells = <0>;
		usbdp_phy0_orientation_switch: endpoint@0 {
			reg = <0>;
			remote-endpoint = <&usbc0_orien_sw>;
		};

		usbdp_phy0_dp_altmode_mux: endpoint@1 {
			reg = <1>;
			remote-endpoint = <&dp_altmode_mux>;
		};
	};
};

&usbdrd3_0 {
	status = "okay";
};

&usbdrd_dwc3_0 {
	status = "okay";
	dr_mode = "otg";                 // OTG 双角色
	usb-role-switch;                 // 角色由 tcpm 控制
	port {
		#address-cells = <1>;
		#size-cells = <0>;
		dwc3_0_role_switch: endpoint@0 {
			reg = <0>;
			remote-endpoint = <&usbc0_role_sw>;
		};
	};
};

/* 2. CC/PD 芯片 (fusb302, 挂 I2C2) */
&i2c2 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c2m0_xfer>;

	usbc0: fusb302@22 {
		compatible = "fcs,fusb302";
		reg = <0x22>;
		interrupt-parent = <&gpio0>;
		interrupts = <RK_PC4 IRQ_TYPE_LEVEL_LOW>;    // INT GPIO0_C4
		int-n-gpios = <&gpio0 RK_PC4 GPIO_ACTIVE_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&usbc0_int>;
		vbus-supply = <&vbus5v0_typec_charge>;       // OTG VBUS 由充电芯片供
		charge-dev = <&sc8886>;                       // 关联充电芯片
		suspend-disable-irq;
		status = "okay";

		ports {
			#address-cells = <1>;
			#size-cells = <0>;

			port@0 {
				reg = <0>;
				usbc0_role_sw: endpoint@0 {
					remote-endpoint = <&dwc3_0_role_switch>;
				};
			};
		};

		/* USB-C 连接器声明 */
		usb_con: connector {
			compatible = "usb-c-connector";
			label = "USB-C";
			data-role = "dual";
			power-role = "dual";
			try-power-role = "sink";            // 默认受电
			op-sink-microwatt = <1000000>;      // 低于 1W 放弃
			/* 本板可接受的输入电压/电流 (PD sink 能力, 按充电芯片填) */
			sink-pdos =
				<PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)
				 PDO_FIXED(9000, 3000, PDO_FIXED_USB_COMM)
				 PDO_FIXED(12000, 2000, PDO_FIXED_USB_COMM)>;
			/* 本板可对外输出 (OTG 时) */
			source-pdos =
				<PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)>;
			mode-switch = <&dp0>;                // DP altmode 切换到 dp0

			altmodes {
				#address-cells = <1>;
				#size-cells = <0>;

				altmode@0 {
					reg = <0>;
					svid = /bits/ 16 <0xff01>;      // DP altmode
					vdo = <0x00001c46>;             // 2 lane DP + USB3
				};
			};

			ports {
				#address-cells = <1>;
				#size-cells = <0>;

				port@0 {
					reg = <0>;
					usbc0_orien_sw: endpoint {
						remote-endpoint = <&usbdp_phy0_orientation_switch>;
					};
				};

				port@1 {
					reg = <1>;
					dp_altmode_mux: endpoint {
						remote-endpoint = <&usbdp_phy0_dp_altmode_mux>;
					};
				};
			};
		};
	};
};

/* 3. DP 输出 (altmode 显示) */
&dp0 {
	status = "okay";
};

&dp0_in_vp2 {
	status = "okay";
};

&route_dp0 {
	status = "okay";
	connect = <&vp2_out_dp0>;
};

/* 4. 充电芯片 + 电量计 (I2C4) */
&i2c4 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c4m3_xfer>;

	sc8886: sc8886@6b {
		status = "okay";
		compatible = "ti,bq25703";            // sc8886 兼容 bq25703 协议
		reg = <0x6b>;
		ti,usb-charger-detection = <&usbc0>;  // 充电检测靠 fusb302
		ti,charge-current = <2000000>;        // 充电电流 2A
		interrupt-parent = <&gpio4>;
		interrupts = <RK_PC1 IRQ_TYPE_LEVEL_LOW>;
		otg-mode-en-gpios = <&gpio4 RK_PC0 GPIO_ACTIVE_HIGH>;  // OTG 使能
		pinctrl-names = "default";
		pinctrl-0 = <&charger_int>;
		extcon = <&u2phy0>;
		ti,max-input-voltage = <20000000>;
		ti,max-input-current = <6000000>;
		ti,max-charge-voltage = <8400000>;    // 双节电池 8.4V
		ti,input-current = <2500000>;
		ti,minimum-sys-voltage = <6144000>;
		ti,otg-voltage = <5000000>;           // OTG 输出 5V/1.5A
		ti,otg-current = <1500000>;
		pd-charge-only = <0>;                 // PD 口不只做充电(还要通信)
		typec0-discharge-gpios = <&gpio1 RK_PA5 GPIO_ACTIVE_HIGH>;

		regulators {
			vbus5v0_typec_charge: vbus5v0-typec-charge {
				regulator-compatible = "otg-vbus";
				regulator-name = "vbus5v0_typec_charge";
			};
		};
	};

	cw2017: cw2017@63 {
		status = "okay";
		compatible = "cellwise,cw2017";
		reg = <0x63>;
		cellwise,battery-profile = /bits/ 8
			< 0x3C 0x00 ... 0xA2 >;   // 64 字节电池特性 (从电池厂/参考 dtsi 复制)
		cellwise,dual-cell;                    // 双节电芯
		cellwise,monitor-interval-ms = <5000>;
		cellwise,alert-level = <10>;           // 低于 10% 告警
		cellwise,design-capacity-amh = <5000>; // 设计容量 5000mAh
	};
};

&pinctrl {
	typec0 {
		usbc0_int: usbc0-int {
			rockchip,pins = <0 RK_PC4 RK_FUNC_GPIO &pcfg_pull_up>;
		};

		charger_int: charger-int {
			rockchip,pins = <4 RK_PC1 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

　　DP altmode 音频 (DP 音频走 spdif, 不需要 DP 声音可整段省略):

```
&spdif_tx2 {
	status = "okay";
};

/ {
	dp0_sound: dp0-sound {
		status = "okay";
		compatible = "rockchip,hdmi";
		rockchip,card-name = "rockchip-dp0";
		rockchip,mclk-fs = <512>;
		rockchip,cpu = <&spdif_tx2>;
		rockchip,codec = <&dp0 1>;
		rockchip,jack-det;
	};
};
```

　　充电芯片驱动注意:
- bq25700_charger.c (瑞芯微/Firefly 增强版, 原厂 SDK 已含) 支持
  ti,bq25700 / ti,bq25703 / southchip,sc8885 / southchip,sc8886 四个
  compatible (bq25703 与 sc8886 共用 bq25703 寄存器 map), 及
  otg-mode-en-gpios / typec0-discharge-gpios / pd-charge-only /
  ti,charge-current 扩展属性; charge-dev 属性 6.12 驱动未解析
- cw2017_battery.c 支持 cellwise,dual-cell / design-capacity-amh 等,
  6.12 驱动纯轮询无中断
- dts 里 firefly,battery-max-voltage / max-temp / min-temp 是电池保护
  私有属性, 内核驱动未引用 (留给上层应用), 可不移植
- 充放电三芯片 (CW2017/SC8886/FUSB302) 的原理/联动链路/完整移植/验证
  见 charging.md

## 4. 方式二: 非全功能 Type-C

　　USB3 OTG + DP altmode, 无充电管理芯片。参考板 itx-3588j / roc-rk3588s-pc / aio-3588q。

　　与方式一的差异: 没有充电芯片/电量计, OTG VBUS 由一个普通 GPIO regulator
控制, sink 只声明 5V。

### 4.1 硬件连接 (roc-rk3588s-pc 为例)

```
Type-C 口:
  CC/PD   ====> FUSB302 (I2C2_M0, 地址 0x22), INT ====> GPIO0_C4 (低有效)
  USB2    ====> u2phy0
  USB3    ====> usbdrd3_0 / usbdrd_dwc3_0
  DP lane ====> usbdp_phy0
  SBU1/SBU2 方向 ====> GPIO4_B5 / GPIO4_A7 (高有效)
  OTG VBUS 5V 使能 ====> GPIO1_B1 (vbus5v0_typec0, 高有效)
```

　　itx-3588j 差异: fusb302 INT = GPIO0_D3, SBU = GPIO4_A6/A7,
OTG VBUS 使能走 PCA9555 IO1_4。

### 4.2 设备树配置

　　参考: rk3588-firefly-roc-rk3588s-pc.dtsi (FF_TYPEC0)

```
/* 1. OTG VBUS: 普通 GPIO regulator (代替充电芯片的 otg-vbus) */
/ {
	vbus5v0_typec0: vbus5v0-typec0 {
		compatible = "regulator-fixed";
		regulator-name = "vbus5v0_typec0";
		regulator-min-microvolt = <5000000>;
		regulator-max-microvolt = <5000000>;
		enable-active-high;
		gpio = <&gpio1 RK_PB1 GPIO_ACTIVE_HIGH>;
		pinctrl-names = "default";
		pinctrl-0 = <&vbus5v0_typec0_en>;
		vin-supply = <&vcc5v0_sys>;
	};
};

/* 2. USB/PHY: 与方式一相同 (u2phy0/usbdp_phy0/usbdrd3_0/dwc3 全套) */
&u2phy0 {
	status = "okay";
};

&u2phy0_otg {
	status = "okay";
	rockchip,typec-vbus-det;
};

&dp0 {
	mode-switch;
	status = "okay";
};

&usbdp_phy0 {
	status = "okay";
	orientation-switch;
	mode-switch;
	svid = <0xff01>;
	sbu1-dc-gpios = <&gpio4 RK_PB5 GPIO_ACTIVE_HIGH>;
	sbu2-dc-gpios = <&gpio4 RK_PA7 GPIO_ACTIVE_HIGH>;

	port { ... };      // 同方式一 (orientation/mux 两个 endpoint)
};

&usbdrd3_0 {
	status = "okay";
};

&usbdrd_dwc3_0 {
	status = "okay";
	dr_mode = "otg";
	usb-role-switch;
	port { ... };      // 同方式一 (role switch endpoint)
};

/* 3. fusb302: 无充电芯片关联 */
&i2c2 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c2m0_xfer>;

	usbc0: fusb302@22 {
		compatible = "fcs,fusb302";
		reg = <0x22>;
		interrupt-parent = <&gpio0>;
		interrupts = <RK_PC4 IRQ_TYPE_LEVEL_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&usbc0_int>;
		vbus-supply = <&vbus5v0_typec0>;    // 指向 GPIO regulator
		status = "okay";

		ports { ... };                      // 同方式一

		usb_con: connector {
			compatible = "usb-c-connector";
			label = "USB-C";
			data-role = "dual";
			power-role = "dual";
			try-power-role = "sink";
			op-sink-microwatt = <1000000>;
			sink-pdos =
				<PDO_FIXED(5000, 1000, PDO_FIXED_USB_COMM)>;   // 只 5V
			source-pdos =
				<PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)>;

			mode-switch = <&dp0>;
			altmodes { ... };               // 同方式一

			ports { ... };                  // 同方式一
		};
	};
};

/* 4. DP: itx 与 pc 板 dp0 部分 */
&dp0_in_vp2 {
	status = "okay";
};

&route_dp0 {
	status = "okay";
	connect = <&vp2_out_dp0>;
};
```

　　与方式一的逐条差异:
- 无 charge-dev 属性 (没有充电芯片)
- sink-pdos 只声明 5V 一档 (无 PD 高压受电需求)
- vbus-supply 指向自己的 GPIO regulator
- itx-3588j 的 altmode vdo = <0x00001c46> (2lane+USB3),
  roc-pc 用 <0xffffffff> (capability 未知时兜底), 推荐写准确值
- itx-3588j 不加载 dp0 的 route (其 DP 显示路由规划不同), 按板实际配置

### 4.3 纯数据口裁剪 (无 DP altmode)

　　删掉: &dp0 / dp0_in_vp2 / route_dp0 / usbdp_phy0 的 mode-switch + svid /
connector 的 mode-switch + altmodes 段 / dp_altmode_mux endpoint。
usbdp_phy0 只作为 USB3 PHY 使用。

## 5. 验证测试

```
# tcpm 日志 (插拔 Type-C 观察)
dmesg | grep -i -E "fusb302|tcpm"
# 插入后应看到: Attached (sink/source), PD 协商 "negotiated 5000 mV, ..."

# 角色与状态
cat /sys/class/typec/port0/data_role      # host / device / dual
cat /sys/class/typec/port0/power_role     # source / sink
cat /sys/class/typec/port0/orientation    # normal / reversed (反插检测)

# DP altmode
ls /sys/class/drm/                        # 插 DP 线后 card?-DP-1 connected

# USB OTG
# 插 U 盘 => host 模式 => lsusb 应看到设备
# 插 PC => device 模式 => PC 识别出板子 (gadget)

# 充电 (仅全功能口)
cat /sys/class/power_supply/*-battery/capacity
cat /sys/class/power_supply/*-battery/status     # Charging/Discharging

# 常见问题:
# 1. tcpm 报 Ra/Rd 状态不停跳: CC 的 INT 引脚极性错或没上拉
# 2. OTG 不切换角色: usb-role-switch / dwc3_0_role_switch 端点没成对配置
# 3. DP altmode 不输出: mode-switch/svid 少配, 或 vdo lane 配置错
# 4. 不充电: ti,charge-current/max-charge-voltage 超出电池规格,
#    充电芯片拒绝启动
# 5. PD 只协商 5V: sink-pdos 最高档与输入能力不匹配
```
