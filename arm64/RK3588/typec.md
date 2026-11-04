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

## 6. 实战实录: DP altmode 协商成功但无画面 (aio-3588l, 2026-11-03)

　　AIO-3588L (rk3588_6.12.69_sdk, 6.12.81 内核) TypeC0 口经 USB-C→DP
转接器 (Fresco Logic FL7102 billboard, 自带 USB2 hub) 接 DP 触摸屏
(WingCoolTouch): PD 全程走通、DP altmode 成功进入、转接器的 USB hub /
billboard / 触摸屏全部正常枚举, 但 `card0-DP-1` 恒 disconnected、屏无
画面。最终根因是 usb-c-connector 的 OF 图缺一条通往 dp0 的边, 与引脚
移植完全无关。本节记录完整排查链、机制、修复与三个大坑。

### 6.1 排查链 (逐层证明, 断点在最后一层)

　　先打开调试再插拔一次 (动态调试重启后失效, 需重开):

```
# 1) 角色/方向实时值
cat /sys/class/typec/port0/{power_role,data_role,orientation}
# 实测: [source] / [host] / normal   (板子正确做了 SRC/DFP-D)

# 2) PD 信令全程回放 (核心证据; debugfs 文件只能 cat 不能 pull)
cat /sys/kernel/debug/usb/tcpm-6-0022/log
#   SRC_ATTACHED -> Discover Identity/SVIDs/MODES (SVID 0xff01)
#   -> DFP_TO_UFP_ENTER_MODE ... finished + Rx VDM 0xff01a144 (ACK)
#   -> Rx VDM 0xff01a150 / 0xff01a151 (DP Status/Config Update)
#   => PD 与 DP altmode 信令 100% 正常

# 3) 动态调试开 8 个文件 + printk
echo 'file drivers/usb/typec/tcpm/tcpm.c +p
file drivers/usb/typec/tcpm/fusb302.c +p
file drivers/usb/typec/altmodes/displayport.c +p
file drivers/usb/typec/class.c +p
file drivers/usb/typec/mux.c +p
file drivers/usb/typec/bus.c +p
file drivers/phy/rockchip/phy-rockchip-usbdp.c +p
file drivers/gpu/drm/rockchip/dw-dp.c +p' > /sys/kernel/debug/dynamic_debug/control
echo 7 > /proc/sys/kernel/printk
```

　　插屏后逐层对证据:

| 环节 | 证据 | 结论 |
|---|---|---|
| usbdp phy mux 回调 | dmesg `received DP status: 0x0000008a, conf: 0x00000406, mode:4` | 被调用; lane 配置已下发; status bit1 = HPD 已由转接器替屏拉起 |
| dw-dp debugfs | `cat /sys/kernel/debug/dri/0/dw-dp0/dp_status` => `usbdp hpd: yes / hpd status: unplug` | dw-dp 认为没插屏 |
| dw-dp mux 回调 | dw-dp.c 的 `hotplug from the usbdp` 等 dbg 一条不出现 | **未被调用 => 断点在这** |
| mux 设备 | `ls /sys/class/typec_mux/` => `fed80000.phy-mux` + `fde50000.dp-mux` 都在 | dp 的 mux 注册了, 但无人调用 |
| connector | `cat /sys/class/drm/card0-DP-1/status` => disconnected | 无 EDID, 无画面 |
| billboard | usb 总线恒枚举 `1d5c:7102 Generic Billboard` | 转接器认为 DP 未建立 (billboard 只在 DP 配置未成功时保持枚举) |

### 6.2 机制与根因

　　6.12 的 dw-dp 节点带 `mode-switch` 属性时 (dw_dp_probe):
- 注册自己的 typec mux (`dw_dp_setup_typec_mux`, 设备名
  `fde50000.dp-mux`), 并置 `dp->usbdp_hpd = true`
- 此模式下 HPD 的**唯一软件路径**是它的 mux 回调
  `dw_dp_typec_mux_set()`: 更新 `dp->hotplug.status` + schedule hpd_work
