# PCIe

　　K3 平台 PCIe 适配笔记: 5 个 RC 控制器 (pcie0_rc-4_rc) + 6 组 PHY 的全部
用法, 含 4-lane 槽位 / 1-lane M.2 / ASM1182e 档位扩展 / WiFi 专用 DMA 池
四种方式。以 Firefly AIBOX-PRO-K3 / itx-k3l 为参考板。

## 1. 原理

### 1.1 控制器与 PHY 总表 (k3.dtsi 基座, 全部 disabled)

| RC 控制器 | 基址 | max-link-speed | 基座 num-lanes | 配套 PHY (每 phy 2-lane) | 引脚组 (基座预置) |
|---|---|---|---|---|---|
| pcie0_rc | 0x80000000 | Gen3 | 8 (按 PHY 拆) | phy0 (0x81d00000) + phy1 (0x81e00000) | pcie0 perst pad79 / clkreq pad81, func5 |
| pcie1_rc | 0x80400000 | Gen3 | - | phy1 | pcie1 perst pad113 / wake 114 / clkreq 115, func5 |
| pcie2_rc | 0x80800000 | Gen3 | - | phy2 (0x81f00000) + phy3 (0x82000000) | pcie2 perst pad58 / wake 59 / clkreq 60, func4 |
| pcie3_rc | 0x80c00000 | Gen3 | 1 | phy4 (0x82100000 上邻) | pcie3_0_cfg (pad3/4/5 func4); pcie3_1_cfg (pad105/106/107 func5); pcie3_2_cfg (pad124/125/126 func3) 三选一 |
| pcie4_rc | 0x81000000 | Gen3 | 1 | phy5 | pcie4 perst pad76 / wake 80 / clkreq 78, func5 |

- RC compatible = "spacemit,k1-pcie", 驱动
  `drivers/pci/controller/dwc/pcie-spacemit-k1.c`
  (CONFIG_PCIE_SPACEMIT_K1, `default ARCH_SPACEMIT` 随 SOC_SPACEMIT 自动
  =y, **内核配置无需动**); k3_defconfig 显式只有
  `CONFIG_PCIE_SPACEMIT_EP=y` (EP 口, RK1828 NPU 场景, 本篇不展开)。
- PHY compatible = "spacemit,k3-pcie-phy", 每组 `num-lanes = <2>`、
  `spacemit,phy-id = <N>`。
- RC 节点 reg 五段: dbi/dbi2/atu/config space/link — 基座全带好, 板级只写
  pinctrl + phys + num-lanes + 供电。

### 1.2 lane 预算 (多控制器并存的拆分规则)

　　每个 PHY 固定 2 lane, 一个 PHY 同时只能给一个 RC:

| 场景 (itx-k3l 宏组合) | pcie0_rc | pcie1_rc | pcie2_rc |
|---|---|---|---|
| FF_PCIEX16_SLOT (x4 槽) | phy0+phy1, 4-lane | - | - |
| FF_PCIEX16_SLOT + FF_SATA_SSD | phy0, 2-lane (x2 槽) | phy1, 2-lane (SATA 桥) | - |
| aibox-k3 (FF_GMAC0 系) | - | - | phy2+phy3, 2-lane |

　　AIBOX-PRO 的组合: FF_PCIE1 → pcie0_rc x4 (phy0+phy1);
FF_PCIE0 → pcie4_rc x1 (phy5); FF_ASM1182e_* → pcie3_rc x1 (phy4)。

### 1.3 ASM1182e 档位扩展是干什么的

　　ASM1182e 是 PCIe packet switch (4 upstream → 多下游)。AIBOX-PRO 把
phy4/pcie3_rc (Gen2, 1-lane) 接到 ASM1182e, 其下游分出 M.2 座与 WiFi 模组
两个槽 — **一路 RC 扩出两个 PCIe 设备位**。板级做了两级 regulator 链:
`asm1182e_power` (GPIO106, 芯片供电, 100ms 延时) → `asm1182e_perst_release`
(GPIO87, PERST 释放控制, vin 挂在前级) — 用 regulator 链保证"先上电后放
PERST"的时序。

## 2. 硬件连接

### 2.1 参考板信号总表

