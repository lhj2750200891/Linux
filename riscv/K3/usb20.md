# USB2.0

　　K3 平台 USB2.0 专用 host 口适配笔记 (k3.dtsi 的 usb2_host, 非 USB3 口
的伴生 2.0)。以 Firefly aibox-k3 / AIBOX-PRO-K3 为参考板, 覆盖控制器结构、
VBUS 供电管控两种方式与内核配置。

## 1. 原理

### 1.1 K3 的 USB 控制器全景

　　K3 共 5 路 USB (k3.dtsi 基座, 全部 disabled, 全部是 **DWC3** 内核):

| 控制器 | 基址 | PHY | 定位 | 详见 |
|---|---|---|---|---|
| usb2_host | 0xc0a00000 | 仅 u2phy (0xc0a20000) | **专用 USB2 host** | 本篇 |
| usb3_porta | 0xcad00000 | u3phy+u2phy (0xcad2/30000) | OTG/Type-C 能力口 | usb30.md / typec.md |
| usb3_portb/c/d | 0x81400000 起 | u3phy+u2phy | Type-A USB3 | usb30.md |

　　本篇只讲第一行: usb2_host 是**独立**的 USB2 控制器 (不是 USB3 口的
伴生通道), 与 RK3588 的 usb_host0/1 (EHCI) 对应物是它。

### 1.2 基座节点 (k3.dtsi 原文, 自查起点)

```c
usb2_host_u2phy: phy@c0a20000 {
	compatible = "spacemit,k3-usb2-phy";
	reg = <0x0 0xc0a20000 0x0 0x200>;
	#phy-cells = <0>;
	status = "disabled";
};

usb2_host: usb2@c0a00000 {
	compatible = "spacemit,k1-dwc3";
	reg = <0x0 0xc0a00000 0x0 0x10000>;
	spacemit,syscon-apmu = <&syscon_apmu 0x7c>;
	interrupts = <105 IRQ_TYPE_LEVEL_HIGH>,
		     <155 IRQ_TYPE_LEVEL_HIGH>;      /* dwc3 + wakeup */
	interrupt-parent = <&saplic>;
	clocks = <&syscon_apmu CLK_APMU_USB2_BUS>;
	resets = <&syscon_apmu RESET_APMU_USB2>;
	phys = <&usb2_host_u2phy>;
	phy-names = "usb2-phy";
	phy_type = "utmi";
	snps,dis_enblslpm_quirk;
	snps,dis_u2_susphy_quirk;
	snps,dis-del-phy-power-chg-quirk;
	snps,dis-tx-ipgap-linecheck-quirk;
	dr_mode = "host";            /* 专用 host, 不可改 OTG (无 u3phy/角色切换) */
	maximum-speed = "high-speed";
	status = "disabled";
};
```

　　驱动栈: `drivers/usb/dwc3/dwc3-generic-plat.c` 按 "spacemit,k1-dwc3"
匹配 (CONFIG_USB_DWC3_GENERIC_PLAT, Kconfig 里 `default USB_DWC3` 自动
随主驱动开); 上层 xHCI (CONFIG_USB_XHCI_HCD=y)。quirk 组是厂商调好的
稳定性参数, 覆写时原样保留。

### 1.3 DP/DM 引脚的特殊性

　　USB DP/DM 走**专用模拟 pad**, 不在 pinctrl 的 K3_PADCONF 复用体系里
(全 pad 表中查不到 usb 复用组), 设备树/软件层面没有"引脚配置"这一步。
软件要做的只有三件事: 使能控制器与 PHY 节点、(可选) VBUS 供电管控、内核
配置。

## 2. 硬件连接

　　专用 USB2 口的典型板级 (参考 aibox-k3 的 "USB2.0 TYPE-A" 注释):

| 信号 | 来源 | 说明 |
|---|---|---|
| DP/DM | usb2_host_u2phy (0xc0a20000 对应模拟 pad) | 直接连 Type-A 座, 90Ω 差分走线 |
| VBUS 5V | 板上电源, 可经 GPIO 使能 (方式二) | Type-A host 口须对外供 5V |
| GND | - | 与外壳地相连 |

参考板供电差异:

| 参考板 | VBUS/口电管控 | 控制脚 |
|---|---|---|
| aibox-k3 | 无管控, 上电常供 | - |
| AIBOX-PRO (FF_USB20_HOST) | regulator-fixed 由 GPIO 控 | GPIO102, 高有效, 1.8V 域 |

接线核对要点:

- USB2 口对外供电能力按 HUB/设备需求设计 (典型 ≥500mA/口); GPIO 使能脚
  驱动的是 PMOS/负载开关, 不是直接推 VBUS。
- AIBOX-PRO 的 GPIO102 实际还兼管板上 USB2 HUB 供电 (宏与 4G 模组共享
  hub20/4g 电力拓扑), 自研板无 HUB 时 regulator 直接给座子 VBUS。

## 3. 内核配置

　　k3_defconfig 已齐, **无需改动**:

```
CONFIG_USB_DWC3=y                  # DWC3 主体
CONFIG_USB_DWC3_GENERIC_PLAT=y     # spacemit,k1-dwc3 glue (default USB_DWC3 自动)
CONFIG_USB_XHCI_HCD=y              # host 侧 xHCI
```

## 4. 设备树配置

### 4.1 方式一: 直通 Type-A (aibox-k3)

　　最简方式, 纯使能基座节点, 无供电管控:

```dts
&usb2_host_u2phy {
	status = "okay";
};

&usb2_host {
	status = "okay";
};
```

　　就这两段。dr_mode/maximum-speed/quirks 全在基座, 不用重写。

### 4.2 方式二: GPIO 管控 VBUS/Hub 供电 (AIBOX-PRO)

　　参考板: AIBOX-PRO-K3 (FF_USB20_HOST 分支)。口电/Hub 电经负载开关,
由 regulator-fixed 描述:

```dts
/ {
	vcc5v0_usb20_host: regulator-vcc5v0-usb20-host {
		compatible = "regulator-fixed";
		regulator-name = "vcc5v0_usb20_host";
		regulator-min-microvolt = <3300000>;   /* 见下方陷阱: 参考板
			                                  实际写的是 3.3V, 名字却是 5v0 */
		regulator-max-microvolt = <3300000>;
		gpios = <&gpio K3_GPIO(102) GPIO_ACTIVE_HIGH>;
		enable-active-high;
		regulator-boot-on;                     /* 开机即上电 */
		regulator-always-on;                   /* 且不关 */
		vin-supply = <&vcc5v0_sys>;            /* 5V 系统'regulator-fixed' */
		pinctrl-names = "default";
		pinctrl-0 = <&usb20_host_pwr_en_cfg>;
		status = "okay";
	};
};

&pinctrl {
	usb20_host_pwr_en_cfg: usb20-host-pwr-en-cfg {
		usb20-host-pwr-en-pins {
			pinmux = <K3_PADCONF(102, 0)>;     /* func0 = GPIO */
			bias-disable;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};
};

/* 控制器照方式一使能 */
&usb2_host_u2phy { status = "okay"; };
&usb2_host { status = "okay"; };
```

　　`vcc5v0_sys` 是 5V 系统输入的 regulator-fixed (板级公共供电, 自研板
按自己的电源树写: 输入 DC 座/DCDC 输出的 fixed regulator, 参考各板
common 段)。注意参考板这个 regulator **没有挂到 usb2_host 节点** (无
vbus-supply 引用), 靠 always-on 开机即上电 — 纯供电管控, 不参与 USB
协议层。

### 4.3 属性速查与陷阱

| 属性/节点 | 说明 |
|---|---|
| dr_mode = "host" | 专用口固定 host; 要 OTG 用 usb3_porta (typec.md) |
| maximum-speed = "high-speed" | 480Mbps 上限 |
| interrupts 第二条 | wakeup 中断, 远程唤醒用 |
| snps,\* quirks | 厂商稳定性组, 保留勿删 |
| regulator-boot-on / always-on | 供电时序: bootloader 后内核立即开, 不随口状态切换 |

陷阱清单:

- **参考板 regulator 电压声明错误**: `vcc5v0_usb20_host` 名字是 5V,
  min/max 却都写 3300000 (3.3V) — Firefly 复制粘贴遗留。自研板按真实
  VBUS 电压写 5000000, 别把错误一起抄了。
- USB2 口不识别设备: 先看 `lsusb` 有无 xHCI 总线、`dmesg | grep -i dwc3`
  有无 probe; PHY 没使能 (usb2_host_u2phy 忘了) 时控制器 probe 也会失败。
- 不要给 usb2_host 加 dr_mode = "otg" 之类的"增强": 无 u3phy/ID 脚体系,
  改了不工作。
- GPIO102 若被你的板子挪作他用 (它同时是 aibox-pro PCIE WiFi 区块外的
  通用脚), 挪前查 pad 冲突表 (README 汇总)。

## 5. 验证测试

```bash
# 1. 控制器 probe 成功
dmesg | grep -E "c0a00000|dwc3" | head    # "DWC3" 注册与 xHCI 归属
ls /sys/bus/platform/devices/ | grep c0a0

# 2. 总线与插拔
lsusb                                     # Bus 编号含 xHCI; 插 U 盘再 lsusb 对比
dmesg -w &                                # 插拔看枚举日志

# 3. 读写吞吐 (U 盘)
lsblk                                     # 设备名
hdparm -t /dev/sda                        # USB2 理论 480M, 实测 ~35MB/s 级

# 4. 供电管控验证 (方式二)
cat /sys/class/regulator/.../state        # 或量 VBUS: 插入设备前应已有 5V (always-on)

# 5. 无设备时的排查顺序
#    a) zcat /proc/config.gz | grep DWC3               -> 驱动
#    b) dmesg | grep -iE "dwc3|xhci"                   -> probe 报错/phy 缺失
#    c) cat /sys/kernel/debug/usb/devices              -> 总线拓扑
```