- usbdp phy 写的 vo-grf bits[11:10] (hpd_trigger) 是 PHY 层 sink HPD
  配置选择, dw-dp 软件不消费, 替代不了这条路径

　　而 typec core 给 altmode 挑 mux 的方式 (typec_port_register_altmode
-> typec_mux_get(&port->dev) -> fwnode_connection_find_matches): **沿
usb-c-connector 的 OF 图逐边收集远端设备中带 `mode-switch` 属性者**
(非递归, 上限 TYPEC_MUX_MAX_DEVS=3), typec_mux_set() 把整个集合挨个调
一遍。原有图只有两条边:

```
connector port@0 <-> usbdp_phy0_orientation_switch   (orientation-switch)
connector port@1 <-> usbdp_phy0_dp_altmode_mux       (mode-switch, 命中)
```

　　dp0 虽带 mode-switch 属性且 mux 已注册, 但**不在 connector 图里**,
永远进不了集合 => `dw_dp_typec_mux_set()` 无人调用 => `hotplug.status`
恒 false => HPD unplug。修复 = 给 connector 图补一条边直达 dp0 节点
(typec 匹配只要求走到带 mode-switch 的节点, 不关心挂在 dp0 哪个 port)。

　　版本对照 (解释"为什么别处没这问题"): 引脚三方一致 (5.10/6.1/6.12
逐项核对过); 6.1 官方 aio dtsi **根本没启用 &dp0** —— 不存在"以前能
亮"的基准, 6.12 是首次把 dp0 挂上 TypeC0; usbdp phy 的 mux 回调两版
等价; dw-dp 的 HPD 路径两版也等价; 6.12 的 typec_mux_match 是新版
(只查 mode-switch 属性, 旧版按 svid 匹配)。

### 6.3 修复 dts (aio-3588l.dtsi, 已验证出画面 + 触摸)

```
&i2c6 {
	usbc0: fusb302@22 {
		...
		usb_con: connector {
			...
			ports {
				port@0 { /* usbc0_orien_sw -> usbdp_phy0_orientation_switch */ };
				port@1 { /* dp_altmode_mux -> usbdp_phy0_dp_altmode_mux */ };

				port@2 {                          /* 新增 */
					reg = <2>;
					usbc0_dp0_mux: endpoint {
						remote-endpoint = <&dp0_typec_mux>;
					};
				};
			};
		};
	};
};

/* dp0 新增 port@2 与 connector 互指 (为何不用 port@1: 见 6.4 坑一) */
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

　　修复后事件时序 (mux 集合按图上 port 序号顺序调用, lane 切换先于
HPD): altmode notify -> [phy-mux] lane 切 DP + mode_change -> [dp-mux]
hotplug.status=true + hpd_work -> connector connected -> dw-dp enable ->
usbdp phy 重新 setup 消费 mode_change (lane mux 写硬件) -> link
training -> 出画面。

### 6.4 三个大坑

　　1. **图边不能挂 dp0 的 port@1。** port@1 是 DRM 下游端口,
`dw_dp_bridge_attach()` -> `drm_of_find_panel_or_bridge(dp0, port=1)`
拿它找 panel/next bridge; 连到 connector (两者都不是) 会返回
-EPROBE_DEFER(-517), 启动报 `dw-dp fde50000.dp: failed to attach bridge:
-517`, dw-dp 直接 probe 失败。第一版修复就栽在这。正解: dp0 新增
port@2, port@1 (dp0_out) 保持空。

　　2. **USB-A→C 烧录线插 TypeC0 是 SNK 死循环, 勿误判。** A→C 线在
C 端拉 Rp, 板子 (DRP) 识别为 SNK attach 后等 Source_Capabilities, A 口
永不发 PD => HARD_RESET 循环 => 超时停留 5V, 无害。识别特征: 插入后
dmesg 有 `charger = USB_SDP_CHARGER` + gadget 枚举 (USB_STATE=
CONFIGURED)。tcpm log 里的 SNK+HARD_RESET 若发生在烧录线插入时, 与
DP 转接器无关 —— 排查 DP 时曾被它带偏一轮。

　　3. **probe 顺序竞争 (潜在, 本板未触发)。** 补边后 typec_mux_get
要求 `fde50000.dp-mux` 已注册; 若 fusb302 probe 早于 dw-dp, altmode
注册会 defer 且 vendor tcpm 忽略返回值不重试 => PD 正常但 altmode 不
协商。识别: tcpm log 里 PD 走完但没有 ENTER_MODE。若遇到: 让 dw-dp
probe 提前, 或内核侧给 altmode 注册补 defer 重试。

### 6.5 验证

```
# 启动阶段: 不得出现 failed to attach bridge
dmesg | grep -E "dw-dp|attach bridge"

