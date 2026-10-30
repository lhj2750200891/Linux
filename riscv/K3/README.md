# K3 (Spacemit) 平台适配笔记总览

　　Firefly K3 系列板卡 (AIBOX-K3 / AIBOX-PRO-K3 / ITX-K3L 等) 的 BSP
适配笔记索引。SDK:
`/media/lhj/data/t-chip/7.code/riscv/spacemit/k3_6.18.3_sdk/bsp-src/linux-6.18`
(内核 6.18, arch/riscv)。每份 md 自包含: 单份照做即可完成该模块适配,
不依赖读板级公共 dtsi (基座 SoC 四件套除外)。

## 1. 模块文件清单

| 模块 | 文件 | 方式划分 | 参考板 |
|---|---|---|---|
| LED | led.md | 三色灯 GPIO45/75/122; RS485 方向灯 | AIBOX-PRO / aibox-k3 |
| 按键 | key.md | GPIO 按键 (F12/power); RPMI 电源键 | AIBOX-PRO |
| 调试串口 | debug.md | uart0 三组 pad 选择 | 各板通用 |
| RTC | rtc.md | rpmi_rtc 零改动; PCF8563; HYM8563(定时开机) | aibox-k3 / AIBOX-PRO |
| 看门狗 | watch.md | SoC watchdog (删 spa,wdt-disabled); PC9202 私有 chrdev | aibox-k3 |
| 网口 | gmac.md | GMAC0-3 + YT8531, delayline 每板重调 | AIBOX-PRO (4口) |
| USB2.0 | usb20.md | 纯使能; GPIO 供电 regulator | AIBOX-PRO |
| USB3.0 | usb30.md | 四口直出; VL817 hub | aibox-k3 / AIBOX-PRO |
| Type-C | typec.md | fusb302 + tcpm (仅 5V, 无 PD 快充) | aibox-k3 (唯一) |
| PCIe | pcie.md | x4 槽; 1-lane M.2; ASM1182e 扩展; 多 RC 并存 | AIBOX-PRO / itx |
| WiFi/BT | wifi-bt.md | PCIe M.2 (无 SDIO 方案) + USB BT + rfkill | AIBOX-PRO / itx |
| DP | dp.md | DP1 直出; LT2404 桥接 + DP 音频 | aibox-k3 |
| eDP | edp.md | AUX/EDID 自检, 无 panel 节点 | deepcomputing |
| MIPI DSI | mipi-dsi.md | 屏表机制 (lcds+force-attached) + GT9xxx 触摸 | itx-k3l-DSI0 |
| MIPI CSI | mipi-csi.md | 三路 IMX415, 四套编号不对齐 | itx-k3l |
| HDMI | hdmi.md | **无原生 HDMI** = DP0 + LT2404 桥 | itx-k3l |
| SATA | sata.md | **无原生 SATA** = PCIe 转 AHCI 桥; UFS 顺带 | itx-k3l |
| SD/eMMC | sdcard.md | sdcard/sdio/emmc 三路 k3-sdhci; RPMI PMIC 供电 | itx / bananapi-f3 |
| 音频 | sound-card.md | i2s(sspa) + es8389 codec (compatible 陷阱) | itx FF_ES8390 |
| CAN | can.md | flexcan0-4 原生 5 路 (FD), 上游驱动 | 平台通用 |
| 杂项 | misc-modules.md | PWM×26/SPI/QSPI-NOR/IR/温控/风扇/EtherCAT/大块头索引 | spcda400 / bananapi-f3 |

## 2. 设备树基座 (所有 md 共用的 include)

```dts
#include <dt-bindings/gpio/gpio.h>       /* GPIO_ACTIVE_x */
#include <dt-bindings/input/input.h>     /* key.md 需要, 原在 common.dtsi */
#include "k3.dtsi"                       /* SoC 控制器全集 (RK3588 的 rk3588s.dtsi 对应物);
                                            K3_GPIO(x) 宏就定义在 k3.dtsi 头部 */
#include "k3-rdomain.dtsi"               /* RCPU 域: r_i2c/rpwm/adma/ri2s/sound_card_dpX */
#include "k3-pinctrl.dtsi"               /* 全部 pinctrl 组 (K3_PADCONF 宏) */
#include "k3_opp_table.dtsi"             /* CPU OPP */
```

