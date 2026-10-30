# AIBOX-PRO 以太网设备树移植适配说明

> 静态检查日期：2026-08-05

## 1. 文档目的

本文用于说明如何把 AIBOX 的以太网设备树配置移植到 AIBOX-PRO，并解释当前 AIBOX-PRO 中两路“以太网”实际对应的硬件链路、需要修改的设备树节点、内核配置、引脚和供电要求，以及验证时容易忽略的问题。

当前对比文件：

- 原始参考板：`k3-firefly-aibox-k3.dts`、`k3-firefly-aibox-k3.dtsi`
- 目标板：`k3-firefly-aibox-pro.dts`、`k3-firefly-aibox-pro.dtsi`
- SoC 公共定义：`k3.dtsi`、`k3-pinctrl.dtsi`
- 公共板级定义：`k3-firefly-common.dtsi`
- DTB 构建入口：当前目录 `Makefile`

## 2. 当前移植结论

从当前设备树源码和最终生成的 DTB 对比结果看，AIBOX-PRO 的以太网设备树移植在静态配置层面已经成功：

- `FF_GMAC0` 和 `FF_GMAC1` 均已在 `k3-firefly-aibox-pro.dts` 中启用。
- AIBOX-PRO 与 AIBOX 的原生 RGMII 网口节点、PHY 地址、复位 GPIO、时钟调相参数、FIFO 深度和 pinctrl 配置一致。
- AIBOX-PRO 与 AIBOX 的 USB3 Port-D 网络链路、PHY 状态和 GPIO53 供电控制配置一致。
- 最终 DTB 中相关节点均为 `status = "okay"`，且没有缺失 label 或 phandle。
- 内核默认配置中包含 SpacemiT STMMAC、Realtek PHY、EtherCAT、K3 EtherCAT GMAC 和 RTL8152 USB 网卡驱动。

但是，“设备树移植成功”只表示硬件描述关系完整。网口能否实际正常通信，仍取决于：

- AIBOX-PRO 原理图中的 PHY 型号、PHY 地址和 RGMII 电压是否与 AIBOX 一致。
- GPIO37 是否仍连接原生 PHY 的复位脚。
- GPIO53 是否仍控制板载 USB 网卡或其 USB3 PHY 的 5V 电源。
- RGMII TX/RX 调相值是否适合 AIBOX-PRO 的 PCB 走线长度。
- 原生网口是作为普通 Linux IP 网卡使用，还是被 EtherCAT 专用驱动接管。

## 3. 两路以太网链路的真实关系

### 3.1 `FF_GMAC0` 并没有启用 SoC 的 `eth0`

当前设备树中的 `FF_GMAC0` 名称容易产生误解。它启用的是：

- `usb30_phy_5v` 固定 5V 电源。
- `usb3_portd_u2phy`。
- `usb3_portd_u3phy`。
- `usb3_portd` DWC3 主机控制器。

也就是说，当前 `FF_GMAC0` 实际对应的是一条 USB3 Host 链路，而不是直接启用 SoC 的原生 GMAC0 控制器。结合内核配置中的 `CONFIG_USB_RTL8152`，这一路通常用于板载 USB 转以太网控制器。

典型链路可以理解为：

```text
K3 USB3 Port-D
├── USB2 PHY
├── USB3 PHY
├── DWC3 Host 控制器
└── 板载 USB 转以太网芯片
    └── Linux USB 网卡驱动，例如 r8152
```

因此，这一路网络设备的 Linux 接口名称不是由 `eth0:` 设备树 label 决定，而取决于 USB 网卡枚举顺序、驱动加载顺序和 `net.ifnames` 配置。

### 3.2 `FF_GMAC1` 才是 SoC 原生 RGMII 千兆网口

`FF_GMAC1` 主要启用：

- `&eth1` 原生 STMMAC/DWMAC 控制器。
- `&ec_master` EtherCAT Master 描述节点。
- `gmac1_cfg` RGMII pinctrl。
- MDIO 总线下地址为 1 的外部 PHY。

典型链路为：

