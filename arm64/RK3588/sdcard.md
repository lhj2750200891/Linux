# SD 卡 / eMMC

　　TF 卡 (sdmmc) / SDIO WiFi (sdio) / eMMC (sdhci HS400ES) 三个独立控制器的配置全景。

## 1. RK3588 SD 控制器全景

| 控制器 | 地址 | 驱动 (compatible) | 引脚 | 用途 |
|---|---|---|---|---|
| sdmmc | fe2c0000 | rk3588-dw-mshc (dw_mci) | sdmmc_clk/cmd/det/bus4 (固定, 无复用) | TF 卡 |
| sdio  | fe2d0000 | rk3588-dw-mshc (dw_mci) | sdiom1_pins: CLK=GPIO3_A5 CMD=GPIO3_A4 D0-D3=GPIO3_A0/A1/A2/A3 | SDIO WiFi (AIC8800 等) |
| sdhci | fe2e0000 | rockchip,rk3588-dwcmshc | eMMC 专用 (BGA 引出) | eMMC (HS400 1.8V Enhanced Strobe) |

　　说明:
- 三个是**独立控制器**, 互不影响; TF 卡 (sdmmc) 和 SDIO WiFi (sdio)
  是两个东西, 不要混淆
- sdmmc 引脚硬件固定 (无 M0/M1 之分), sdio 有多组复用 (本 BSP 默认 M1)
- SDIO WiFi 常见配合: sdio (数据) + uart (BT HCI) + pwrseq (WL_REG_ON),
  见 wifi-bt.md 方式三

　　内核配置 (defconfig 已开):

```
CONFIG_MMC_DW=y
CONFIG_MMC_DW_ROCKCHIP=y        # sdmmc/sdio (dw_mci)
CONFIG_MMC_SDHCI_OF_DWCMSHC=y   # eMMC (sdhci)
```

　　(注意: base dtsi 的 sdhci 节点自带 `supports-cqe;`, Firefly 板级用
`/delete-property/supports-cqe;` 关掉, 原因见方式三。)

## 2. 方式一: TF 卡 (sdmmc)

　　参考板: AIO-3588SG。

### 2.1 硬件连接

```
TF 卡座:
  DAT0-3/CLK/CMD ====> sdmmc (fe2c0000), 4bit (硬件固定引脚, 无复用选项)
  卡电源 3.3V/1.8V (信号) ====> vccio_sd_s0 (PMIC rk806 可调, SDR104 切 1.8V)
  卡电源使能:
    SG 板: vcc3v3_sd_s0 = GPIO3_C6 (高有效)
    q 板:  PCA9555 IO1_5
    l-qua: GPIO1_D6
```

### 2.2 设备树配置 (SG 板完整版)

```
/* 1. 卡槽供电 */
/ {
	vcc3v3_sd_s0: vcc3v3-sd-s0 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_sd_s0";
		enable-active-high;
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		gpio = <&gpio3 RK_PC6 GPIO_ACTIVE_HIGH>;
		pinctrl-names = "default";
		pinctrl-0 = <&sd_pwr_en>;
		vin-supply = <&vcc_3v3_s3>;
		regulator-state-mem {
			regulator-off-in-suspend;      // 休眠断卡电
		};
	};
};

/* 2. 控制器 (基础项在 common dtsi, 自研板全量写) */
&sdmmc {
	status = "okay";
	max-frequency = <150000000>;        // 150MHz
	no-sdio;                           // 不要扫描 SDIO 设备
	no-mmc;                            // 不是 eMMC
	bus-width = <4>;
	cap-mmc-highspeed;
	cap-sd-highspeed;
	disable-wp;                         // 卡座无写保护检测
	sd-uhs-sdr104;                      // UHS-I SDR104 (需 vccio 可切 1.8V)
	vqmmc-supply = <&vccio_sd_s0>;      // 信号电平电源
	vmmc-supply = <&vcc3v3_sd_s0>;      // 卡电源 (SG 板)
};

/* 3. pinctrl */
&pinctrl {
	sd {
		sd_pwr_en: sd-pwr-en {
			rockchip,pins = <3 RK_PC6 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};
```

　　无独立供电控制的板 (如 itx) 可省 vmmc-supply 和电源节点, 只保留
vqmmc-supply。vccio_sd_s0 是 PMIC 的 PLDO5 (rk3588-rk806-single.dtsi
里 `vccio_sd_s0: PLDO_REG5`, 1.8-3.3V 可调), 经
rk3588-firefly-rk806-single.dtsi 链入, 不需自己写。

