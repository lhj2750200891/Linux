# PHY 与高速控制器

　　适配一块新板, 最常卡住的问题不是"怎么写节点", 而是"我该开哪个节点"——
USB3 A 口到底用 usbhost3_0 还是 usbdrd3_0? PCIe 插槽为什么开了控制器还是不出
设备? SATA 为什么抢了 USB3 的口? 本文回答"怎么找到正确的控制器与 PHY 并打
开", 同时把 RK3588/RK3588S 全部 PHY 家族的功能、绑定关系、冲突互斥一次性列
全。所有 label/地址/compatible/status 均核实自本 SDK
`kernel/arch/arm64/boot/dts/rockchip/rk3588s.dtsi` 与 `rk3588.dtsi`。

## 1. 控制器与 PHY: 一条高速链路的两层

　　一个 USB3 / PCIe / SATA / DP 外设从 SoC 到连接器, 要经过两层硬件:

```
        应用/内核驱动 (drivers/usb/host/xhci-*.c 等)
              │  通过通用 PHY 框架 phy_init/phy_power_on
              ▼
        控制器 (数字层, 协议状态机)          ← dtsi 里的控制器节点
        如 xHCI/dw-pcie/dw-ahci/DP controller     reg=寄存器地址, clocks, interrupts
              │  高速串行差分对 (lane)
              ▼
        PHY (模拟层, 串化/解串/电气驱动)      ← dtsi 里的 phy 节点
        如 combphy/usbdp_phy/pcie30phy            reg=PHY 寄存器, ref clock, resets
              │  TX± / RX± 差分对
              ▼
        SoC 焊盘 → PCB 走线 → 连接器
```

　　两层分工: 控制器懂协议 (包格式、链路训练、DMA), PHY 懂电气 (8b/10b 编
码、预加重、阻抗匹配)。所以**开一条链路必须两处同时 status = "okay"**: 只开
控制器不开 PHY, probe 时 phy_init 拿不到 PHY 会报错或 -517 (EPROBE_DEFER);
只开 PHY 不开控制器, PHY probe 成功但永远没人用它, 外设照样没反应。

　　PHY 节点有一个统一的关键属性 `#phy-cells`: 值为 0 时, 控制器直接写
`phys = <&u2phy2_host>`; 值为 1 时, 还要追加一个"模式"参数, 如
`phys = <&combphy0_ps PHY_TYPE_PCIE>`——这个参数在 PHY 驱动 probe 时告诉它
把模拟电路配成哪种协议。

## 2. 先分清三类接口: 你的外设走哪类

　　"找控制器"的方法按外设类型分三条路, 先对照判定:

| 类 | 外设 | 信号特征 | 定位方法 |
|---|---|---|---|
| A: GPIO 复用类 | UART / I2C / SPI / GMAC / CAN / PWM / SD | 普通数字 IO | 查 pinctrl dtsi 的引脚复用, 无 PHY 概念 (见 README "怎么查找"方法论) |
| B: USB2 模拟专用类 | USB 2.0 口 / Type-C 的低速对 | 一对 DP/DM 差分, 焊盘专用 | 直接找 u2phy 节点, 不占 GPIO 复用, pinctrl 里查不到 |
| C: SerDes/PIPE 类 | USB3 / PCIe / SATA / DP / HDMI / eDP / MIPI | 多对高速差分 lane | 找 PHY 节点, lane 从焊盘到连接器是硬连线 |

　　判别的土办法是数差分对: 原理图上一个 USB-A 座只引出一对 DP/DM → USB2,
找 u2phy; 引出 DP/DM 之外还有一对 SS TX± 和一对 SS RX± (共 5 对) → USB3,
USB2 对归 u2phy、SS 对归 combphy, 一个座同时挂两颗 PHY。金手指/座子上 TX±
RX± REFCLK 各一对 → PCIe, 找对应 combphy 或 pcie30phy。

