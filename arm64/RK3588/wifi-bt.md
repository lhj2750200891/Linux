# WiFi / BT

　　三种无线方式: PCIe+UART (AP6275P) / PCIe+USB BT (RTL8852BE) / SDIO+UART (AIC8800), 含 rkwifibt 启动脚本机制。

## 1. RK3588 WiFi/BT 总体架构

　　RK3588 本身不含无线, WiFi/BT 全部外接, 按总线分三大类:

| 总线 | WiFi | BT | 芯片/板 |
|---|---|---|---|
| PCIe + UART | PCIe WiFi (bcmdhd) | UART HCI (bcm) | AP6275P: AIO-3588SG / itx-3588j / q |
| PCIe + USB | PCIe WiFi (8852be.ko) | USB HCI (rtk_btusb.ko) | RTL8852BE: aio-3588jd4 |
| SDIO + UART | SDIO WiFi | UART HCI | AIC8800: aio-3588l-qua |

- WiFi 走 PCIe 或 SDIO; BT 数据走 UART **或 USB (RTL 系)**, BT SCO 语音走 I2S
- RTL8852BE 是组合卡: WiFi 走 PCIe (10ec:b852), **BT 走 USB (0bda:b852)**,
  两路接口都要连到模组, 少一路就少一半功能
- 驱动/固件/加载由 rkwifibt 框架 (external/rkwifibt) 提供:
  S36wifibt-init.sh → scripts/wifibt-init.sh → wifibt-util.sh 按芯片查表
- 通用内核配置 (defconfig 已开):
```
CONFIG_RFKILL=y
CONFIG_RFKILL_GPIO=y
CONFIG_BT=y
CONFIG_BT_HCIUART=y
CONFIG_BT_HCIUART_H4=y
CONFIG_BT_HCIUART_BCM=y         # Broadcom 芯片
```
```
# RTL8852BE 的 BT 走 USB, 必须关闭内核自带 btusb, 否则与 rtk_btusb 冲突!
# CONFIG_BT_HCIBTUSB is not set
```

　　芯片专属 (firefly-linux.config):
```
CONFIG_WIFI_BUILD_MODULE=y      # rkwifibt 模块化编译
CONFIG_AIC8800_WLAN_SUPPORT=m   # aic8800 (SDIO)
CONFIG_RTL8852BE=m              # RTL8852BE WiFi (PCIe)
```

## 2. rkwifibt 框架 (三种方式共用)

　　源码位置: external/rkwifibt
- drivers/ : wifi/bt 驱动源码 (bcmdhd, aic8800, realtek 等)
- firmware/ : 固件, 按芯片分目录, 安装到 /vendor/etc/firmware 或 /lib/firmware
- S36wifibt-init.sh : 开机服务入口
- scripts/wifibt-init.sh + wifibt-util.sh : 按芯片名查表选驱动/固件

　　查表要点 (wifibt-util.sh):
| 芯片 | WiFi VID:PID | WiFi 驱动 | BT 通路 |
|---|---|---|---|
| AP6275P | 14e4:449d | bcmdhd_pcie.ko | UART: brcm_patchram_plus1 下载 .hcd |
| RTL8852BE | 10ec:b852 | 8852be.ko | USB: rtk_btusb.ko + rtl8852bu_fw |
| AIC8800D80 | - | aic8800_fdrv.ko | UART: rtk_hciattach rtk_h5 |

　　BT 上下电与固件加载 (bcmdhd 系):
- BT_REG_ON 上电 → UART 发 HCI 命令 → brcm_patchram_plus1 下载 .hcd
- 脚本优先用 brcm_patchram_plus1 --enable_hci --no2bytes
  --use_baudrate_for_download --baudrate 1500000
- 6.12 上 hciattach bcm43xx 首条 HCI 命令会超时, 仅作兜底保留

　　Realtek 芯片的 BT 由 wifibt-init.sh 的 Realtek 分支分发
(scripts/wifibt-init.sh do_init_bt):
- WIFIBT_BT_TTY 有值 (设备树配了 BT UART 节点) → init_bt_rtk_uart:
  加载 hci_uart 模块后 `rtk_hciattach -n -s 115200 $TTY rtk_h5`
- WIFIBT_BT_TTY 为空 → init_bt_rtk_usb: 加载 rtk_btusb.ko,
  芯片枚举为 USB 设备 (RTL8852BE 的 BT 就是这条路, 0bda:b852)
- init_bt_rtk_usb 里若检测到 /sys/module/btusb 存在会直接报错退出:
  "Please disable CONFIG_BT_HCIBTUSB in kernel!" --- 内核必须关掉自带 btusb

　　rtk_btusb 驱动 (drivers/bluetooth_usb_driver/rtk_bt.c) 的 USB ID 表含
8852 系: `{ 0x0BDA, 0xB852, 0x8852, ..., "rtl8852bu_fw", "rtl8852bu_config" }`,
固件在 external/rkwifibt/firmware/realtek/RTL8852BE/ 下:

```
rtl8852be.ko            # WiFi (PCIe, 放 drivers 下随模块编)
rtl8852bu_fw            # BT 固件 (USB 口的 BT 用, bu=USB)
rtl8852bu_config        # BT 配置 (波特率/功能开关)
```

　　WIFIBT_BT_TTY 的取值逻辑 (wifibt-util.sh bt_tty()): 解析设备树
/sys/firmware/devicetree/base/pinctrl/wireless-bluetooth/ 下挂的 uartN
节点名, 推出 /dev/ttySN; 没配 UART 节点的卡 (RTL8852BE USB BT) 不需要它。

　　BT SCO 语音 (免提通话) 走 i2s1_8ch/bt_sco, 32K 时钟取自 hym8563
(见 rtc 模块), 声卡部分见声卡模块。

## 3. 方式一: PCIe WiFi + UART BT (AP6275P)

　　参考板: AIO-3588SG。

### 3.1 硬件连接

```
AP6275P 模组 (M.2 E key 座):
  PCIe 差分对 ====> pcie2x1l2 (fe1a0000), PHY combphy0_ps    WiFi 数据
  I2C 不用
  WL_REG_ON (WiFi 使能)  ====> GPIO0_C7 (高有效)
  WIFI host 中断 wake    ====> GPIO0_A0 (低有效, wlan 唤醒)
  BT_REG_ON (BT 使能)    ====> GPIO0_D0 (高有效)
  BT wake (BT 唤醒)      ====> GPIO0_C6 (高有效)
  BT wake_host (唤醒主控) ====> GPIO0_C5 (低有效)
  BT UART  ====> UART9_M2: RX=GPIO3_D4 TX=GPIO3_D5
                 CTS=GPIO3_D3 RTS=GPIO3_D2
  BT 32.768KHz ====> hym8563 (RTC 芯片输出, 无需 GPIO)
  PERST# ====> GPIO3_D1
  座 3.3V 电源使能 ====> GPIO1_D7 (vcc3v3_pcie20_1l2)
```

### 3.2 设备树配置

　　参考: rk3588-firefly-aio-3588sg.dtsi (FF_WIFIBT)

```
/* 1. WiFi 节点 + BT 控制节点 (wlan/bluetooth-platdata) */
/ {
	wireless_wlan: wireless-wlan {
		compatible = "wlan-platdata";
		wifi_chip_type = "ap6275p";                       // rkwifibt 查表用
		pinctrl-names = "default";
		pinctrl-0 = <&wifi_host_wake_irq>, <&wifi_poweren_gpio>;
		WIFI,host_wake-gpios = <&gpio0 RK_PA0 GPIO_ACTIVE_HIGH>;  // WIFI_HOST_WAKE
		WIFI,poweren-gpios   = <&gpio0 RK_PC7 GPIO_ACTIVE_HIGH>;  // WL_REG_ON
		status = "okay";
	};

	wireless_bluetooth: wireless-bluetooth {
		compatible = "bluetooth-platdata";
		clocks = <&hym8563>;                              // 32.768K 来自 RTC
		clock-names = "ext_clock";
		uart_rts-gpios = <&gpio3 RK_PD2 GPIO_ACTIVE_LOW>; // uart9 rts 脚
		pinctrl-names = "default", "rts_gpio";
		pinctrl-0 = <&uart9m2_rtsn>, <&bt_reset_gpio>,
		            <&bt_wake_gpio>, <&bt_irq_gpio>;
		pinctrl-1 = <&uart9_gpio>;                        // 休眠时 rts 切 GPIO
		BT,reset-gpios     = <&gpio0 RK_PD0 GPIO_ACTIVE_HIGH>;  // BT_REG_ON
		BT,wake-gpios      = <&gpio0 RK_PC6 GPIO_ACTIVE_HIGH>;  // BT_WAKE_APB
		BT,wake_host-gpios = <&gpio0 RK_PC5 GPIO_ACTIVE_HIGH>;  // BT_HOST_WAKE
		status = "okay";
	};
};

/* 2. BT UART (uart9, M2 复用: RX=GPIO3_D4 TX=GPIO3_D5) */
&uart9 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&uart9m2_xfer &uart9m2_ctsn>;
};

/* 3. pinctrl: WiFi/BT 控制脚 */
&pinctrl {
	wireless-wlan {
		wifi_host_wake_irq: wifi-host-wake-irq {
			rockchip,pins = <0 RK_PA0 RK_FUNC_GPIO &pcfg_pull_down>;
		};
		wifi_poweren_gpio: wifi-poweren-gpio {
			rockchip,pins = <0 RK_PC7 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};

	wireless-bluetooth {
		bt_reset_gpio: bt-reset-gpio {
			rockchip,pins = <0 RK_PD0 RK_FUNC_GPIO &pcfg_pull_none>;
		};
		bt_wake_gpio: bt-wake-gpio {
			rockchip,pins = <0 RK_PC6 RK_FUNC_GPIO &pcfg_pull_none>;
		};
		bt_irq_gpio: bt-irq-gpio {
			rockchip,pins = <0 RK_PC5 RK_FUNC_GPIO &pcfg_pull_none>;
		};
		uart9_gpio: uart9-gpio {
			rockchip,pins = <3 RK_PD2 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};

/* 4. PCIe 载体 (WiFi 数据走 PCIe, 控制器必须配!) */
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
	status = "okay";                 // pcie2x1l2 的 PHY (与 SATA0 互斥)
};

&pcie2x1l2 {
	status = "okay";
	reset-gpios = <&gpio3 RK_PD1 GPIO_ACTIVE_HIGH>;    // PERST#
	vpcie3v3-supply = <&vcc3v3_pcie20_1l2>;
	rockchip,skip-scan-in-resume;      // WiFi 场景: 休眠唤醒后不重扫描
};
```

