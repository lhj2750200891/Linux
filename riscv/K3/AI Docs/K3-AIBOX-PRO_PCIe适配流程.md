# K3-AIBOX-PRO PCIe 适配流程

## 1. 文档目的

本文根据当前目录中的以下 4 张原理图，对 K3-AIBOX-PRO 的 PCIe 拓扑进行推断，并给出硬件检查、BSP 配置、Linux 驱动适配、调试和验收流程：

- `pcie-1.png`：ASM1182e 下游 M-Key M.2 接口
- `pcie-2.png`：ASM1182e 下游 E-Key Wi-Fi/BT 接口
- `pcie-3.png`：PCIe 3.0 x4 M.2 和 PCIe/SATA 复用 M.2
- `pcie-4.png`：ASM1182e PCIe Switch、电源、复位及上下行连接

本文中的设备树节点名和 GPIO 编号为适配框架，最终必须以 K3 BSP、完整原理图、BOM 和实际焊接配置为准。

## 2. PCIe 拓扑推断

根据网络名和连接关系，整板拓扑推断如下：

```text
K3 SoC
├── PCIe 3.0 Port0 x4
│   └── M2_1：M-Key 2280，直连 NVMe x4
│
├── PCIe/Combo PHY x1 或 SATA
│   └── M2_2：M-Key 2280，PCIe x1 / SATA 二选一
│
└── PCIe 2.0_1 x1
    └── ASM1182e PCIe Switch
        ├── Port 5：M-Key 2280，NVMe x1
        └── Port 7：E-Key 无线模块
            ├── WLAN：PCIe x1
            └── Bluetooth：USB 2.0
```

### 2.1 接口对应关系

| 接口 | 原理图依据 | SoC 连接 | 工作模式 | 主要用途 |
|---|---|---|---|---|
| M2_1 | `pcie-3.png` 上半部分 | `PCIE30_PORT0` | PCIe 3.0 x4 | 高速 NVMe SSD |
| M2_2 | `pcie-3.png` 下半部分 | `PCIE0_TX/RX` 与 `SATA_TX/RX` 复用 | PCIe x1 或 SATA | NVMe/SATA 二选一 |
| 扩展 M.2 | `pcie-1.png` | ASM1182e Port 5 | PCIe x1 | 低速 NVMe/扩展卡 |
| E-Key | `pcie-2.png` | ASM1182e Port 7 | PCIe x1 + USB 2.0 | PCIe Wi-Fi + USB 蓝牙 |
| ASM1182e 上行 | `pcie-4.png` | `PCIE20_1` | PCIe 2.0 x1 | 扩展两个下行 PCIe 端口 |

### 2.2 关键结论

1. K3 侧 PCIe 控制器应配置为 Root Complex（RC），M.2 设备和 ASM1182e 都是下游设备。
2. M2_1 是唯一的 PCIe 3.0 x4 高性能接口，应优先用于系统盘或高性能 NVMe。
3. `pcie-1.png` 中的 M.2 与 `pcie-2.png` 中的 Wi-Fi 共享 ASM1182e 的 PCIe 2.0 x1 上行带宽。
4. M2_2 使用 PCIe/SATA Combo PHY，同一时刻只能选择 PCIe 或 SATA，不能同时启用。
5. E-Key 插槽中的 WLAN 走 PCIe，Bluetooth 走 USB 2.0。二者应分别调试。

## 3. 适配前准备

### 3.1 确认硬件版本和焊接配置

开始修改 BSP 前，应先核对：

- 整板版本是否与 4 张原理图一致。
- ASM1182e、可选 EEPROM、0Ω电阻和标记为 `NC` 的器件是否实际焊接。
- M2_1、M2_2、扩展 M.2、E-Key 的实际插槽编号和外壳丝印。
- `ASM1182e_PWR_EN`、`K3_PCIE0_PERSTN`、M.2 PERST# 对应的 K3 GPIO 编号。
- K3 SoC 的 `PCIE30_PORT0`、`PCIE20_1` 和 Combo PHY 在 BSP 中对应的设备树节点。
- 各 M.2 插槽 3.3V 电源的额定电流和同时启动能力。

### 3.2 BSP 中搜索相关节点

可在内核源码中执行：

```bash
rg -n "pcie3|pcie2|pcie30|pcie20|combphy|sata|vpcie|perst" \
    arch/arm64/boot/dts drivers/phy drivers/pci
```

重点寻找 K3 官方参考板中已经能够工作的 PCIe 控制器、PHY、电源和复位配置，优先基于参考配置修改，不要凭空编写时钟和 PHY 参数。