　　B/C 两类的关键认知: **lane 是硬线**。RK3588 每颗 PHY 的差分对在芯片内部
已经固定连到某几个焊盘, 板卡设计时引到哪个连接器, 软件就只能用那颗 PHY, 不
存在"把 PCIe 配到 combphy2"这种自由。适配前先看原理图确认差分对走向, 再回
来对号入座, 顺序反了会白查半天。

## 3. RK3588 全部 PHY 家族

　　rk3588s.dtsi 定义了 RK3588S 的全部 PHY, rk3588.dtsi (全片) `#include
"rk3588s.dtsi"` (rk3588.dtsi:7) 后追加全片独有 PHY。逐颗列表:

| PHY (label) | 地址 | compatible | #phy-cells | SoC dtsi 默认 | 管什么 |
|---|---|---|---|---|---|
| u2phy0 (usb2-phy@0, 3588s:3615) | usb2phy0_grf 内 | rockchip,rk3588-usb2phy | 端口 0 | disabled | Type-C0 的 USB2 低速对 (u2phy0_otg: otg-port, :3628) |
| u2phy1 (rk3588.dtsi:96) | usb2phy1_grf 内 | 同上 | 端口 0 | disabled | Type-C1 的 USB2 低速对 (u2phy1_otg, 仅全片) |
| u2phy2 (usb2-phy@8000, :3642) | usb2phy2_grf 内 | 同上 | 端口 0 | disabled | USB2 host 口 0 (u2phy2_host: host-port, :3654) |
| u2phy3 (usb2-phy@c000, :3668) | usb2phy3_grf 内 | 同上 | 端口 0 | disabled | USB2 host 口 1 + USB3 A 口低速对 (u2phy3_host, :3680) |
| combphy0_ps (phy@fee00000, :7979) | fee00000 | rockchip,rk3588-naneng-combphy | 1 | disabled | 复合 PIPE PHY: PCIe2 / SATA / USB3 三选一 (服务 pcie2x1l2 / sata0) |
| combphy1_ps (rk3588.dtsi:729) | fee10000 | 同上 | 1 | disabled | 同上, 仅全片 (服务 pcie2x1l0 / sata1) |
| combphy2_psu (phy@fee20000, :7995) | fee20000 | 同上 | 1 | disabled | 同上 (服务 usbhost3_0 / sata2 / pcie2x1l1) |
| pcie30phy (rk3588.dtsi:746) | fee80000 | rockchip,rk3588-pcie3-phy | 0 | disabled | PCIe3 专用 4-lane PIPE PHY, 可整用 (3x4) 或拆分 (3x2) |
| usbdp_phy0 (phy@fed80000, :7901) | fed80000 | rockchip,rk3588-usbdp-phy | 1 | disabled | Type-C0 的 USB3.1 + DP1.4 复合 PHY |
| usbdp_phy1 (rk3588.dtsi) | fed90000 | 同上 | 1 | disabled | Type-C1 同款, 仅全片 |
| hdptxphy0 (phy@fed60000, :7886) | fed60000 | rockchip,rk3588-hdptx-phy | 0 | disabled | HDMI2.1 / eDP 复用 PHY 0 |
| hdptxphy1 (rk3588.dtsi) | fed70000 | 同上 | 0 | disabled | HDMI2.1 / eDP PHY 1, 仅全片 |
| mipidcphy0 (phy@feda0000, :7923) | feda0000 | rockchip,rk3588-mipi-dcphy | 1 | **okay** | MIPI D-PHY: DSI 输出 + CSI 输入复合 0 |
| mipidcphy1 (phy@fedb0000, :7939) | fedb0000 | 同上 | 1 | **okay** | 同上 1 |
| csi2_dcphy0/1、csi2_dphy0~3 (:2121~2169) | — | (软件路由节点) | — | — | 链路包装节点, 实体都指向 mipidcphy, 摄像头适配时只改这些包装点的 status |

　　三个值得注意的细节:

- **mipidcphy 是全表唯一默认 okay 的 PHY** (本 SDK 如此), 其余全部
  disabled——板级必须显式开的规律对显示/存储/USB 类 PHY 一律成立, 拿不准就
  去目标 dtsi 里看一眼 status。
- combphy 的 `#phy-cells = <1>` 模式参数取值来自
  `kernel/include/dt-bindings/phy/phy.h:14~25`: `PHY_TYPE_SATA=1、
  PHY_TYPE_PCIE=2、PHY_TYPE_USB2=3、PHY_TYPE_USB3=4、PHY_TYPE_DP=6`。同一颗
  PHY 配哪种协议, 就是由控制器节点里 phys 属性的这个参数决定的, 不是 PHY
  节点自己写的。
- u2phy 是 syscon (grf) 内部的 simple-mfd 子节点, 地址是 grf 内偏移 (如
  usb2-phy@0), 依赖父节点的 `rockchip,usbctrl-grf` 属性, 端口 (otg-port /
  host-port) 才是真正被控制器引用的实体。

## 4. 控制器 ↔ PHY 绑定总表

　　下表是"开某外设要动哪几个节点"的总索引, 全部取自两个 dtsi 的 phys 属
性原文:

| 外设 | 控制器 (label @地址) | phys 属性原文 | PHY |
|---|---|---|---|
| USB2 host 口 0 | usb_host0_ehci @fc800000 (:3364) + usb_host0_ohci @fc840000 (:3377) | `phys = <&u2phy2_host>` | u2phy2_host |
| USB2 host 口 1 | usb_host1_ehci @fc880000 (:3389) + usb_host1_ohci @fc8c0000 | `phys = <&u2phy3_host>` | u2phy3_host |
| Type-C0 (OTG/双 role) | usbdrd3_0 (:3330) 内 usbdrd_dwc3_0 | `<&u2phy0_otg PHY_TYPE_USB2>, <&usbdp_phy0 PHY_TYPE_USB3>` | u2phy0_otg + usbdp_phy0 |
| Type-C1 (仅全片) | usbdrd3_1 (rk3588.dtsi) | `<&u2phy1_otg PHY_TYPE_USB2>, <&usbdp_phy1 PHY_TYPE_USB3>` | u2phy1_otg + usbdp_phy1 |
| USB3 A 口 (5Gbps host) | usbhost3_0 (:3438) 内 usbhost_dwc3_0 @fcd00000 | `phys = <&combphy2_psu PHY_TYPE_USB3>` | combphy2_psu (+伴生 u2phy3_host) |
| PCIe3 x4 | pcie3x4 @fe150000 (rk3588.dtsi:457) | `phys = <&pcie30phy>` | pcie30phy |
| PCIe3 x2 | pcie3x2 @fe160000 (rk3588.dtsi:512), num-lanes=<2> | `phys = <&pcie30phy>` | pcie30phy |
| PCIe2.0 l0 (仅全片) | pcie2x1l0 @fe170000 (rk3588.dtsi:567) | `phys = <&combphy1_ps PHY_TYPE_PCIE>` | combphy1_ps |
| PCIe2.0 l1 | pcie2x1l1 @fe180000 (3588s:6634) | `phys = <&combphy2_psu PHY_TYPE_PCIE>` | combphy2_psu |
| PCIe2.0 l2 | pcie2x1l2 @fe190000 (3588s:6688) | `phys = <&combphy0_ps PHY_TYPE_PCIE>` | combphy0_ps |
| SATA0 | sata0 @fe210000 (:6798) | `phys = <&combphy0_ps PHY_TYPE_SATA>` | combphy0_ps |
| SATA1 (仅全片) | sata1 | `phys = <&combphy1_ps PHY_TYPE_SATA>` | combphy1_ps |
| SATA2 | sata2 @fe230000 (:6813) | `phys = <&combphy2_psu PHY_TYPE_SATA>` | combphy2_psu |
| DP0 | dp0 (dp@fec40000) | `phys = <&usbdp_phy0 PHY_TYPE_DP>` | usbdp_phy0 |
| DP1 (仅全片) | dp1 | `phys = <&usbdp_phy1 PHY_TYPE_DP>` | usbdp_phy1 |
| HDMI0 / eDP0 | hdmi0 / edp0 | (通过中间节点引用) | hdptxphy0 |
| HDMI1 / eDP1 (仅全片) | hdmi1 / edp1 | 同上 | hdptxphy1 |
| MIPI DSI0 | dsi0 | dsi 传输层引 mipidcphy0 | mipidcphy0 |
| MIPI DSI1 | dsi1 | 同上 | mipidcphy1 |
| MIPI CSI (摄像头) | csi2_dcphy0/1 包装节点 → mipi2_csi2 | 包装节点内部 phys 指向 mipidcphy | mipidcphy0/1 |