# 插 DP 转接器 + 屏后:
cat /sys/class/drm/card0-DP-1/status        # => connected
dmesg | grep "hotplug from the usbdp"       # dw-dp mux 回调出现
dmesg | grep 1d5c                           # billboard 不再枚举 (DP 成功后撤下)

# 最终状态 (2026-11-03 实测): 显示 + WingCoolTouch 触摸全部正常
modetest -M rockchip -c                     # DP-1 connected
```

### 6.6 DP 音频: 声卡已自带, 无声只差默认路由 (2026-11-04)

　　画面修好后的第二个问题: DP 屏不出声。结论先行 —— **内核音频链从未坏
过**: 声卡 `rockchip-dp0` 一直注册着 (来自 firefly-common.dtsi 的 FF_DP0
段, 模板同 rk3588s-evb.dtsi 的 dp0-sound, 板级**无需重复添加**)。无声纯粹
是 pipewire/wireplumber 的默认输出还指着 ES8388, 把默认 sink 切过去即可。

音频链与 ALSA 层验证:

```
# 链路: spdif_tx2 (cpu) -> "rockchip,hdmi" machine 驱动
#        -> hdmi-audio-codec (dw-dp probe 注册的平台设备, .spdif=1) => 声卡 rockchip-dp0
aplay -l                                    # rockchip-dp0 在列 (本次实测 card 4)
speaker-test -D plughw:4,0 -c 2 -t sine     # 绕开 pipewire 直测 => 屏喇叭出声 (实测)
```

　　ALSA 直测出声而播放视频无声 => 问题锁定在用户空间路由, 不在内核:

```
# sink 编号动态, 每次先 status 看编号再 set-default
runuser -u firefly -- env XDG_RUNTIME_DIR=/run/user/1000 wpctl status
#   Sinks:  52  ALSA 插卡 es8388 (默认 *)
#           58  Display Port                       <- 想要的
runuser -u firefly -- env XDG_RUNTIME_DIR=/run/user/1000 wpctl set-default 58
```

　　三个坑:
　　1. **root 直接 `wpctl status` 报 "Could not connect to PipeWire"** —
pipewire session 属 firefly(uid 1000), root 没有自己的 session, 必须借
`XDG_RUNTIME_DIR=/run/user/1000`(runuser / sudo -u 均可)。
　　2. 设备上 **没有 pactl**, 只有 wpctl(/usr/bin)。
　　3. **拔屏即回落**: DP sink 随屏注销, wireplumber 默认自动回落 ES8388;
重插屏要重新 set-default, dp-sound 报 "not found" 多半是屏没插着。

　　一键脚本已装板端 `/usr/local/bin/dp-sound`(root 也能跑):

```sh
#!/bin/sh
export XDG_RUNTIME_DIR=/run/user/1000
ID=$(wpctl status | grep "Display Port" | head -1 | grep -oE "[0-9]+\." | tr -d ".")
if [ -n "$ID" ]; then
    wpctl set-default "$ID" && echo "DP audio is now the default output (sink $ID)"
else
    echo "Display Port sink not found (screen unplugged?)"
    exit 1
fi
```

　　GUI 同样能切: 设置 → 声音 → 输出 → 选 "Display Port"。播放验证:

```
sudo -u firefly XDG_RUNTIME_DIR=/run/user/1000 gst-play-1.0 4K_H264_bird.mp4
```
