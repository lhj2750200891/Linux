# WiFi/BT

　　K3 平台无线适配笔记: WiFi 走 PCIe (M.2 模组自动枚举), BT 走 USB 或由
rfkill 管控开关。以 Firefly AIBOX-PRO-K3 (WiFi 经 ASM1182e 扩展) /
itx-k3l (WiFi 直挂 pcie3_rc + BT 走 USB2.0) 为参考板。K3 参考板**无
SDIO WiFi** 方案 (RK3588 的 AIC8800/SDIO 组合在此无对应)。

## 1. 原理

### 1.1 WiFi: PCIe M.2 模组, 设备树不写芯片节点

　　两块参考板的 WiFi 都是 **PCIe M.2 模组** (RTL8852BE / AP 类 2230 卡),
设备树只配置: RC 控制器使能 + 模组供电 regulator + (可选) restricted DMA
池。**没有任何 WiFi 芯片节点** — PCIe 枚举自动匹配模组驱动, 换卡只换内核
配置里的驱动。

| 参考板 | WiFi 挂法 | 供电 | 备注 |
|---|---|---|---|
| AIBOX-PRO (FF_ASM1182e_PCIE0_WIFI) | pcie3_rc (phy4, Gen2 1-lane) → ASM1182e 扩展 | vcc3v3_wifi (GPIO99) | restricted-dma-pool 32MB + clkreq pad107 |
| itx-k3l (FF_WIFI_BT) | pcie3_rc 直挂 (phy4, 1-lane) | wifi_3v3 (GPIO38) | pcie3_2_cfg 基座组 (perst124/wake125/clkreq126, func3) |

### 1.2 BT: USB 接口 + rfkill 开关

　　参考板 BT 都走 **USB 总线** (模组 USB BT 通道), 设备树层面只有:

- USB 控制器使能 (itx 把 usb3_portb 降级为纯 USB2.0 口专供 BT, 见 4.2);
- `rfkill-gpio` 节点做蓝牙使能开关 (shutdown-gpios 接模组 BT_REG_ON/
  BT_DISABLE 脚), 用户态 `rfkill block/unblock bluetooth` 控制。

### 1.3 rfkill-gpio 框架

　　`net/rfkill/rfkill-gpio.c` (CONFIG_RFKILL_GPIO, k3_defconfig 已 =y),
compatible "rfkill-gpio": 把一个 GPIO 包装成 rfkill 开关设备, 出现在
`/sys/class/rfkill/`。两个关键属性:

- `radio-type`: "wlan" / "bluetooth", 决定 rfkill 类型 (用户态按类型批量
  block/unblock)。
- `shutdown-gpios`: 使能/禁止脚, rfkill unblock = 释放模组, block = 拉住。

## 2. 硬件连接

### 2.1 参考板信号总表

| 参考板 | 信号 | GPIO | IO 域 | 电气 |
|---|---|---|---|---|
| AIBOX-PRO | WiFi 供电 wifi_pwr_en | GPIO99 | - | 高有效, 100ms 延时 |
| AIBOX-PRO | WLAN disable | GPIO127 | 1.8V | bias-pull-down, DS25 (低 = 模组使能, ACTIVE_LOW) |
| AIBOX-PRO | BT disable | GPIO73 | 3.3V | bias-pull-down, DS38 |
| itx-k3l | WiFi 供电 | GPIO38 | - | 高有效, vin=vcc3v3_sys |
| itx-k3l | WLAN disable | pca9555 (I2C 扩展) PCA_IO1_6 | - | GPIO 扩展器, 高有效 |
| itx-k3l | BT disable | pca9555 PCA_IO1_7 | - | 同上 |

接线核对要点:

- M.2 E-key 座: PCIe 差分对 + USB2.0 D+/D- + BT/WLAN 控制脚全部在座子上,
  模组一插全通。
- disable 脚极性注意: AIBOX-PRO 用 `GPIO_ACTIVE_LOW` (拉低 = 模组工作),
  itx 扩展器脚用 `GPIO_ACTIVE_HIGH` — 按模组手册的 W_DISABLE/BT_REG_ON
  定义确定, 抄错则模组"永不上线"或"关不掉"。
