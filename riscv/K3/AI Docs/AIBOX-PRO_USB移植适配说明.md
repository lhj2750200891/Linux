# AIBOX-PRO USB2.0、USB3.0 与 Type-C 设备树移植适配说明

> 静态检查日期：2026-08-05

## 1. 文档目的

本文用于说明 AIBOX-PRO 的 USB2.0、USB3.0 Type-A、USB Type-C 和板载 USB 网络链路如何从 AIBOX 设备树移植，并重点梳理各控制器、PHY、供电、Hub、Type-C CC 控制器及角色切换之间的关系。

当前对比文件：

- 原始参考板：`k3-firefly-aibox-k3.dts`、`k3-firefly-aibox-k3.dtsi`
- 目标板：`k3-firefly-aibox-pro.dts`、`k3-firefly-aibox-pro.dtsi`
- SoC USB 控制器基础定义：`k3.dtsi`
- 公共 pinctrl：`k3-pinctrl.dtsi`

## 2. 当前移植结论

从当前源码和最终生成的 DTB 看，AIBOX-PRO 的 USB 主功能链路已经完整移植：

- `FF_TYPE_C` 已启用。
- `FF_USB20_HUB` 已启用。
- `FF_USB30_TYPEA` 已启用。
- 与板载 USB 网卡相关的 `FF_GMAC0` 已启用。
- USB2 Host、USB3 Port-A/B/C/D、所有相关 U2/U3 PHY 和 FUSB302 均为 `status = "okay"`。
- Type-C FUSB302 已正确放在 I²C0 下，I²C0 也已启用。
- Type-C role-switch 和 orientation-switch 的双向 graph phandle 均完整。
- USB3 Port-B 下的 VL817 USB2/USB3 companion Hub 节点与 AIBOX 一致。
- 各固定 5V 电源节点、GPIO 和 pinctrl 与 AIBOX 对应关系一致。

当前还有 Type-C graph 的非致命 DTC 告警，建议清理后再作为最终版本提交。告警不会阻止 DTB 生成，但保持零板级告警更有利于后续维护。

## 3. USB 总体拓扑

当前 AIBOX-PRO 的 USB 资源可以划分为四组：

| 功能 | SoC 控制器 | PHY | 工作模式 | 主要外设/接口 |
|---|---|---|---|---|
| 独立 USB2 Host | `usb2_host` | `usb2_host_u2phy` | Host、High-Speed | USB2 Type-A/USB2 Hub |
| USB Type-C | `usb3_porta` | Port-A U2 PHY + U3 PHY | OTG/双角色 | Type-C 接口、FUSB302 |
| USB3 Type-A | `usb3_portb`、`usb3_portc` | 各自 U2 PHY + U3 PHY | Host | 两组 USB3 Type-A，其中 Port-B 带 VL817 Hub |
| 板载 USB 网卡 | `usb3_portd` | Port-D U2 PHY + U3 PHY | Host | USB 转以太网芯片 |

这里最重要的概念是：

> 一个 USB3 物理端口通常同时需要一个 USB2 PHY 和一个 USB3 PHY。

原因是 USB3 Type-A 或 Type-C 接口同时包含：

- USB2 D+/D- 通道，由 U2 PHY 处理。
- USB3 SuperSpeed TX/RX 差分通道，由 U3 PHY 处理。

因此，USB3 端口的 U2 PHY 不是独立 USB2 Host 控制器。它是该 USB3 端口内部用于兼容 USB2 设备的组成部分。

## 4. 顶层宏与功能边界

AIBOX-PRO 当前启用：

```dts
#define FF_GMAC0
#define FF_TYPE_C
#define FF_USB20_HUB
#define FF_USB30_TYPEA
```

对应关系：

| 宏 | 控制范围 | 不控制的内容 |
|---|---|---|
| `FF_TYPE_C` | Port-A、FUSB302、Type-C VBUS、角色和方向切换 | 独立 USB2 Host、Port-B/C/D |
| `FF_USB20_HUB` | 独立 USB2 Host、GPIO77 VBUS、GPIO2 Hub 电源 | USB3 Port-A/B/C/D |
| `FF_USB30_TYPEA` | USB3 Port-B/C、GPIO78 USB3 电源、VL817 Hub | Type-C Port-A、Port-D USB 网卡 |
| `FF_GMAC0` | USB3 Port-D 和 GPIO53 电源 | SoC 原生 RGMII 网口 |

