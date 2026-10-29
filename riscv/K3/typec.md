# Type-C

　　K3 平台 Type-C 口适配笔记: fusb302 (TCPM 控制器) + usb3_porta (OTG 双
角色) + u3phy 方向切换的完整链路。以 Firefly aibox-k3 (FF_TYPE_C 分支) 为
参考板 — AIBOX-PRO 无 Type-C, 这是 K3 参考板里唯一的 Type-C 方案。与
RK3588 的差异: K3 参考板只做 5V source/sink, 无 PD 快充协议栈硬件
(无 buck-boost 充电芯片), 充电场景见对应充电文档。

## 1. 原理

### 1.1 链路全景

　　一条 Type-C 口由四个角色组成, 设备树里用 **graph (endpoint 互指)**
串起来:

```
usb-c-connector (usb_con)                    fusb302@22 (TCPM, CC 检测/PD 5V)
   port@0  role 切换  <------------------>    usb3_porta (dwc3) usb-role-switch
   port@1  方向切换  <------------------>     usb3_porta_u3phy (orientation-switch)
```

- **角色切换** (host↔device): fusb302 检测 CC 上的角色 → TCPM 框架通知
  connector → connector 的 role endpoint → dwc3 的 role switch endpoint →
  dwc3 drd.c 切 host/gadget。
- **方向切换** (正插/反插): fusb302 报告 CC 方向 → connector orientation
  endpoint → u3phy 的 orientation switch endpoint → PHY 内部把 DP/DM 与
  SS 对切到正确的引脚对。
- **VBUS**: sink 时对外取电, source 时由板级 5V regulator (GPIO 使能)
  对外供电; fusb302 本身不带功率级。

### 1.2 属性解析对照 (谁在读什么 — 全部源码核实)

| 设备树属性 | 解析者 | 有效性 |
|---|---|---|
| fcs,int_n-gpios | drivers/usb/typec/tcpm/fusb302.c (`devm_gpiod_get(dev, "fcs,int_n")`) | 有效 |
| linux,host-role-before-vbus | drivers/usb/typec/tcpm/tcpm.c | 有效 (厂商扩展) |
| vbus-supply | fusb302.c (source 态开/关) | 有效 |
| usb-role-switch | dwc3 (drd.c 注册 role switch) | 有效 |
| role-switch-default-mode | drivers/usb/common/common.c (role switch 框架) | 有效 |
| spacemit,synchronous-role-switch | drivers/usb/dwc3/drd.c | 有效 (厂商扩展) |
| monitor-vbus | drivers/usb/dwc3/gadget.c | 有效 |
| orientation-switch | drivers/phy/... (u3phy 驱动注册 typec_mux) | 有效 |
| connector 的 PD 数组 (sink/source-pdos) | tcpm.c | 有效 |

　　与 charging.md/RK3588 笔记里"遗留属性清单"不同, 本节点属性**全部有
解析**, 可放心照抄。

### 1.3 dwc3 侧的角色属性组

　　usb3_porta 基座不带 dr_mode, Type-C 用法在板级覆写时一次性补全:

```c
dr_mode = "otg";                        /* 双角色 */
usb-role-switch;                        /* 注册 role switch (graph 接入点) */
spacemit,synchronous-role-switch;       /* 厂商: 切角色同步完成, 不异步延迟 */
role-switch-default-mode = "peripheral";/* 上电默认 device 态 (等 CC 判定) */
monitor-vbus;                           /* gadget 侧监测 VBUS 决定行为 */
```

## 2. 硬件连接

　　参考板: aibox-k3。Type-C 座 24P 全功能接法:

| 信号 | 接向 | 说明 |
|---|---|---|
| CC1/CC2 | fusb302 (0x22) 的 CC1/CC2 脚 | 角色与方向检测, **必须** 5.1k±% Rp/Rd 由 fusb302 内部处理 |
| D+/D- | usb3_porta_u2phy (0xcad20000) DP/DM | 经 Type-C 座 SBU 旁的 D+/D- 针 |
| SS1±/SS2± | usb3_porta_u3phy (0xcad30000) SS 对 | SuperSpeed 双通道 |
| VBUS | 板上 5V 负载开关 (GPIO60 使能) ↔ 座 VBUS | source 对外 5V/3A; sink 时外部输入 |
| INT_N | fusb302 INT → GPIO58 | 中断通知 TCPM |
| GND/SHIELD | - | 外壳地 |

