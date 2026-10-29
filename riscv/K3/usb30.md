# USB3.0

　　K3 平台 USB3.0 Type-A 口适配笔记: 4 路 USB3 (usb3_porta/b/c/d, DWC3 +
双 PHY) 的 host 用法。以 Firefly AIBOX-PRO-K3 (porta 单 Type-A) / aibox-k3
(portb/c 双口 + VL817 一扩四) 为参考板。Type-C/OTG 用法在 typec.md。

## 1. 原理

### 1.1 四路 USB3 控制器 (k3.dtsi 基座, 全部 disabled)

| 控制器 | DWC3 基址 | u2phy | u3phy | 中断 | 备注 |
|---|---|---|---|---|---|
| usb3_porta | 0xcad00000 | 0xcad20000 | 0xcad30000 | 118/156 | u3phy 兼 "spacemit,k3-typec-switch", 可做 OTG/Type-C |
| usb3_portb | 0x81400000 | 0x81500000 | 0x81f00000 | 121/157 | 纯 host |
| usb3_portc | 0x81700000 | 0x81800000 | 0x82000000 | 122/158 | 纯 host |
| usb3_portd | 0x81a00000 | 0x81b00000 | 0x82100000 | 123/159 | 纯 host |

　　每路 = 1 个 DWC3 控制器 (compatible "spacemit,k1-dwc3", 驱动
`drivers/usb/dwc3/dwc3-generic-plat.c`) + 2 个 PHY
("spacemit,k3-usb2-phy" / "spacemit,k3-usb3-phy")。基座节点自带头部 quirk
组与 `phys = <&u3phy>, <&u2phy>` 双 PHY 引用, 板级只做: 使能三节点 +
dr_mode + (可选) vbus-supply。

　　portb/c/d 基址在 0x81400000 段、porta 在 0xcad00000 段 — debugfs/平台
设备按地址查时别在同一个段里找。

### 1.2 porta 基座原文 (自查起点, b/c/d 同构)

```c
usb3_porta_u2phy: phy@cad20000 {
	compatible = "spacemit,k3-usb2-phy";
	reg = <0x0 0xcad20000 0x0 0x200>;
	#phy-cells = <0>;
	status = "disabled";
};

usb3_porta_u3phy: phy@cad30000 {
	compatible = "spacemit,k3-usb3-phy", "spacemit,k3-typec-switch";
	spacemit,syscon-apmu = <&syscon_apmu>;
	spacemit,syscon-apb-spare = <&pll>;
	clocks = <&syscon_apmu CLK_APMU_USB3_PORTA_BUS>;
	reg = <0x0 0xcad30000 0x0 0x200>,
	      <0x0 0xcad40000 0x0 0x200>;
	#phy-cells = <0>;
	status = "disabled";
};

usb3_porta: usb3@cad00000 {
	compatible = "spacemit,k1-dwc3";
	reg = <0x0 0xcad00000 0x0 0x10000>;
	spacemit,syscon-apmu = <&syscon_apmu 0x3c4>;
	interrupts = <118 IRQ_TYPE_LEVEL_HIGH>,
		     <156 IRQ_TYPE_LEVEL_HIGH>;
	interrupt-names = "dwc3", "wakeup";
	interrupt-parent = <&saplic>;
	clocks = <&syscon_apmu CLK_APMU_USB3_PORTA_BUS>;
	resets = <&syscon_apmu RESET_APMU_USB3_PORTA>;
	phys = <&usb3_porta_u3phy>, <&usb3_porta_u2phy>;
	phy-names = "usb3-phy", "usb2-phy";
	phy_type = "utmi";
	snps,dis_enblslpm_quirk;
	snps,dis_u2_susphy_quirk;
	snps,dis_u3_susphy_quirk;
	snps,dis-del-phy-power-chg-quirk;
	snps,dis-tx-ipgap-linecheck-quirk;
	snps,parkmode-disable-ss-quirk;
	status = "disabled";
};
```

　　基座节点**不带 dr_mode** (默认 peripheral) — 板级必须写
`dr_mode = "host"`, 这是"配了 PHY 不工作"的头号原因。

## 2. 硬件连接

　　Type-A USB3 = 9 针: USB3 差分对 (SSRX±/SSTX±, 走 u3phy 专用模拟 pad)
+ USB2 差分对 DP/DM (走 u2phy 专用模拟 pad) + VBUS + GND。DP/DM 与
SS 对都是专用模拟 pad, **不进 pinctrl 复用体系**, 软件无引脚配置项。

