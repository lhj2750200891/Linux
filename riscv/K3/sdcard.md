# SD/eMMC

　　K3 平台 SD/eMMC 适配笔记: 3 个 k3-sdhci 控制器 (sdcard/sdio/emmc)
的板级配置, 含 itx SD 卡参考 (cd/供电/延迟调参) 与 eMMC 参考 (HS400
增强频闪)。K3 无独立 eMMC 控制器, 三路同驱动; SD 卡 IO 电压经
**RPMI regulator** (LGA PMIC) 供 — 这与 RK3588 的 vccio 体系完全不同。

## 1. 原理

### 1.1 控制器总表 (k3.dtsi 基座, 全部 disabled)

| 控制器 | 基址 | 中断 | 用途 | 引脚组 (基座) |
|---|---|---|---|---|
| sdcard | 0xd4280000 | saplic 99 | SD 卡 (4-bit) | mmc1_cfg + mmc1_cd_cfg / mmc1_uhs_cfg |
| sdio | 0xd4280800 | saplic 100 | SDIO 设备 (WiFi 等) | (K3 参考板未用, WiFi 走 PCIe) |
| emmc | 0xd4281000 | saplic 101 | eMMC (8-bit) | mmc2_cfg (pads 122-126 func1) |

- compatible = "spacemit,k3-sdhci", 驱动
  `drivers/mmc/host/sdhci-of-k1.c` (CONFIG_MMC_SDHCI_OF_K1,
  defconfig 已 =y, 含 SDHCI/PLTFM 基础) — **内核配置无需动**。
- 时钟名 core/io, SD 卡基座 clock-frequency 由板级覆盖
  (itx 写 204.8MHz)。

### 1.2 信号延迟调参 (类似 RK3588 的 io-domain 痛点)

　　itx SD 卡节点带 `spacemit,tx_delaycode = <0xc5>` — SD 高频时钟的
TX 相位延迟 (十六进制, 驱动直写控制器寄存器)。换卡座走线长度变了要
像 gmac delayline 一样重调: 起值抄参考板, 读出错时逐档加减。

### 1.3 IO 供电: RPMI regulator (LGA PMIC)

　　K3 参考板的电源树不在 Linux PMIC 驱动下, 而在 **RCPU 域的
rpmi_regulator** (k3-firefly-lga.dtsi, PMIC 经 RPMI mailbox 管理):
pvin/adcdcX/dcdcX/aldoX 全在里面, aldo1 (1.8-3.3V 可调, always-on)
作 SD 卡 vqmmc。自研板若沿用 LGA PMIC, 直接 `#include
"k3-firefly-lga.dtsi"` 风格抄 regulator 段 (FF_RPMI_LGA 宏)。

## 2. 硬件连接

| 信号 | SD 卡 (sdcard) | eMMC (emmc) | 说明 |
|---|---|---|---|
| 数据 D0-D3 | pad132-135 func0 (mmc1_cfg) | pad122-125 func1 (mmc2_cfg) | SD 4-bit / eMMC 8-bit |
| CMD | pad136 func0 | pad126 func1 | |
| CLK | 基座组内 (专用) | 同 | 不单独引出 |
| CD (卡检测) | **GPIO86**, 低 = 插入 | - (eMMC 无) | cd-gpios ACTIVE_LOW |
| D4-D7 (eMMC) | - | 专用 pad | 8-bit 总线, 不进 pinctrl 表 |
| VCC 3.3V | vcc3v3_sd (板级 regulator) | 板级常供 | vmmc-supply |
| VCCQ IO | aldo1 (RPMI PMIC, 1.8/3.3V 切换) | 1.8V 常供 | vqmmc-supply |

接线核对要点:

- **pad122-126 (mmc2) 三处冲突**: pad122 = 红色 LED (led.md GPIO122)、
  pad124/125/126 = pcie3_2_cfg 的 perst/wake/clkreq (func3) — eMMC
  (func1) 与这些功能二选一, 规划时先定 eMMC。
- SD 的 cd 脚极性: 参考板 GPIO86 低有效 (插卡拉低); 换卡座按其开关
  类型定, 抄反则"插卡无反应/拔卡仍识别"。
- SD 走线长的板子 vqmmc 若固定 3.3V 不支持 UHS, clock-frequency 降到
  50MHz 稳 (uhs pinctrl 组就不引用)。

## 3. 内核配置

```
# k3_defconfig 已有 (存储链全套已编, 无需补):
CONFIG_MMC_SDHCI=y
CONFIG_MMC_SDHCI_PLTFM=y
CONFIG_MMC_SDHCI_OF_K1=y           # spacemit,k3-sdhci 驱动
CONFIG_MMC_BLOCK=y / CONFIG_BLK_DEV_... 默认齐
```

## 4. 设备树配置

### 4.1 方式一: SD 卡 (itx FF_SDCARD 展开)

