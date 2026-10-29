# USB3.0

　　USB3.0 Type-A 5Gbps 口 (usbhost3_0 + combphy2_psu) 与 USB3 HUB 一扩四场景。参考板 AIO-3588SG / aio-3588sjd4。

## 1. RK3588 USB3 控制器全景

| 控制器 | 地址 | USB3 PHY | USB2 PHY | 用途 |
|---|---|---|---|---|
| usbdrd3_0 / usbdrd_dwc3_0 | fcd40000(dbg)/dwc3 | usbdp_phy0 (共享) | u2phy0 | Type-C0 OTG |
| usbdrd3_1 / usbdrd_dwc3_1 | - | usbdp_phy1 (共享) | u2phy1 | Type-C1 OTG |
| usbhost3_0 / usbhost_dwc3_0 | fcd00000 | combphy2_psu | u2phy3 | USB3.0 A 口 |

　　说明:
- RK3588 的 USB3 有两类: OTG 双角色 (usbdrd) 和纯主机 (usbhost3_0)
- Type-A USB3 口走 usbhost3_0: USB3 差分对接 combphy2_psu,
  USB2 D+/D- 对接 u2phy3, 两组 PHY 同时要配
- combphy2_psu 与 SATA2/pcie2x1l1 互斥 (见 sata/pcie 模块)
- u2phy3 与 USB2 口 2 (usb_host1) 互斥 (见 usb20 模块)
- usbdp_phy0/1 也被 DP 用: Type-C DP altmode 见 typec 模块,
  独立 DP/VGA 口见 vga 模块; 纯 USB3 OTG 时 usbdp_phy 不加 mode-switch

　　内核配置 (defconfig 已开):

```
CONFIG_USB_XHCI_HCD=y
CONFIG_USB_DWC3=y
CONFIG_USB_DWC3_ROCKCHIP=y (若为 =m 注意 rootfs 里要有模块)
CONFIG_PHY_ROCKCHIP_NANENG_COMBO_PHY=y   # combphy2_psu
CONFIG_PHY_ROCKCHIP_TYPEC=y              # usbdp phy
```

## 2. 方式一: USB3.0 Type-A 口 (usbhost3_0)

　　参考板: AIO-3588SG。

### 2.1 硬件连接

```
USB3.0 Type-A 口:
  USB3 差分对 (TX/RX) ====> combphy2_psu
  D+/D-              ====> u2phy3
  VBUS 5V 电源使能    ====> GPIO4_B5 (vcc5v0_usb_host, 高有效)
```

### 2.2 设备树配置

　　参考: rk3588-firefly-aio-3588sg.dtsi (FF_USB30_HOST)

```
/ {
	vcc5v0_usb_host: vcc5v0-usb-host {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc5v0_usb_host";
		enable-active-high;
		regulator-boot-on;
		regulator-always-on;
		regulator-min-microvolt = <5000000>;
		regulator-max-microvolt = <5000000>;
		gpio = <&gpio4 RK_PB5 GPIO_ACTIVE_HIGH>;    // VBUS 使能脚
		vin-supply = <&vcc5v0_usb>;
	};
};

&u2phy3 {                               // USB2 伴生 PHY
	status = "okay";
};

&u2phy3_host {
	status = "okay";
	phy-supply = <&vcc5v0_usb_host>;
};

&combphy2_psu {                         // USB3 PHY (与 SATA2/pcie2x1l1 互斥!)
	status = "okay";
};

&usbhost3_0 {
	status = "okay";
};

&usbhost_dwc3_0 {
	status = "okay";
	dr_mode = "host";
};
```

## 3. 方式二: USB3 一扩四 (HUB + USB-SATA)

　　参考板: aio-3588sjd4。

　　aio-3588sjd4 用 usbhost_dwc3_0 出 USB3, 经 GL33121 HUB 一扩四接
GL3321G USB转SATA 桥做 4 口 SATA (拓扑与两个 Firefly 私有驱动见 sata
模块)。这里只列 USB 侧要点:

- USB 侧配置同方式一 (usbhost3_0 + combphy2_psu + u2phy3 + dwc3 host)
- jd4 板 vcc5v0_usb_host 是 always-on 无 GPIO (电源常供)
- HUB 复位/桥芯片时序节点 (vcc_hub3_reset / gl3321g) 属于 sata 模块内容
- 验证: lsusb 应看到 05e3:0620 (GL33121) 类 HUB + 4 个桥设备

## 4. 验证测试

```
# 控制器注册
dmesg | grep -i -E "dwc3|xhci"
# 应看到: xhci-hcd ... DWC3 host controller, 双 roothub (USB3+USB2)

# 插 USB3 U 盘/硬盘
lsusb -t
# USB3 设备应挂 5000M 分支:
# /: Bus 02.Port 1: Dev 1, Class=root_hub, Driver=xhci-hcd/..., 5000M
#     |__ Port 2: Dev 2, If 0, Class=..., Driver=usb-storage, 5000M

lsblk                         # 应出现 sda
dd if=/dev/sda of=/dev/null bs=1M count=500 iflag=direct
# USB3 U 盘 ~ 150-350MB/s; USB2 会卡在 ~40MB/s

# 常见问题:
# 1. 只有 480M: combphy2_psu 未使能, 只剩 USB2 伴生 PHY 在跑
# 2. 枚举失败: VBUS 使能 GPIO 极性错/没供电
# 3. combphy 报冲突: combphy2_psu 被 sata2 或 pcie2x1l1 占用,
#    检查互斥节点状态
# 4. 大盘掉电: VBUS 供不动 (USB3 硬盘要 ~900mA), 加外部供电或换
#    带 PMOS 的电源电路
```
