# SATA

　　K3 平台 SATA 适配笔记: K3 **没有原生 SATA 控制器** (全 dts 无
ahci/sata 控制器节点), SATA 盘 = **PCIe 转 SATA 桥芯片** (ASM116x 类
AHCI 桥) 挂在 RC 下面, PCIe 枚举自动识别, 设备树**零桥芯片节点**。
itx-k3l 的 FF_SATA_SSD ("PCIE TO SATA") 是实装参考; 板载存储另有 UFS
(ufshc) 选项一并说明。

## 1. 原理

### 1.1 K3 的存储通路全景

| 通路 | 控制器 | 说明 |
|---|---|---|
| NVMe SSD | pcieN_rc + NVMe 盘 | pcie.md 4.x 方式, BLK_DEV_NVME=y |
| **SATA 盘** | pcieN_rc + **PCIe→SATA 桥** | 本篇, 桥芯片无 dts 节点 |
| UFS | ufshc@0xc0e00000 ("spacemit,k3-ufshcd") | k3.dtsi 基座, 板载 eMMC/UFS 位 |
| SD/eMMC | sdhc (k3.dtsi) | 见mmc相关篇 |

　　RK3588 有原生 SATA3.0 控制器 (combphy 复用), K3 **没有对应物** —
别去找 "k3 sata 节点", 不存在; 板级工作全在 "选 RC + 供电 + (itx 类
板) 通道切换开关"。

### 1.2 itx-k3l 的 SATA 设计: ASW3810 通道切换

　　itx 板同一组 PCIe 差分对 (phy1, 2-lane) 经 **ASW3810 模拟开关**
二选一走线:

- `ASW3810_SEL = L` → 差分对到 **SATA 桥芯片** (FF_SATA_SSD 宏,
  PCIE_OR_SATA=0, **itx 默认**);
- `ASW3810_SEL = H` → 差分对到 **PCIEX16 槽** (FF_PCIEX16_SLOT 宏)。

　　软件用两个 **regulator-fixed 节点表达这个开关** (pcie_or_sata_sel,
enable-active-low 挂 pca9555_2) — 本质是 GPIO 控制的上电顺序描述,
自研板没有这颗开关 (桥直连 RC) 时**整个 sel 节点可以不写**。

### 1.3 桥芯片本身

　　PCIe→SATA 桥 (ASM1166/ASM1064 等) 是标准 PCIe 设备: 枚举后绑
ahci 驱动 (SATA_AHCI), 出 /dev/sdX + /dev/sataN — **设备树里没有任何
桥节点**。参考板里 spcda400 曾有 ASM1164 设计 ("old ASM1164 design on
PCIe1/phy1 and remains off", 已停用, 现路由改为 M.2 NVMe + 双
RTL8125) — 说明 Firefly 也从桥接方案转向 NVMe, 自研板选型时先想清楚
要不要 SATA。

## 2. 硬件连接

　　参考板: itx-k3l FF_SATA_SSD (ASW3810 切到 SATA 侧)。

| 信号 | 接法 | 说明 |
|---|---|---|
| PCIe 2-lane 差分对 | pcie1_rc ← phy1 | 桥芯片上行口 |
| ASW3810_SEL | pca9555_2 PCA_IO0_5, **低 = SATA** | 通道开关 (itx 特有) |
| SATA 3V3 供电 | **GPIO100** (vcc3v3_sata, 高有效) | sata_pwr_en_cfg, 3.3V 域 |
| SATA 2.5V 供电 | vcc25_64_sata (常开, 无 GPIO) | 桥/信号 2.5V, vin=vcc5v0_sys |
| SATA 盘接口 | 桥芯片下游 SATA 座 | 数据+电源按盘规格 |

接线核对要点:

- 自研板 **桥芯片直连 RC** (无开关): 只需 phy/pcieN_rc 使能 + 桥供电
  regulator, ASW3810/pcie_or_sata_sel 段整段省略。
- 桥芯片上行 lane 数: 2-lane (phy1) 时 Gen3 x2 ≈ 2GB/s, 6 口 SATA 共享
  该带宽, 多盘并发写要算带宽账。
- GPIO100 在 aibox-k3 是 usb3 vbus 相关脚 (usb30.md 方式一), 复用冲突
  自查 README 冲突表。

## 3. 内核配置

```
# k3_defconfig 已有 (SATA 链全套已编, 无需补):
CONFIG_ATA=y
CONFIG_SATA_AHCI=y                 # PCIe→SATA 桥枚举后绑此驱动
CONFIG_BLK_DEV_SD=y                # SCSI 盘 (sdx 节点)
CONFIG_BLK_DEV_NVME=y              # NVMe 备选方案
# UFS 方案:
CONFIG_SCSI_UFSHCD=y
CONFIG_SCSI_UFSHCD_PLATFORM=y
CONFIG_SCSI_UFS_SPACEMIT_K3=y      # spacemit,k3-ufshcd
```

## 4. 设备树配置

### 4.1 方式一: 桥芯片直连 RC (自研板推荐, 最小集)

