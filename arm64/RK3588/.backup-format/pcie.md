# PCIe 适配笔记

## 1. RK3588 PCIe 控制器全景

| 控制器节点 | 地址 | 速率 | 依赖 PHY | Firefly 宏 |
|---|---|---|---|---|
| pcie3x4 | fe150000 | PCIe3.0 x4 | pcie30phy | FF_PCIE3_X4 |
| pcie3x2 | fe160000 | PCIe3.0 x2 | pcie30phy | FF_PCIE3_X2(共用) |
| pcie2x1l0 | fe170000 | PCIe2.0 x1 | combphy1_ps | FF_PCIE2_1L0 |
| pcie2x1l1 | fe180000 | PCIe2.0 x1 | combphy2_psu | (rk182x 拆分用) |
| pcie2x1l2 | fe190000 | PCIe2.0 x1 | combphy0_ps | FF_PCIE2_1L2 |

注意:
- combphy0_ps 与 SATA0 互斥 (同一组 PHY, 二选一)
- combphy1_ps 与 USB3 OTG1 互斥, combphy2_psu 与 SATA2 互斥
- pcie30phy 是 4 lane 共享 PHY, 通过 phymode 决定拆分方式

## 2. PCIe3.0 PHY 模式速查 (dt-bindings/phy/phy-snps-pcie3.h)

```
PHY_MODE_PCIE_NANBNB      = 0  /* P1:PCIe3x2  +  P0:PCIe3x2  */
PHY_MODE_PCIE_NANBBI      = 1  /* P1:PCIe3x2  +  P0:PCIe3x1*2 */
PHY_MODE_PCIE_NABINB      = 2  /* P1:PCIe3x1*2 + P0:PCIe3x2  */
PHY_MODE_PCIE_NABIBI      = 3  /* P1:PCIe3x1*2 + P0:PCIe3x1*2 */
PHY_MODE_PCIE_AGGREGATION = 4  /* PCIe3x4 聚合 */
```

内核配置 (defconfig 已开):

```
CONFIG_PCIE_DW_ROCKCHIP=y         # PCIe 控制器驱动
CONFIG_PHY_ROCKCHIP_SNPS_PCIE3=y  # PCIe3.0 PHY
CONFIG_PHY_ROCKCHIP_NANENG_COMBO_PHY=y  # PCIe2.0 combphy
```

## 3. 方式一: PCIe2.0 x1 (pcie2x1l2 + combphy0_ps) — AIO-3588SG / 接 WiFi

AIO-3588SG 使用, M.2 (E key) 接 AP6275P WiFi 模块。

### 3.1 硬件连接

```
M.2 E key WiFi:
  PERST# ====> GPIO3_D1 (reset-gpios)
  3.3V 电源使能 ====> GPIO1_D7 (vcc3v3_pcie20_1l2)
```

### 3.2 设备树配置

```
/ {
	vcc3v3_pcie20_1l2: vcc3v3-pcie20-1l2 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_pcie20_1l2";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio1 RK_PD7 GPIO_ACTIVE_HIGH>;
		startup-delay-us = <5000>;
		vin-supply = <&vcc12v_dcin>;
	};
};

&combphy0_ps {
	status = "okay";
};

&pcie2x1l2 {
	status = "okay";
	reset-gpios = <&gpio3 RK_PD1 GPIO_ACTIVE_HIGH>;
	vpcie3v3-supply = <&vcc3v3_pcie20_1l2>;
	rockchip,skip-scan-in-resume;      // 休眠唤醒后跳过重扫描
};
```

注意:
- combphy0_ps 与 SATA0 互斥,两者不能同时使能
- rockchip,skip-scan-in-resume 适用于 WiFi 场景(休眠唤醒后不重新扫描,
  避免 WiFi 断连); 若接 SSD 等设备则不要加

## 4. 方式二: PCIe2.0 x1 (pcie2x1l0 + combphy1_ps) — roc-rk3588-rt / aio-3588q 等

接 WiFi (rt 板) 或 4G/5G 模块 (q 板)。

### 4.1 硬件连接 (roc-rk3588-rt 为例)

