# AI-BOX-PRO-M2 模块与 J2（1～260）引脚对应表

## 1. 文档说明

- 原理图文件：`K3_Linux_SDK_6.18/subject.pdf`
- 原理图标题：`MB-AIBOX PRO-V02-20260715`
- 原理图版本：`V0.2`
- 物理引脚编号依据：原理图第 4 页 `04.MXM Connector(main)` 中的 `J2`
- J2 编号读取规则：**以信号连接线正下方标注的数字作为该连接线的物理引脚编号**，不能使用连接线上方或视觉距离最近的数字。
- 本文只整理载板功能模块实际使用的 J2 物理编号，不展开模块内部芯片引脚。
- 普通 GND 引脚未在每个模块中重复列出；主供电引脚单独汇总。
- 同一个 J2 引脚可能因 0Ω 电阻、模拟开关或不同装配方案被多个模块复用，详见“复用与装配注意事项”。

## 2. 主供电与系统控制

### 2.1 CORE_VCC / VDD_IN 主供电

| 电源网络 | J2 编号 | J2 引脚名称 |
|---|---:|---|
| CORE_VCC | 253 | VDD_IN1 |
| CORE_VCC | 254 | VDD_IN2 |
| CORE_VCC | 255 | VDD_IN3 |
| CORE_VCC | 256 | VDD_IN4 |
| CORE_VCC | 257 | VDD_IN5 |
| CORE_VCC | 258 | VDD_IN6 |
| CORE_VCC | 259 | VDD_IN7 |
| CORE_VCC | 260 | VDD_IN8 |

### 2.2 电源、复位与休眠控制

| 原理图页 | 模块信号 | J2 编号 | J2 侧名称/说明 |
|---|---|---:|---|
| 8 | MOD_SLEEP* | 180 | 模组休眠控制 |
| 8 | SHUTDOWN_REQ | 235 | J2 侧为 `PMIC_EXT_EN` |
| 4 | PMIC_BBAT | 237 | PMIC 后备电源相关引脚 |
| 4 | POWER_EN | 239 | 模组电源使能 |
| 20 | SYS_RESET* | 241 | 系统复位输入 |
| 8 | SLEEP/WAKE | 242 | J2 侧为 `SLEEP/WAKE*` |

## 3. Micro-SD Card（第 9 页）

| Micro-SD 模块信号 | J2 编号 | J2 侧功能 |
|---|---:|---|
| GPIO53 | 208 | SD 卡检测相关 GPIO，J2 侧复用为 `SDMMC_DET/GPIO0_A4` |
| GPIO60 | 220 | SD 卡电源/控制 GPIO |
| SDMMC_DAT0 | 221 | SDMMC_D0 |
| SDMMC_DAT1 | 223 | SDMMC_D1 |
| SDMMC_DAT2 | 225 | SDMMC_D2 |
| SDMMC_DAT3 | 227 | SDMMC_D3 |
| SDMMC_CMD | 229 | SDMMC_CMD |
| SDMMC_CLK | 231 | SDMMC_CLK |

## 4. HDMI TX（第 10 页）

| HDMI 模块信号 | J2 编号 | J2 侧功能 |
|---|---:|---|
| HDMI_TX_SBD_N | 59 | HDMI0_TX1_SBDN / eDP AUXN |
| HDMI_TX_SBD_P | 61 | HDMI0_TX1_SBDP / eDP AUXP |
| HDMI_TX2_N | 65 | HDMI/DP 差分通道 |
| HDMI_TX2_P | 67 | HDMI/DP 差分通道 |
| HDMI_TX1_N | 71 | HDMI/DP 差分通道 |
| HDMI_TX1_P | 73 | HDMI/DP 差分通道 |
| HDMI_TX0_N | 77 | HDMI/DP 差分通道 |
| HDMI_TX0_P | 79 | HDMI/DP 差分通道 |
| HDMI_TXC_N | 83 | HDMI 时钟/DP Lane3 N |
| HDMI_TXC_P | 85 | HDMI 时钟/DP Lane3 P |
| HDMI_TX_ON_H | 90 | HDMI 电源/输出控制 |
| HDMI_TX_CEC_M0 | 96 | HDMI CEC |
| HDMI_TX_HPDIN_M0 | 98 | HDMI Hot Plug Detect |
| HDMI_TX_SDA | 100 | HDMI DDC SDA，同时被 DP 模块使用 |
| HDMI_TX_SCL | 102 | HDMI DDC SCL，同时被 DP 模块使用 |