| 功能 | 信号 | GPIO/pad | 说明 |
|---|---|---|---|
| PCIe 3V3 供电使能 | pcie_pwr_en | GPIO50 (AIBOX-PRO) / GPIO105 (itx M.2) | 高有效, 1.8V 域 |
| pcie0 (x4 槽) | perst | pad79 func5 | 复用功能, 非 GPIO |
| pcie0 | clkreq | pad81 func5 | |
| pcie4 (M.2) | perst | pad76 func5 | |
| pcie4 | wake | pad80 func5 | |
| pcie4 | clkreq | pad78 func5 | |
| pcie1 (itx) | perst/wake/clkreq | pad113/114/115 func5 | |
| pcie2 (itx) | perst/wake/clkreq | pad58/59/60 func4 | |
| ASM1182e 电源 | asm1182e_pwr_en | GPIO106 | 1.8V 域 |
| ASM1182e PERST 释放 | asm1182e_perst | GPIO87 | 1.8V 域 |
| WiFi 供电 (WiFi 方式) | wifi_pwr_en | GPIO99 | 1.8V 域 |
| WiFi clkreq (WiFi 方式) | pcie3_wifi_clkreq | pad107 | 板级组 |

接线核对要点:

- perst/wake/clkreq 是**复用功能脚** (func4/5), 不是 GPIO — pinctrl 组里
  func 号错一位整个口无复位/时钟请求。
- perst/clkreq 组电气: `bias-pull-up; drive-strength = <38>; power-source
  = <3300>` (AIBOX-PRO, DS 大电流档 3.3V 域); itx 基座组是 bias-disable +
  DS 25 — 参考板间也不一致, 按自己硬件确定。
- 供电时序铁律: 槽位 3V3 → 上电稳定 (startup-delay-us) → PERST 释放 →
  链路训练。ASM1182e 方案的 regulator 链就是这个时序的软件表达。

## 3. 内核配置

```
# k3_defconfig 已有 (RC 驱动随 SOC_SPACEMIT 自动启用):
CONFIG_PCIE_SPACEMIT_K1=y        # spacemit,k1-pcie host 驱动 (default ARCH_SPACEMIT)
CONFIG_PCIE_SPACEMIT_EP=y        # EP 口 (RK1828 用, 普通 RC 板可不开)
CONFIG_PCI_MSI=y                 # PCIE_SPACEMIT 依赖
# NVMe/AHCI 等终端设备驱动按需: CONFIG_BLK_DEV_NVME=y 等
```

## 4. 设备树配置

### 4.1 方式一: x4 槽位 (AIBOX-PRO FF_PCIE1)

```dts
/ {
	vcc3v3_pcie: vcc3v3-pcie {
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_pcie";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		gpio = <&gpio K3_GPIO(50) GPIO_ACTIVE_HIGH>;
		enable-active-high;
		regulator-boot-on;
		regulator-always-on;
		pinctrl-names = "default";
		pinctrl-0 = <&pcie_pwr_en_cfg>;
		startup-delay-us = <5000>;
		vin-supply = <&vcc12v_dcin>;   /* 板级输入电源, 按实际电源树 */
		status = "okay";
	};
};

&phy0 { status = "okay"; };
&phy1 { status = "okay"; };

&pcie0_rc {
	pinctrl-names = "default";
	pinctrl-0 = <&pcie0_1_cfg>;        /* 基座组: perst79/clkreq81 func5 */
	phys = <&phy0>, <&phy1>;
	phy-names = "phy0", "phy1";

	num-lanes = <4>;
	vpcie3v3-supply = <&vcc3v3_pcie>;
	status = "okay";
};

&pinctrl {
	pcie_pwr_en_cfg: pcie-pwr-en-cfg {
		pcie-pwr-en-pin {
			pinmux = <K3_PADCONF(50, 0)>;
			bias-disable;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};

	pcie0-1-cfg {
		pcie0-0-pins {
			pinmux = <K3_PADCONF(79, 5)>,   /* pcie0 perst */
				 <K3_PADCONF(81, 5)>;   /* pcie0 clkreq */
			bias-pull-up;
			drive-strength = <38>;
			power-source = <3300>;
		};
	};
};
```

### 4.2 方式二: 1-lane M.2 (AIBOX-PRO FF_PCIE0 → pcie4_rc)