　　与 RK3588 笔记的差别: K3 显示/摄像头节点**不在 k3.dtsi**, 按接口
拆分, 板级按需再 include: `k3-dp0.dtsi` / `k3-dp1.dtsi` /
`k3-edp0.dtsi` (DP0 与 eDP0 同物理通路, 二选一) / `lcd_dsi_panel.dtsi`
(DSI 链) / `k3-camera.dtsi` (CSI 全套) / `lcd/lcd_xxx.dtsi` (屏表)。

## 3. FF_* 宏体系 (Firefly 参考板的读法)

　　参考板按功能切成 `k3-firefly-<板>.dtsi` 主文件 + 每个外设一个
`#ifdef FF_XXX` 块, 顶层 dts 用 `#define FF_XXX` 决定烧哪种配置 —
**同一个板名有多个顶层 dts** (如 itx-k3l / itx-k3l-dsi0 /
itx-k3l-pciex16-slot), 差异只在宏组合:

| 宏 | 含义 |
|---|---|
| FF_HDMI0 / FF_DSI0_V3 (HDMI0_OR_DSI0) | pad 二选一: 1=HDMI0 (DP0+LT2404), 0=DSI0 屏 |
| PCIE_OR_SATA → FF_SATA_SSD / FF_PCIEX16_SLOT | 差分对二选一: 0=SATA 桥 (默认), 1=x16 槽 |
| FF_PCIE1 / FF_PCIE0 / FF_ASM1182e_PCIE0_M2/WIFI | PCIe 槽位分配 |
| FF_CAM_CSI0/1/2_IMX415 (+FF_PCA955X) | 摄像头路 |
| FF_DP1 | DP1 口 (aibox-k3 实装) |
| FF_PCA9555_1/2 | I2C GPIO 扩展器 (itx 屏控/外设脚都在上面) |

　　自研板建议**不用宏**, 直接把选定的 #ifdef 块内容抄进自己的 dts —
本系列 md 已替你展开完毕。

## 4. 引脚冲突速查表 (跨模块 pad/GPIO 复用互斥)

　　同一脚两种用途**不能共存** (func 互斥), 规划引脚前对照:

| 引脚 | 用途 A | 用途 B | 出处 |
|---|---|---|---|
| pad 54/55 | i2c1 (pcf8563 RTC) | gmac2 区块 pad | rtc.md / gmac.md |
| pad 75 | 绿色 LED (GPIO75) | cam0 clk (func2) | led.md / mipi-csi.md |
| pad 74 | cam1 clk (func2) | LT2404 reset GPIO74 (aibox-k3 DP1) | mipi-csi.md / dp.md |
| pad 85 | cam2 clk (func1) | LT2404 power GPIO85 (aibox-k3 DP1) | mipi-csi.md / dp.md |
| pad 99 | cam3 clk (func6, 3.3V) | — (cam 时钟档位与其他 func 互斥) | mipi-csi.md |
| pad 58/59/60 | pcie2 perst/wake/clkreq (func4) | Type-C INT58/VBUS_EN60 (GPIO) | pcie.md / typec.md |
| pad 106 | pwm18 (eDP 背光) | ASM1182e 电源 GPIO106 | edp.md / pcie.md |
| pad 107 | HDMI 3V3 使能 (itx) | pcie3 WiFi clkreq (AIBOX-PRO) | hdmi.md / wifi-bt.md |
| pad 100 | SATA 3V3 (itx) | usb3 vbus (aibox-k3) | sata.md / usb30.md |
| pad 38 | wifi_3v3 (itx) | DSI TE (dsi_1_cfg func6) | wifi-bt.md / mipi-dsi.md |
| GPIO 101 | pcf8563 INT (aibox-k3) | eDP 屏电源 gpios-power | rtc.md / edp.md |
| GPIO 118 | usb_sel | eDP 屏 enable gpios-enable | usb30.md / edp.md |
| pad 122-126 | mmc2 eMMC (func1) | 红色 LED (GPIO122) + pcie3_2 perst/wake/clkreq (func3, pad124-126) | sdcard.md / led.md / pcie.md |
| pad 76/78/80/81 | pcie4 perst/clkreq/wake (func5) | can0 档2 (pad76/77) + can3 档0 (pad80/81) | pcie.md / can.md |
| dp0 / edp0 | **同一物理通路** (同 DPU0 同 0xcac84000), 两个 dtsi 二选一 | | hdmi.md / edp.md |
| FF_HDMI0 / FF_DSI0 | 同一组 pad, 硬件二选一 | | hdmi.md / mipi-dsi.md |
| FF_SATA_SSD / FF_PCIEX16_SLOT | 同一差分对 (ASW3810 开关) | | sata.md / pcie.md |
| usb3_portb | USB3 口; WiFi-BT 方式降级 USB2-only | | usb30.md / wifi-bt.md |