```text
K3 eth1 STMMAC
├── RGMII TX/RX/时钟/控制信号
├── MDIO/MDC 管理总线
├── 外部千兆 PHY，地址 1
├── GPIO37 PHY Reset
└── RJ45/网络变压器
```

## 4. 顶层宏开关

AIBOX-PRO 顶层 DTS 中必须包含：

```dts
#define FF_GMAC0
#define FF_GMAC1
```

对应关系：

| 宏 | 实际功能 | 主要节点 |
|---|---|---|
| `FF_GMAC0` | 板载 USB3 转以太网链路 | `usb3_portd`、Port-D U2/U3 PHY、GPIO53 供电 |
| `FF_GMAC1` | SoC 原生 RGMII 千兆网口 | `eth1`、MDIO PHY、GPIO37 Reset、EtherCAT Master |

如果只需要原生 RGMII 网口，可以仅保留 `FF_GMAC1`。如果板载 USB 网卡存在，则应同时保留 `FF_GMAC0`。

## 5. `FF_GMAC0` 的移植要点

### 5.1 5V 固定电源

当前配置创建了 `usb30_phy_5v`：

```dts
usb30_phy_5v: usb30-phy-5v-regulator {
    compatible = "regulator-fixed";
    regulator-name = "usb30_phy_5v";
    regulator-min-microvolt = <5000000>;
    regulator-max-microvolt = <5000000>;
    regulator-always-on;
    regulator-boot-on;
    enable-active-high;
    gpio = <&gpio K3_GPIO(53) GPIO_ACTIVE_HIGH>;
    pinctrl-names = "default";
    pinctrl-0 = <&usb30_phy_5v_en_cfg>;
    status = "okay";
};
```

移植时必须确认：

1. GPIO53 在 AIBOX-PRO 上仍是该电源或板载 USB 网卡的使能脚。
2. 使能极性仍为高有效。
3. 该 GPIO 所属 IO 电源域为 1.8V；当前 pinctrl 使用 `power-source = <1800>`。
4. 如果硬件已经改为常供电，应删除 GPIO 控制，而不是保留一个没有实际连接的使能脚。

### 5.2 Port-D 控制器和 PHY

必须同时启用以下三个节点：

```dts
&usb3_portd_u2phy {
    status = "okay";
};

&usb3_portd_u3phy {
    status = "okay";
};

&usb3_portd {
    status = "okay";
};
```

不能只启用 `usb3_portd` 而不启用 U2/U3 PHY。USB3 控制器需要：

- U2 PHY 用于 USB2 枚举、兼容和控制阶段。
- U3 PHY 用于 SuperSpeed 数据链路。
- DWC3 控制器负责 Host 控制和设备枚举。

如果板载 USB 网卡只工作在 USB2 速度，需要检查 U3 PHY、电源、参考时钟和高速差分线，而不能只看 USB 网卡驱动。

### 5.3 GPIO53 与 USB3 Hub 注释的关系

USB3 Port-B 的 VL817 Hub 节点中保留了“GPIO53 曾用于 Hub Reset、现在由硬件完成复位”的注释，而 `FF_GMAC0` 又使用 GPIO53 控制 `usb30_phy_5v`。

当前设备树中没有两个设备同时申请 GPIO53，因此没有软件层面的 GPIO 冲突。但移植时必须确认 AIBOX-PRO 硬件已经把 Hub Reset 改为硬件复位，否则 GPIO53 可能在硬件上存在复用冲突。

## 6. `FF_GMAC1` 的移植要点

### 6.1 原生 MAC 基本配置

当前 `eth1` 主要参数如下：

```dts
&eth1 {
    pinctrl-names = "default";
    pinctrl-0 = <&gmac1_cfg>;

    max-speed = <1000>;
    tx-fifo-depth = <8192>;
    rx-fifo-depth = <8192>;
    snps,tso;
    snps,force_sf_dma_mode;
    phy-mode = "rgmii";
    phy-handle = <&rgmii1>;
    snps,reset-gpios = <&gpio 1 5 GPIO_ACTIVE_LOW>;
    snps,reset-delays-us = <0 20000 100000>;

    spacemit,wake-irq-enable;
    spacemit,clk-tuning-enable;
    spacemit,clk-tuning-by-delayline;
    spacemit,tx-phase = <47>;
    spacemit,rx-phase = <53>;

    status = "okay";
};
```