四个宏分别管理不同的控制器或板载设备，不能因为都属于 USB 就只保留一个宏。

## 5. 独立 USB2.0 Host 链路

### 5.1 控制器与 PHY

独立 USB2 Host 使用：

```dts
&usb2_host_u2phy {
    status = "okay";
};

&usb2_host {
    status = "okay";
};
```

`k3.dtsi` 中该控制器默认定义为：

- `dr_mode = "host"`。
- `maximum-speed = "high-speed"`。
- 使用单独的 USB2 PHY。

这一路只能工作到 USB2 High-Speed，不具备 SuperSpeed 通道。

### 5.2 USB2 VBUS 与 Hub 电源

`FF_USB20_HUB` 创建两路固定电源：

1. `vcc5v0_hub20`
   - GPIO2 高有效。
   - 为 USB2 Hub 或相关 Hub 电路供电。
   - 使用 `hub20_pwr_en_cfg`。

2. `vcc5v0_usb_host`
   - GPIO77 高有效。
   - regulator 名称在 AIBOX-PRO 中为 `vcc5v0_usb20_host`。
   - 为 USB2 Host/Type-A VBUS 链路供电。
   - 使用 `usb20_vcc5v0_en_cfg`。

两路电源都配置了：

```dts
regulator-always-on;
regulator-boot-on;
```

因此系统启动后会保持供电。移植时必须确认：

- GPIO2 和 GPIO77 在 AIBOX-PRO 上仍连接相同电源使能。
- GPIO2 IO 电压为 1.8V。
- GPIO77 IO 电压为 3.3V。
- Hub 芯片复位、电源时序是否由硬件保证。

## 6. USB3 Type-A 链路

### 6.1 Host0：USB3 Port-C

当前注释将 Port-C 作为 Host0：

```dts
&usb3_portc_u2phy {
    status = "okay";
};

&usb3_portc_u3phy {
    status = "okay";
};

&usb3_portc {
    status = "okay";
};
```

必须同时启用 U2 PHY、U3 PHY 和控制器。

### 6.2 Host1：USB3 Port-B

当前注释将 Port-B 作为 Host1：

```dts
&usb3_portb_u2phy {
    status = "okay";
};

&usb3_portb_u3phy {
    status = "okay";
};

&usb3_portb {
    status = "okay";
};
```

Port-B 下还描述了 VL817 Hub 的两个逻辑设备：

```dts
hub_2_0: hub@1 {
    compatible = "usb2109,2817";
    reg = <1>;
    peer-hub = <&hub_3_0>;
};

hub_3_0: hub@2 {
    compatible = "usb2109,817";
    reg = <2>;
    peer-hub = <&hub_2_0>;
};
```

这两个节点不是两颗独立 Hub，而是同一颗 USB3 Hub 芯片在 USB2 总线和 USB3 总线上的 companion 设备：

```text
VL817 物理 Hub
├── USB2 Hub 功能：usb2109,2817
└── USB3 Hub 功能：usb2109,817
```

`peer-hub` 用来告诉内核两者属于同一个物理 Hub，从而正确处理端口配对和电源管理。

### 6.3 USB3 Type-A 电源关系

USB3 Type-A 使用：

- `vcc5v0_usb30_host1`
  - GPIO78 高有效。
  - 使用 `usb30_vcc5v0_en_cfg`。
  - 作为实际可控的 5V 供电节点。

- `vcc5v0_usb30_host0`
  - 没有独立 GPIO。
  - `vin-supply = <&vcc5v0_usb30_host1>`。
  - 表示 Host0 电源由 Host1 的上游 5V 电源派生。

因此两路 USB3 Type-A 在设备树中不是完全独立供电。GPIO78 或上游 5V 关闭时，两个 Host 口都可能失去 VBUS。

移植时应核对：

