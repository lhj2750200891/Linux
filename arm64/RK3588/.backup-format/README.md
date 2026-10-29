# RK3588 BSP 适配笔记 (基于瑞芯微原厂 SDK)

基于 rk3588_6.12.69_sdk, 展开 Firefly 板 (主要为 AIO-3588SG, 辅以
itx-3588j / aio-3588q / aio-3588sjd4 / aio-3588jd4 / aio-3588l-qua /
roc-rk3588s-pc / robotic-evb-v11) 的设备树配置, 供自研板移植参考。

每个模块一个 md 文件, 三段式结构: 硬件连接 (引脚级) / 设备树配置 /
验证测试。模块内按板子差异分多个"方式"。

## 已实现模块一览

| 模块 | 文件 | 内容 (方式划分) | 完成日期 |
|---|---|---|---|
| LED | [led.md](led.md) | GPIO LED (格式参考模板) | 2026-10-29 |
| 按键 | [key.md](key.md) | GPIO 按键 + ADC 按键 | 2026-10-29 |
| RTC | [rtc.md](rtc.md) | hym8563, 32K 输出 | 2026-10-29 |
| 看门狗 | [watchdog.md](watchdog.md) | I2C 看门狗芯片 (pc9202) | 2026-10-29 |
| 调试串口 | [debug.md](debug.md) | fiq-debugger / UART2 | 2026-10-29 |
| PCIe | [pcie.md](pcie.md) | 5 种方式: 2x1l0/2x1l2/3x2/3x4、复用与拆分 | 2026-10-29 |
| SATA | [sata.md](sata.md) | 直连 SATA + USB HUB 一扩四 (GL3321G) | 2026-10-29 |
| DP 转 VGA | [vga.md](vga.md) | DP + DP 转 VGA 桥 | 2026-10-29 |
| eDP | [edp.md](edp.md) | eDP 屏 + 触摸 (GT9xxx) | 2026-10-29 |
| GMAC 千兆网 | [gmac.md](gmac.md) | SG 单口 (tx_delay 调试) + q 双口 PHY | 2026-10-29 |
| HDMI | [hdmi.md](hdmi.md) | 单口 / itx 双口 + HDMI RX | 2026-10-29 |
| MIPI CSI 摄像头 | [mipi-csi.md](mipi-csi.md) | IMX415 全链路 + 双摄 CAM0/CAM1 切换 | 2026-10-29 |
| MIPI DSI 屏 | [mipi-dsi.md](mipi-dsi.md) | MIPI 屏完整序列+触摸+在位检测 / LT9211D 转 LVDS | 2026-10-29 |
| Type-C | [typec.md](typec.md) | 全功能 (PD 充电+DP) / 非全功能 (仅 OTG+DP) | 2026-10-29 |
| USB2.0 | [usb20.md](usb20.md) | usb_host0/1 口, u2phy 冲突说明 | 2026-10-29 |
| USB3.0 | [usb30.md](usb30.md) | Type-A 5Gbps 口 + 一扩四场景 | 2026-10-29 |
| CAN | [can.md](can.md) | 内置 can1/can2 + SPI MCP2518FD | 2026-10-29 |
| RS232/RS485 | [rs232-rs485.md](rs232-rs485.md) | RS232 多路 / RS485 自动换向 / GPIO 方向控制 | 2026-10-29 |
| WiFi/BT | [wifi-bt.md](wifi-bt.md) | PCIe+UART (AP6275P) / PCIe+USB BT (RTL8852BE, 含 BT 走 UART 范本) / SDIO+UART (AIC8800) | 2026-10-29 |
| 声卡 | [sound-card.md](sound-card.md) | ES8388 (es8323 驱动) / ES8390 (es8389 驱动) + HDMI/eDP/DP/BT SCO | 2026-10-29 |
| 4G/5G 模组 | [4g-5g-module.md](4g-5g-module.md) | USB 型 (EC20/EM05, QMI/MBIM) / PCIe 型 (itx pcie2x1l1) / 通话音频 (i2s1+bt_sco) | 2026-10-29 |
| LVDS 屏 | [lvds.md](lvds.md) | LT9211D 桥接 (驱动移植实录: 6.12 API 差异/编译错误全解) | 2026-10-29 |
| SD 卡 / SDIO | [sdcard.md](sdcard.md) | TF 卡 (sdmmc) + SDIO WiFi (sdio) / eMMC (sdhci) 全景 | 2026-10-29 |
| 其他模块 | [misc-modules.md](misc-modules.md) | 风扇(手控/温控/FG) / MC3230 / 蜂鸣器 / INA226 / SPI spidev / RTL8126 5G 网口 / SW3203 / WOL / M.2 SSD | 2026-10-29 |

## 待实现模块

| 模块 | 说明 |
|---|---|
| (暂无) | 需求出现时补充 (misc-modules.md 内已收编风扇/G-Sensor/蜂鸣器/INA226/SPI/RTL8126/SW3203/WOL/M.2) |

## 引脚冲突速查 (跨模块)