### 2.3 验证测试

```
# 扫卡
dmesg | grep -i -E "mmc|sdmmc"
# 应看到 fe2c0000.mmc 扫到 SD 卡, 列出容量/速率模式
# SDR104 生效: "sdmmc: new ultra high speed SDR104 SDHC card"

# 读写
mount /dev/mmcblk1p1 /mnt/sd        // 设备号看 dmesg (eMMC 占 mmcblk0 时 SD 是 mmcblk1)
dd if=/dev/mmcblk1 of=/dev/null bs=1M count=100 iflag=direct   // 读测

# 速率
cat /sys/kernel/debug/mmc1/clk      // 实际工作时钟
hdparm -t /dev/mmcblk1

# 常见问题:
# 1. 扫不到卡: 先量卡槽 3.3V (vmmc 使能脚), 再查 vccio_sd_s0 是否被引脚
#    复用冲突拉走
# 2. 只能 50MHz: sd-uhs-sdr104 需 vccio 切 1.8V, rk806 的 vccio_sd_s0
#    必须挂在 sdmmc 的 vqmmc 上才会自动切换
# 3. 读写不稳: 降 max-frequency 到 100000000 验证是否信号完整性问题
# 4. sdmmc 与 sdio (WiFi) 是两个控制器, 互不影响, 但 vccio 若共用需注意
```

## 3. 方式二: SDIO WiFi (sdio)

　　参考板: aio-3588l-qua (rk182x)。

### 3.1 硬件连接

```
WiFi 模组 (rk182x / AIC8800 类):
  SDIO CLK/CMD/D0-3 ====> sdio M1: CLK=GPIO3_A5 CMD=GPIO3_A4
                            D0-D3=GPIO3_A0/A1/A2/A3 (sdiom1_pins)
  WL_REG_ON         ====> GPIO3_A7 (pwrseq 复位脚, 低有效)
  BT HCI            ====> UART7 (BT 侧节点见 wifi-bt.md 方式三)
```

### 3.2 设备树配置

```
/* 1. 上电时序 (先拉 WL_REG_ON 再扫卡) */
/ {
	sdio_pwrseq: sdio-pwrseq {
		compatible = "mmc-pwrseq-simple";
		pinctrl-names = "default";
		pinctrl-0 = <&wifi_enable_h>;
		post-power-on-delay-ms = <200>;
		reset-gpios = <&gpio3 RK_PA7 GPIO_ACTIVE_LOW>;   /* WL_REG_ON */
		status = "okay";
	};
};

/* 2. 控制器 */
&sdio {
	status = "okay";
	max-frequency = <150000000>;
	no-sd;                             // 不扫 SD 卡 (纯 SDIO 设备)
	no-mmc;
	bus-width = <4>;
	disable-wp;
	cap-sd-highspeed;
	cap-sdio-irq;
	keep-power-in-suspend;             // 休眠保持供电 (WiFi 唤醒场景)
	mmc-pwrseq = <&sdio_pwrseq>;
	non-removable;                     // 焊死在板上, 无卡检测
	sd-uhs-sdr104;
	vmmc-supply = <&vcc3v3_sys>;
};
```

　　与 TF 卡的关键差异: no-sd (反向排除) / cap-sdio-irq / non-removable /
keep-power-in-suspend / mmc-pwrseq — 全是"焊接式 SDIO 设备"语义。

　　本节配完 SDIO 控制器侧, dmesg 应能扫到 SDIO 函数设备 (3.3 验证);
WiFi 网卡驱动加载/固件/BT UART 属 wifi-bt.md 方式三, 按需再配。

### 3.3 验证测试

```
dmesg | grep -i -E "sdio|mmc1"
# 应看到 mmc1 扫到 SDIO 函数: "mmc1: new ultra high speed SDR104 SDIO
# card at address 0001" + 厂商函数注册 (aic8800/rk182x)

ls /sys/bus/sdio/devices/          // SDIO 功能块
ip link                            // wifi 网口是否出现

# 常见问题:
# 1. 扫不到设备: pwrseq 没生效 (WL_REG_ON 未拉高), 示波器量 GPIO3_A7
# 2. 扫到但驱动不绑: 模组 SDIO VID/PID 不在驱动支持的表里,
#    对比 drivers/net/wireless/... 下该芯片的 sdio_device_id
# 3. 速率只有 25MHz: bus-width 不是 4 或模组不支持 SDR104
```

