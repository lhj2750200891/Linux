# USB2.0

　　USB2.0 Type-A 主机口 (EHCI/OHCI + u2phy): 引脚全景与 u2phy 复用冲突说明。参考板 AIO-3588SG。

## 1. RK3588 USB2 主机口全景

| 控制器 | 地址 | PHY | 说明 |
|---|---|---|---|
| usb_host0_ehci/ohci | fc800000/fc840000 | u2phy2_host | USB2.0 口 1 |
| usb_host1_ehci/ohci | fc880000/fc8c0000 | u2phy3_host | USB2.0 口 2 |

　　说明:
- 每个原生 USB2 口是 EHCI(高速)+OHCI(全速) 成对出现的, 两个都要使能
- usb_host2 (RK3588 完整版) 一般不用
- USB2 口的 5V VBUS 由板级 GPIO 控制 (regulator-fixed + phy-supply),
  常供时可只给 always-on 的 regulator
- Type-C 口的 USB2 (u2phy0/u2phy1) 属于 Type-C 链路, 见 typec 模块

　　内核配置 (defconfig 已开):

```
CONFIG_USB_EHCI_HCD=y
CONFIG_USB_OHCI_HCD=y
CONFIG_PHY_ROCKCHIP_INNO_USB2=y   # u2phy
```

## 2. 方式一: USB2.0 口 1 (usb_host0)

　　参考板: AIO-3588SG。

### 2.1 硬件连接

```
USB2.0 Type-A 口:
  D+/D-  ====> u2phy2 (SOC 内置 USB2 PHY, 无需引脚配置)
  VBUS 5V 电源使能 ====> vcc5v0_usb20_host0 (常供, 无 GPIO 直接 always-on)
```

### 2.2 设备树配置

　　参考: rk3588-firefly-common.dtsi (FF_USB20_HOST0)

```
/ {
	vcc5v0_usb20_host0: vcc5v0-usb20-host0 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc5v0_usb20_host0";
		regulator-boot-on;
		regulator-always-on;
		regulator-min-microvolt = <5000000>;
		regulator-max-microvolt = <5000000>;
		enable-active-high;
		vin-supply = <&vcc5v0_usb>;      // 上级 5V 总电源
		// 有独立使能脚时加: gpio = <&gpioX RK_PXX GPIO_ACTIVE_HIGH>;
	};
};

&usb_host0_ehci {
	status = "okay";
};

&usb_host0_ohci {
	status = "okay";
};

&u2phy2 {
	status = "okay";
};

&u2phy2_host {
	status = "okay";
	phy-supply = <&vcc5v0_usb20_host0>;   // VBUS 供电关联
};
```

## 3. 方式二: USB2.0 口 2 (usb_host1)

　　参考板: AIO-3588SG。

### 3.1 硬件连接

```
USB2.0 Type-A 口:
  D+/D-  ====> u2phy3
  VBUS 5V 电源使能 ====> vcc5v0_usb20_host1 (常供)
```

　　注意: u2phy3 同时是 USB3 口 (usbhost_dwc3_0) 的 USB2 伴生 PHY!
若板上 USB3 口 (见 usb30 模块) 已用 u2phy3_host,
则 USB2 口 2 与 USB3 口冲突, 二者只能用一个 (SG 板即如此: USB20_HOST1
与 USB30 共用 u2phy3, 默认给 USB3 用)。

　　usb_host1 配置方法与方式一对称:

```
&usb_host1_ehci {
	status = "okay";
};

&usb_host1_ohci {
	status = "okay";
};

&u2phy3 {
	status = "okay";
};

&u2phy3_host {
	status = "okay";
	phy-supply = <&vcc5v0_usb20_host1>;
};
```

## 4. 验证测试

```
# 控制器注册
dmesg | grep -i -E "ehci|ohci|usb"
# 应看到: ehci-platform fc800000.usb: EHCI Host Controller ...

# 插 U 盘
lsusb                        # 应看到新设备
dmesg | tail                 # usb 1-1: new high-speed USB device

# 供电检查 (插大电流设备掉电时)
cat /sys/class/regulator/*/name | grep usb20

# 速度确认 (USB2 口应 480M)
lsusb -t
# 5000M=USB3.0, 480M=USB2.0, 12M/1.5M=全速/低速 (OHCI 兜底)

# 常见问题:
# 1. 插上无反应: u2phy2/u2phy2_host 漏使能, 或 VBUS 没电 (量引脚电压)
# 2. 只有全速 (12M): OHCI 正常 EHCI 挂了, 检查两个节点都 okay
# 3. USB3 设备插 USB2 口只有 480M: 正常, USB2 口物理上不支持 5Gbps
```