　　内核配置: PCIe 驱动 defconfig 已开 (CONFIG_PCIE_DW_ROCKCHIP=y +
CONFIG_PHY_ROCKCHIP_NANENG_COMBO_PHY=y)。WiFi 驱动 bcmdhd 以模块加载
后 lspci 里能扫到 14e4:449d。

　　注意: combphy0_ps 与 SATA0 互斥 (板上同时有 SATA0 时 WiFi 座换路);
rockchip,skip-scan-in-resume 专用于 WiFi (接 SSD 等存储不要加)。

　　bcmdhd 驱动的固件路径 (rkwifibt 安装后):
/lib/firmware/broadcom/AP6275_PCIE/fw_bcm43752a2_pcie_ag.bin
/lib/firmware/broadcom/AP6275_PCIE/nvram_ap6275p.txt
BT 固件: /lib/firmware/broadcom/AP6275_PCIE/BCM4362A2.hcd

### 3.3 验证

　　见 6 节。

## 4. 方式二: PCIe WiFi + USB BT (RTL8852BE)

　　参考板: aio-3588jd4。

**RTL8852BE 是 PCIe+USB 组合卡**: WiFi 走 PCIe (10ec:b852, 8852be.ko),
**BT 走 USB** (0bda:b852, rtk_btusb.ko)。jd4 原厂 dtsi 只写了无线侧节点,
BT 靠 USB 枚举 + rkwifibt 脚本自动加载 rtk_btusb, **不需要 UART 节点,
但模组的 USB D+/D- 必须接到主控某路 USB host 口** (硬件不接 BT 就没)。

### 4.1 硬件连接

```
RTL8852BE 模组:
  PCIe 差分对   ====> pcie3x4 (fe160000)           WiFi 数据
  USB D+/D-     ====> 任一 USB2.0 host 口          BT 数据 (组合卡!)
  WIFI host 中断 wake ====> PCA9555 IO1_2 (高有效)
  WIFI disable (硬件禁用脚) ====> GPIO0_D3 (被 hog 恒拉低 = 保持模组常开)
```

### 4.2 设备树配置

　　参考: rk3588-firefly-aio-3588jd4.dtsi (FF_WIFI_RTL8852BE)

```
/* 1. WiFi 节点 */
/ {
	wireless_wlan: wireless-wlan {
		compatible = "wlan-platdata";
		wifi_chip_type = "rtl8852be";                  // rkwifibt 查表用
		WIFI,host_wake_irq = <&pca9555 PCA_IO1_2 GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
};
```

　　pinctrl 中 wifi_wdisable_gpio 被作为 GPIO hog 恒拉低
(禁用"硬件禁用脚", 模组保持常开):

```
&pinctrl {
	wifi-w-disable {
		wifi_wdisable_gpio: wifi-wdisable-gpio {
			gpio-hog;
			gpios = <RK_PD3 GPIO_ACTIVE_HIGH>;
			output-low;
			line-name = "wifi-wdisable";
		};
	};
};
```

　　WiFi 载体 pcie3x4 的完整配置 (jd4 原样: pcie3x2 被覆盖关掉,
模组电源 vcc3v3_pcie3x2_1 = PCA9555 IO0_4; 自研板直接用完整定义版):

```
/ {
	vcc3v3_pcie3x2_1: vcc3v3-pcie3x2-1 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_pcie3x2_1";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&pca9555 PCA_IO0_4 GPIO_ACTIVE_HIGH>;   // 模组电源使能
		startup-delay-us = <5000>;
		vin-supply = <&vcc12v_dcin>;
	};
};

&pcie3x2 {
	status = "disabled";     // jd4: 3x2 槽不用, 让路给 WiFi
};

&pcie3x4 {
	status = "okay";
	vpcie3v3-supply = <&vcc3v3_pcie3x2_1>;
};
```