　　注意两个"一个座两颗 PHY"的结构: Type-C 全功能口由 u2phy (低速) +
usbdp_phy (高速 SS/DP) 两颗共同服务; USB3 A 口由 u2phy3_host (低速对) +
combphy2_psu (SS 对) 共同服务, 但 dwc3 节点只绑 combphy, 低速对走
usb_host1_ehci/ohci——所以开 USB3 A 口实际要动**四个**控制器节点加两颗 PHY
(见 §8 实例 2)。

## 5. 冲突互斥: 一颗 PHY 同时只能有一个高速主人

　　PHY 冲突是 RK3588 适配最高频的翻车点, 规律就一句话: **共用同一颗
combphy/usbdp/hdptxphy 的外设互斥, 同一时刻只能开一个**。全部冲突组:

| PHY | 争夺者 (同一时刻只能选一个, 若 PHY 支持分时则除外) | 典型翻车 |
|---|---|---|
| combphy0_ps | sata0 ⨯ pcie2x1l2 | SATA 和 PCIe2 插槽共用走线, 开了一个忘关另一个 |
| combphy1_ps (仅全片) | sata1 ⨯ pcie2x1l0 | 同上 |
| combphy2_psu | usbhost3_0 ⨯ sata2 ⨯ pcie2x1l1 | USB3 A 口与 SATA2/M.2(PCIe2) 三选一; 4G 模组用 pcie2x1l1 时 USB3 A 口必须关 |
| usbdp_phy0 | usbdrd3_0 的 USB3 通道 ⨯ dp0 的 DP 通道 | Type-C 全功能口 DP alt-mode 与 USB3 分时复用 SS 对 (硬件 mux), DP+USB2 可并存, DP+USB3 同开则出口只有一种 |
| usbdp_phy1 (仅全片) | usbdrd3_1 ⨯ dp1 | 同上 |
| hdptxphy0 | hdmi0 ⨯ edp0 | 同一 PHY 两种显示输出二选一 |
| hdptxphy1 (仅全片) | hdmi1 ⨯ edp1 | 同上 |
| pcie30phy | pcie3x4 (整 4 lane) 或 pcie3x2 (占 2 lane) | 3x2 模式下另 2 lane 的归属由 rc 芯片配置, 板级只需选一个 rc 节点开 |
| mipidcphy0 | dsi0 输出 ⨯ CSI0 输入 | DSI 屏与 MIPI 摄像头共用, 软件链路包装节点处切换 |
| u2phy3 | USB2 口 1 的 DP/DM ⨯ USB3 A 口低速对 | 板卡把两座接到同一 u2phy 端口时的硬件取舍, 软件层面两个控制器可同开 |

　　冲突的本质还是 §2 那句话: lane 是硬线。芯片出厂就把 combphy0_ps 的差分
对连到固定的焊盘组, 板卡把这个焊盘组引给了 SATA 座, 就不可能同时再引给
PCIe 插槽——不是软件不许, 是物理上没有第二条线。README "引脚冲突速查"表中
combphy/usbdp/hdptxphy 各行即来自本表。