关键检查点：

| 属性 | 作用 | 移植注意事项 |
|---|---|---|
| `phy-mode = "rgmii"` | 指定 MAC 与 PHY 接口模式 | 必须与原理图和 PHY strap 配置一致 |
| `max-speed = <1000>` | 限定最高千兆 | 如果硬件只支持百兆，应修改 |
| `phy-handle` | 指向 MDIO PHY | label 必须存在且地址正确 |
| `snps,reset-gpios` | 控制 PHY Reset | `&gpio 1 5` 对应 GPIO37，必须核对原理图 |
| `reset-delays-us` | PHY 复位前、中、后延时 | PHY 型号变化时应按数据手册调整 |
| `tx-phase`、`rx-phase` | RGMII 时钟相位调节 | PCB 走线变化时可能需要重新调试 |
| `tx/rx-fifo-depth` | MAC FIFO 深度 | 当前与 AIBOX 相同，一般无需改变 |

### 6.2 MDIO 和 PHY 地址

当前 PHY 配置为：

```dts
mdio {
    #address-cells = <1>;
    #size-cells = <0>;
    compatible = "snps,dwmac-mdio";

    rgmii1: phy@1 {
        compatible = "ethernet-phy-id001c.c916";
        reg = <0x1>;
        device_type = "ethernet-phy";
    };
};
```

移植时必须确认 PHY 的 MDIO 地址仍为 `1`。如果 PHY strap 电阻改变为其他地址，MAC 驱动将无法在 `phy@1` 找到设备，通常表现为：

- MAC 驱动加载，但无法连接 PHY。
- `ethtool` 显示无链路。
- MDIO 读写超时或 PHY ID 读取失败。

PHY 型号变化时，不建议直接复制固定 PHY ID compatible，应根据实际 PHY 和绑定要求修改。

### 6.3 RGMII pinctrl

`gmac1_cfg` 对公共 pinctrl 进行了板级覆盖：

- 删除未使用或冲突的 `gmac1-2-pins`、`gmac1-4-pins`、`gmac1-5-pins`。
- 保留并设置主要 RGMII pin group 为 1.8V。
- 使用 GPIO37 作为 PHY Reset，并设置为 1.8V IO。

如果 AIBOX-PRO PHY 的 IO 电压改为 3.3V，不能继续直接使用当前 `power-source = <1800>`。必须同时核对 SoC IO 电源域能力和硬件供电，错误电压可能造成通信异常甚至硬件风险。

## 7. EtherCAT 与普通 Ethernet 的关系

当前设备树启用了：

```dts
&ec_master {
    status = "okay";
    master0 {
        main-device = <&eth1>;
    };
};
```

同时内核配置启用了：

```text
CONFIG_ETHERCAT=y
CONFIG_EC_MASTER=y
CONFIG_EC_DEVICE=y
CONFIG_EC_K3_GMAC=y
```

这表示 `eth1` 被指定为 EtherCAT Master 的主设备。IgH EtherCAT Master 的设计要求被接管的 `net_device` 不再由普通 Linux IP 协议栈使用。

因此需要提前明确产品需求：

- 如果该 RGMII 口用于 EtherCAT，应保留 `ec_master` 绑定，并使用 EtherCAT 工具测试。
- 如果该 RGMII 口用于普通 TCP/IP 网络，需要确认当前内核是否仍由标准 STMMAC 驱动注册普通网卡；必要时关闭 EtherCAT 专用配置或禁用 `ec_master`。
- 不应假设一个物理口可以同时稳定承担 EtherCAT 实时通信和普通 IP 通信。

这不是 AIBOX-PRO 相比 AIBOX 新引入的问题，因为两套设备树配置一致，但它会直接影响“网口是否能作为普通网卡使用”的判断。

## 8. 内核配置要求

原生 RGMII 网口至少需要：

```text
CONFIG_STMMAC_ETH=y
CONFIG_DWMAC_SPACEMIT_ETHQOS=y
CONFIG_REALTEK_PHY=y
```