## 4. 硬件检查流程

### 4.1 断电检查

1. 检查 3.3V、1.2V 电源对地是否短路。
2. 检查 M.2 插槽方向和 Key 类型。
3. 检查 PCIe 差分对是否缺件、错焊或经过未焊接的 0Ω电阻。
4. 核对 PERST#、CLKREQ#、WAKE# 的上拉电阻和实际焊接状态。
5. 确认 SoC TX 侧 AC 耦合电容已存在，避免额外重复串联电容。

### 4.2 上电检查

至少测量以下项目：

| 测试项 | 预期结果 |
|---|---|
| M.2 3.3V | 上电稳定，无明显跌落 |
| Wi-Fi 3.3V | `WIFI_PWR_EN` 有效后稳定输出 |
| ASM1182e 3.3V | 电源使能后正常 |
| ASM1182e 1.2V | 电源使能后正常 |
| REFCLK | 对应端口存在约 100MHz 差分参考时钟 |
| PERST# | 上电初期保持低，电源和时钟稳定后变高 |
| CLKREQ# | 电平和低功耗状态符合器件要求 |

推荐的 ASM1182e 初始上电顺序：

1. 拉有效 `ASM1182e_PWR_EN`。
2. 等待 3.3V、1.2V 电源稳定。
3. 确保 PCIe 参考时钟稳定。
4. 保持上游 PERST# 为低，初次调试可预留 100～200ms。
5. 释放 `K3_PCIE0_PERSTN`。
6. ASM1182e 完成初始化后，通过 `PE_RST_OUT` 释放下游设备。

具体延时应结合 ASM1182e 和 K3 的数据手册确认。

## 5. BSP 和设备树适配

以下 DTS 代码仅表达配置结构。节点名、GPIO 控制器、引脚号、时钟、复位和 PHY 参数必须替换为 K3 BSP 中的真实定义。

### 5.1 适配 PCIe 3.0 x4 M2_1

```dts
&pcie30_port0 {
    status = "okay";
    num-lanes = <4>;
    max-link-speed = <3>;

    vpcie3v3-supply = <&vcc3v3_m2_1>;
    reset-gpios = <&gpioX PIN_M2_1_PERST GPIO_ACTIVE_LOW>;
};
```

适配要求：

- 配置为 RC 模式。
- Lane 数配置为 x4，不要配置成 x1 或 x2。
- 启用对应 PCIe 3.0 PHY、参考时钟和控制器复位。
- 正确描述 3.3V 插槽电源及 PERST#。
- MSI/MSI-X 必须正常，NVMe 驱动通常依赖 MSI/MSI-X。

### 5.2 适配 PCIe 2.0 x1 至 ASM1182e

```dts
&pcie20_1 {
    status = "okay";
    num-lanes = <1>;
    max-link-speed = <2>;

    vpcie3v3-supply = <&vcc3v3_asm1182>;
    reset-gpios = <&gpioX PIN_ASM_PERST GPIO_ACTIVE_LOW>;
};
```

还应把 `ASM1182e_PWR_EN` 描述为固定电源、GPIO 电源或板级控制信号。例如：

```dts
vcc3v3_asm1182: regulator-asm1182 {
    compatible = "regulator-fixed";
    regulator-name = "vcc3v3-asm1182";
    regulator-min-microvolt = <3300000>;
    regulator-max-microvolt = <3300000>;
    gpio = <&gpioX PIN_ASM_PWR_EN GPIO_ACTIVE_HIGH>;
    enable-active-high;
    startup-delay-us = <100000>;
};
```

注意事项：

- `reset-gpios`、`perst-gpios` 或专用 reset 控制器的写法取决于 K3 PCIe binding。
- ASM1182e 是透明 PCIe Switch，通常不需要厂商专用 Linux 驱动。
- 不需要在设备树中静态创建下游 NVMe 和 Wi-Fi PCIe 设备。
- PCIe `bus-range` 和 MMIO `ranges` 必须能够容纳交换芯片及下游桥和设备。
- 如果原理图中的可选 EEPROM 已焊接，应核对其配置内容；如果未焊接，应确认 ASM1182e 默认 strap 配置能够正常工作。

### 5.3 适配 M2_2 的 PCIe/SATA 复用

#### 选择 PCIe/NVMe 模式

```dts
&pcie_combo_port {
    status = "okay";
    num-lanes = <1>;
};

&sata_port {
    status = "disabled";
};
```

同时把 Combo PHY 设置为 PCIe 模式。

#### 选择 SATA 模式