　　自研板无 PCA9555 时把 gpio 换普通 GPIO; pcie3x4 的 PHY (pcie30phy)
用默认模式即可, lane 数由控制器按 link 协商。

　　BT 走 USB: **不需要任何 BT 专属设备树节点**。wifibt-init.sh Realtek
分支发现无 TTY 后自动走 init_bt_rtk_usb, 加载 rtk_btusb.ko, 按
USB ID 0bda:b852 匹配固件 rtl8852bu_fw。

　　内核配置注意 (关键坑):

```
# CONFIG_BT_HCIBTUSB is not set   # 必须关! 内核自带 btusb 会抢绑 USB BT,
                                  # 脚本检测到直接报错退出:
                                  # "Please disable CONFIG_BT_HCIBTUSB in kernel!"
CONFIG_RTL8852BE=m                # WiFi 驱动 (firefly-linux.config)
```

　　BT 固件 (rkwifibt 安装后): /lib/firmware/rtl8852bu_fw (+ rtl8852bu_config),
源目录 external/rkwifibt/firmware/realtek/RTL8852BE/ (bu = USB 口 BT)。

　　BT SCO 语音: RTL8852BE 的 USB BT 走 SCO over USB, 不需要 i2s1_8ch/bt_sco
声卡节点 (那是 UART BT 模组的接法)。

### 4.3 自研板 BT 走 UART 时的完整范本 (RTL 其他 UART 卡, 如 8852BU-VA)

　　若自研板选的 RTL 卡 BT 引出的是 UART 而非 USB, 除 wireless_wlan 外还要配
wireless_bluetooth + uartN (结构参考 q 板 AP6275P, 引脚换自己的):

```
/* 1. BT 电源/唤醒控制节点 (bluetooth-platdata) */
/ {
	wireless_bluetooth: wireless-bluetooth {
		status = "okay";
		compatible = "bluetooth-platdata";
		bt_port = "/dev/ttyS6";                 // BT 所在 UART
		clocks = <&hym8563>;                    // 32.768K 由 RTC 提供
		clock-names = "ext_clock";
		uart_rts-gpios = <&gpio1 RK_PA2 GPIO_ACTIVE_LOW>;
		pinctrl-names = "default", "rts_gpio";
		pinctrl-0 = <&uart6m1_rtsn>, <&bt_gpio>;
		pinctrl-1 = <&uart6_gpios>;
		BT,power-gpios     = <&gpio0 RK_PC6 GPIO_ACTIVE_HIGH>;   // BT_REG_ON
		BT,wake-gpios      = <&gpio0 RK_PC5 GPIO_ACTIVE_HIGH>;
		BT,wake_host-gpios = <&gpio0 RK_PA0 GPIO_ACTIVE_HIGH>;
	};
};

/* 2. BT UART (uart6, M1 复用: RX=GPIO1_A0 TX=GPIO1_A1 RTS=GPIO1_A2) */
&uart6 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&uart6m1_xfer &uart6m1_ctsn &uart6m1_rtsn>;
};

/* 3. pinctrl: BT 控制脚 + rts 切 GPIO 态 (休眠时保持电平用) */
&pinctrl {
	wireless-bluetooth {
		bt_gpio: bt-gpio {
			rockchip,pins =
				<0 RK_PC6 RK_FUNC_GPIO &pcfg_pull_none>,
				<0 RK_PC5 RK_FUNC_GPIO &pcfg_pull_none>,
				<0 RK_PA0 RK_FUNC_GPIO &pcfg_pull_none>;
		};
		uart6_gpios: uart6-gpios {
			rockchip,pins = <1 RK_PA2 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};
```

　　配了 BT UART 节点后, wifibt-init.sh Realtek 分支转走 init_bt_rtk_uart:
`rtk_hciattach -n -s 115200 /dev/ttyS6 rtk_h5`
(rtk_hciattach 在 rkwifibt/bin, hci_uart 驱动源码在
rkwifibt/drivers/bluetooth_uart_driver/)。此路同样要求关 CONFIG_BT_HCIBTUSB。

### 4.4 差异说明

- wifi_chip_type 写 "rtl8852be" → rkwifibt 加载 8852be.ko (WiFi)
- BT 通路判定 (wifibt-init.sh): 有 BT UART 节点 → rtk_hciattach (UART);
  无 → rtk_btusb.ko (USB)。RTL8852BE 原生 BT 就是 USB 口
- CONFIG_RTL8852BE=m 在 firefly-linux.config; CONFIG_BT_HCIBTUSB 必须关
- WiFi 固件随驱动; BT 固件 rtl8852bu_fw/rtl8852bu_config 在
  rkwifibt/firmware/realtek/RTL8852BE/

## 5. 方式三: SDIO WiFi + UART BT (AIC8800)

　　参考板: aio-3588l-qua。

