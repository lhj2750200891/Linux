# K3-AIBOX-PRO PCIe 连接关系速查

## 1. 整体拓扑

```text
K3 SoC
├── PCIE30_PORT0（PCIe 3.0 x4）
│   └── M2_1：M-Key 2280 NVMe
│
├── PCIE0 / SATA Combo PHY（x1）
│   └── M2_2：M-Key 2280，PCIe或SATA二选一
│
└── PCIE20_1（PCIe 2.0 x1）
    └── ASM1182e PCIe Switch
        ├── Port 5 → 扩展 M-Key M.2
        └── Port 7 → E-Key Wi-Fi
                     └── Bluetooth另外通过USB 2.0连接
```

## 2. 接口快速对应表

| 接口 | 上游连接 | PCIe宽度 | 电源 | 原理图 |
|---|---|---:|---|---|
| M2_1 | K3 `PCIE30_PORT0`直连 | x4 | `OVCC3V3_M2-1` | `pcie-3.png`上半部分、`pcie-5.png` |
| M2_2 | K3 `PCIE0/SATA` Combo PHY直连 | x1 | `OVCC3V3_M2-2` | `pcie-3.png`下半部分、`pcie-5.png` |
| 扩展 M.2 | ASM1182e Port 5 | x1 | `OVCC3V3_PCIE1` | `pcie-1.png`、`pcie-4.png` |
| E-Key Wi-Fi | ASM1182e Port 7 | x1 | `WIFI_3V3` | `pcie-2.png`、`pcie-4.png` |
| ASM1182e | K3 `PCIE20_1` | 上行x1 | `VCC33_82`、`VCC12_82` | `pcie-4.png` |

## 3. M2_1：PCIe 3.0 x4直连

位置：`pcie-3.png`上半部分，连接器 U7。

```text
K3 PCIE30_PORT0_CLK_P/N  → M2_1 REFCLKP/REFCLKN
K3 PCIE30_PORT0_TX0～TX3 → M2_1 PET0～PET3
K3 PCIE30_PORT0_RX0～RX3 ← M2_1 PER0～PER3
K3 PCIE1_RST             → M2_1 PERST#
K3 PCIE1_CLKREQ          ← M2_1 CLKREQ#
K3 PCIE_WAKE             ← M2_1 PEWAKE#
```

电源连接：

```text
VCC_DC
  → U9 DC-DC
  → VCC3V3_AC1
  → R195（10mΩ电流采样）
  → OVCC3V3_M2-1
  → M2_1的3.3V引脚
```

控制和监测：

```text
AC_3V3_EN  → U9 EN
U9 PGOOD   → VDDC_PG_3
U16        → 通过I2C4监测M2_1电压和电流
```

用途：优先连接 PCIe 3.0 x4 NVMe SSD。

## 4. M2_2：PCIe/SATA复用接口

位置：`pcie-3.png`下半部分，连接器 U19。

```text
K3 PCIE0_EP_CLK_P/N          → M2_2 REFCLKP/REFCLKN
K3 PCIE0_TX0_P/N或SATA_TX_P/N → M2_2 PET0P/N
K3 PCIE0_RX0_P/N或SATA_RX_P/N ← M2_2 PER0P/N
K3 PCIE0_RST                 → M2_2 PERST#
K3 PCIE0_CLKREQ              ← M2_2 CLKREQ#
K3 PCIE_WAKE                 ← M2_2 PEWAKE#
```

电源连接：

```text
VCC_DC
  → U35 DC-DC
  → VCC3V3_AC2
  → R432（10mΩ电流采样）
  → OVCC3V3_M2-2
  → M2_2的3.3V引脚
```

控制和监测：

```text
AC_3V3_EN  → U35 EN
U35 PGOOD  → VDDC_PG_4
U36        → 通过I2C4监测M2_2电压和电流
```

注意：PCIe和SATA共用一组高速差分线及 Combo PHY，软件中只能选择一种模式。

## 5. ASM1182e上行连接

位置：`pcie-4.png`，U20。

```text
K3 PCIE20_1_TX_P/N       → ASM1182e上行RX_P/N
K3 PCIE20_1_RX_P/N       ← ASM1182e上行TX_P/N
K3 PCIE20_1_REFCLK_P/N   → ASM1182e上行PECLK_P/N
K3 PCIE0_CLKREQ_N        ↔ ASM1182e PECLKREQ#
K3 PCIE0_PERSTN          → Q22 → ASM1182e PE_RST_82
ASM1182e PE_RST_OUT_82   → 下游M.2和Wi-Fi复位
```

部分高速网络名带有 `SATA30_1`，说明该 SoC PHY 可能也存在模式复用。适配时应确认该 PHY 已选择 PCIe模式。

电源连接：

```text
ASM1182e_PWR_EN
  ├── 控制3.3V电源路径 → VCC33_82
  └── 控制1.2V DC-DC   → VCC12_82/VDD12_82
```

ASM1182e的正确上电顺序：

```text
打开ASM1182e电源
  → 3.3V和1.2V稳定
  → 100MHz参考时钟稳定
  → 释放PE_RST_82
  → ASM1182e释放PE_RST_OUT_82
  → 下游设备开始链路训练
```

## 6. ASM1182e Port 5：扩展 M.2

接口位置：`pcie-1.png`，U17。