```dts
&pcie_combo_port {
    status = "disabled";
};

&sata_port {
    status = "okay";
};
```

同时把 Combo PHY 设置为 SATA 模式并启用 AHCI 驱动。

禁止同时启用 PCIe 和 SATA 控制器，否则可能出现 PHY 申请冲突、控制器初始化失败或接口完全不工作。

### 5.4 适配 E-Key Wi-Fi 和 Bluetooth

Wi-Fi 部分需要：

- ASM1182e 下游 PCIe 链路正常。
- `WIFI_PWR_EN` 打开 `WIFI_3V3`。
- `WL_REG_ON`、`WIFI_DISABLE_L` 处于允许工作状态。
- 根据 Wi-Fi 芯片型号启用对应内核驱动和固件。
- 如需系统唤醒，配置 `WIFI_WAKE` 中断和 wakeup 属性。

Bluetooth 部分需要：

- 启用连接到 `HUB_HOST_DP4/DM4` 的 USB Host/Hub 端口。
- `BT_DISABLE_L` 处于允许工作状态。
- 启用 `CONFIG_BT_HCIBTUSB` 或模块要求的其他驱动。
- 如需唤醒，配置 `BT_HOST_WAKE`。

`32KOUT_WIFI` 经过电平转换后提供给无线模块。若模块要求外部 32.768kHz 时钟，应确认该时钟已打开且电压域正确。

## 6. 内核配置检查

建议至少检查：

```text
CONFIG_PCI=y
CONFIG_PCIEPORTBUS=y
CONFIG_PCI_MSI=y
CONFIG_PCIEASPM=y
CONFIG_BLK_DEV_NVME=y

CONFIG_ATA=y
CONFIG_SATA_AHCI=y
CONFIG_SATA_AHCI_PLATFORM=y

CONFIG_USB=y
CONFIG_USB_XHCI_HCD=y
CONFIG_BT=y
CONFIG_BT_HCIBTUSB=y
CONFIG_RFKILL=y
```

同时启用 K3 对应的：

- PCIe Host Controller 驱动。
- PCIe/Combo PHY 驱动。
- 时钟、复位、GPIO 和 regulator 驱动。
- 实际 Wi-Fi 芯片驱动及固件加载支持。

如果需要从 NVMe 启动，还应在 U-Boot 中启用对应 PCIe Host、NVMe、分区和文件系统支持，并同步修改 U-Boot 使用的设备树。

## 7. 分阶段调试流程

为减少多个端口互相干扰，建议按以下顺序逐项启用。

### 7.1 第一阶段：直连 PCIe 3.0 x4

初次调试只启用 `PCIE30_PORT0 → M2_1`，其余 PCIe 控制器先关闭。

```bash
dmesg | grep -Ei 'pci|pcie|nvme|aer'
lspci -nn
lspci -tv
nvme list
```

查看链路能力和协商结果：

```bash
lspci -s <NVMe-BDF> -vv
```

目标结果：

```text
LnkSta: Speed 8GT/s, Width x4
```

如果只能协商到 x1、x2 或 Gen1，应检查 Lane 配置、PHY、参考时钟、供电和信号完整性。

### 7.2 第二阶段：ASM1182e 上行链路

启用 `PCIE20_1`、ASM1182e 电源和复位，暂时可以不插下游设备。

```bash
lspci -nn
lspci -tv
dmesg | grep -Ei 'pci|pcie|link|aer'
```

预期能看到 ASMedia PCI bridge。ASMedia 的 PCI Vendor ID 通常为 `1b21`，实际 Device ID 以枚举结果为准。

### 7.3 第三阶段：ASM1182e 下游设备

分别插入扩展 NVMe 和 E-Key 无线模块：

```bash
lspci -tv
lspci -nnk
nvme list
lsusb
rfkill list
```

预期拓扑类似：

```text
K3 PCIe Root Port
└── ASM1182e
    ├── PCI bridge
    │   └── NVMe SSD
    └── PCI bridge
        └── PCIe Wi-Fi
```

蓝牙设备应出现在 `lsusb` 中，而不是 `lspci` 中。

### 7.4 第四阶段：M2_2 Combo PHY

分别生成 PCIe 版本和 SATA 版本的设备树进行验证：

- PCIe 模式：使用 NVMe SSD，检查 `lspci` 和 `nvme list`。
- SATA 模式：使用 SATA M.2 SSD，检查 `dmesg`、`lsblk` 和 AHCI 日志。

### 7.5 第五阶段：低功耗和压力测试

