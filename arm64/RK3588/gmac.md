# 千兆网口

　　千兆网口 (RGMII + RTL8211F PHY): AIO-3588SG 单口 (含 tx_delay 调试) 与 q/itx 双口。

　　RK3588 内置两个千兆 MAC 控制器 (gmac0/gmac1), RGMII 总线外挂 PHY 芯片
(Firefly 各板用 RTL8211F)。PCIe 网卡方案 (RTL8125) 不属于本模块, 见 pcie 模块。

## 1. 控制器与引脚全景

| 控制器 | 地址 | 节点定义位置 | pinctrl 定义 |
|---|---|---|---|
| gmac0 | fe1b0000 | rk3588.dtsi | rk3588-extra-pinctrl.dtsi (GPIO2/GPIO4) |
| gmac1 | fe1c0000 | rk3588s.dtsi | rk3588s-pinctrl.dtsi (GPIO3) |

　　RGMII 信号引脚表 (均 func 1):

| 信号 | gmac0 | gmac1 |
|---|---|---|
| MDC / MDIO | GPIO4_C4 / GPIO4_C5 | GPIO3_C2 / GPIO3_C3 |
| TXD0 / TXD1 / TXEN | GPIO2_B6 / GPIO2_B7 / GPIO2_C0 | GPIO3_B3 / GPIO3_B4 / GPIO3_B5 |
| TXD2 / TXD3 | GPIO2_B1 / GPIO2_B2 | GPIO3_A0 / GPIO3_A1 |
| TXCLK | GPIO2_B3 | GPIO3_A4 |
| RXD0 / RXD1 / RXDV_CRS | GPIO2_C1 / GPIO2_C2 / GPIO4_C2 | GPIO3_A7 / GPIO3_B0 / GPIO3_B1 |
| RXD2 / RXD3 | GPIO2_A6 / GPIO2_A7 | GPIO3_A2 / GPIO3_A3 |
| RXCLK | GPIO2_B0 | GPIO3_A5 |

　　双网口板上 gmac0 走 GPIO2/GPIO4、gmac1 走 GPIO3, 引脚无冲突, 可同时使用。

　　驱动配置 (defconfig 已开, PHY 用内核自带 realtek.c, 无 Firefly 私有驱动):

```
CONFIG_STMMAC_ETH=y            # GMAC 控制器驱动
CONFIG_REALTEK_PHY=y           # RTL8211F PHY 驱动 (drivers/net/phy/realtek.c)
```

　　注意:
- Firefly 的 firefly-linux.config 里有 CONFIG_FIREFLY_RTL8211F_REG=y,
  但整棵内核树找不到该符号的任何 Kconfig/代码, 属历史遗留孤儿 config, 不需要移植
- RTL8125 PCIe 网卡 (2.5G) 走 pcie 控制器, 用 CONFIG_R8125=m, 见 pcie 模块

## 2. 方式一: 单网口 (gmac1)

　　参考板: AIO-3588SG。

### 2.1 硬件连接

```
RTL8211F PHY:
  RGMII 数据/时钟 ====> gmac1 引脚组 (见上表 GPIO3 部分)
  MDC/MDIO       ====> GPIO3_C2 / GPIO3_C3 (mdio1 总线, PHY 地址 0x1)
  PHY 复位 (RST)  ====> GPIO1_A1 (低有效)
```

### 2.2 设备树配置

　　参考: rk3588-firefly-common.dtsi (FF_GMAC1) + rk3588-firefly-aio-3588sg.dtsi 覆盖

```
&gmac1 {
	status = "okay";
	phy-mode = "rgmii-rxid";          // RX delay 由 PHY 芯片内部提供, SOC 只调 tx_delay
	clock_in_out = "output";          // SOC 输出时钟给 PHY
	snps,reset-gpio = <&gpio1 RK_PA1 GPIO_ACTIVE_LOW>;   // SG 板: GPIO1_A1
	snps,reset-active-low;
	snps,reset-delays-us = <0 20000 100000>;   // 复位时序: 0/20ms/100ms (100ms 针对 rtl8211f)
	pinctrl-0 = <&gmac1_miim &gmac1_tx_bus2 &gmac1_rx_bus2
	             &gmac1_rgmii_clk &gmac1_rgmii_bus>;
	tx_delay = <0x37>;                // SG 板走线实测值
	phy-handle = <&rgmii_phy1>;
};

&mdio1 {
	rgmii_phy1: phy@1 {
		compatible = "ethernet-phy-ieee802.3-c22";
		reg = <0x1>;               // RTL8211F MDIO 地址
	};
};
```

　　RGMII 时序说明:
- RGMII 规范要求 TX/RX 方向各约 2ns 延迟 (相对时钟偏移采样)
- phy-mode = "rgmii-rxid": RX 延迟在 PHY 芯片内部完成 (RTL8211F
  由硬件 strap 配好), SOC 端不再设 rx_delay
- TX 延迟由 SOC GRF 寄存器调整, 即 tx_delay 属性, 范围 0x00~0x7F,
  每档约 150ps, 与 PCB 走线长度相关, 各板不同必须实测:

| 板 | gmac0 tx_delay | gmac1 tx_delay |
|---|---|---|
| firefly-common 默认 | 0x45 | 0x42 |
| AIO-3588SG | - | 0x37 |
| aio-3588q (双口) | 0x47 | 0x4f |
| itx-3588j (双口) | 0x42 | 0x3f |

## 3. 方式二: 双网口 (gmac0 + gmac1)

　　参考板: aio-3588q / itx-3588j。

### 3.1 硬件连接

```
网口0 (RTL8211F): gmac0 引脚组 (GPIO2/GPIO4), 复位 ====> GPIO3_C7 (低有效)
网口1 (RTL8211F): gmac1 引脚组 (GPIO3),       复位 ====> GPIO3_B7 (低有效)
两个 PHY 各挂自己的 mdio 总线 (mdio0/mdio1), 地址都是 0x1
```

### 3.2 设备树配置

　　在方式一基础上增加 gmac0 一份对称配置:

```
&gmac0 {
	status = "okay";
	phy-mode = "rgmii-rxid";
	clock_in_out = "output";
	snps,reset-gpio = <&gpio3 RK_PC7 GPIO_ACTIVE_LOW>;
	snps,reset-active-low;
	snps,reset-delays-us = <0 20000 100000>;
	pinctrl-0 = <&gmac0_miim &gmac0_tx_bus2 &gmac0_rx_bus2
	             &gmac0_rgmii_clk &gmac0_rgmii_bus>;
	tx_delay = <0x47>;                  // aio-3588q 实测值
	phy-handle = <&rgmii_phy0>;
};

&mdio0 {
	rgmii_phy0: phy@1 {
		compatible = "ethernet-phy-ieee802.3-c22";
		reg = <0x1>;
	};
};
```

　　双口/长走线稳定性: 用 pinctrl 覆盖增强 TX 数据线驱动强度
(aio-3588q / itx-3588j 做法, 信号质量差或长走线时使用):

```
&pinctrl {
	gmac0 {
		/override/ gmac0_tx_bus2: gmac0-tx-bus2 {
			rockchip,pins =
				/* gmac0_txd0 */
				<2 RK_PB6 1 &pcfg_pull_up_drv_level_6>,
				/* gmac0_txd1 */
				<2 RK_PB7 1 &pcfg_pull_up_drv_level_6>,
				/* gmac0_txen */
				<2 RK_PC0 1 &pcfg_pull_up_drv_level_6>;
		};

		/override/ gmac0_rgmii_bus: gmac0-rgmii-bus {
			rockchip,pins =
				/* gmac0_txd2 */
				<2 RK_PB1 1 &pcfg_pull_up_drv_level_6>,
				/* gmac0_txd3 */
				<2 RK_PB2 1 &pcfg_pull_up_drv_level_6>;
		};
	};

	gmac1 {
		/override/ gmac1_tx_bus2: gmac1-tx-bus2 {
			rockchip,pins =
				/* gmac1_txd0 */
				<3 RK_PB3 1 &pcfg_pull_up_drv_level_6>,
				/* gmac1_txd1 */
				<3 RK_PB4 1 &pcfg_pull_up_drv_level_6>,
				/* gmac1_txen */
				<3 RK_PB5 1 &pcfg_pull_up_drv_level_6>;
		};

		/override/ gmac1_rgmii_bus: gmac1-rgmii-bus {
			rockchip,pins =
				/* gmac1_txd2 */
				<3 RK_PA0 1 &pcfg_pull_up_drv_level_6>,
				/* gmac1_txd3 */
				<3 RK_PA1 1 &pcfg_pull_up_drv_level_6>;
		};
	};
};
```

## 4. 验证测试

```
# 驱动与 PHY 枚举
dmesg | grep -i -E "stmmac|eth|rtl"
# 应看到: eth%d: ..., PHY[...]: driver [...] (rtl8211f) regs:...

# 链路状态 (插上网线)
ethtool eth0
# Speed: 1000Mb/s, Duplex: Full, Link detected: yes

# tx_delay 校验 (最关键!)
iperf3 -s                       # 板端起服务, PC 端打流测 RX 方向
iperf3 -c <板IP>                # 板端打流测 TX 方向, 双向各测 3 分钟
# 千兆口双向都应稳定跑 930~950Mbps;
# 不丢包但速率只有 300~600Mbps 且波动大 => tx_delay 不准, 以 0x10 步进微调

# 大包长稳 (RGMII 时序不稳会偶发 CRC 错)
ping -s 1472 -f <网关IP>        # flood ping 大包 10 分钟, 0 丢包为合格

# 查看丢包/CRC 统计
ifconfig eth0                   # errors/dropped 应为 0
ethtool -S eth0 | grep -iE "err|crc|drop"
```

　　常见问题:
1. PHY 枚举不到 (dmesg 无 rtl8211f): 检查 mdio 节点 reg 地址、
   PHY 复位引脚/极性、snps,reset-delays-us 复位延时是否给足 100ms
2. link up 但 ping 不通/大量丢包: tx_delay 与走线不匹配, 微调
3. 只有一个方向性能差: TX 方向问题调 tx_delay; RX 方向问题检查
   phy-mode 是否 rgmii-rxid 且 PHY 硬件 RX delay 配置正确
4. 偶发断流: 参考方式二的 pinctrl 驱动加强
