# 千兆网

　　K3 平台千兆以太网适配笔记: SoC 内置 4 个 GMAC (spacemit,k3-gmac, DWMAC
5.10a 内核) + YT8531 PHY 的 RGMII 接法。以 Firefly AIBOX-PRO-K3 (单口
eth1) / itx-k3l (四口 eth0-3) 为参考板, 覆盖引脚组、delayline 相位调参、
WOL 与内核配置。

## 1. 原理

### 1.1 控制器与驱动栈

　　K3 有 4 个千兆 MAC (k3.dtsi 基座, 全部默认 disabled):

| 控制器 | 基址 | 中断 | pad 区块 |
|---|---|---|---|
| eth0 | 0xcac80000 | 132/276 | pad 0-20 |
| eth1 | 0xcac82000 | 133/277 | pad 21-41 |
| eth2 | 0xcac8e000 | 134/278 | pad 42-58 |
| eth3 | 0xa0000000 | 135/279 | pad 59-75 |

　　compatible = "spacemit,k3-gmac", "snps,dwmac-5.10a" — 标准 **stmmac**
驱动栈 + 厂商 glue 层:

- glue: `drivers/net/ethernet/stmicro/stmmac/dwmac-spacemit-ethqos.c`
  (CONFIG_DWMAC_SPACEMIT_ETHQOS, k3_defconfig 已 =y), 处理
  `spacemit,apmu`/`ctrl-offset`/`dline-offset` 寄存器访问 (delayline 调相
  用的 APMU 偏移就在这)。
- 内核配置 k3_defconfig 已齐: `CONFIG_STMMAC_ETH=y`、
  `CONFIG_STMMAC_SELFTESTS=y`。
- 基座节点还引用三个共享配置节点 (同样在 k3.dtsi, 勿删): `gmac_axi_setup`
  (AXI 突发 256)、`gmac_default_rxq_setup` / `gmac_default_txq_setup`
  (各 2 队列, DCB 算法, SP 调度) — `snps,axi-config` / `snps,mtl-*-config`
  指过去。

### 1.2 RGMII 时序: delayline 相位调参 (移植成败关键)

　　参考板不用标准的 `rx-internal-delay-ps`/`tx-internal-delay-ps`, 而是
走厂商 delayline 调相:

```c
spacemit,clk-tuning-enable;        /* 打开时钟调参 */
spacemit,clk-tuning-by-delayline;  /* 用 APMU delayline (而非 PHY 侧) 调 */
spacemit,tx-phase = <47>;          /* TX 延迟线相位, 0..255 */
spacemit,rx-phase = <53>;          /* RX 延迟线相位 */
```

　　**相位值与 PCB 走线长度强相关, 换板必须重调**: 同一颗 eth1,
itx-k3l 与 AIBOX-PRO 都是 47/53 (同源设计), 但同板上的四个口分别是
eth0=65/50、eth1=47/53、eth2=53/52、eth3=51/54 — 四组互不相同。自研板
照抄任何一组都可能千兆链路丢包/起不来, 调参方法见 5.3。

### 1.3 PHY: Motorcomm YT8531

　　两块参考板全部使用 YT8531 (PHY ID 001c.c916), 挂在 GMAC 自己的
mdio 总线 (`snps,dwmac-mdio`) 上, 地址统一 reg=1。设备树用
`compatible = "ethernet-phy-id001c.c916"` 精确绑定 (跳过自动探测)。

## 2. 硬件连接

　　RGMII 千兆口 = MAC pad 组 (12 根数据 + 2 根管理) + PHY (YT8531) + RJ45
带变压器。

### 2.1 eth1 引脚表 (AIBOX-PRO 单口, gmac1_cfg 基座组, func 1)