　　自查口诀: **开任何一个 USB3/PCIe/SATA/DP/HDMI/eDP/DSI 之前, 先在上表找
到它用的 PHY, 确认同组的其他外设节点都已 status = "disabled"。**

## 6. RK3588 与 RK3588S: 动手前先确认芯片

　　rk3588.dtsi 在 rk3588s.dtsi 基础上追加 (include 关系见 §3), 差量就是全
片多出的控制器与 PHY:

| 增量 (仅 RK3588 全片) | 用途 | 对应 PHY |
|---|---|---|
| pcie3x4 @fe150000 | PCIe3 x4 (如 aio-3588jd4 WiFi、通用 PCIe 槽) | pcie30phy |
| pcie3x2 @fe160000 | PCIe3 x2 (如 itx-3588j NVMe 槽) | pcie30phy |
| pcie2x1l0 @fe170000 | PCIe2.0 一 lane | combphy1_ps |
| usbdrd3_1 | Type-C1 (OTG+DP) | u2phy1 + usbdp_phy1 |
| dp1 / hdmi1 / edp1 | 第二路 DP / HDMI / eDP | usbdp_phy1 / hdptxphy1 |
| sata1 | 第二路 SATA | combphy1_ps |
| combphy1_ps @fee10000 / u2phy1 / usbdp_phy1 / hdptxphy1 | 上述各链路的 PHY | — |

　　反过来说, RK3588S 只有一路 Type-C (usbdrd3_0)、一颗可用 combphy 之外的
情况同全片; S 芯片适配时如果照抄全片板卡的 pcie3x4/usbdrd3_1 节点, dtc 会
报 label 未定义错误——这是选型写错 dtsi 的第一时间信号。

## 7. 方法论: 从连接器反查控制器与 PHY 的四步

　　拿到一块新板 (或改板), 按这四步走, 每步都只做一件事:

### 第 1 步: 原理图上数差分对, 判接口类型

　　目标连接器引出的差分对清单直接决定 PHY 类型: 仅 DP/DM 一对 → USB2, 跳
到 u2phy; DP/DM + SS TX/RX 两对 → USB3; TX±/RX±/CLK±/PERST#/WAKE → PCIe;
SATA A+/A- → SATA; TMDS 差分组 → HDMI; AUX+SSTX 差分组 → DP; CLK+4 data →
MIPI。USB2 对与 SS 对同座出现 (USB3 A 口/Type-C) 时记录"两颗 PHY"结论。

### 第 2 步: 在 SoC dtsi 里 grep 出该 PHY 的全部主人

```
cd kernel/arch/arm64/boot/dts/rockchip
# 假设第 1 步判定用到 combphy2_psu, 列出所有引用它的控制器:
grep -n -B30 "phys = <&combphy2_psu" rk3588s.dtsi rk3588.dtsi | \
    grep -E "^[a-z]+.*[0-9]+[-:]\s+(usb|sata|pcie)[0-9a-z_]*: |phys ="
# 反过来, 从控制器找它绑的 PHY:
grep -n -A20 "usbhost3_0: usbhost3_0" rk3588s.dtsi | grep "phys ="
grep -n -A12 "pcie2x1l2: pcie@"        rk3588s.dtsi | grep -E "phys|num-lanes"
grep -n -A12 "usb_host0_ehci: usb@"    rk3588s.dtsi | grep "phys"
```

　　`-B30`/`-A20` 的窗口必须够大: 控制器节点的 label 行离 phys 属性可能有
30 行 (中间是 clocks/interrupts), 窗口太小会只见 phys 不见 label, 不知道是
谁的属性。同时注意 rk3588.dtsi 与 rk3588s.dtsi 都要 grep——全片独有的绑定
只在后者 (见 §6)。

### 第 3 步: 查 PHY 节点定义, 确认默认状态与父级资源