```dts
/ {
	/* SATA 桥/座供电, GPIO 按你板选脚; 无开关控制时 always-on 常供 */
	vcc3v3_sata: vcc3v3-sata {
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_sata";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		regulator-always-on;
		regulator-boot-on;
		enable-active-high;
		gpios = <&gpio K3_GPIO(100) GPIO_ACTIVE_HIGH>;  /* 按你板选脚 */
		pinctrl-0 = <&sata_pwr_en_cfg>;
		pinctrl-names = "default";
		vin-supply = <&vcc3v3_sys>;
		status = "okay";
	};
};

&phy1 { status = "okay"; };

&pcie1_rc {
	pinctrl-names = "default";
	pinctrl-0 = <&pcie1_2_cfg>;        /* 基座组: perst113/wake114/clkreq115 func5 */
	phys = <&phy1>;
	phy-names = "phy1";

	num-lanes = <2>;
	vpcie3v3-supply = <&vcc3v3_sata>;
	status = "okay";
};

&pinctrl {
	sata_pwr_en_cfg: sata-pwr-en-cfg {
		sata-pwr-en-pin {
			pinmux = <K3_PADCONF(100, 0)>;
			bias-disable;
			drive-strength = <25>;
			power-source = <3300>;
		};
	};
};
```

### 4.2 方式二: itx 完整复刻 (ASW3810 开关 + 双电源)

　　FF_SATA_SSD 宏展开的全部节点 — 硬件上确有 ASW3810 类开关才照抄:

```dts
/ {
	/* 通道选择: L --> SATA, H --> PCIEX16_SLOT (itx 特有) */
	pcie_or_sata_sel: pcie-or-sata-sel {
		compatible = "regulator-fixed";
		regulator-name = "pcie_or_sata_sel";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		regulator-always-on;
		regulator-boot-on;
		enable-active-low;
		/* 参考板经 I2C 扩展器; 自研板可换 <&gpio K3_GPIO(N) ...> */
		gpios = <&pca9555_2 PCA_IO0_5 GPIO_ACTIVE_LOW>;
		status = "okay";
	};

	/* SATA 信号 2.5V (常开, 无控制脚) */
	vcc25_64_sata: vcc25-64-sata {
		compatible = "regulator-fixed";
		regulator-name = "vcc25_64_sata";
		regulator-min-microvolt = <2500000>;
		regulator-max-microvolt = <2500000>;
		regulator-always-on;
		regulator-boot-on;
		enable-active-high;
		vin-supply = <&vcc5v0_sys>;
		status = "okay";
	};

	/* vcc3v3_sata: GPIO100, 同 4.1 */
};

&phy1 { status = "okay"; };

&pcie1_rc {
	pinctrl-names = "default";
	pinctrl-0 = <&pcie1_2_cfg>;
	phys = <&phy1>;
	phy-names = "phy1";

	num-lanes = <2>;
	status = "okay";                    /* itx 原文不挂 vpcie3v3, 供电由
	                                       vcc3v3_sata/vcc25_64_sata 独立常供 */
};
```

### 4.3 UFS 板载存储 (顺带)

```dts
&ufshc {
	status = "okay";                   /* 基座节点 ufshc@0xc0e00000 已配好
	                                      时钟/复位/lane, 使能即可 */
};
```

### 4.4 属性速查与陷阱

| 属性/节点 | 说明 |
|---|---|
| vpcie3v3-supply | 桥上行供电; itx 原文省略 (板级电源独立), 自研板建议挂上 |
| num-lanes = <2> | phy1 单组 2-lane; 桥上行按 lane 预算 (pcie.md 1.2) |
| pcie_or_sata_sel | regulator 表达的通道开关, 无开关硬件则不写 |
| vcc25_64_sata | 2.5V 常开电源; 若你板桥芯片无 2.5V 轨则不写 |
| enable-active-low | sel 节点极性 (低=SATA); 照抄前先量开关脚逻辑 |

陷阱清单:

- **别找原生 SATA 节点**: K3 没有, 只有 PCIe 桥; dmesg 里 SATA 盘的
  probe 行来自 ahci 驱动 (PCIe 设备), 不是平台设备。
- **FF_SATA_SSD 与 FF_PCIEX16_SLOT 二选一**: 同一组差分对, itx 用开关
  切; 自研板按硬件选其一, 宏/节点别双开 (两个都开 = pcie0 lane 拆分
  逻辑错乱)。
- 桥芯片型号与盘数: ASM1166 (6口)/ASM1064 (4口) 上行都是 PCIe Gen3
  x2 级 — 6 盘并发时单盘 ~330MB/s, 不是每盘 6Gbps。
- SATA 线/座供电: 3.5" 盘要 12V/5V 外供, 桥板上只有 3V3/2V5 信号电 —
  供电设计在硬件侧, 软件别指望 regulator 拉起 12V。
- UFS 若不用, 基座 status disabled 即可, 不影响 SATA; 用 UFS 时
  注意 freq-table-hz 时钟档 (基座已带 491.52MHz/19.2MHz)。

## 5. 验证测试

```bash
# 1. PCIe 层: 桥枚举
lspci | grep -iE "sata|ahci|asm"     # 桥芯片应出现
dmesg | grep -iE "ahci|ata[0-9]" | head -15   # ahci probe + 盘口探测

# 2. 盘节点
ls /dev/sd*                          # SATA 盘 (桥下) / UFS 盘
ls /dev/nvme*                        # NVMe 方案对照

# 3. 读写
smartctl -a /dev/sda                 # 经桥读 SMART
dd if=/dev/sda of=/dev/null bs=1M count=500   # 读速 (x2 Gen3 应数百 MB/s)

# 4. UFS 方案
dmesg | grep -i ufs                  # ufshc probe 行
cat /sys/bus/scsi/devices/*/model    # UFS 盘型号

# 5. 排查顺序
#    a) lspci 无桥          -> 供电/PCIE 链路 (pcie.md 5 节全套)
#    b) lspci 有但无 sdX    -> CONFIG_SATA_AHCI / BLK_DEV_SD
#    c) 识别慢/降速         -> ASW3810 sel 极性 (量开关脚) / lane 数
#    d) 多盘丢盘            -> 上行带宽 (num-lanes) / 桥供电 2.5V 轨
```