## 5. USB2.0 HUB（第 11 页）

| USB2 HUB 信号 | J2 编号 | 说明 |
|---|---:|---|
| AC_FAN_PWM | 89 | 原理图第 4 页交叉引用到第 11 页，同时也用于加速卡风扇控制 |
| HUB20_PWR_EN | 91 | USB2 HUB 电源使能 |
| USB20_VCC5V0_EN | 224 | USB2.0 端口 5V 电源使能 |

## 6. Audio Port（第 12 页）

| 音频模块信号 | J2 编号 | J2 侧功能 |
|---|---:|---|
| HP_DET_L | 114 | 耳机插入检测 |
| PHONE_CTL | 122 | 耳机/音频通路控制 |
| SARADC3 | 149 | J2 侧为 `SARADC_IN6` |
| I2C4_SCL | 187 | Codec/外设控制 I2C 时钟 |
| I2C4_SDA | 189 | Codec/外设控制 I2C 数据 |
| I2S0_DOUT | 195 | I2S0_SDO0 |
| I2S0_DIN | 197 | I2S0_SDI0 |
| I2S0_FS | 199 | I2S0_LRCK |
| I2S0_SCLK | 201 | I2S0_SCLK |
| I2S0_MCLK | 213 | I2S0_MCLK |

## 7. USB3.0 HUB（第 13 页）

| USB3 HUB 信号 | J2 编号 | 说明 |
|---|---:|---|
| USBSS0_RX_N | 41 | USB3 SuperSpeed RX N |
| USBSS0_RX_P | 43 | USB3 SuperSpeed RX P |
| USBSS0_TX_N | 47 | USB3 SuperSpeed TX N |
| USBSS0_TX_P | 49 | USB3 SuperSpeed TX P |
| USB0_D_N | 109 | 经第 4 页 USB 模拟开关 U8 接到 `USB0_DN` |
| USB0_D_P | 111 | 经第 4 页 USB 模拟开关 U8 接到 `USB0_DP` |
| USB30_HUB_RST | 126 | USB3 HUB 复位，原理图中为可选/装配网络 |

## 8. USB3.0 Port（第 14 页）

| USB3 端口信号 | J2 编号 | 说明 |
|---|---:|---|
| USB30_VCC5V0_EN | 226 | USB3.0 端口 5V 电源使能 |

## 9. RS232（第 15 页）

| RS232 模块信号 | J2 编号 | 说明 |
|---|---:|---|
| UART8_TX_M0 | 205 | RS232 发送数据 |
| UART8_RX_M0 | 207 | RS232 接收数据；与第 4 页 `USB_SEL` 装配网络存在复用 |

## 10. RS485（第 16 页）

| RS485 模块信号 | J2 编号 | 第 4 页中间网络名 | 说明 |
|---|---:|---|---|
| UART3_TXD | 101 | RS485_TX | RS485 收发器发送输入 |
| UART3_RXD | 103 | RS485_RX | RS485 收发器接收输出 |
| 485_RE_DE | 105 | RS485_RE_DE | RS485 接收/发送方向控制 |

## 11. SPI-CAN / MCP2518FD（第 17 页）

| SPI-CAN 模块信号 | J2 编号 | J2 侧复用功能 |
|---|---:|---|
| SPI1_MOSI | 106 | SPI1_MOSI_M2 / GPIO1_D1 |
| SPI1_SCK | 108 | SPI1_CLK_M2 / GPIO1_D2 |
| SPI1_MISO | 110 | SPI1_MISO_M2 / GPIO1_D0 |
| SPI1_CS_N | 112 | SPI1_CS0_M2 / GPIO1_D3 |
| CAN_INT | 214 | GPIO/中断输入；原理图网络为 `CAN_INT` |

> `CAN_INT` 的 J2 物理编号是 214。设备树中的 `gpio56` 是 SoC GPIO 控制器内部编号，不等于 J2 物理引脚编号。

## 12. DP Connector（第 18 页）