| 信号 | pad | 备注 | 信号 | pad | 备注 |
|---|---|---|---|---|---|
| rx_ctl | 21 | MII/RMII 复用 | tx d0 | 27 | |
| rx d0 | 22 | | tx d1 | 28 | |
| rx d1 | 23 | | tx_ctl | 32 | |
| rxc | 24 | RGMII 收时钟 | mdc | 33 | 管理 |
| rx d2 | 25 | RGMII 增补 | mdio | 34 | 管理 |
| rx d3 | 26 | RGMII 增补 | int (PHY) | 35 | 可选组 gmac1_int_pins |
| tx_clk | 29 | RGMII 发时钟 | ref_clk 出 | 36 | 可选组 gmac1_refclk_pins |
| tx d2 | 30 | RGMII 增补 | pps | 41 | 可选组 gmac1_pps_pins |
| tx d3 | 31 | RGMII 增补 | PHY reset | GPIO37 | snps,reset-gpios, 低复位 |

　　电气: 全组 `bias-disable; drive-strength = <9>` (DS4, 注意比 GPIO 的
25 小)。gmac0/2/3 同构, pad 区块整体平移 (eth0 从 pad0, eth2 从 pad42,
eth3 从 pad59 起), 完整表查 k3-pinctrl.dtsi 的 gmacN_cfg。

### 2.2 itx-k3l 四口参数总表

| 口 | MAC | PHY reset GPIO | tx-phase | rx-phase |
|---|---|---|---|---|
| eth0 | eth0 | GPIO20 | 65 | 50 |
| eth1 | eth1 | GPIO37 | 47 | 53 |
| eth2 | eth2 | GPIO57 | 53 | 52 |
| eth3 | eth3 | GPIO36 | 51 | 54 |

接线核对要点:

- `snps,reset-gpios = <&gpio K3_GPIO(20) GPIO_ACTIVE_LOW>` + reset-delays
  `<0 20000 100000>` (复位前 0us, 拉低 20ms, 释放后等 100ms 再扫 MDIO)。
- AIBOX-PRO eth1 的 reset 写法是裸 `<&gpio 1 5 ...>` (= 全局 GPIO37),
  itx 写 `<&gpio K3_GPIO(37) ...>` — 两种等价, 推荐宏写法。
- RJ45 变压器中心抽头/终端电阻按 YT8531 参考, 网口不通先查复位时序与
  delayline 相位, 再查线序。

## 3. 内核配置

```
# k3_defconfig 已有:
CONFIG_STMMAC_ETH=y                # stmmac 主体
CONFIG_STMMAC_SELFTESTS=y
CONFIG_DWMAC_SPACEMIT_ETHQOS=y     # K3 glue 层
# PHY 驱动: YT8531 走标准 C22 探测 (genphy), 无需专门 CONFIG;
# mdio 由 snps,dwmac-mdio 声明, stmmac 内建支持
```

　　WOL (网络唤醒) 需要节点带 `spacemit,wake-irq-enable` (走 eth_wake_irq
第二中断), 写法见 4.1; 无此属性时 ethtool wol 命令无效。

## 4. 设备树配置

### 4.1 方式一: 单口 eth1 (AIBOX-PRO)

```dts
&eth1 {
	pinctrl-names = "default";
	pinctrl-0 = <&gmac1_cfg>;          /* 基座组: base+RGMII 增补, func1 */

	max-speed = <1000>;
	tx-fifo-depth = <8192>;
	rx-fifo-depth = <8192>;
	snps,tso;
	snps,force_sf_dma_mode;
	phy-mode = "rgmii";
	phy-handle = <&rgmii1>;
	snps,reset-gpios = <&gpio K3_GPIO(37) GPIO_ACTIVE_LOW>;
	snps,reset-delays-us = <0 20000 100000>;

	spacemit,wake-irq-enable;          /* WOL 中断使能 (vendor) */

	spacemit,clk-tuning-enable;
	spacemit,clk-tuning-by-delayline;
	spacemit,tx-phase = <47>;          /* 与布线相关, 换板重调! */
	spacemit,rx-phase = <53>;

	status = "okay";

	mdio {
		#address-cells = <1>;
		#size-cells = <0>;
		compatible = "snps,dwmac-mdio";

		rgmii1: phy@1 {
			compatible = "ethernet-phy-id001c.c916";
			reg = <1>;
			device_type = "ethernet-phy";
		};
	};
};
```