如果用于 EtherCAT，还需要：

```text
CONFIG_ETHERCAT=y
CONFIG_EC_MASTER=y
CONFIG_EC_DEVICE=y
CONFIG_EC_K3_GMAC=y
```

板载 USB 网口通常还需要：

```text
CONFIG_USB_XHCI_HCD=y
CONFIG_USB_DWC3=y
CONFIG_USB_RTL8152=y或m
```

如果 `CONFIG_USB_RTL8152=m`，根文件系统必须包含 `r8152.ko` 及其依赖，或者在系统启动后手动加载模块。

## 9. AIBOX-PRO 与 AIBOX 的差异及影响

对最终 DTB 的相关子树逐项比较后，以下关键参数完全一致：

- `eth1` 节点路径与状态。
- RGMII 模式和最高速率。
- PHY 地址和 PHY ID compatible。
- PHY Reset GPIO 和延时。
- TX/RX FIFO 深度。
- TX/RX phase。
- EtherCAT `main-device = <&eth1>` 关系。
- Port-D U2 PHY、U3 PHY 和控制器状态。
- GPIO53 供电控制。

因此，AIBOX-PRO 在以太网部分相对 AIBOX 的源码排版、节点顺序或括号风格变化不会影响功能。只要硬件连接与 AIBOX 相同，当前配置应能正常工作。

## 10. 常见故障定位

### 10.1 原生网口完全不存在

检查：

- `eth1` 最终状态是否为 `okay`。
- `CONFIG_DWMAC_SPACEMIT_ETHQOS` 是否启用。
- 是否被 EtherCAT 专用驱动接管。
- pinctrl 是否申请失败。

### 10.2 网口存在但一直无 Link

重点检查：

- PHY 地址是否为 1。
- GPIO37 复位极性和复位延时。
- PHY 1.8V/3.3V IO 电压。
- RGMII TX/RX 相位。
- PHY 时钟、晶振和网络变压器。

### 10.3 只能百兆，不能千兆

重点检查：

- RGMII 高速信号完整性。
- TX/RX phase 是否适配 AIBOX-PRO PCB。
- 网线和对端是否支持千兆。
- PHY 是否正确加载固件或扩展配置。

### 10.4 板载 USB 网口不存在

重点检查：

- `usb3_portd`、U2 PHY、U3 PHY 是否全部为 `okay`。
- GPIO53 是否输出有效电平。
- USB 网卡是否出现在 `lsusb`。
- `r8152` 模块是否加载。
- USB3 差分线异常时，设备可能降级为 USB2，而不是完全消失。

## 11. 简单测试步骤

### 11.1 编译检查

```bash
make ARCH=riscv k3-firefly-aibox-pro.dtb
```

确认 DTB 正常生成，并重点检查是否出现 `eth1`、`gmac1_cfg`、`usb3_portd` 或 PHY 相关错误。

### 11.2 查看网络接口

```bash
ip -br link
ls /sys/class/net
dmesg | grep -Ei 'stmmac|dwmac|phy|rgmii|r8152|ethercat'
```

正常情况下应能看到原生 RGMII 网口以及板载 USB 网口；实际接口名称取决于系统命名规则和 EtherCAT 配置。

### 11.3 普通 Ethernet 测试

如果网口未被 EtherCAT 接管：

```bash
ip link set eth0 up
udhcpc -i eth0
ethtool eth0
ping -c 4 <网关IP>
iperf3 -c <服务器IP>
```

根据 `ip -br link` 的实际结果替换 `eth0`。

### 11.4 板载 USB 网口测试

```bash
lsusb
modprobe r8152
ip -br link
ethtool <USB网卡接口>
ping -I <USB网卡接口> -c 4 <对端IP>
```

### 11.5 EtherCAT 测试

如果原生 RGMII 口用于 EtherCAT：

```bash
ethercat master
ethercat slaves
ethercat domains
```

连接 EtherCAT 从站后，应能识别 Master 和 Slave。此时不要再使用该口执行普通 DHCP、Ping 或 TCP/IP 测试。