### 5.1 硬件连接

```
AIC8800 模组:
  SDIO  ====> &sdio (mmc@fe2d0000), 4bit
  SDIO 复位/使能 (pwrseq) ====> GPIO3_A7 (低有效)
  BT UART ====> UART7_M1: RX=GPIO3_C1 TX=GPIO3_C0 RTS=GPIO3_C2 CTS=GPIO3_C3
  BT reset     ====> GPIO3_A6 (高有效)
  BT wake      ====> GPIO3_B0 (高有效)
  BT wake_host ====> GPIO3_B1 (高有效)
  WIFI host wake ====> GPIO3_B7 (高有效)
  BT port = /dev/ttyS7 (对应 uart7)
```

### 5.2 设备树配置

　　参考: rk3588-firefly-aio-3588l-qua-rk182x.dtsi

```
/* 1. SDIO 上电时序 (pwrseq) */
/ {
	sdio_pwrseq: sdio-pwrseq {
		compatible = "mmc-pwrseq-simple";
		clocks = <&hym8563>;                 // 32K
		clock-names = "ext_clock";
		reset-gpios = <&gpio3 RK_PA7 GPIO_ACTIVE_LOW>;    // 低有效复位
		post-power-on-delay-ms = <200>;      // 上电后等 200ms 再扫卡
	};

	keep_wifi_power_on: keep-wifi-power-on {  // WiFi 电源常开
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "keep_wifi_power_on";
		regulator-always-on;
		regulator-boot-on;
	};
};

/* 2. SDIO 控制器 */
&sdio {
	status = "okay";
	max-frequency = <150000000>;       // 150MHz
	bus-width = <4>;
	no-sd;                             // 只插 SDIO 设备, 无 SD 卡
	no-mmc;
	disable-wp;
	cap-sd-highspeed;
	cap-sdio-irq;                      // SDIO 中断休眠唤醒
	keep-power-in-suspend;             // 休眠不断电
	sd-uhs-sdr104;
	non-removable;
	mmc-pwrseq = <&sdio_pwrseq>;
	vmmc-supply = <&vcc3v3_sys>;
};

/* 3. WiFi 节点 */
/ {
	wireless_wlan: wireless-wlan {
		compatible = "wlan-platdata";
		wifi_chip_type = "aic8800";
		keep_wifi_power_on;                        // 电源常开 (不走 pwrseq 断电)
		pinctrl-names = "default";
		pinctrl-0 = <&wifi_host_wake_irq>;
		WIFI,host_wake-gpios = <&gpio3 RK_PB7 GPIO_ACTIVE_HIGH>;
		WIFI,host_wake_irq  = <&gpio3 RK_PB7 GPIO_ACTIVE_HIGH>;
		status = "okay";
		/* 使能脚已由 pwrseq 管理, 无需 poweren */
	};
};

/* 4. BT 控制节点 (bluetooth-platdata) + BT UART (uart7, M1 复用) */
	wireless_bluetooth: wireless-bluetooth {
		compatible = "bluetooth-platdata";
		bt_port = "/dev/ttyS7";                    // uart7 = ttyS7
		uart_rts-gpios = <&gpio3 RK_PC2 GPIO_ACTIVE_LOW>;   // UART7_RTSN_M1
		pinctrl-names = "default", "rts_gpio";
		pinctrl-0 = <&uart7m1_rtsn>, <&bt_reset_gpio>,
		            <&bt_wake_gpio>, <&bt_wake_host_gpio>;
		pinctrl-1 = <&uart7_rts_gpio>;             // 休眠时 rts 切 GPIO
		BT,reset-gpios     = <&gpio3 RK_PA6 GPIO_ACTIVE_HIGH>;  // BT_REG_ON
		BT,wake-gpios      = <&gpio3 RK_PB0 GPIO_ACTIVE_HIGH>;  // host->BT
		BT,wake_host-gpios = <&gpio3 RK_PB1 GPIO_ACTIVE_HIGH>;  // BT->host
		BT,wake_host_irq   = <&gpio3 RK_PB1 GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
};

&uart7 {
	status = "okay";
	pinctrl-names = "default";
	/* CTS 必接: 模组 RTS_N -> SoC CTS (GPIO3_C3), 否则流控不成立 HCI 发不出 */
	pinctrl-0 = <&uart7m1_xfer &uart7m1_ctsn>;
};

/* 5. pinctrl: WiFi/BT 控制脚 */
&pinctrl {
	wireless-wlan {
		wifi_host_wake_irq: wifi-host-wake-irq {
			rockchip,pins = <3 RK_PB7 RK_FUNC_GPIO &pcfg_pull_down>;
		};
	};

	wireless-bluetooth {
		bt_reset_gpio: bt-reset-gpio {
			rockchip,pins = <3 RK_PA6 RK_FUNC_GPIO &pcfg_pull_none>;
		};
		bt_wake_gpio: bt-wake-gpio {
			rockchip,pins = <3 RK_PB0 RK_FUNC_GPIO &pcfg_pull_up>;
		};
		bt_wake_host_gpio: bt-wake-host-gpio {
			rockchip,pins = <3 RK_PB1 RK_FUNC_GPIO &pcfg_pull_none>;
		};
		uart7_rts_gpio: uart7-rts-gpio {
			rockchip,pins = <3 RK_PC2 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};

BT 波特率/固件路径由 rkwifibt 脚本按 aic8800 查表决定,
aic8800 BT 走 rtk_hciattach 类协议 (非 bcm)。
```