　　说明: 基座 eth1 节点 (disabled) 已含时钟/复位/中断/axi-rxq-txq 引用,
这里只做覆盖使能; MAC 地址 `mac-address = [00 00 00 00 00 00]` 在基座,
量产时由用户态 (udev/ifup 或厂商工具) 写入真实地址。

### 4.2 方式二: 四口 (itx-k3l)

　　把 4.1 的模板对 eth0/eth2/eth3 各来一份, 差异只有三处: pinctrl 组
(gmac0_cfg/gmac2_cfg/gmac3_cfg)、reset GPIO、两个 phase 值 — 全部按 2.2
表填。PHY 节点同构 (reg=1, 001c.c916)。

### 4.3 属性速查与陷阱

| 属性 | 值域 | 说明 |
|---|---|---|
| phy-mode | rgmii / rmii / mii | K3 pad 组对三种模式预置了不同增补组, 换模式要换 cfg |
| spacemit,tx/rx-phase | 0..255 | delayline 相位, **每板每口都要调** |
| snps,reset-gpios / reset-delays-us | - | PHY 复位三段时序 |
| spacemit,wake-irq-enable | bool | WOL 用 eth_wake_irq (第二中断) |
| realtek,aldps-enable / clkout-disable / link-poll | - | **itx-k3l 挂在 YT8531 上, 驱动不解析 (遗留属性)**, 是 RTL8211F 的属性 |
| max-speed | 1000 | 千兆; RMII 场景写 100 |

陷阱清单:

- **realtek,\* 属性无效**: itx-k3l 四个 PHY 节点带 realtek,\* 系列属性, 但
  PHY 是 Motorcomm YT8531, 这些属性无任何驱动读取 — 自研板照抄只会误导
  排查方向, 应删除 (YT8531 的 ALDPS/clkout 由 PHY 内部默认)。
- 千兆协商上了但 iperf 丢包/巨慢: 十有八九是 delayline 相位没按自己板子
  调 (1.2 节)。
- eth3 基址在 0xa0000000 (与其他三个不同段), 单独检查其时钟域是否使能。
- pad 冲突: gmac2 区块与 i2c1 (pad54/55)、LED GPIO45 等重叠 — 多外设并存
  时先做 pad 冲突表 (README 有汇总)。

## 5. 验证测试

### 5.1 基础链路

```bash
# 1. 网卡出现与驱动链
ip link show eth1
dmesg | grep -iE "stmmac|eth1" | head    # "registration OK" / MDIO 总线

# 2. PHY 与协商状态
ethtool eth1                             # Speed: 1000Mb/s, Link: yes
ethtool -i eth1                          # driver: stmmaceth

# 3. 实际吞吐 (千兆应 ~940Mbps)
iperf3 -c <对端IP> -t 10
```

### 5.2 delayline 相位调参 (自研板必做)

```bash
# 方法: vendor 调参接口 / 或最直接 — 修改 dts 的 tx/rx-phase 重编译, 烧写,
# 用 iperf3 大包双向打流看错误计数:
ip -s link show eth1                     # errors/dropped 应为 0
iperf3 -c <IP> -R -t 30                  # 反向也打

# 经验区间: 参考板四口分布在 47..65 / 50..54, 从 53/53 起步,
# ±5 步进扫, 找 errors=0 且吞吐最大的窗口; 窗口两侧分别对应
# RX 采样过晚/过早 (现象: 小包通大包丢 / 特定速率丢包)
```

### 5.3 排查顺序

```bash
# 网口完全不起:
#   a) dmesg | grep -i phy          -> PHY reset/MDIO 探测
#   b) cat /sys/kernel/debug/pinctrl/*/pinmux-pins | grep 21
#                                    -> pad 是否切到 func1
#   c) ethtool -t eth1 online       -> stmmac 自测 (SELFTESTS 已编入)
#   d) 检查 mdio: ls /sys/bus/mdio_bus/devices/   -> 应有 <bus>:01
```