基础链路稳定后，再启用 ASPM、CLKREQ#、WAKE# 和系统休眠唤醒。

```bash
lspci -vv | grep -E 'LnkCap|LnkSta|ASPM'
dmesg -w | grep -Ei 'pcie|aer|nvme|timeout|link'
```

建议测试：

- NVMe 连续读写和多轮重启。
- 多块设备同时启动。
- ASM1182e 下游 NVMe 与 Wi-Fi 同时传输。
- 冷启动、热重启、待机和唤醒。
- 高低温条件下的链路稳定性。

初次定位链路问题时，可以临时限制为 Gen1 或关闭 ASPM；确认根因后应恢复目标速率和电源管理配置。

## 8. 常见问题定位

| 现象 | 优先检查项 |
|---|---|
| PCIe Root Port 报 Link Down | PHY 模式、参考时钟、PERST#、3.3V、Lane 配置 |
| 看不到 ASM1182e | 1.2V/3.3V、`ASM1182e_PWR_EN`、上游 REFCLK、上游 PERST# |
| 能看到 ASM1182e，但下游都看不到 | `PE_RST_OUT`、下游时钟、插槽 3.3V、bus-range/MMIO资源 |
| 只看不到扩展 NVMe | M.2 插槽供电、Port 5 连接、SSD兼容性、PERST# |
| Wi-Fi 不存在 | Wi-Fi 3.3V、WL_REG_ON、WIFI_DISABLE_L、PCIe下游链路 |
| Wi-Fi 正常但蓝牙不存在 | USB Host/Hub、USB D+/D-、BT_DISABLE_L、BT USB驱动 |
| M2_2 完全不工作 | PCIe/SATA 模式选择错误、Combo PHY 冲突 |
| NVMe 枚举后超时 | MSI/MSI-X、供电跌落、AER、IOMMU/SMMU、链路稳定性 |
| 链路降到 Gen1/x1 | Lane/PHY配置、阻抗、串扰、时钟质量、供电、连接器接触 |
| 休眠后设备丢失 | ASPM、CLKREQ#、WAKE#、电源域和 PERST# 恢复时序 |

## 9. 性能预期

| 接口 | 理论链路 | 使用建议 |
|---|---|---|
| M2_1 | PCIe 3.0 x4，理论约 3.9GB/s | 系统盘、高速 NVMe |
| M2_2 PCIe模式 | PCIe x1，速率取决于 K3 控制器 | 普通 NVMe或扩展设备 |
| M2_2 SATA模式 | SATA，速率取决于 SATA控制器 | SATA M.2 SSD |
| ASM1182e 下游总带宽 | PCIe 2.0 x1 上行，所有下游共享 | Wi-Fi、低吞吐 NVMe |

ASM1182e 上行的有效总吞吐通常为约 400MB/s 量级，扩展 NVMe 与 Wi-Fi 同时工作时会竞争这条链路。因此不能把 ASM1182e 下游 M.2 当作 PCIe 3.0 x4 接口使用。

## 10. 验收标准

完成适配后，应至少满足以下条件：

- [ ] M2_1 能稳定枚举 NVMe，链路达到 Gen3 x4。
- [ ] ASM1182e 每次冷启动和热重启均能稳定枚举。
- [ ] ASM1182e 下游 NVMe 和 PCIe Wi-Fi 均能正常枚举。
- [ ] E-Key 蓝牙能够通过 USB 正常识别。
- [ ] M2_2 能按选定模式稳定工作，PCIe/SATA 不发生 PHY 冲突。
- [ ] 所有 PCIe 设备使用 MSI/MSI-X 时无中断异常。
- [ ] 压力测试期间无持续 AER、Completion Timeout 或 NVMe reset。
- [ ] 多轮冷启动、热重启、休眠唤醒后设备不丢失。
- [ ] ASPM 开启后链路仍保持稳定。
- [ ] 实际链路宽度和速率符合对应接口设计。

## 11. 后续实施建议

实际修改 K3 BSP 时，建议依次提交以下内容：

1. PCIe 3.0 x4 M2_1 的控制器、PHY、电源和复位配置。
2. ASM1182e 的电源控制、复位时序及 PCIe 2.0 x1 上行配置。
3. Wi-Fi/BT 电源、使能、USB和唤醒配置。
4. M2_2 的 PCIe/SATA 两套互斥配置。
5. ASPM、休眠唤醒和压力测试相关优化。

每完成一个阶段，都应保留启动日志、`lspci -tv`、`lspci -vv` 和电源/复位测量结果，避免多个端口同时修改后难以定位故障。