- AIBOX-PRO 是否仍由 GPIO78 同时控制两路 USB3 Type-A 电源。
- 如果两路电源已经拆分，应该创建两个独立 regulator 和 GPIO，而不是沿用级联关系。
- 如果只有一组 USB3 Type-A，应该关闭未连接的控制器，避免无意义的枚举和功耗。

## 7. USB Type-C 链路

### 7.1 Type-C 不是只启用一个 USB 控制器

完整 Type-C 链路至少包含：

```text
FUSB302 CC 控制器
├── 检测插入、拔出和 CC 方向
├── 协商 Source/Sink 电源角色
├── 控制 VBUS
└── 通知 USB 控制器和 PHY

K3 USB3 Port-A
├── U2 PHY：USB2 数据
├── U3 PHY：USB3 SuperSpeed 数据和方向切换
└── DWC3：Host/Peripheral 角色切换
```

只启用 Port-A 而没有 FUSB302，接口可能只能保持固定角色；只启用 FUSB302 而没有 Port-A，则只能检测 Type-C 状态但无法传输 USB 数据。

### 7.2 FUSB302 与 I²C0

当前正确配置为：

```dts
&i2c0 {
    pinctrl-names = "default";
    pinctrl-0 = <&i2c0_0_cfg>;
    status = "okay";

    usbc0: fusb302@22 {
        compatible = "fcs,fusb302";
        reg = <0x22>;
        fcs,int_n-gpios = <&gpio K3_GPIO(58) GPIO_ACTIVE_LOW>;
        linux,host-role-before-vbus;
        pinctrl-names = "default";
        pinctrl-0 = <&usbc0_int_cfg>;
        vbus-supply = <&vcc5v0_usb20_typec>;
        status = "okay";
    };
};
```

移植时必须保证：

- FUSB302 是 I²C0 地址 `0x22`。
- GPIO58 是低有效、开漏类型的中断信号，并有正确上拉。
- I²C0 IO 电压当前配置为 3.3V。
- FUSB302 驱动 `CONFIG_TYPEC_FUSB302` 已启用。
- TCPM/Type-C 核心依赖已启用。

### 7.3 Type-C VBUS

Type-C VBUS 使用：

```dts
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
```

它与 USB2/USB3 Type-A 的 always-on VBUS 不同：

- Type-C VBUS 由 FUSB302 通过 regulator framework 动态控制。
- 当接口作为 Source/Host 时，FUSB302 可以打开 GPIO60 输出 5V。
- 当接口作为 Sink/Device 时，不应主动向接口输出 VBUS。

因此不要给该 regulator 随意增加 `regulator-always-on`，否则可能破坏 Type-C Source/Sink 电源角色管理。

### 7.4 USB 数据角色切换

FUSB302 connector 的 Port0 连接 DWC3 role switch：

```text
usbc0_role_sw
    <------ remote-endpoint ------>
dwc3_0_role_switch
```

DWC3 Port-A 配置：

```dts
dr_mode = "otg";
usb-role-switch;
spacemit,synchronous-role-switch;
role-switch-default-mode = "peripheral";
monitor-vbus;
```

作用分别为：

| 属性 | 作用 |
|---|---|
| `dr_mode = "otg"` | 允许 Host 和 Peripheral 双角色 |
| `usb-role-switch` | 使用 Type-C/role-switch framework 控制角色 |
| `synchronous-role-switch` | 等待角色切换同步完成 |
| `role-switch-default-mode = "peripheral"` | 未确定角色时默认 Device |
| `monitor-vbus` | 监控 VBUS 状态 |

### 7.5 Type-C 正反插方向切换

FUSB302 connector 的 Port1 连接 Port-A U3 PHY orientation switch：

```text
usbc0_orien_sw
    <------ remote-endpoint ------>
u2phy0_orientation_switch
```

虽然 label 名称为 `u2phy0_orientation_switch`，该 endpoint 实际位于 `usb3_porta_u3phy` 节点下。它负责根据 Type-C CC 方向配置 SuperSpeed 差分通道方向。

如果 USB2 正常但 USB3 只在某一个插头方向工作，应优先检查：