### 5.3 差异说明

- SDIO 无法即插即用, 上电时序靠 sdio_pwrseq 保证 (先拉高复位→200ms→扫卡)
- aic8800 同时通过 CONFIG_AIC8800_WLAN_SUPPORT=m 编出 aic8800_fdrv.ko
- BT 固件在 rkwifibt/firmware/aic8800 目录
- aio-3588l-qua 板上 aic8800 没有独立 WiFi 使能脚, 由 pwrseq 统一管理

## 6. 验证测试

```
# 1. PCIe WiFi (方式一/二): 先看设备在位
lspci | grep -i -E "broadcom|realtek"
# AP6275P: 14e4:449d; RTL8852BE: 10ec:b852

# 2. SDIO WiFi (方式三): 看 mmc 扫卡
dmesg | grep -i -E "mmc|sdio"
# 应看到(fe2d0000.sdio) 扫描到 aic8800 (vendor 0x0131 等)

# 3. 驱动加载 (rkwifibt)
dmesg | grep -i -E "bcmdhd|8852be|aic8800|rkwifi"
lsmod | grep -E "bcmdhd|8852|aic"

# 4. 接口出现
ip link                            # wlan0 出现
iw dev wlan0 scan | grep SSID      # 扫描
iw dev wlan0 connect "SSID" key 0:PASSWD
udhcpc -i wlan0                    # 获取 IP

# 5. BT (UART 方式, AP6275P/AIC8800/RTL-UART 卡)
dmesg | grep -i -E "hci_uart|bluetooth|ttyS"
hciattach /dev/ttyS9 bcm43xx 1500000 flow   # AP6275P (脚本自动做)
hciconfig -a
hciconfig hci0 up
hcitool scan                       # 应扫到设备

# 5b. BT (USB 方式, RTL8852BE)
lsusb | grep 0bda:b852             # BT 应枚举为 USB 设备
dmesg | grep -i rtk_btusb          # rtk_btusb 绑定 + 固件下载日志
hciconfig hci0 up && hcitool scan

# 6. 电源/休眠
cat /sys/kernel/debug/gpio | grep -E "PC7|PD0"    # 使能脚状态
echo mem > /sys/power/state                       // 休眠唤醒后 WiFi/BT 应仍可用
rfkill list                                       // 查看/解除软硬阻塞

# 常见问题:
# 1. PCIe 设备扫不到: PCIE 复位脚/时钟脚没配对 (见 pcie 模块)
# 2. SDIO 扫不到卡: post-power-on-delay-ms 太短, 或 reset-gpios 极性错
# 3. bcmdhd 加载成功但 wlan0 无: nvram 缺失或 chip_type 不匹配
# 4. BT hciattach 超时: UART 波特率/flow 控制脚配错,
#    hciattach 命令对不上芯片协议 (bcm/rtk 要分清)
# 5. 休眠后 WiFi 掉线: 缺 keep-power-in-suspend 或 bcmdhd 没开 wow 手法,
#    官方固件不支持 wakeup 参数时用 host wake 脚本兜底
# 6. RTL8852BE 的 BT 枚举不到 (lsusb 无 0bda:b852): 模组 USB D+/D-
#    没接到主控 USB 口, 或该口 USB 控制器未使能 (见 usb20 模块)
# 7. rtk_btusb 加载即报错: 内核开了 CONFIG_BT_HCIBTUSB, 自带 btusb
#    抢绑了设备, 关掉重编 (脚本会提示 "Please disable ... in kernel!")
```

## 7. 实战复盘: ITX-3588J "蓝牙打不开" (2026-11-03 已修复验证)

现象: 开机后 hci0 能起来, 但开机 1~2 分钟后所有 HCI 命令 -110 超时
(0x0C1A/0x0C03/0x0401), 蓝牙彻底打不开; 厂测(linux-qa bluetooth-001)失败。

### 7.1 根因链 (四层叠加)