## 4. 方式三: eMMC (sdhci)

　　Firefly 全系板卡通用, 无板间差异。

### 4.1 硬件连接

```
eMMC (BGA 焊在板上, 引脚不外走, 无复用选项):
  8bit 数据 + CLK/CMD/RST ====> sdhci (fe2e0000), 控制器侧固定
  供电 VCC 3.3V (闪存核心) / VCCQ 1.8V (IO) ====> 板上 PMIC 常供
  时钟: CCLK_EMMC 200MHz / BCLK_EMMC 200MHz / TMCLK 24MHz
        (base dtsi assigned-clock 已配, 板级不用管)
```

### 4.2 设备树配置 (rk3588-firefly-common.dtsi 原样, 所有 Firefly 板共用)

```
&sdhci {
	status = "okay";
	bus-width = <8>;                        // 8bit DDR
	no-sdio;                                // 只跑 eMMC
	no-sd;
	non-removable;                          // 焊死, 无卡检测
	max-frequency = <200000000>;            // 200MHz
	mmc-hs400-1_8v;                         // HS400 1.8V
	mmc-hs400-enhanced-strobe;              // Enhanced Strobe (时钟从
	                                        // 卡侧 52M 独立时钟走)
	/delete-property/supports-cqe;          // 关 CQE (见下方说明)
	full-pwr-cycle-in-suspend;              // 休眠时完整断电流程
};
```

**/delete-property/supports-cqe 说明**: base dtsi (rk3588s.dtsi /
rk3588-base.dtsi) 的 sdhci 节点带 `supports-cqe;` (CQE = Command
Queue Engine, eMMC 5.1 命令队列)。Firefly 板级把它删掉 --- CQE 与
某些颗粒/IO 时序组合下有稳定性问题, 且 Rockchip 的分区工具链对
CQE 适配一般。自研板建议: 先照抄 Firefly 关掉, 系统稳定后想提
4K 随机性能再试着删掉这行 delete-property 对比压测。

### 4.3 验证测试

```
# 1. 扫卡与速率模式
dmesg | grep -i -E "sdhci|mmc0"
# HS400ES 生效应看到:
# "mmc0: new HS400 enhanced strobe MMC card at address 0001"

cat /sys/kernel/debug/mmc0/ios    # clock/bus_width/timing (hs400es)

# 2. 读写
dd if=/dev/mmcblk0 of=/dev/null bs=1M count=200 iflag=direct
hdparm -t /dev/mmcblk0

# 3. RPMB / boot 分区
ls /dev/mmcblk0boot* /dev/mmcblk0rpmb    # boot0/boot1/rpmb 出现即 eMMC
                                         // 标准分区正常

# 4. 常见问题:
# 1. 枚举失败 "switch to bus width 8 failed": VCCQ 1.8V 不稳或
#    mmc-hs400-1_8v 与颗粒不支持 --- 降到 mmc-hs200-1_8v 试
# 2. 高频读写 IO error: 先关 enhanced-strobe 再降 max-frequency
#    到 150000000 逐级排查信号完整性
# 3. CQE 开了之后随机 IO 崩: 回到 /delete-property/supports-cqe;
# 4. 分区: Rockchip 方案 eMMC 头部有 param 分区表 (uboot/trust/
#    boot...), 用 RKDevTool/upgrade_tool 写, 直接 fdisk 会破坏
#    loader 分区 --- 自研板首次烧写用 SDK 的分区表 (parameter.txt)
# 5. mmcblk 编号: eMMC/sdmmc 谁是 mmcblk0 由 probe 顺序定, 以
#    dmesg 为准, 脚本别写死设备号
```

## 5. 引脚冲突速查

| 资源 | 模块 A | 模块 B |
|---|---|---|
| GPIO3_A0/A4/A5.. (sdio M1) | SDIO WiFi | mipim1_camera0/2_clk 等复用 |
| vccio_sd_s0 | TF 卡 SDR104 | 引脚复用拉低电平者 |
| GPIO3_C6 (SG 板 vcc3v3_sd_s0) | TF 卡电源 | — (无冲突, 独占) |