- orientation graph 是否双向连接。
- FUSB302 是否正确报告 orientation。
- U3 PHY 的 orientation-switch 驱动是否加载。
- Type-C 高速 MUX 或 PCB 差分线连接。

## 8. Port-D 与以太网的交叉关系

`FF_GMAC0` 使用 USB3 Port-D，因此 Port-D 虽然属于 USB 控制器，但通常被板载 USB 网卡占用。

```text
usb3_portd
└── 板载 USB Ethernet
    └── Linux r8152 等 USB 网卡驱动
```

这解释了为什么以太网设备树中会出现 USB3 PHY 和 DWC3 控制器，也解释了 USB 调试时为什么不能只检查外部 Type-A 和 Type-C 接口。

如果关闭 `FF_GMAC0`：

- Port-D 控制器和 PHY 会保持 disabled。
- GPIO53 供电不会创建。
- 对应板载 USB 网卡将无法枚举。

## 9. AIBOX-PRO 与 AIBOX 的 USB 差异

最终 DTB 对比显示，两块板以下内容一致：

- USB2 Host、Port-A/B/C/D 路径和状态。
- 所有 U2/U3 PHY 状态。
- FUSB302 地址、中断 GPIO和 VBUS supply。
- Type-C 数据角色和方向 graph 的连接目标。
- VL817 USB2/USB3 companion Hub compatible 和地址。
- GPIO2、GPIO53、GPIO60、GPIO77、GPIO78 的用途。
- USB3 Host0/Host1 电源级联关系。

存在的有效差异：

### 9.1 `vcc5v0_usb_host` 所属宏变化

AIBOX 将 `vcc5v0_usb_host` 放在 `FF_USB30_TYPEA` 条件中，AIBOX-PRO 将其放在 `FF_USB20_HUB` 条件中。

AIBOX-PRO 的处理更符合节点实际用途，因为该 regulator 使用 GPIO77 和 `usb20_vcc5v0_en_cfg`，名称也改为 `vcc5v0_usb20_host`。

当前两个宏都已启用，所以最终供电节点始终存在，不影响当前功能。如果未来只关闭 USB3 Type-A，AIBOX-PRO 的 USB2 Host 供电仍会保留，这是更合理的依赖关系。

### 9.2 regulator 名称变化

```text
AIBOX:     vcc5v0_usb30_host
AIBOX-PRO: vcc5v0_usb20_host
```

该变化只影响 regulator framework 中显示的名称和调试信息。设备树 label、节点路径、GPIO77 和电压参数没有改变，因此不会影响 USB 控制器工作。

### 9.3 Type-C graph 写法变化

AIBOX-PRO 已把 connector 下没有 `reg` 的 `endpoint@0` 改为 `endpoint`，这是正确方向。但当前 `usb3_porta_u3phy` 下仍保留：

```dts
endpoint {
    reg = <0>;
};
```

这会产生 `unit_address_vs_reg` 和 `graph_endpoint` 告警。因为该 `port` 只有一个 endpoint，建议同时删除：

- `#address-cells`
- `#size-cells`
- endpoint 中的 `reg = <0>`

保留普通 `endpoint` 即可。

`usb3_porta` 下只有一个 `port@0`，同样可以删除 `ports` 下的地址单元、把 `port@0` 改为 `port` 并删除 `reg`。这些调整主要用于清理 DTC graph 告警，不改变角色切换连接关系。

## 10. 内核配置要求

USB Host 和 DWC3 至少需要：

```text
CONFIG_USB_XHCI_HCD=y
CONFIG_USB_DWC3=y
```

Type-C 至少需要：

```text
CONFIG_TYPEC_TCPM=y
CONFIG_TYPEC_FUSB302=y
```

板载 USB 网卡需要相应 USB 网络驱动，例如：

```text
CONFIG_USB_RTL8152=y或m
CONFIG_USB_USBNET=y或m
```

如果驱动编译为模块，必须确认根文件系统中存在对应 `.ko` 文件并能正确加载。

## 11. 常见故障与交叉定位

### 11.1 USB2 设备正常，USB3 设备只能跑 USB2

说明 DWC3 和 U2 PHY 大概率正常，应重点检查：