参考板板级管控信号 (纯 GPIO, 与协议无关):

| 参考板 | 信号 | GPIO | 配置 | IO 域 | 作用 |
|---|---|---|---|---|---|
| AIBOX-PRO | VBUS 使能 | GPIO100 | 高有效, 常开 | 1.8V | Type-A 5V 输出 (regulator-fixed) |
| AIBOX-PRO | HUB 复位 | GPIO77 | hog 输出低 | 3.3V | 板载 hub 复位保持 |
| AIBOX-PRO | USB 选择 | GPIO118 | hog 输出高, 上拉 | 1.8V | USB 多路开关切到 host 侧 |
| aibox-k3 | (portb) hub 复位 | GPIO53 | 预留, 硬件自复位 | - | VL817 3V3_RST, 驱动不管控 |

接线核对要点:

- VBUS 供电能力: Type-A 口按 ≥900mA (USB3 规格) 设计; GPIO 驱动负载开关
  PMOS, 不直推 VBUS。
- AIBOX-PRO 两个 hog 挂在 `&gpio` 节点下 (gpio-hog 语法), 开机由 gpio
  驱动直接打到目标电平, 不占用户 GPIO。
- SS 对与 DP/DM 各走各自 PHY, 硬件上对应 Type-A 座的不同针脚; 只接
  DP/DM 不接 SS 对 = 降速为 480M 也能工作, 反之不通。

## 3. 内核配置

　　k3_defconfig 已齐, **无需改动** (与 usb20.md 同一套):

```
CONFIG_USB_DWC3=y
CONFIG_USB_DWC3_GENERIC_PLAT=y     # spacemit,k1-dwc3
CONFIG_USB_XHCI_HCD=y
CONFIG_USB_XHCI_PCI=y              # 插 PCIe USB 扩展卡时用
```

## 4. 设备树配置

### 4.1 方式一: 单 Type-A + GPIO 管控 (AIBOX-PRO porta)

```dts
/ {
	usb30_vcc5v0_en: regulator-usb30-vcc5v0-host {
		compatible = "regulator-fixed";
		regulator-name = "usb30_vcc5v0_host";
		regulator-min-microvolt = <5000000>;
		regulator-max-microvolt = <5000000>;
		gpios = <&gpio K3_GPIO(100) GPIO_ACTIVE_HIGH>;
		enable-active-high;
		regulator-boot-on;
		regulator-always-on;
		pinctrl-names = "default";
		pinctrl-0 = <&usb30_vcc5v0_en_cfg>;
		status = "okay";
	};
};

/* 两个 GPIO 直接开机打平 (hog), 不占用户态 */
&gpio {
	pinctrl-names = "default";
	pinctrl-0 = <&usb30_hub_rst_cfg>, <&usb_sel_cfg>;

	usb30-hub-rst-hog {
		gpio-hog;
		gpios = <K3_GPIO(77) GPIO_ACTIVE_HIGH>;
		output-low;
		line-name = "usb30_hub_rst";
	};

	usb-sel-host-hog {
		gpio-hog;
		gpios = <K3_GPIO(118) GPIO_ACTIVE_HIGH>;
		output-high;
		line-name = "usb_sel_host";
	};
};

&usb3_porta_u2phy {
	status = "okay";
};

&usb3_porta_u3phy {
	status = "okay";
};

&usb3_porta {
	vbus-supply = <&usb30_vcc5v0_en>;   /* VBUS 交给 regulator 框架 */
	dr_mode = "host";                   /* 必写! 基座默认 peripheral */
	status = "okay";
};

&pinctrl {
	usb30_vcc5v0_en_cfg: usb30-vcc5v0-en-cfg {
		usb30-vcc5v0-en-pin {
			pinmux = <K3_PADCONF(100, 0)>;
			drive-strength = <25>;
			power-source = <1800>;
			bias-disable;
		};
	};

	usb30_hub_rst_cfg: usb30-hub-rst-cfg {
		usb30-hub-rst-pin {
			pinmux = <K3_PADCONF(77, 0)>;
			drive-strength = <25>;
			power-source = <3300>;
			bias-disable;
		};
	};

	usb_sel_cfg: usb-sel-cfg {
		usb-sel-pin {
			pinmux = <K3_PADCONF(118, 0)>;
			drive-strength = <25>;
			power-source = <1800>;
			bias-pull-up;
		};
	};
};
```