板级管控脚:

| 信号 | GPIO | IO 域 | 配置 |
|---|---|---|---|
| VBUS 使能 (usb20_otg_en) | GPIO60 | 1.8V | 高有效 |
| fusb302 INT | GPIO58 | 1.8V | 内部上拉, 低有效中断 |

接线核对要点:

- CC 脚直连 fusb302, 中间不得串电阻 (芯片内部集成 Rp/Rd 切换)。
- VBUS 负载开关要能双向阻断 (sink 态不能把外部 5V 倒灌进本板 5V 轨), 用
  理想二极管/背靠背 PMOS 方案。
- SS 对的 TX/RX 极性随正反插变化, 由 u3phy orientation switch 在芯片内
  交换 — PCB 不需要额外开关电路。

## 3. 内核配置

　　k3_defconfig 现状: `CONFIG_TYPEC=y`、`CONFIG_TYPEC_FUSB301=m` (另一颗
芯片!)。**缺 TCPM 框架与 fusb302 驱动**, 必须补:

```
# k3_defconfig 需追加:
CONFIG_TYPEC_TCPM=y        # TCPM 框架 (fusb302 依赖)
CONFIG_TYPEC_FUSB302=y     # fusb302 TCPM 控制器驱动
CONFIG_USB_ROLE_SWITCH=y   # role switch 框架 (dwc3/connector 依赖; 常已随其他选中)
CONFIG_CONFIGFS_FS=y       # gadget 功能配置 (device 态挂 Android/MSD 时)
# gadget 按需: CONFIG_USB_CONFIGFS / USB_F_MASS_STORAGE / USB_F_FS 等
```

## 4. 设备树配置

　　参考板: aibox-k3 (FF_TYPE_C 分支), 完整展开如下 (挂在 i2c0 总线的
fusb302; 你的板子按自己的 I2C 口调整):

```dts
/ {
	vcc5v0_usb20_typec: vcc5v0-usb20-typec-regulator {
		compatible = "regulator-fixed";
		regulator-name = "vcc5v0_usb20_typec";
		regulator-min-microvolt = <5000000>;
		regulator-max-microvolt = <5000000>;
		enable-active-high;
		gpio = <&gpio K3_GPIO(60) GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&usb20_otg_en_cfg>;
		pinctrl-names = "default";
		vin-supply = <&vcc5v0_sys>;
		status = "okay";
	};
};

&i2c0 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c0_0_cfg>;              /* 基座组, i2c0 默认位置 */

	usbc0: fusb302@22 {
		compatible = "fcs,fusb302";
		reg = <0x22>;
		fcs,int_n-gpios = <&gpio K3_GPIO(58) GPIO_ACTIVE_LOW>;
		linux,host-role-before-vbus;        /* VBUS 到来前先按 CC 定 host 角色 */
		pinctrl-names = "default";
		pinctrl-0 = <&usbc0_int_cfg>;
		vbus-supply = <&vcc5v0_usb20_typec>;
		status = "okay";

		usb_con: connector {
			compatible = "usb-c-connector";
			label = "USB-C";
			data-role = "dual";
			power-role = "dual";
			try-power-role = "sink";
			op-sink-microwatt = <1000000>;  /* 5V/1A = 5W 吸收能力 */
			sink-pdos =
				<PDO_FIXED(5000, 1000, PDO_FIXED_USB_COMM)>;
			source-pdos =
				<PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)>;

			ports {
				#address-cells = <1>;
				#size-cells = <0>;

				port@0 {
					reg = <0>;
					usbc0_role_sw: endpoint@0 {
						remote-endpoint = <&dwc3_0_role_switch>;
					};
				};

				port@1 {
					reg = <1>;
					usbc0_orien_sw: endpoint {
						remote-endpoint = <&u2phy0_orientation_switch>;
					};
				};
			};
		};
	};
};

/* PHY 与控制器: 注意 orientation 端点在 u3phy 节点上 (label 叫 u2phy0_* 是
 * Firefly 的命名误导, 节点归属以挂载位置为准) */
&usb3_porta_u2phy {
	status = "okay";
};

&usb3_porta_u3phy {
	status = "okay";

	orientation-switch;

	port {
		#address-cells = <1>;
		#size-cells = <0>;
		u2phy0_orientation_switch: endpoint@0 {
			reg = <0>;
			remote-endpoint = <&usbc0_orien_sw>;
		};
	};
};

&usb3_porta {
	dr_mode = "otg";
	usb-role-switch;
	spacemit,synchronous-role-switch;
	role-switch-default-mode = "peripheral";
	monitor-vbus;
	status = "okay";

	ports {
		#address-cells = <1>;
		#size-cells = <0>;
		port@0 {
			reg = <0x0>;
			dwc3_0_role_switch: endpoint {
				remote-endpoint = <&usbc0_role_sw>;
			};
		};
	};
};

&pinctrl {
	usb20_otg_en_cfg: usb20-otg-en-cfg {
		usb20-otg-en-pin {
			pinmux = <K3_PADCONF(60, 0)>;
			bias-disable;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};

	usbc0_int_cfg: usbc0-int-cfg {
		usbc0-int-pin {
			pinmux = <K3_PADCONF(58, 0)>;
			bias-pull-up;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};
};
```