| DP 模块信号 | J2 编号 | 说明 |
|---|---:|---|
| HDMI_TX2_N / DP Lane2 N | 65 | 与 HDMI 共用高速通道 |
| HDMI_TX2_P / DP Lane2 P | 67 | 与 HDMI 共用高速通道 |
| HDMI_TX1_N / DP Lane1 N | 71 | 与 HDMI 共用高速通道 |
| HDMI_TX1_P / DP Lane1 P | 73 | 与 HDMI 共用高速通道 |
| HDMI_TX0_N / DP Lane0 N | 77 | 与 HDMI 共用高速通道 |
| HDMI_TX0_P / DP Lane0 P | 79 | 与 HDMI 共用高速通道 |
| HDMI_TXC_N / DP Lane3 N | 83 | 与 HDMI 时钟通道共用 |
| HDMI_TXC_P / DP Lane3 P | 85 | 与 HDMI 时钟通道共用 |
| HDMI_TX_SDA | 100 | DP AUX/控制相关复用网络 |
| HDMI_TX_SCL | 102 | DP AUX/控制相关复用网络 |
| 3V3_DP_EN | 124 | DP 3.3V 电源使能 |

## 13. Ethernet / NET_PROT（第 19 页）

### 13.1 GBE1

| 网络信号 | J2 编号 |
|---|---:|
| GBE1_MDI0_P | 70 |
| GBE1_MDI0_N | 72 |
| GBE1_MDI1_P | 74 |
| GBE1_MDI1_N | 76 |
| GBE1_MDI2_P | 80 |
| GBE1_MDI2_N | 82 |
| GBE1_MDI3_P | 84 |
| GBE1_MDI3_N | 86 |
| PHY1_CFG_EXT | 92 |
| PHY1_CFG_LDO1 | 94 |

### 13.2 GBE0

| 网络信号 | J2 编号 |
|---|---:|
| GBE0_MDI0_N | 186 |
| GBE0_MDI0_P | 188 |
| PHY0_CFG_EXT | 190 |
| GBE0_MDI1_N | 192 |
| GBE0_MDI1_P | 194 |
| PHY0_CFG_LDO1 | 196 |
| GBE0_MDI2_N | 198 |
| GBE0_MDI2_P | 200 |
| GBE0_MDI3_N | 204 |
| GBE0_MDI3_P | 206 |

## 14. KEY / LED（第 20 页）

| 按键/LED 信号 | J2 编号 | 说明 |
|---|---:|---|
| GPIO_1 | 116 | 通用按键/GPIO |
| GPIO_2 | 118 | 通用按键/GPIO |
| GPIO_3 | 120 | 通用按键/GPIO |
| FORCE_RECOVERY* | 216 | 强制恢复按键 |
| LED1 | 218 | 用户/状态 LED |
| TEST_LED | 222 | 测试 LED |
| LED2 | 234 | 用户/状态 LED |
| SYS_RESET* | 241 | 系统复位按键 |

## 15. FAN / CONNECTOR（第 21 页）

| 风扇模块信号 | J2 编号 | 说明 |
|---|---:|---|
| FAN_TACH_OTHER | 55 | 经第 4 页装配电阻接入 `FAN_TACH` 的候选来源 |
| FAN_TACH_NV | 208 | 经第 4 页二极管汇合到 `FAN_TACH` 的候选来源 |
| GPIO114 / FAN_PWM | 232 | `GPIO114` 驱动/连接第 21 页风扇 PWM 通路 |

> `FAN_TACH` 不是单一 J2 引脚直接连接。第 4 页通过 `FAN_TACH_NV`、`FAN_TACH_OTHER` 和装配器件选择/汇合，实际使用哪一路应结合 R33、R242、D52、D53 的实装情况确认。

## 16. USB2.0 OTG Type-C（第 22 页）

| USB OTG 信号 | 最终 J2 编号 | 说明 |
|---|---:|---|
| USB_OTG_D_N | 109 | 经第 4 页 U8 模拟开关后接到 `USB0_DN` |
| USB_OTG_D_P | 111 | 经第 4 页 U8 模拟开关后接到 `USB0_DP` |
| USB_SEL | 207 | U8 通道选择；与 `UART8_RX_M0` 所在引脚存在装配复用 |

## 17. USB Type-C Debug（第 23 页）

| 调试串口信号 | J2 编号 |
|---|---:|
| UART0_TXD_1V8 | 238 |
| UART0_RXD_1V8 | 240 |