```text
ASM1182e PECLKIN5_P/N → PCIE0_M2_CLK_P/N → M.2 REFCLKP/REFCLKN
ASM1182e TX5_P/N      → PCIE0_TX0_P/N_M2  → M.2 PET0P/N
ASM1182e RX5_P/N      ← PCIE0_RX0_P/N_M2  ← M.2 PER0P/N
ASM1182e PE_RST_OUT   → PCIE0_RST_OUT     → M.2 PERST#
M.2 CLKREQ#           → PCIE0_CLKREQ
M.2 PEWAKE#           → PCIE_WAKE
```

特点：

- 只连接 Lane 0，因此是 PCIe x1。
- 没有连接 SATA差分线，按当前原理图只能使用 PCIe/NVMe设备。
- 与 E-Key Wi-Fi共享 ASM1182e 的 PCIe 2.0 x1 上行带宽。

电源网络为 `OVCC3V3_PCIE1`。在目前图片中尚未看到该网络的完整电源源头，需要在其余电源页继续搜索 `OVCC3V3_PCIE1`。

## 7. ASM1182e Port 7：E-Key Wi-Fi/BT

接口位置：`pcie-2.png`，U52。

### 7.1 Wi-Fi的PCIe连接

```text
ASM1182e PECLKIN7_P/N → PCIE0_WIFI_CLK_P/N → E-Key REFCLKP/REFCLKN
ASM1182e TX7_P/N      → PCIE0_TX0_P/N_WIFI  → E-Key PET0P/N
ASM1182e RX7_P/N      ← PCIE0_RX0_P/N_WIFI  ← E-Key PER0P/N
ASM1182e PE_RST_OUT   → PCIE0_RST_OUT       → E-Key PERST#
E-Key CLKREQ#         → WIFI_CLKREQ
E-Key PEWAKE#         → PCIE_WAKE
```

### 7.2 Bluetooth和辅助信号

```text
E-Key USB_DP/DM      ↔ HUB_HOST_DP4/DM4   （Bluetooth USB 2.0）
32KOUT_WIFI          → E-Key 32.768kHz时钟
WL_REG_ON            → 无线模块WLAN使能
WIFI_DISABLE_L       → WLAN禁用控制
BT_DISABLE_L         → Bluetooth禁用控制
WIFI_WAKE            ← WLAN唤醒
BT_HOST_WAKE         ← Bluetooth唤醒
```

电源连接：

```text
VCC3V3_SYS
  → U51电源开关
  → WIFI_3V3
  → E-Key 3.3V引脚

WIFI_PWR_EN → U51 EN
```

注意：Wi-Fi出现在 `lspci`，Bluetooth出现在 `lsusb`，应分开排查。

## 8. M.2公共电源控制

`pcie-5.png` 中 U9和U35共用同一个使能信号：

```text
AC_3V3_EN
  ├── U9 EN  → M2_1电源
  └── U35 EN → M2_2及相关M.2电源
```

所以设备树中不要让两个独立 regulator 节点重复申请同一个 GPIO。建议将其建模为一个公共 M.2 电源使能域，或者由板级电源时序统一控制。

`pcie-5.png` 中还有一路：

```text
VCC3V3_AC2 → R430 → OVCC3V3_M2_2
```

`OVCC3V3_M2_2` 与 `OVCC3V3_M2-2` 名称不同。当前 5 张图片不足以确认它最终连接到哪个接口，应按完整原理图网络名继续追踪，不能直接认为两者是同一网络。

## 9. ASM1182e配置I2C

`pcie-4.png` 左下角 U28 是可选的 24C08 配置 EEPROM：

```text
ASM1182e MSCL/MSDA → U28 24C08
```

用途是让 ASM1182e 在上电时读取端口和功能配置。默认情况下，连接 K3 I2C4 的 R324/R325 标注为 `NC`，因此该总线通常由 ASM1182e自己使用，不需要在 K3 Linux设备树中添加 EEPROM节点。

## 10. 按故障现象查连接

| 故障现象 | 首先检查的连接 |
|---|---|
| M2_1完全没有电 | `AC_3V3_EN → U9 → R195 → OVCC3V3_M2-1` |
| M2_2完全没有电 | `AC_3V3_EN → U35 → R432 → OVCC3V3_M2-2` |
| M2_1有电但Link Down | `PCIE30_PORT0`时钟、Lane 0～3、PERST# |
| M2_2有电但Link Down | Combo PHY的PCIe/SATA模式、时钟、PERST# |
| 看不到ASM1182e | `ASM1182e_PWR_EN`、3.3V、1.2V、上行时钟、`PE_RST_82` |
| 能看到ASM1182e但下游都没有 | `PE_RST_OUT_82`、Port 5/7时钟、下游3.3V |
| Wi-Fi不存在 | ASM Port 7、`WIFI_PWR_EN`、`WL_REG_ON`、`WIFI_DISABLE_L` |
| Wi-Fi正常但蓝牙不存在 | `HUB_HOST_DP4/DM4`、`BT_DISABLE_L`、USB Host配置 |
| NVMe启动时掉电 | M.2 3.3V压降、10mΩ采样电阻、DC-DC限流和输入电源 |

## 11. 原理图图片索引

| 图片 | 主要内容 |
|---|---|
| `pcie-1.png` | ASM1182e Port 5下游 M-Key M.2 |
| `pcie-2.png` | ASM1182e Port 7下游 E-Key Wi-Fi/BT |
| `pcie-3.png` | 直连 PCIe 3.0 x4 M2_1和PCIe/SATA复用 M2_2 |
| `pcie-4.png` | ASM1182e、上下行高速线、电源、复位和配置EEPROM |
| `pcie-5.png` | M.2 3.3V DC-DC、电源使能、电流采样和I2C监控 |