### 4.2 属性速查与陷阱

| 属性/节点 | 说明 |
|---|---|
| try-power-role = "sink" | 双角色口的首选初始角色; source-pdos 声明 5V/3A 对外能力 |
| op-sink-microwatt | 对外声明吸收功率; 仅 5V 方案填 5W 级 |
| PDO_FIXED(5000, x, USB_COMM) | K3 参考板只做固定 5V (pd.h 宏, 由基座链引入 — 自带 include `dt-bindings/usb/pd.h`!) |
| reg = <0x22> | fusb302 固定地址 |
| role-switch-default-mode | "peripheral"/"host"; 建议 peripheral (等 CC 判定) |

陷阱清单:

- **pd.h 头文件**: PDO_FIXED 宏来自 `<dt-bindings/usb/pd.h>`, 原本由
  k3-firefly-common.dtsi include — 公共文件禁用后必须写进自己的 dts。
- **orientation endpoint 挂在 u3phy 不是 u2phy**: Firefly 的 label 名
  (u2phy0_orientation_switch) 是误导, 实际节点在 usb3_porta_u3phy 下;
  抄错节点归属则方向切换失效 (反插不识别)。
- CONFIG 只开了 TYPEC 不够: TCPM 与 FUSB302 缺省都没编 (且别与
  TYPEC_FUSB301 混淆, 那是另一颗芯片), /sys/class/typec 不出 port0 时先
  查配置。
- fusb302 INT 中断不触发: CC 检测全靠中断驱动, INT 脚 pinctrl 忘配/极性
  反 → 角色永不切换, dmesg 也可能静默。
- source 态 VBUS 无输出: vbus-supply regulator 的 GPIO 电路/使能极性
  (enable-active-high) 与硬件不符。

## 5. 验证测试

```bash
# 1. Type-C 口出现
ls /sys/class/typec/              # port0
cat /sys/class/typec/port0/data_role      # 应随插拔在 [host] device 间切换
cat /sys/class/typec/port0/power_role

# 2. 正反插方向 (反插后 data_role 依旧正确 = orientation 链 OK)
#    反复正插/反插 U 盘观察:
dmesg -w &                        # 枚举日志 + "orientation" 相关打印
lsusb

# 3. source 态输出 (接手机/小灯量 VBUS)
#    板作 source: VBUS 5V; 手机显示"正在充电"
#    板作 sink (接 PC): /sys/class/typec/port0/power_role 变 sink, dmesg 见 vbus 5V in

# 4. device (gadget) 态: 板接 PC 应枚举 (默认 peripheral)
dmesg | grep -iE "dwc3|gadget" | tail

# 5. 排查顺序
#    a) zcat /proc/config.gz | grep -E "TCPM|FUSB302"     -> 驱动未编 (最常见)
#    b) dmesg | grep -i fusb302                            -> I2C/INT 报错
#    c) i2cdetect -y 0 | grep -w 22                        -> 芯片在位
#    d) data_role 不切: CC 焊接/INT 脚
#    e) 反插失效: orientation endpoint 归属 (u3phy!)
```