```
厂测 rfkill block bluetooth  (或 guardian 瞬态 block)
    ↓ systemd-rfkill 的 12s 事件窗恰好截到 blocked 态
/var/lib/systemd/rfkill/platform-wireless-bluetooth:bluetooth 被写成 "1\n"
    ↓ 下次开机 ~1-2min 后 systemd-rfkill.socket 被 /dev/rfkill 打开触发
守护进程回放 blocked 态 → rfkill0 硬 block → BT_REG_ON 拉低 → 芯片断电
    ↓ hci0 还注册着, 每条 HCI 命令超时
rfkill-bt.c 收到 block → hci_dev_do_poweroff → write_scan_enable/Reset 全 -110
    ↓
旧版 wifibt-init.sh 的 BT guardian 被 bash -e 静默杀死(任一命令失败即退),
彻底无人救治 → 蓝牙永久打不开
```

要点:
- AP6275P 固件在 RAM: **BT_REG_ON 任何一次掉电都会清掉固件**, 恢复必须重新
  patchram 下载(实测 4~8s, 不可能 2s 内完成)。
- systemd-rfkill 是 socket 激活的, 开机后任何 /dev/rfkill 打开都会唤醒它回放
  保存态; guardian 重初始化时的瞬态 block 正好喂给它存下来 → 跨重启毒化闭环。
- `#!/bin/bash -e` + guardian 循环体里无保护的失败命令 = guardian 静默死亡,
  这才是"永远打不开"的直接原因。

### 7.2 修复 (external/rkwifibt/scripts/wifibt-init.sh, 已同步 SDK)

1. **屏蔽毒源**: `systemctl mask systemd-rfkill.service systemd-rfkill.socket`,
   脚本里新增 `scrub_bt_rfkill_save`(init 成功后把保存的 BT 态改写回 "0\n"),
   双保险。
2. **guardian 重写为单循环**:
   - 外部 rfkill block (state != 1) = 有意关断 → **挂起不动手**(不 killall、
     不重初始化、不对抗), 否则会把厂测期间的 hci0 拆没;
   - 健康 = hci0 存在 && `hciconfig hci0` 含 UP && rfkill==1 (旧代码拿 state==0
     当健康, 反了);
   - hci0 DOWN 时先温柔 `hciconfig hci0 up`(毫秒级断电固件常幸存, <100ms 恢复),
     失败才全量重初始化(REG_ON bounce + 重下载), 并 debounce 1s 防止把
     bluetooth_switch_test 的 0.2s up/down 当故障;
   - 循环体全部 `|| true`, bash -e 杀不死。
3. **AMPAK patchram 时序两坑**:
   - hci0 在下载中途就注册, `wait_bt` 立刻返回 → guardian 把好端端的下载拆掉
     (旧版"永远在重连"churn 的机制); 必须等日志出现
     `Done setting line discpline`(patchram --enable_hci 后打, 注意拼写就是
     discpline)再认为下载完;
   - marker 后补丁段还要走 ldisc 传 1~3s (`--use_baudrate_for_download`),
     立刻 `hciconfig hci0 up` 会失败并又拆掉一次; 用 2s 步进重试 8 次。
   - `--patchram` 参数给目录必须带尾斜杠 `/lib/firmware/brcm/`, AMPAK 自动
     检测按 目录/文件 两种方式解析。
4. **fallback 顺序**: `brcm_patchram_plus1 --enable_hci --no2bytes
   --use_baudrate_for_download --tosleep 200000 --baudrate 1500000 --patchram
   $fw_dir/ $tty` 优先(AP6275P 上 hciattach bcm43xx 下载后首条命令必超时),
   hciattach 兜底。

### 7.3 厂测 (linux-qa bluetooth-001-check-and-scan.t)

测试自己 `rfkill block`+`unblock` 会真断电清固件, 旧版只 sleep 2 就查
hciconfig —— UART 蓝牙物理上不可能 2s 内恢复。已在测试中加 `bt_wait_exist`/
`bt_wait_ready` 轮询(预算 40s), ITX-3588J 实测 5/5 全过(含扫描发现 6 设备)。
任何 UART BT 板(各 AP6xxx/AIC 型号)同理。

### 7.4 验证结论 (ITX-3588J, 6.12.69)

- 冷开机: ~3s 内 hci0 UP, hcitool scan RC=0, 单 patchram 进程无 churn;
- rfkill block 3s 深断电 → unblock → guardian 全量重下载 → 15s 内 scan RC=0;
- 厂测 5 项全过; 手机能配对;
- 板上曾有的坑: 手动复现"断电后 patchram 卡在 proc_reset"是因为缺了
  do_init_bt 的 btwrite 写入(REG_ON bounce 后 `echo 1 >
  /proc/bluetooth/sleep/btwrite` 会把 RTS 从 GPIO 态切回 UART 态), 脚本完整
  路径无此问题。
- 板上部署: /usr/bin/wifibt-init.sh (备份 .bak-20261103), systemd-rfkill 已
  mask; 回滚: 还原备份 + `systemctl unmask systemd-rfkill.service
  systemd-rfkill.socket`。