- BT 走 USB 的模组 (如 RTL8852BE): USB 口必须给到模组的 USB D+/D-, 且该
  USB 通道 2.0 就够 (BT 3.0 Mbps 级)。

## 3. 内核配置

```
# k3_defconfig 已有:
CONFIG_RFKILL=y
CONFIG_RFKILL_GPIO=y               # rfkill-gpio 驱动
CONFIG_BT=m                        # BT 协议栈 (模块化)
CONFIG_BT_HCIBTUSB=m               # USB BT (HCI over USB) — BT 走 USB 用
CONFIG_BT_HCIUART=m                # UART BT (若走串口模组才需要)
CONFIG_BT_HCIBTSDIO=m              # SDIO BT (K3 参考板未用)

# WiFi 驱动按所插模组追加, 例如:
CONFIG_RTL8852BE=y                 # Realtek RTL8852BE (PCIe)
# 或 CONFIG_BRCMFMAC=y             # Broadcom AP6275P 类
```

　　WiFi 模组固件放 `/lib/firmware/` (rtl_bt/、brcm/ 等按驱动要求)。

## 4. 设备树配置

### 4.1 方式一: WiFi 经 ASM1182e + USB BT (AIBOX-PRO)

　　WiFi 部分即 pcie.md 4.3 的 WiFi 版 (pcie3_rc + restricted DMA 池 +
vcc3v3_wifi GPIO99), 此处不重复; 补 BT/rfkill 段:

```dts
/ {
	rfkill_wifi: rfkill-wifi {
		compatible = "rfkill-gpio";
		label = "rfkill-pcie-wlan";
		radio-type = "wlan";
		shutdown-gpios = <&gpio K3_GPIO(127) GPIO_ACTIVE_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&wifi_disable_cfg>;
		status = "okay";
	};

	rfkill_bt: rfkill-bt {
		compatible = "rfkill-gpio";
		label = "rfkill-usb-bt";
		radio-type = "bluetooth";
		shutdown-gpios = <&gpio K3_GPIO(73) GPIO_ACTIVE_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&bt_disable_cfg>;
		status = "okay";
	};
};

&pinctrl {
	wifi_disable_cfg: wifi-disable-cfg {
		wifi-disable-pins {
			pinmux = <K3_PADCONF(127, 0)>;
			bias-pull-down;      /* 默认拉低 = 模组使能 (ACTIVE_LOW) */
			drive-strength = <25>;
			power-source = <1800>;
		};
	};

	bt_disable_cfg: bt-disable-cfg {
		bt-disable-pins {
			pinmux = <K3_PADCONF(73, 0)>;
			bias-pull-down;
			drive-strength = <38>;
			power-source = <3300>;
		};
	};
};
```

　　BT 的 USB 通道: 模组 USB D+/D- 接到某路 USB host 口 (AIBOX-PRO 经板上
hub 到 USB 通道, 见 usb30.md 的 hub 拓扑), USB 控制器正常使能即可。

### 4.2 方式二: WiFi 直挂 pcie3_rc + BT 专用 USB2.0 口 (itx-k3l)

　　**亮点写法**: usb3_portb 删掉基座双 PHY 引用, 重配为纯 2.0 PHY —
SuperSpeed PHY 省下, 口作 BT/USB2 设备专用:

```dts
/ {
	wifi_3v3: wifi-3v3 {
		compatible = "regulator-fixed";
		regulator-name = "wifi_3v3";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio K3_GPIO(38) GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&wifi_pwr_en_cfg>;
		pinctrl-names = "default";
		vin-supply = <&vcc3v3_sys>;
		status = "okay";
	};

	rfkill_pcie_wlan: rfkill-pcie-wlan {
		compatible = "rfkill-gpio";
		label = "rfkill-pcie-wlan";
		radio-type = "wlan";
		shutdown-gpios = <&pca9555_ri2c1 PCA_IO1_6 GPIO_ACTIVE_HIGH>;
		status = "okay";
	};

	rfkill_m2_bt: rfkill-m2-bt {
		compatible = "rfkill-gpio";
		label = "rfkill-m2-bt";
		radio-type = "bluetooth";
		shutdown-gpios = <&pca9555_ri2c1 PCA_IO1_7 GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
};

/* WiFi: pcie3_rc 直挂 */
&phy4 { status = "okay"; };

&pcie3_rc {
	pinctrl-names = "default";
	pinctrl-0 = <&pcie3_2_cfg>;    /* 基座组: perst124/wake125/clkreq126, func3 */
	phys = <&phy4>;
	phy-names = "phy4";

	num-lanes = <1>;
	vpcie3v3-supply = <&wifi_3v3>;
	status = "okay";
};

/* BT: portb 降级 USB2-only */
&usb3_portb_u2phy { status = "okay"; };
&usb3_portb_u3phy { status = "disabled"; };

&usb3_portb {
	/* 先删基座预置的双 PHY 引用, 再按 2.0-only 重配 */
	/delete-property/ phys;
	/delete-property/ phy-names;
	maximum-speed = "high-speed";
	phys = <&usb3_portb_u2phy>;
	phy-names = "usb2-phy";
	reset-on-resume;
	status = "okay";
};
```

　　说明: `pca9555_ri2c1` 是 itx 板上 I2C GPIO 扩展器 (RCPU i2c1) 的
label, 自研板没有扩展器时换成普通 `<&gpio K3_GPIO(N) ...>`; PCA_IO1_6/7
来自扩展器驱动的 pin 宏。

### 4.3 属性速查与陷阱

| 属性 | 说明 |
|---|---|
| radio-type | wlan / bluetooth, rfkill 分类键 |
| shutdown-gpios | 极性按模组 W_DISABLE 定义; pull-down 默认态要配套想清楚 |
| vpcie3v3-supply | WiFi 模组 3V3; itx 直挂方式挂 wifi_3v3 |
| /delete-property/ phys | 覆盖式删基座属性的标准写法 (BT 专用口) |
| reset-on-resume | resume 时复位控制器, BT 掉线恢复用 |

陷阱清单:

- **极性写反**: rfkill "unblock 后模组不上线"多半是 shutdown-gpios 极性
  与模组定义相反; 量模组侧 W_DISABLE 电平验证。
- itx 的 rfkill 挂在 I2C 扩展器上, 扩展器节点 (pca9555) 必须先工作, 否则
  rfkill probe 失败 — 自研板无扩展器时用普通 GPIO。
- WiFi 模组驱动没编 (CONFIG_RTL8852BE 等不在 defconfig): lspci 能看到
  设备但 wlan0 不出现, dmesg 报 "Direct firmware load failed" 或无驱动
  probe。
- BT 走 USB 但 `CONFIG_BT_HCIBTUSB` 未开 (参考板是 =m, 记得装模块) 或
  rfkill 默认 block: `rfkill list` 全是 blocked 时 hci0 不会注册。
- usb3_portb 降级写法必须先 `/delete-property/ phys` — 直接覆盖会因属性
  重复合并报错。

## 5. 验证测试

```bash
# 1. PCIe 层: 模组枚举
lspci | grep -i network          # WiFi 模组应出现
dmesg | grep -iE "pcie.*link|wifi" | head

# 2. 网卡出现
ip link show                     # wlan0
nmcli device wifi list           # 扫描 (或 iw dev wlan0 scan)

# 3. rfkill 状态与开关
rfkill list                      # 两颗 (wlan + bluetooth) 与 DT label 对应
rfkill unblock all
rfkill block bluetooth && rfkill unblock bluetooth   # 开关切换, 量模组脚电平

# 4. BT: hci 出现与扫描
hciconfig -a                     # hci0 (USB 总线)
bluetoothctl power on ; scan on  # 扫到周围设备 = 全链路通
lsusb | grep -i bluetooth        # USB 层枚举 (0bda:xxxx 等)

# 5. 排查顺序
#    a) lspci 无模组       -> 供电/PCIE 链路 (pcie.md 5 节)
#    b) lspci 有但无 wlan0 -> 模组驱动 CONFIG + 固件
#    c) 无 hci0            -> HCIBTUSB + rfkill block 状态 + USB 口枚举
#    d) rfkill 设备缺失    -> dmesg | grep rfkill (GPIO probe 失败/扩展器未就绪)
```