```dts
/* 前置: vcc3v3_sd (板级 regulator, 按你供电树) 与 aldo1 (RPMI PMIC,
 * 见 1.3 节) 已存在 */

&sdcard {
	pinctrl-names = "default", "uhs";
	pinctrl-0 = <&mmc1_cfg &mmc1_cd_cfg>;      /* 基座组: pads132-136 func0
	                                              + cd 脚组 */
	pinctrl-1 = <&mmc1_uhs_cfg &mmc1_cd_cfg>;  /* UHS 档 (电气覆写) */
	bus-width = <4>;
	wp-inverted;                               /* 写保护极性反转 */
	cd-gpios = <&gpio K3_GPIO(86) GPIO_ACTIVE_LOW>;
	vmmc-supply = <&vcc3v3_sd>;
	vqmmc-supply = <&aldo1>;
	no-mmc;                                    /* 该口只做 SD */
	no-sdio;
	clock-frequency = <204800000>;             /* UHS 档控制器时钟 */
	spacemit,tx_delaycode = <0xc5>;            /* TX 相位延迟, 走线变则重调 */
	status = "okay";
};
```

　　参考板另有第三态 pinctrl "debug" (mmc1_jtag_cfg), 调试用, 自研板
两态即可。

### 4.2 方式二: eMMC (k1-bananapi-f3 展开 + 基座组补全)

```dts
&emmc {
	pinctrl-names = "default";
	pinctrl-0 = <&mmc2_cfg>;           /* 基座组: pads122-126 func1 */
	bus-width = <8>;
	mmc-hs400-1_8v;
	mmc-hs400-enhanced-strobe;
	non-removable;
	no-sd;
	no-sdio;
	status = "okay";
};
```

　　注意 pad122-126 冲突 (2 节): 用 eMMC 就别再把 122 当 LED、124-126
当 pcie3。

### 4.3 方式三: SDIO (预留给 WiFi 类设备)

　　基座 sdio@0xd4280800 使能写法与 sdcard 同构 (pinctrl 用 sdio 对应
组, no-sd / no-mmc 限定)。**K3 参考板 WiFi 全走 PCIe, 无 SDIO 实装
参考** — 用前先确认你的模组接口。

### 4.4 属性速查与陷阱

| 属性 | 说明 |
|---|---|
| cd-gpios | 卡检测; 极性按卡座开关, 常见 ACTIVE_LOW |
| vmmc/vqmmc-supply | 卡电源/IO 电源; vqmmc 挂 RPMI regulator (aldo1) |
| clock-frequency | 控制器时钟; UHS 用 204.8MHz, 不稳降 50MHz |
| spacemit,tx_delaycode | TX 延迟 hex 值; 读错误率高时逐档调 |
| no-mmc/no-sdio/no-sd | 限定协议, 排除枚举歧义 |
| mmc-hs400-enhanced-strobe | eMMC HS400 ES; 时钟由控制器专门提供 |

陷阱清单:

- **vqmmc 悬空不写**: SD 卡以默认电平工作, UHS 档协商失败 (恒
  high-speed); 电压切换依赖 vqmmc regulator。
- tx_delaycode 抄别的板: 走线不同相位不同, 现象是挂载后随机 IO
  error — 按 dmesg mmc 报错微调。
- eMMC 与 LED/pcie3 的 pad 冲突 (2 节): 上电 LED 不亮或 pcie3 训练
  失败先查这里。
- rpmi_regulator 未使能时 aldo1 不存在, dts 引用编译报 undefined
  label — 用 LGA PMIC 板记得 include lga regulator 段。

## 5. 验证测试

```bash
# 1. 控制器 probe
dmesg | grep -iE "sdhci|mmc[0-9]" | head -15
ls /sys/class/mmc/

# 2. eMMC
ls /dev/mmcblk*                      # mmcblk1 (emmc) + boot0/1 分区
cat /sys/class/mmc-host/*/mmc_host/mmc1/*/name   # 器件名

# 3. SD 卡热插拔
#    插拔卡, dmesg -w 应见 card insert/remove
mount /dev/mmcblk0p1 /mnt && ls /mnt

# 4. 速率
cat /sys/class/mmc-host/*/mmc_host/mmc*/ios | grep -E "timing|clock"
dd if=/dev/mmcblk1 of=/dev/null bs=1M count=200   # HS400 应数百 MB/s

# 5. 排查顺序
#    a) 控制器不在    -> CONFIG_MMC_SDHCI_OF_K1 / 基座 status
#    b) SD 插卡无反应 -> cd-gpios 极性 (量 GPIO86)
#    c) UHS 失败回高速 -> vqmmc (aldo1) 未供/RPMI 未通
#    d) 随机 IO error -> tx_delaycode 重调
#    e) eMMC 无 D4-7  -> bus-width=8? pad 组用 mmc2_cfg
```