## 5. k3_defconfig 缺项清单 (各 md 内核配置节的汇总)

　　已编好无需动: SERIAL_8250、STMMAC/DWMAC_SPACEMIT_ETHQOS、
USB_DWC3(+GENERIC_PLAT)、XHCI、PCIE_SPACEMIT_K1 (随 SOC_SPACEMIT 自动)、
RFKILL(_GPIO)、DRM_SPACEMIT、SPACEMIT_INNO_DP、SPACEMIT_MIPI_PANEL、
BT=m (HCIBTUSB/HCIUART=m)、MEDIA_SUPPORT + SPACEMIT_K3_CCIC(_IOMMU) +
CAM_IMX415、ATA/SATA_AHCI/BLK_DEV_SD/BLK_DEV_NVME、SCSI_UFS_SPACEMIT_K3、
MMC_SDHCI(_PLTFM/_OF_K1)、CAN + CAN_FLEXCAN、PWM_PXA、SPI +
SPI_SPACEMIT_K1 + SPI_SPIDEV + SPI_FSL_QUADSPI、MTD_SPI_NOR、
IR_SPACEMIT_K1、K3_THERMAL、SENSORS_PWM_FAN、EC_MASTER。

　　defconfig **没编, 按模块要补**:

| CONFIG | 模块 |
|---|---|
| LEDS_GPIO | led.md |
| KEYBOARD_GPIO | key.md |
| RTC_DRV_PCF8563 / RTC_DRV_HYM8563 | rtc.md |
| PC9202_WATCHDOG (厂商树外) | watch.md |
| TYPEC_TCPM + TYPEC_FUSB302 | typec.md |
| SPACEMIT_K3_CAM_IMX415_FF (可选, ioctl 版) | mipi-csi.md |
| SND_SOC_ES8389 (defconfig 仅 imply, 未编则补) | sound-card.md |
| SPI_K1_QSPI (与 FSL_QUADSPI 同 compatible, **二选一勿双开**) | misc-modules.md |

## 6. 厂商私有/遗留属性 (内核已核实解析者)

- `spacemit,p1` (hym8563): 闹钟 INT 保持低 1s → 定时开机 (rtc.md)
- `spa,wdt-disabled` (SoC watchdog): 有此属性 = 狗不启动, 删它才开 (watch.md)
- `driver-names` (PC9202): 必填, 决定 /dev/wdt_base 私有设备名 (watch.md)
- `force-attached` + `/lcds` 屏表: K3 DSI 屏按名字查表, 不是标准 panel-compatible (mipi-dsi.md)
- `gpios-power` / `gpios-enable` (eDP): **裸数字 u32** 全局 GPIO 号, 非引用式 (edp.md)
- 遗留无解析 (写了白写): `linux,default-trigger="ir-power-click"` 系列、
  `compatible="firefly,led"`、`realtek,*` (YT8531 上)、PC9202 `index`
- 参考板 voltage 笔误陷阱: vcc5v0_usb20_host 名为 5V 声明 3.3V (usb20.md)

## 7. 方法论

1. **先读 SDK 再写** — 每份 md 的引脚/属性/CONFIG 全部从
   arch/riscv/boot/dts/spacemit/ 与 drivers/ 源码核实, 不凭记忆。
2. **属性找解析者** — 厂商属性逐一 grep 驱动源码确认 of_property_read
   位置 (md 内标注 文件:行号), 无解析者列入遗留清单。
3. **参考板跨板对照** — 同一外设多块板写法不同时 (如 LT2404 两种节点),
   说明是"都合法"而不是"抄谁都对", md 里两种都给。
4. **编号体系先理后写** — K3 的 camN 组/csi-id/VCLK/csiPHY 四套编号
   不对齐、GPIO 全局编号 (K3_GPIO) 与 pad 空间分离, 抄错一层就全链
   不通。
5. **单份 md 自包含验证** — 合格标准: 只拿这一份 md + 干净 dts, 能
   从 include 到 modetest/v4l2-ctl/iperf 全程走通。