## 18. 4G/5G Module（第 24 页）

| 4G/5G 模块信号 | J2 编号 | 说明 |
|---|---:|---|
| 4G_PWR_EN | 211 | 4G/5G 模块电源使能 |

> 4G/5G 模块的 USB 数据通道来自板载 USB HUB 页面之间的网络连接，不是全部直接连接到 J2，因此这里只列直接连接 J2 的控制信号。

## 19. M.2 PCIe（第 25 页）

| M.2 PCIe 信号 | J2 编号 | 说明 |
|---|---:|---|
| PCIE_WAKE* | 181 | M.2 PCIe 唤醒信号，共用于第 25、26、28 页 |

> 第 25 页 M.2 PCIe 的主要高速数据和时钟由 ASM1182e/其他 PCIe 页面转接，不全部直接连接 J2。

## 20. M.2 PCIe Wi-Fi / Bluetooth（第 26 页）

| Wi-Fi/BT 信号 | J2 编号 | 说明 |
|---|---:|---|
| K3_PCIED_CLKREQN | 97 | K3 PCIe 时钟请求相关控制 |
| BT_DISABLE | 130 | Bluetooth 禁用控制 |
| AP_M2_WAKE_BT | 132 | AP 唤醒 Bluetooth |
| PCIE_WAKE* | 181 | PCIe Wake |
| 32KOUT_WIFI | 212 | Wi-Fi 32kHz 时钟输出 |
| BT_M2_WAKE_AP | 215 | Bluetooth 唤醒 AP |
| WIFI_PWR_EN | 228 | Wi-Fi 电源使能 |
| WIFI_DIS | 230 | Wi-Fi 禁用控制 |
| PCIE30X1_0_CLKREQN_M0 | 236 | PCIe CLKREQ |

## 21. Accelerator Card POWER/FAN（第 27 页）

| 加速卡模块信号 | J2 编号 | 说明 |
|---|---:|---|
| AC_FAN_PWM | 89 | 加速卡风扇 PWM |
| AC_3V3_EN | 107 | 加速卡 3.3V 电源使能 |
| I2C4_SCL | 187 | 加速卡管理 I2C 时钟 |
| I2C4_SDA | 189 | 加速卡管理 I2C 数据 |

## 22. PCIe 扩展接口（第 28 页）

### 22.1 PCIe 3.0 Port0 ×2

| PCIe 信号 | J2 编号 |
|---|---:|
| PCIE30_PORT0_RX0N | 133 |
| PCIE30_PORT0_RX0P | 135 |
| PCIE30_PORT0_TX0N | 136 |
| PCIE30_PORT0_TX0P | 138 |
| PCIE30_PORT0_RX1N | 139 |
| PCIE30_PORT0_RX1P | 141 |
| PCIE30_PORT0_TX1N | 142 |
| PCIE30_PORT0_TX1P | 144 |
| PCIE30_PORT0_CLKN | 162 |
| PCIE30_PORT0_CLKP | 164 |

### 22.2 PCIe 3.0 Port1 ×2

| PCIe 信号 | J2 编号 |
|---|---:|
| PCIE30_PORT1_TX0N | 150 |
| PCIE30_PORT1_RX0N | 151 |
| PCIE30_PORT1_TX0P | 152 |
| PCIE30_PORT1_RX0P | 153 |
| PCIE30_PORT1_TX1N | 156 |
| PCIE30_PORT1_RX1N | 157 |
| PCIE30_PORT1_TX1P | 158 |
| PCIE30_PORT1_RX1P | 159 |

### 22.3 PCIe 2.0 / SATA 复用通道

| PCIe/SATA 信号 | J2 编号 |
|---|---:|
| PCIE0_RX0_N / SATA_RX0_N | 169 |
| PCIE0_RX0_P / SATA_RX0_P | 171 |
| PCIE0_TX0_N / SATA_TX0_N | 174 |
| PCIE0_EP_CLK_N | 175 |
| PCIE0_TX0_P / SATA_TX0_P | 176 |
| PCIE0_EP_CLK_P | 177 |

### 22.4 PCIe 控制信号

| PCIe 控制信号 | J2 编号 |
|---|---:|
| PCIE_WAKE* | 181 |
| PCIE1_CLKREQ* | 182 |
| PCIE1_RST* | 183 |
| PCIE0_CLKREQ* | 184 |
| PCIE0_RST* | 185 |