### 4.2 方式二: 多口直出 + VL817 一扩四 (aibox-k3)

　　portc/portd 纯直出 (三行使能, 以 portc 为例; portd 在 aibox-k3 上是
与 FF_GMAC0 一起开的, 自研板按需独立使能):

```dts
&usb3_portc_u2phy { status = "okay"; };
&usb3_portc_u3phy { status = "okay"; };
&usb3_portc { status = "okay"; };      /* 纯 host 直出时 dr_mode 可省? 不可,
                                          纯 host 直出也要写 dr_mode="host" */
```

　　portb 挂 VL817 双核 hub (USB2+USB3 各 4 口, `peer-hub` 互相指认;
aibox-k3 写法, hub 复位由硬件完成, GPIO53 仅预留):

```dts
&usb3_portb_u2phy { status = "okay"; };
&usb3_portb_u3phy { status = "okay"; };

&usb3_portb {
	status = "okay";
	#address-cells = <1>;
	#size-cells = <0>;

	/* VL817 USB2.0 hub (4 ports) */
	hub_2_0: hub@1 {
		compatible = "usb2109,2817";
		reg = <1>;
		peer-hub = <&hub_3_0>;
	};

	/* VL817 USB3.0 hub (4 ports) */
	hub_3_0: hub@2 {
		compatible = "usb2109,817";
		reg = <2>;
		peer-hub = <&hub_2_0>;
	};
};
```

　　说明: hub@1/hub@2 的 reg 是 hub 在该总线上的**设备地址** (插上后枚举
顺序固定 1/2), 配合驱动内建 on-board hub 支持
(`usb2109,2817`/`usb2109,817` 是内核认可的板载 hub compatible); 若无此
声明 hub 也能用 (普通枚举), 声明后获得 peer-hub 联动复位等管理能力。

### 4.3 属性速查与陷阱

| 属性 | 说明 |
|---|---|
| dr_mode | host / otg / peripheral; **host 口必写 host** (基座默认 peripheral) |
| vbus-supply | regulator 框架管控 VBUS; always-on 型也可不挂 (纯供电) |
| gpio-hog | 开机固定电平; 挂在 &gpio 下, 写在普通节点无效 |
| usb-role-switch | OTG 才用 (typec.md), host 口别加 |
| #address-cells/#size-cells | 挂板载 hub 子节点时 usb3_portb 节点需补 |

陷阱清单:

- **dr_mode 忘写** → 枚举成 gadget/不工作; XHCI 不出现, dmesg 无 "xHCI
  host controller"。
- 三个节点 (控制器 + 两个 PHY) **缺一不可**, 只开控制器不开 u3phy = 2.0
  降速通, 只开 u3phy 不开 u2phy = 大部分设备不通 (连枚举都靠 2.0)。
- hub@1/hub@2 的 reg 不是随意值: 与 hub 硬件枚举地址对应, 参考板为 1/2。
- gpio-hog 的 gpios 展开是 `<K3_GPIO(77) GPIO_ACTIVE_HIGH>` 两格 — K3_GPIO
  宏自带 bank/pin 两格, 与普通 gpios 属性写法一致。

## 5. 验证测试

```bash
# 1. 控制器与总线
dmesg | grep -iE "xhci|dwc3" | head     # 每个使能的口应有一组 xHCI 注册
ls /sys/bus/platform/devices/ | grep -E "cad0|814|817|81a"
lsusb -t                                  # 树状拓扑: 5000M/480M 速率一目了然

# 2. 速率验证 (插 USB3 U 盘)
lsusb -t                                  # 设备应挂 5000M 分支
dd if=/dev/zero of=/mnt/usb/test bs=1M count=500 oflag=direct
                                          # USB3 U 盘应有 200-400MB/s 级

# 3. hub 扩展验证 (方式二)
lsusb -t                                  # 应见 VL817 (2109:0817/2817) 及其下 4 口

# 4. VBUS 供电 (方式一)
# 插入手机等 sink 设备, dmesg 应见枚举为 USB 设备 (不是充电专态)
# 万用表量 VBUS: 常电设计应恒 5V

# 5. 排查顺序
#    a) dr_mode 是否 host (dmesg 里 controller 出现 "host" 字样)
#    b) 三节点 status 是否全 okay
#    c) dmesg | grep -i phy               -> PHY probe 报错
#    d) VBUS 有电但枚举失败               -> SS 对焊接/座子
```