### 7.5 复盘续: "重启后厂测仍不通过" (v6 → v13, 2026-11-03 下午)

用户重启板子后厂测再次失败 → 连做 4 次冷启动排障, 在 v6 之上又挖出 5 个
叠加 bug (脚本现为 v13, md5 86236eb1, 板上+SDK 均同步):

1. **killall 15 字符截断 (churn 元凶)**: killall 按内核 comm 匹配, comm 最长
   15 字符, `brcm_patchram_plus1`(19 字符)截成 `brcm_patchram_pl` → **永远
   杀不掉**。setsid 的 loader 活着, 新 patchram 与旧 loader 双写 ttyS6 →
   后续所有下载必烂 → guardian 无限 churn (fx.log 一小时涨 1.4 万行)。
   修复: `kill_bt_loaders()` = `pkill -9 -f 全命令行` + pgrep 校验循环。
2. **dispatch 后台化陷阱**: 脚本底部 `start_wifibt "$1" &` 让主脚本秒退:
   (a) systemd 立刻认为服务已结束; (b) `timeout 40 bash -x script` 形同
   虚设——后台子进程带着重定向继续写日志, "已结束"的 tail 是快照, 日志
   还在涨 (10228→13857 行才发现); (c) 服务重启时新旧实例叠着抢 tty。
   修复: start_wifibt 入口 flock 单例锁 (/var/run/.wifibt-init.lock)。
3. **rfkill block = 断电, 下载前必须校验**: 本板 rfkill block 直接切 BT 电源。
   带 block 启动的下载是"静默死亡": 芯片无电 → hci0 永不注册 → loader 卡
   proc_reset。A/B 实测: block 时 patchram 25s 无 hci0; unblock 后 2s UP。
   修复: do_init_bt 弹跳后强制 unblock_all; init_bt_brcm_uart 下载前等
   "state==1 且连续稳定 ~2s" (最多 20s)。
4. **combo 模组电源时序竞速 (重启偶发挂的原因)**: AP6275P WiFi/BT 共电,
   WLAN 驱动 (WLAN_RFKILL, poweren gpio) 开机 power-sequencing 会动共享
   电源 GPIO; BT 下载撞上就被切电 → patchram ~12s 自灭 → "Failed to init
   BT"。同脚本同固件, 有的 boot 8s 成功有的挂, 纯看竞速 (02:58 好/用户
   重启挂的原因)。修复: 3 的稳定窗兜住起步, 5 的 residue 处理兜住输了
   竞速后的自愈 (秒级)。
5. **guardian 分不清"残留 block"和"有意关断"**: v6 铁则 state!=1 就按住 →
   开机电源时序留下的 block 让 guardian 按住整场 boot, BT 死到不知何时有
   外部 actor 把 state 翻回 1 (实测 ~4 分钟)。修复: saw_unblocked 状态
   机——启动以来从未见过 1 = 开机残留 → 主动清 (清完走正常健康检查→
   重初始化); 见过 1→0 = 有意关断 (厂测) → 按住不动。

诊断手法 (实测有效):
- **patchlog mtime = patchram 启动探测器**: 脚本启动 loader 时 `>"$brcm_log"`
  截断即更新 mtime; mtime 冻结 = 本次 boot 从没启动过下载。
- bash -x + 后台 dispatch: tail 给的"结尾"只是快照, 先看日志还在不在涨。
- `grep -c "for i in"` 数 wait_bt 轮询规模, 估算 churn 速度。
- 抓现行靠 A/B: 同脚本手动 patchram, 只差 rfkill block/unblock。
- pgrep -f 会自匹配自己的命令行; pgrep -x 对 >15 字符进程名零匹配。

厂测环境注意 (linux-qa): 板上 /tmp 是 tmpfs, 重启即清 (qa 环境/脚本/备份
都要重传); 测试须 root 跑 (用例内部 sudo 无 TTY 会失败); /tmp/qa 布局:
.t 在包根目录 + `env.ini -> part/ITX-3588J.ini` + lib/。

v13 验证记录 (2026-11-03, 4 次冷启动):
- v11 boot: init 输了竞速, guardian 在厂测 unblock 后自愈 → 厂测 6/6——
  证明"测试 40s 轮询 + guardian 自愈"链路稳, 用户投诉场景已闭环;
- v13 boot (终版): 开机 8s "Successfully init BT", 零干预, hci0 UP,
  rfkill 稳定, 单 patchram; 厂测 6/6, 扫描 5 设备。
- 版本演进 md5: v6 9e9235ae → v8 fe33994a → v9 792d30a5 → v10 6ca89ca6 →
  v11 66b0a808 → v12 bcc8afb5 → v13 86236eb1。
- 旧版 btwrite 说明作废补充: 6.12 内核上该板 `/proc/bluetooth/sleep/btwrite`
  不存在, 弹跳实际全靠 rfkill (echo 0/1 > rfkill0/state)。