```
# combphy 家族逐颗看: 地址/ref 时钟/复位/pipe-grf/默认 status
grep -n -A16 "combphy[012]_[a-z]*: phy@" rk3588s.dtsi rk3588.dtsi
grep -n -A16 "pcie30phy: phy@"           rk3588.dtsi
grep -n -A20 "usbdp_phy0: phy@"          rk3588s.dtsi
```

　　两个必查项: 默认 status 是 disabled 还是 okay (决定板级要不要写
status); PHY 的 `rockchip,pipe-grf` / `rockchip,pipe-phy-grf` 指向的 syscon
节点是否在用的这颗 SoC dtsi 里存在 (grf 缺失时 PHY probe 会 defer)。

### 第 4 步: 板级 dts 写覆盖, 控制器+PHY 成对开

　　PHY 与控制器节点都是 SoC 内部节点, 板级用 `&label {}` 覆盖即可 (自研板
的电源/reset-gpios/target-supply 等新增属性也挂进同一覆盖块)。两条铁律:
控制器与 PHY 两处 status 都要 okay; §5 冲突组里同 PHY 的其他主人一律
disabled。具体写法看 §8 六个实例。

## 8. 六种典型链路的完整 DT 实例

　　以下实例的板级覆盖均出自 SDK 板卡文件实际写法 (AIO-3588SG /
rk3588-firefly-common.dtsi #ifdef 分支), 直接可抄改。

### 实例 1: USB2.0 Type-A 口 (仅一对 DP/DM)

```
　　硬件: USB-A 母座 DP/DM → SoC USB2 host 口 0 差分对 (硬线到 u2phy2),
    VBUS 由 GPIO 门控轨供电。

/ {
    vcc5v0_host: vcc5v0-host-regulator {
        compatible = "regulator-fixed";
        enable-active-high;
        gpio = <&gpio4 RK_PB5 GPIO_ACTIVE_HIGH>;
        pinctrl-names = "default";
        pinctrl-0 = <&vcc5v0_host_en>;
        regulator-name = "vcc5v0_host";
        regulator-min-microvolt = <5000000>;
        regulator-max-microvolt = <5000000>;
        vin-supply = <&vcc5v0_sys>;
    };
};

&u2phy2 {
    status = "okay";
};

&u2phy2_host {                      /* VBUS 检测, 无则看门狗类设备枚举不稳 */
    phy-supply = <&vcc5v0_host>;
};

&usb_host0_ehci {                   /* 高速 (EHCI) */
    status = "okay";
};

&usb_host0_ohci {                   /* 全速/低速 (OHCI), 与 EHCI 同口共 PHY */
    status = "okay";
};
```

　　要点: EHCI+OHCI 是同一物理口的两套速率引擎, **必须成对开**; PHY 侧开
u2phy2 即可, host-port 子节点随父 probe。USB2 引脚不出现在 pinctrl dtsi 是
正常的 (焊盘专用, §2 B 类)。

### 实例 2: USB3.0 Type-A 口 (5Gbps, DP/DM + SS 两对)

```
　　硬件: USB-A 母座 DP/DM → u2phy3 差分对; SS TX±/RX± → combphy2_psu。
    注意: 该口占用了 combphy2_psu, sata2/pcie2x1l1 同板即不可用 (§5)。

&u2phy3 {                           /* 低速对所在 PHY */
    status = "okay";
};

&usb_host1_ehci {                   /* 该口的 USB2 前速走 host1 控制器 */
    status = "okay";
};

&usb_host1_ohci {
    status = "okay";
};

&combphy2_psu {                     /* SS 对 PHY, 模式由 dwc3 的 phys 参数决定 */
    status = "okay";
};

&usbhost3_0 {                       /* DWC3 包装层 (时钟/复位) */
    status = "okay";
};
```

　　要点: usbhost_dwc3_0 的 `phys = <&combphy2_psu PHY_TYPE_USB3>` 在 SoC
dtsi 里已写死 (3588s:3456), 板级**不需要也不能改 PHY_TYPE**——PHY 的协议模
式跟着控制器节点走。参考板: AIO-3588SG 同开这五个节点
(rk3588-firefly-aio-3588sg.dtsi:238~253)。

### 实例 3: Type-C 全功能口 (USB3 + DP + PD)

　　全功能口链路长: u2phy0_otg + usbdp_phy0 (USB3/DP 分时) + fusb307 PD 控
制器 + typec-port/connector 图, 还牵 DP 显示链。此处只给 PHY/控制器骨架,
PD 与 connector 图配置见 typec.md (职责边界):

```
&u2phy0 {
    status = "okay";
};

&usbdp_phy0 {
    status = "okay";
    /* orientation-switch / mode-switch 属性与 typec 图有关, 见 typec.md */
};

&usbdrd3_0 {
    status = "okay";
};
```

　　参考板: AIO-3588SG 启用 u2phy0 + usbdp_phy0
(rk3588-firefly-aio-3588sg.dtsi:262~275)。

### 实例 4: PCIe 2.0 一 lane (M.2 / 模组 / 桥片)

```
　　硬件: 插槽 PCIE_TX±/RX± → combphy0_ps 差分对; REFCLK 由座子供或板载晶振;
    PERST#/WAKE 接 GPIO; 槽供电 3.3V 门控。

&combphy0_ps {
    status = "okay";
};

&pcie2x1l2 {
    status = "okay";
    reset-gpios = <&gpio3 RK_PD1 GPIO_ACTIVE_HIGH>;
    vpcie3v3-supply = <&vcc3v3_pcie30>;
};
```

　　要点: reset-gpios 极性与芯片手册核对 (rc 驱动拉低复位再释放); 模组类
(WiFi/4G) 多在 1.8V IO 域, 注意 vpcie1v8/vpcie3v3 别配反。参考板:
AIO-3588SG 的 FF_PCIE2_1L2 分支 (rk3588-firefly-aio-3588sg.dtsi:1537 附近)
即为上述写法, reset 脚 GPIO3_D1; ITX-3588J 的 4G 模组走 pcie2x1l1 (同一
combphy2_psu, 见 4g-5g-module.md)。

### 实例 5: PCIe 3.0 x2 (NVMe SSD)

```
　　硬件: x2 插槽 lane0/1 → pcie30phy 前两 lane; 时钟 CLK_PCIE2L_PIPE 由
    SoC cru 提供时无需板级处理, REFCLK 按插槽设计。

&pcie30phy {
    status = "okay";
};

&pcie3x2 {
    status = "okay";
    num-lanes = <2>;                /* SoC dtsi 已有, 板级确认勿改丢 */
    reset-gpios = <&gpio4 RK_PB0 GPIO_ACTIVE_HIGH>;
    vpcie3v3-supply = <&vcc3v3_pcie30>;
};
```

　　要点: pcie30phy 与 pcie3x4/pcie3x2 是一父二子的关系, 开 3x2 就不能再开
3x4 (同一颗 4-lane PHY); num-lanes=2 与 SoC dtsi 一致即可, x4 板开 pcie3x4
时对应改 4。参考板: ITX-3588J NVMe 槽 (见 pcie.md 方式三)。仅 RK3588 全片
有本实例与实例 6 的 sata1; RK3588S 上 pcie3x2 label 不存在, dtc 直接报错。

### 实例 6: SATA (直连硬盘座)

```
　　硬件: SATA 座 A+/A- → combphy0_ps 差分对; 座子供 5V + 3.3V 门控。

&combphy0_ps {
    status = "okay";
};

&sata0 {
    status = "okay";
    target-supply = <&vcc3v3_sata0>;    /* 硬盘电源门控, AHCI 驱动上电时序用 */
};
```

　　要点: target-supply 在 rk3588-firefly-common.dtsi FF_SATA0 分支中的写法
原样; 与实例 4 互斥——同一颗 combphy0_ps, SATA0 和 pcie2x1l2 只能活一个,
Firefly 用 #if defined(FF_SATA0) / FF_PCIE2_1L2 编译期互斥, 自研板在 dts 里
直接把另一侧写 disabled 即可。

## 9. 验证与排查

### 板端验证

```
# 控制器/PHY 是否 probe (按地址找, §4 表的地址直接当索引)
ls /sys/bus/platform/devices/ | grep -E "fcd00000|fee00000|fe190000"

# USB: 枚举结果与速率 (1.5M/12M=USB2, 480M=USB2 HS, 5000M=USB3)
lsusb -t
cat /sys/kernel/debug/usb/devices | grep -E "^[TSDB]"

# PCIe: 链路是否训练 + 速率
lspci -vvv | grep -E "LnkCap|LnkSta"     # LnkSta: 2.5/5/8/16 GT/s, x1/x2/x4
cat /sys/class/nvme/nvme0/model 2>/dev/null

# SATA: 盘与链路
cat /sys/class/ata_link/ata1/sata_spd 2>/dev/null
smartctl -i /dev/sda | grep -i "sata version"

# 通用 PHY 状态 (哪些 PHY 已被框架接管)
grep -H . /sys/class/phy/*/uevent 2>/dev/null
cat /sys/kernel/debug/phy/*/status 2>/dev/null   # 部分驱动支持
```

### 症状 → 根因速查

| 症状 | 最可能根因 | 处置 |
|---|---|---|
| 控制器完全不在 /sys, probe 都没跑 | SoC dtsi 默认 disabled 且板级没写 status | 回 §3/§4 对照表补 `&控制器 {} + &phy {}` 两处 okay |
| 控制器 probe 报 -517 (defer) 且不回来 | 依赖的 PHY/grf 节点 disabled 或缺失 | 查 devices_deferred (`grep -r devices_deferred /sys/kernel/debug/`), 补开对应 PHY |
| PHY probe 成功但控制器报 PHY 错 | PHY 被 §5 冲突组的另一个节点占了, 或另一节点同开抢 mode | 冲突组内只留一个 okay, 其余 disabled |
| USB3 A 口只认出 480M 设备, SS 设备不识别 | combphy 未开或 mode 不是 USB3 (控制器节点没生效) | 查 combphy2_psu 与 usbhost3_0 两处 status; lsusb -t 看速率 |
| USB3 A 口 USB2 设备也不识别 | 伴生侧没开 (u2phy3/usb_host1_ehci/ohci) | 补实例 2 的全部五个节点 |
| PCIe lspci 无设备, LnkSta 不出现 | reset-gpios 极性反 / 时钟 CLK_PCIE_AUX/PIPE 未配 / vpcie3v3 未供 | 手册核极性; combphy/pcie30phy status; 万用表测槽供电 (点位见 power.md) |
| SATA 盘时隐时现 | target-supply 门控轨 always-on 属性缺失, probe 后掉电 | 门控轨加 regulator-always-on 或确认上电时序 |
| 全片节点在 S 芯片报 dtc 错 (label undefined) | 芯片选错 dtsi, 引用了全片独有 label | 对照 §6 增量表换控制器 |
| dtc 报 "duplicate label" | 板级重复定义 SoC 已有节点 | 板级一律用 `&label {}` 覆盖, 不重写全节点 |
| 枚举正常但速率/吞吐异常 | PHY 参考时钟 (refclk) 走板载晶振但未配, 或链路降级 (PCIe 2.5GT/s) | 看链路协商值; 硬件检查 REFCLK 载入 |

　　职责边界: 本文管"链路两端是谁、怎么找到、怎么互斥"; 单个外设的引脚级
配置、供电、速率调优见 pcie.md / usb30.md / usb20.md / sata.md /
typec.md / hdmi.md / mipi-csi.md / mipi-dsi.md; 供电轨本身见 power.md。