```
M.2 E key WiFi:
  PERST# ====> GPIO4_A5 (reset-gpios, aio-3588q 为 GPIO1_B4)
  3.3V 电源使能 ====> GPIO2_C3 (vcc3v3_pcie20_1l0)
```

### 4.2 设备树配置

```
/ {
	vcc3v3_pcie20_1l0: vcc3v3-pcie20-1l0 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_pcie20_1l0";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio2 RK_PC3 GPIO_ACTIVE_HIGH>;
		startup-delay-us = <5000>;
		vin-supply = <&vcc3v3_sys>;
	};
};

&combphy1_ps {
	status = "okay";
};

&pcie2x1l0 {
	status = "okay";
	reset-gpios = <&gpio4 RK_PA5 GPIO_ACTIVE_HIGH>;
	rockchip,perst-inactive-ms = <500>;  // PERST# 释放前等待时间
	vpcie3v3-supply = <&vcc3v3_pcie20_1l0>;
};
```

注意:
- rt 板源码注释: WiFi 场景 rockchip,skip-scan-in-resume 需与 WLAN platdata
  配合使用, 否则导致休眠唤醒不可用, 因此此方式用 perst-inactive-ms 替代
  (与方式一行为相反, 以实际休眠唤醒测试为准)
- combphy1_ps 与 USB3 OTG1 互斥

## 5. 方式三: PCIe3.0 x2 + x1 (NANBBI 模式) — aio-3588jd4

pcie30phy 拆成 P1:x2 + P0:x1*2, pcie3x2 跑 2 lane + pcie3x4 跑 1 lane,
两个独立插槽。

### 5.1 硬件连接 (aio-3588jd4)

```
PCIe3.0 x2 插槽 (pcie3x2):
  PERST# ====> GPIO4_B0
  3.3V 电源使能 ====> GPIO2_C5 (vcc3v3_pcie3x2_0)
PCIe3.0 x1 插槽 (pcie3x4):
  PERST# ====> GPIO4_B6
  3.3V 电源使能 ====> GPIO2_C5 (vcc3v3_pcie3x2_1, 与 x2 同一 GPIO)
```

### 5.2 设备树配置

```
/ {
	vcc3v3_pcie3x2_0: vcc3v3-pcie3x2-0 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_pcie3x2_0";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio2 RK_PC5 GPIO_ACTIVE_HIGH>;
		startup-delay-us = <5000>;
		vin-supply = <&vcc12v_dcin>;
	};

	vcc3v3_pcie3x2_1: vcc3v3-pcie3x2-1 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_pcie3x2_1";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio2 RK_PC5 GPIO_ACTIVE_HIGH>;   // 与 x2 同一 GPIO
		startup-delay-us = <5000>;
		vin-supply = <&vcc12v_dcin>;
	};
};

&pcie3x2 {
	status = "okay";
	num-lanes = <2>;
	reset-gpios = <&gpio4 RK_PB0 GPIO_ACTIVE_HIGH>;
	vpcie3v3-supply = <&vcc3v3_pcie3x2_0>;
};

&pcie3x4 {
	num-lanes = <1>;
	reset-gpios = <&gpio4 RK_PB6 GPIO_ACTIVE_HIGH>;
	vpcie3v3-supply = <&vcc3v3_pcie3x2_1>;
	status = "okay";
};

&pcie30phy {
	rockchip,pcie30-phymode = <PHY_MODE_PCIE_NANBBI>;
	status = "okay";
};
```

## 6. 方式四: PCIe3.0 x4 聚合 (AGGREGATION 模式) — aio-3588q / itx-3588j

pcie30phy 4 lane 全部聚合给 pcie3x4, 接 M.2 NVMe SSD。

### 6.1 硬件连接 (aio-3588q)

```
M.2 M key NVMe SSD:
  PERST# ====> GPIO4_B6
  3.3V 电源使能 ====> GPIO2_C5 (vcc3v3_pcie30)
```

### 6.2 设备树配置