- 对应 U3 PHY 是否为 `okay`。
- SuperSpeed PHY 时钟和复位。
- USB3 差分线和连接器。
- Type-C orientation switch。
- Hub 的 USB3 companion 是否枚举。

### 11.2 USB3 Type-A 两个端口同时无电

检查 GPIO78 和 `vcc5v0_usb30_host1`。由于 Host0 从 Host1 regulator 派生，上游电源异常可能同时影响两个端口。

### 11.3 Type-C 可以充电但没有 USB 数据

检查：

- Port-A 控制器、U2 PHY、U3 PHY状态。
- role-switch graph。
- DWC3 是否切换到正确角色。
- Type-C 数据线和高速 MUX。

### 11.4 Type-C 只能作为 Device 或只能作为 Host

检查：

- FUSB302 是否正常 probe。
- GPIO58 中断是否触发。
- VBUS GPIO60 是否受 regulator 控制。
- `data-role`、`power-role` 和 `try-power-role`。
- `usb-role-switch` 是否注册成功。

### 11.5 Type-C 只有一个插头方向支持 USB3

检查 orientation-switch graph 和 U3 PHY。USB2 D+/D- 不依赖高速方向切换，因此可能两个方向都能使用 USB2，但只有一个方向能使用 USB3。

### 11.6 板载网口消失但外部 USB 正常

检查 Port-D、GPIO53 和 USB 网卡驱动，而不是 Port-B、Port-C 或独立 USB2 Host。

## 12. 简单测试步骤

### 12.1 DTB 编译检查

```bash
make ARCH=riscv k3-firefly-aibox-pro.dtb
```

确认没有 FUSB302 地址、phandle、pinctrl 或 regulator 引用错误。建议清理本文提到的 Type-C graph 告警后再提交最终版本。

### 12.2 查看控制器和 USB 拓扑

```bash
dmesg | grep -Ei 'usb|xhci|dwc3|fusb302|typec|tcpm'
lsusb
lsusb -t
```

`lsusb -t` 应能区分 480M USB2 链路和 5000M USB3 链路。

### 12.3 USB2 Host 测试

1. 在独立 USB2 Type-A 口插入 U 盘。
2. 执行：

```bash
lsusb -t
dmesg | tail -n 50
lsblk
```

确认设备以 `480M` 枚举并可正常读写。

### 12.4 USB3 Type-A 测试

分别在 Port-B 和 Port-C 对应接口插入 USB3 U 盘：

```bash
lsusb -t
lsblk
dd if=/dev/zero of=/挂载点/usb_test.bin bs=1M count=512 conv=fsync
```

确认设备以 `5000M` 枚举。测试完成后删除测试文件。

### 12.5 VL817 Hub 测试

```bash
lsusb
lsusb -t
```

应同时看到 USB2 Hub 和 USB3 Hub companion。分别插入 USB2 和 USB3 设备，确认两类下游端口均可枚举。

### 12.6 Type-C Device 模式测试

将 AIBOX-PRO Type-C 连接到 PC：

```bash
cat /sys/class/typec/port0/data_role 2>/dev/null
cat /sys/class/typec/port0/power_role 2>/dev/null
dmesg | grep -Ei 'typec|fusb|dwc3|gadget'
```

确认角色切换为 Device/Peripheral，并根据系统 gadget 配置检查 PC 端是否发现设备。

### 12.7 Type-C Host 模式测试

通过 Type-C OTG 转接器连接 U 盘或键鼠：

```bash
cat /sys/class/typec/port0/data_role 2>/dev/null
cat /sys/class/typec/port0/power_role 2>/dev/null
lsusb -t
dmesg | tail -n 80
```

确认角色为 Host，GPIO60 控制的 VBUS 正常输出，外设能够枚举。

### 12.8 Type-C 正反插测试

使用同一个 USB3 Type-C 设备：

1. 正向插入，记录 `lsusb -t` 速度。
2. 拔出后反向插入，再次记录速度。
3. 两个方向都应以相同速度枚举。

如果只有一个方向达到 `5000M`，重点排查 orientation-switch 和 SuperSpeed 差分链路。