## 23. ASM1182e PCIe Switch（第 30 页）

| ASM1182e 相关信号 | J2 编号 | 说明 |
|---|---:|---|
| PCIE20_1_RXN / SATA30_1_RXN | 42 | PCIe Switch 上行 RX N |
| PCIE20_1_RXP / SATA30_1_RXP | 44 | PCIe Switch 上行 RX P |
| PCIE20_1_TXN / SATA30_1_TXN | 48 | PCIe Switch 上行 TX N |
| PCIE20_1_TXP / SATA30_1_TXP | 50 | PCIe Switch 上行 TX P |
| PCIE20_1_REFCLKN | 54 | PCIe 参考时钟 N |
| PCIE20_1_REFCLKP | 56 | PCIe 参考时钟 P |
| ASM1182e_PWR_EN | 93 | ASM1182e 电源使能 |
| K3_PCIED_PERSTN | 95 | K3 到 PCIe Switch 的复位控制 |
| 1182_PCIE_RST | 145 | ASM1182e/下游 PCIe 复位 |
| I2C4_SCL | 187 | 管理 I2C 时钟 |
| I2C4_SDA | 189 | 管理 I2C 数据 |

## 24. 无直接 J2 信号的页面

| 原理图页 | 页面名称 | 说明 |
|---|---|---|
| 1 | History | 文档历史，无硬件连接 |
| 2 | Block Diagram | 系统框图，无直接 J2 引脚 |
| 3 | Power Tree | 电源树说明，无单独信号引脚 |
| 5 | DC IN | 通过系统电源网络最终向 VDD_IN 供电 |
| 6 | CORE-5V | 电源转换页面，最终向主供电网络供电 |
| 7 | System power | 系统电源转换页面，最终向主供电网络供电 |
| 29 | Mark/hole/shell | 结构、孔位和外壳，无电气信号 |

## 25. 复用与装配注意事项

| J2 编号 | 复用网络 | 注意事项 |
|---:|---|---|
| 41/43/47/49 | USB3.0 HUB SuperSpeed | USB3 HUB 专用高速差分组，应保持 90Ω 差分阻抗和 P/N 极性 |
| 55 | USB20_HOST1_DP / FAN_TACH_OTHER | 由 R33、R242 等装配选项决定，不能仅根据网络名判断最终用途 |
| 65/67/71/73/77/79/83/85 | HDMI / DP | HDMI 和 DP 共用高速通道，设备树与硬件通路必须选择一致 |
| 109/111 | USB3 HUB USB2 上行 / USB2 OTG | 通过第 4 页 U8 模拟开关切换，不是两个模块同时直连 |
| 126 | USB30_HUB_RST | 原理图中使用可选网络颜色标识，确认实装和默认上下拉 |
| 181 | PCIE_WAKE* | 第 25、26、28 页共享 |
| 187/189 | I2C4_SCL/SDA | Audio、Accelerator、ASM1182e 多模块共享同一 I2C 总线 |
| 207 | UART8_RX_M0 / USB_SEL | RS232 RX 与 USB 开关选择网络存在装配复用，确认电阻实际焊接方案 |
| 208 | GPIO53 / SD 卡检测 / FAN_TACH_NV | 同一物理引脚周边存在多个板级别名和装配通路 |
| 230 | WIFI_DIS | Wi-Fi 禁用控制信号，不再与上方编号的风扇 PWM 混淆 |
| 232 | GPIO114 / FAN_PWM | 第 21 页风扇 PWM 控制通路；编号取连接线下方的 `232` |

## 26. 与当前设备树适配相关的关键引脚

| 功能 | 信号 | J2 编号 |
|---|---|---:|
| RS232 | UART8_TX_M0 | 205 |
| RS232 | UART8_RX_M0 | 207 |
| RS485 | UART3_TXD | 101 |
| RS485 | UART3_RXD | 103 |
| RS485 | 485_RE_DE | 105 |
| MCP2518FD | SPI1_MOSI | 106 |
| MCP2518FD | SPI1_SCK | 108 |
| MCP2518FD | SPI1_MISO | 110 |
| MCP2518FD | SPI1_CS_N | 112 |
| MCP2518FD | CAN_INT | 214 |