```dts
&phy5 { status = "okay"; };

&pcie4_rc {
	pinctrl-names = "default";
	pinctrl-0 = <&pcie4_1_cfg>;
	phys = <&phy5>;
	phy-names = "phy5";

	num-lanes = <1>;
	vpcie3v3-supply = <&vcc3v3_pcie>;
	status = "okay";
};

&pinctrl {
	pcie4-1-cfg {
		pcie4-0-pins {
			pinmux = <K3_PADCONF(76, 5)>,   /* pcie4 perst */
				 <K3_PADCONF(80, 5)>,   /* pcie4 wake */
				 <K3_PADCONF(78, 5)>;   /* pcie4 clkreq */
			bias-pull-up;
			drive-strength = <38>;
			power-source = <3300>;
		};
	};
};
```

### 4.3 方式三: ASM1182e 扩展 (AIBOX-PRO, 一路 RC 扩 M.2+WiFi)

　　M.2 版 (FF_ASM1182e_PCIE0_M2): 两级 regulator 链控制上电/复位时序:

```dts
/ {
	asm1182e_power: regulator-asm1182e-power {
		compatible = "regulator-fixed";
		regulator-name = "asm1182e_power";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		gpios = <&gpio K3_GPIO(106) GPIO_ACTIVE_HIGH>;
		enable-active-high;
		pinctrl-names = "default";
		pinctrl-0 = <&asm1182e_pwr_en_cfg>;
		startup-delay-us = <100000>;    /* 芯片电源稳定 100ms */
		regulator-boot-on;
		regulator-always-on;
		status = "okay";
	};

	/* PERST 释放也用 regulator 表达: vin 挂 asm1182e_power,
	 * 保证先上电后放 PERST */
	asm1182e_perst_release: regulator-asm1182e-perst-release {
		compatible = "regulator-fixed";
		regulator-name = "asm1182e_perst_release";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		gpios = <&gpio K3_GPIO(87) GPIO_ACTIVE_HIGH>;
		enable-active-high;
		pinctrl-names = "default";
		pinctrl-0 = <&asm1182e_perst_cfg>;
		vin-supply = <&asm1182e_power>;
		startup-delay-us = <100000>;
		regulator-boot-on;
		regulator-always-on;
		status = "okay";
	};
};

&phy4 { status = "okay"; };

&pcie3_rc {
	phys = <&phy4>;
	phy-names = "phy4";
	num-lanes = <1>;
	max-link-speed = <2>;              /* ASM1182e 上行限 Gen2 */
	vpcie3v3-supply = <&asm1182e_perst_release>;
	status = "okay";
};

&pinctrl {
	asm1182e_pwr_en_cfg: asm1182e-pwr-en-cfg {
		asm1182e-pwr-en-pins {
			pinmux = <K3_PADCONF(106, 0)>;
			bias-disable;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};

	asm1182e_perst_cfg: asm1182e-perst-cfg {
		asm1182e-perst-pins {
			pinmux = <K3_PADCONF(87, 0)>;
			bias-disable;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};
};
```

　　WiFi 版 (FF_ASM1182e_PCIE0_WIFI): pcie3_rc 不放 perst, 改配 clkreq +
**restricted DMA 池** (WiFi 模组 DMA 地址受限场景):

```dts
&resmem {
	pcie3_dma_pool: pcie3-dma-pool@1f0000000 {
		compatible = "restricted-dma-pool";
		reg = <0x1 0xf0000000 0x0 0x02000000>;   /* 32MB */
	};
};

&pcie3_rc {
	pinctrl-names = "default";
	pinctrl-0 = <&pcie3_wifi_clkreq_cfg>;   /* 板级组: clkreq pad107 */

	dma-ranges = <0x02000000 0x0 0x80000000
		      0x1 0xf0000000
		      0x0 0x02000000>;
	memory-region = <&pcie3_dma_pool>;
};
/* vcc3v3_wifi: GPIO99 regulator, 结构同 4.1 的 vcc3v3_pcie, wifi 模组供电 */
```

### 4.4 方式四: 多控制器并存 (itx-k3l)

　　FF_SATA_SSD = **PCIe 转 SATA 桥** (详 sata.md) 挂 pcie1_rc
(2-lane), 槽位让出 phy1 时 pcie0_rc 降 2-lane:

```dts
/* SATA 桥上行口 (FF_SATA_SSD, 桥芯片无 dts 节点) */
&phy1 { status = "okay"; };

&pcie1_rc {
	pinctrl-names = "default";
	pinctrl-0 = <&pcie1_2_cfg>;        /* 基座组: 113/114/115 func5 */
	phys = <&phy1>;
	phy-names = "phy1";

	num-lanes = <2>;
	status = "okay";
};

/* x16 槽降为 x2 (FF_PCIEX16_SLOT + FF_SATA_SSD 时) */
&phy0 { status = "okay"; };

&pcie0_rc {
	pinctrl-names = "default";
	pinctrl-0 = <&pcie0_1_cfg>;
	phys = <&phy0>;
	phy-names = "phy0";

	num-lanes = <2>;
	status = "okay";
};

/* M.2 座供电 (itx): GPIO105 */
/ {
	vcc3v3_pcie_m2: vcc3v3-pcie-m2 {
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_pcie_m2";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio K3_GPIO(105) GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&pcie_pwr_en_cfg>;
		pinctrl-names = "default";
		vin-supply = <&vcc12v_dcin>;
		status = "okay";
	};
};
```

### 4.5 属性速查与陷阱

| 属性 | 说明 |
|---|---|
| num-lanes | RC 侧 lane 数; phy0/1 组合时 = 两 phy lane 之和 (4), 单 phy 2-lane |
| phys/phy-names | 多 phy 时顺序对应; phy-names 与 phy 编号一致 |
| max-link-speed | 限速 Gen2/Gen3; ASM1182e 方案写 2 |
| vpcie3v3-supply | 槽位 3V3; 可挂 regulator 链表达上电/复位时序 |
| dma-ranges + memory-region | restricted-dma-pool 32MB, WiFi 模组 DMA 限制场景 |
| regulator-boot-on + always-on | 常供电槽位写法; 热插拔槽另议 |

陷阱清单:

- **一个 PHY 只能给一个 RC**: pcie0 与 pcie1 都想用 phy1 时必须 lane 拆分
  (1.2 节), 否则后 probe 的控制器起不来且报 PHY busy。
- perst/clkreq 的 func 号 (5 或 4) 写错 → 训练失败 (L0 无 link), dmesg 见
  "Link never came up" 类信息。
- 供电 regulator 忘配 startup-delay-us → 设备在电源未稳时被复位, 偶发
  枚举失败 (尤其 ASM1182e 两级链)。
- WiFi 方式的 restricted-dma-pool 地址 (0x1_f0000000) 不能与其他保留内存
  撞 (resmem 段统一规划)。
- pcie2 的 pad58/60 与 aibox-k3 Type-C 的 INT(GPIO58)/VBUS_EN(GPIO60)
  同号 — 同一脚 func0(GPIO) 与 func4(pcie2) 互斥, 两功能不能共存
  (README 冲突速查有记)。

## 5. 验证测试

```bash
# 1. 控制器 probe 与链路训练
dmesg | grep -iE "pcie|dw-pcie" | head -20
#    关键行: "Link up" / RC 枚举信息; "Link never came up" = 训练失败

# 2. 拓扑与设备
lspci                                # RC bridge + 下游设备 (ASM1182e 可见二级 bridge)
lspci -vvv -s <dev> | grep -E "LnkSta|LnkCap"   # 实际速率/带宽 (x4 Gen3 应 8GT/s x4)

# 3. NVMe SSD (方式四)
ls /dev/nvme* ; nvme list

# 4. WiFi 模组 (方式三 WiFi 版)
lspci | grep -i network ; dmesg | grep -i firmware

# 5. 排查顺序
#    a) 3V3 实测槽位有电 -> regulator/GPIO
#    b) PERST 已释放 (示波器/万用表) -> regulator 链/pinctrl func 号
#    c) dmesg | grep -i phy        -> PHY probe (spacemit,k3-pcie-phy)
#    d) cat /sys/kernel/debug/pinctrl/*/pinmux-pins | grep -E "79|81|76"
#                                   -> 确认 func5 已生效
#    e) ASM1182e: lspci -t         -> 树形拓扑里 switch 是否出现
```