```
/ {
	vcc3v3_pcie30: vcc3v3-pcie30 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_pcie30";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio2 RK_PC5 GPIO_ACTIVE_HIGH>;
		startup-delay-us = <5000>;
		vin-supply = <&vcc12v_dcin>;
	};
};

&pcie30phy {
	status = "okay";
	rockchip,pcie30-phymode = <PHY_MODE_PCIE_AGGREGATION>;
};

&pcie3x4 {
	status = "okay";
	reset-gpios = <&gpio4 RK_PB6 GPIO_ACTIVE_HIGH>;
	vpcie3v3-supply = <&vcc3v3_pcie30>;
};
```

## 7. 方式五: PCIe3.0 x1 * 4 (NABIBI 模式) — aio-3588l-qua-rk182x

pcie30phy 拆成 4 个 x1, 同时挂 4 块 SSD。
注意此方式下 pcie2x1l0/l1 的 phys 被改挂到 pcie30phy (借用控制器)。

### 7.1 硬件连接 (aio-3588l-qua-rk182x)

```
M.2 card 0 (pcie2x1l0 借用 pcie30phy lane):
  PERST# ====> GPIO1_B4
M.2 card 1 (pcie2x1l1 借用 pcie30phy lane):
  PERST# ====> GPIO4_A2
ssd 2 (pcie3x2 x1):
  PERST# ====> GPIO1_B7
ssd 3 (pcie3x4 x1):
  PERST# ====> GPIO1_B2
4 路 3.3V 电源共用 vcc3v3_ac
```

### 7.2 设备树配置

```
&pcie30phy {
	rockchip,pcie30-phymode = <PHY_MODE_PCIE_NABIBI>;
	status = "okay";
};

&pcie2x1l0 {
	phys = <&pcie30phy>;                         // 改挂 pcie30phy
	reset-gpios = <&gpio1 RK_PB4 GPIO_ACTIVE_HIGH>;
	rockchip,skip-scan-in-resume;
	vpcie3v3-supply = <&vcc3v3_ac>;
	rockchip,perst-inactive-ms = <800>;
	status = "okay";
};

&pcie2x1l1 {
	phys = <&pcie30phy>;
	reset-gpios = <&gpio4 RK_PA2 GPIO_ACTIVE_HIGH>;
	rockchip,skip-scan-in-resume;
	vpcie3v3-supply = <&vcc3v3_ac>;
	rockchip,perst-inactive-ms = <600>;
	status = "okay";
};

&pcie3x2 {
	num-lanes = <1>;
	reset-gpios = <&gpio1 RK_PB7 GPIO_ACTIVE_HIGH>;
	vpcie3v3-supply = <&vcc3v3_ac>;
	rockchip,skip-scan-in-resume;
	rockchip,perst-inactive-ms = <900>;
	status = "okay";
};

&pcie3x4 {
	num-lanes = <1>;
	reset-gpios = <&gpio1 RK_PB2 GPIO_ACTIVE_HIGH>;
	vpcie3v3-supply = <&vcc3v3_ac>;
	rockchip,skip-scan-in-resume;
	rockchip,perst-inactive-ms = <700>;
	status = "okay";
};
```

## 8. 验证测试

```
# 枚举设备
lspci
# 应看到挂载的设备, 如 NVMe SSD / WiFi ( aperst 释放后自动扫描)

# 查看 link 速率和宽度
lspci -vvv | grep -E "LnkSta|LnkCap"
#   LnkSta: Speed 8GT/s (PCIe3.0), Width x4  为正常聚合模式

# NVMe SSD
lsblk                     # 应出现 nvme0n1
dmesg | grep -i nvme

# WiFi (pcie2x1l2)
lspci | grep -i network   # 应看到 Bus 002 Device ... network controller
dmesg | grep -i -E "wifi|brcm|ap6275"

# 常见问题:
# 1. lspci 无设备: 检查 reset-gpios 极性、电源 GPIO、PHY 互斥关系
# 2. link 训练失败 (Speed 2.5GT/s): 检查 PHY mode 与 num-lanes 匹配
# 3. combphy 报错: 确认没有同时使能互斥的 SATA/USB3 节点
```