| 引脚 | 模块 A | 模块 B |
|---|---|---|
| GPIO1_D0/D1 | spi1m2 MISO/MOSI (SPI) | i2s 通道 (声卡) |
| GPIO3_C1 | LT9211D 桥电源 (LVDS) | can2 |
| GPIO4_PD4/PD5 | uart5m0 | can0m1 |
| GPIO3_PC4/PC5 | uart5m1 | can2m0 |
| combphy2_psu | USB3.0 (usbhost3_0) | SATA2 / pcie2x1l1 |
| u2phy3 | USB2.0 口 2 | USB3.0 口 (USB2 伴生) |
| usbdp_phy0/1 | Type-C0/1 | 独立 DP 口 |
| hdptxphy0/1 | HDMI0/1 | eDP0/1 |
| pcie3x4 | aio-3588jd4 WiFi | 通用 PCIe 槽 |

## 相关 SDK 路径

- 设备树: kernel-6.12/arch/arm64/boot/dts/rockchip/
- 内核配置: rockchip_linux_defconfig + firefly-linux.config
- WiFi/BT 框架: external/rkwifibt/

## 怎么查找某个引脚/外设用的控制器 (方法论)

以"USB3.0 A 口用什么控制器"为例, 四条路径由快到慢:

### 1. 硬件引脚反查控制器 (知道引脚, 查谁在用)

引脚复用表在 `rk3588-base-pinctrl.dtsi`, 每个功能组的 `rockchip,pins`
列出了 "bank pin func":
```
cd kernel-6.12/arch/arm64/boot/dts/rockchip
grep -rn "4 RK_PA6 2\|<1 RK_PD7 2" rk3588-base-pinctrl.dtsi
# 命中的功能组名即是控制器复用名 (如 mipim0_camera4_clk), 上帝视角看全部 M0/M1
grep -B4 "<1 RK_PD7 2" rk3588-base-pinctrl.dtsi
```
func 数字 = 引脚复用功能号, 同一脚多个功能组 = 多个控制器抢一脚,
即互斥点 (引脚冲突速查表就是这么攒出来的)。

### 2. 设备树正查 (知道板子, 看每个外设接的哪个控制器)

```
# 目标板设备树里直接看节点引用, 如 A 口 USB3:
grep -n "combphy2_psu\|usbhost3_0\|dwc3" rk3588-firefly-aio-3588sg*
# 输出即链: A 口 USB3 差分对 ==> combphy2_psu (PHY),
#           控制器 ==> usbhost_dwc3_0 (DWC3 host)
```
SoC 全部控制器清单 (地址/中断/compatible) 在 `rk3588s.dtsi`,
带地址查: `grep -B2 -A10 "fe2c0000\|fcd00000" rk3588s.dtsi`。
compatible 字段最后一个值就是内核驱动匹配名。

### 3. 内核配置反查驱动 (知道控制器名, 查哪个驱动/配置)

```
# compatible "rockchip,rk3588-dw-mshc" 是谁在 matching:
grep -rn "rk3588-dw-mshc" drivers/mmc/host/
# 找到 .c 后看它挂在哪个 CONFIG_ 下:
grep -B5 "rk3588-dw-mshc" drivers/mmc/host/dw_mmc-rockchip.c | head
grep "DW_ROCKCHIP" arch/arm64/configs/rockchip_linux_defconfig
```

### 4. 板端运行时验证 (不确定设备树是否生效时)

```
# 控制器是否 probe 成功 (地址 => 设备)
cat /sys/kernel/debug/mmc/fe2c0000/regs 2>/dev/null   # mmc 举例
ls /sys/bus/platform/devices/ | grep fe2c             # 按地址找
grep -H . /sys/class/mmc_host/*/uevent                # mmc host 注册

# 引脚当前的复用状态 (iomux 实际值, 排除"配了没生效")
cat /sys/kernel/debug/pinctrl/pinctrl-rockchip-pinctrl/pinmux-pins | \
    grep -E "GPIO1_D7|GPIO4_B1"

# USB 专查: 控制器类型 + 速率一目了然
ls /sys/bus/usb/devices/; cat /sys/kernel/debug/usb/devices | head -30
```

### RK3588 常用控制器速记 (查表时的锚点)

| 外设类型 | 控制器命名规律 | 例 |
|---|---|---|
| USB3 | usbdrd3_N(OTG)/usbhost3_0(HOST) + DWC3 | A 口 = usbhost_dwc3_0 |
| USB2 | usb_host0/1_EHCI + u2phyN | |
| SD/SDIO/eMMC | sdmmc/sdio (dw_mci) + sdhci (eMMC) | TF 卡 = sdmmc@fe2c0000 |
| 千兆网 | gmac0/1 (GMAC) + PHY 节点 | |
| PCIe | pcie3x4/3x2/2x1lN | WiFi 常用 pcie2x1l2 |
| 显示 | vop2(显控) + 各接口控制器 + PHY | DP=dp0+usbdp_phy0, eDP=edp0+hdptxphy0 |
| 摄像头 | csi2_dphy/dcphy + mipiN_csi2 | dcphy 与 DSI 共享 PHY |
| 串口 | uartN (N=0..9) | |
