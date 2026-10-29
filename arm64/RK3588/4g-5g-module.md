# 4G/5G 模组

　　USB 型 (EC20/EM05, QMI/MBIM) 与 PCIe 型 (RM520N) 模组接入, 附通话音频 (i2s1 + bt_sco) 配置。

## 1. RK3588 接入 4G/5G 模组的架构

　　模组 (Quectel EC20/EM05/RM500 等, Fibocom L610/NL952 等) 是标准
USB 或 PCIe 设备, 主板侧只做三件事:

```
┌─ 供电:   模组 3.8V 电源 + 使能脚 (regulator-fixed, 峰值电流大)
├─ 数据:   USB2.0 口 (最常见) 或 PCIe x1 (部分 5G 模组)
└─ 音频:   通话语音走 i2s1_8ch + bt_sco 声卡通路 (可选, 需模组支持模拟音频)
```

- **USB 型模组 (绝大多数 4G 和多数 5G)**: 设备树无模组专属节点,
  就是 USB host 口 + 供电; 内核要开 option (AT 口) / qmi_wwan / cdc_mbim,
  USB host 控制器 (EHCI/OHCI + u2phy) 必须使能, 完整配置见 2.2 第 2 段
- **PCIe 型模组 (部分 5G, 如 RM520N PCIe 版)**: 走 pcie2x1lN,
  控制器 + PHY + 模组电源完整配置见 3.2
- 通话音频与 BT SCO 共用同一套声卡结构 (bt_sco codec + i2s1_8ch),
  见 sound-card.md 第 5 节
- Firefly SDK 无拨号工具包 (buildroot 只有 modem-manager), quectel-CM
  等需自行移植; 内核侧网络通道配置见 1.2

### 1.1 板间布局速查

| 板 | 电源使能 | 电压 | 数据通路 | 通话音频 |
|---|---|---|---|---|
| itx-3588j | PCA9555 IO0_0 | 3.8V | pcie2x1l1 (combphy2_psu) | i2s1m0 sdi0/sdo0 |
| aio-3588q | PCA9555 IO0_0 | 板上默认 | (USB/HUB, 未显式配) | i2s1m0 sdi0/sdo0 |
| aio-3588sjd4 | PCA9555 IO1_4 | 板上默认 | (USB, 未显式配) | 无 |
| 自研板建议 | GPIO 或 PCA9555 | 3.8V (峰值 2A+) | USB 优先 | 按需 |

### 1.2 内核配置 (拨号网络通道)

```
# rockchip_linux_defconfig 已开:
CONFIG_USB_SERIAL=y
CONFIG_USB_SERIAL_OPTION=y        # AT 命令口 (ttyUSB0-3)
# CONFIG_PPP is not set           # 注意: PPP 未开, pppd 拨号不可用!
CONFIG_USB_EHCI_HCD=y             # USB2 host 控制器 (模组数据口)
CONFIG_USB_OHCI_HCD=y             # 全速兜底
CONFIG_PHY_ROCKCHIP_INNO_USB2=y   # u2phy (USB2 PHY)
CONFIG_PCIE_DW_ROCKCHIP=y         # PCIe 控制器 (PCIe 型模组)
CONFIG_PHY_ROCKCHIP_NANENG_COMBO_PHY=y  # combphy (PCIe2.0 PHY)

# firefly-linux.config 补开 (网络数据通道):
CONFIG_USB_USBNET=y
CONFIG_USB_NET_QMI_WWAN=y         # QMI 模组 (EC2x/EM05/RM5xx Q 口)
CONFIG_USB_NET_CDC_MBIM=y         # MBIM 模组 (多数 5G)
```

　　按模组协议再补 (menuconfig 自查): cdc_ether (ECM 模组/RNDIS)、
cdc_ncm。走 pppd 拨号的老方案需开 CONFIG_PPP 全家桶, 6.12 defconfig
没开, 要么补配置要么改用 QMI/MBIM 网卡通道 (推荐)。

## 2. 方式一: USB 型 4G 模组 (最常见)

### 2.1 硬件连接

```
4G 模组 (EC20/EM05 类, USB 通路):
  模组 USB D+/D- ====> USB2.0 host 口任一 (u2phy2 或 u2phy3,
                         MiniPCIe 座子的 USB 引脚 36/38)
  模组供电 3.8V  ====> vcc_4g (regulator-fixed), 峰值电流按模组 2A 留量
  PWR_EN 使能    ====> GPIO 或 PCA9555 IO (高有效)
  RESET_N (可选) ====> GPIO (异常恢复用, 不接也可)
  SIM 座         ====> 模组 USIM 引脚 (纯硬件)
```

### 2.2 设备树配置

　　模组本身不需要专属节点, 配两块: 模组供电 + USB host 控制器 (后者
很多人漏配, 模组插上枚举不到十有八九是这里)。

**1) 模组供电 3.8V:**

```
/ {
	vcc_4g: vcc-4g {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc_4g";
		regulator-min-microvolt = <3800000>;
		regulator-max-microvolt = <3800000>;
		regulator-boot-on;
		regulator-always-on;
		enable-active-high;
		gpio = <&gpio0 RK_PC6 GPIO_ACTIVE_HIGH>;   // PWR_EN, 换成自己的脚
		vin-supply = <&vcc5v0_sys>;                // 上级电源
		regulator-state-mem {
			regulator-off-in-suspend;          // 休眠断模组电 (按需)
		};
	};
};
```

**2) USB host 控制器 (以模组接 USB2.0 口 1 / u2phy2 为例; EHCI 高速
+ OHCI 全速成对出现, 都要使能):**

```
/ {
	/* USB 口 VBUS 5V 供电 (给模组/座子供电, 常供无 GPIO 也可) */
	vcc5v0_usb20_host0: vcc5v0-usb20-host0 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc5v0_usb20_host0";
		regulator-boot-on;
		regulator-always-on;
		regulator-min-microvolt = <5000000>;
		regulator-max-microvolt = <5000000>;
		enable-active-high;
		vin-supply = <&vcc5v0_usb>;      // 上级 5V 总电源
		// 有独立使能脚时加: gpio = <&gpioX RK_PXX GPIO_ACTIVE_HIGH>;
	};
};

&usb_host0_ehci {
	status = "okay";
};

&usb_host0_ohci {
	status = "okay";
};

&u2phy2 {
	status = "okay";
};

&u2phy2_host {
	status = "okay";
	phy-supply = <&vcc5v0_usb20_host0>;   // VBUS 供电关联
};
```

　　模组接 USB2.0 口 2 时对称换成 usb_host1_ehci/ohci + u2phy3/u2phy3_host;
但注意 u2phy3 是 USB3.0 口 (usbhost_dwc3_0) 的 USB2 伴生 PHY, 板上
有 USB3 A 口时两者互斥 (选一个用, 见各板实际布局)。

　　若模组接在 MiniPCIe 座且座子有独立供电使能, 同样用 regulator-fixed
写一个挂在座子 3.3V/3.8V 上。

### 2.3 验证测试

```
# 1. USB 枚举 (Quectel=2c7c, Fibocom=2cb7, SIMCom=1e0e)
lsusb | grep -i -E "2c7c|2cb7|1e0e"
# EC20: 2c7c:0125; EM05: 2c7c:030d (按模组)

# 2. 串口 (option 驱动)
dmesg | grep -i -E "option|GSM modem|ttyUSB"
ls /dev/ttyUSB*                    # 通常 3-4 个, ttyUSB2/3 是 AT 口

# 3. 网络通道 (qmi_wwan/cdc_mbim 生效)
dmesg | grep -i -E "qmi_wwan|cdc_mbim|wwan"
ls /sys/class/wwan/                # wwan0 (QMI/MBIM 口)
ip link                            # usb0/wwan0 网卡

# 4. AT 通道测试
microcom -t 5000 /dev/ttyUSB2      # 或 cat/echo
AT
OK
AT+CPIN?                           # SIM 状态 READY
AT+CSQ                             # 信号强度

# 5. 拨号 (QMI 模组, quectel-CM, 需自行移植到 buildroot)
quectel-CM -s cmnet &
udhcpc -i usb0                     # 若 CM 不自带 DHCP

# MBIM 模组:
mbimcli -d /dev/cdc-wdm0 -p --basic-connect-connect=... # 或 modem-manager
nmcli connection add type gsm ifname cdc-wdm0 con-name 4g
nmcli connection up 4g

# 常见问题:
# 1. lsusb 无模组: 供电不足 (3.8V 峰值电流, 电感/DCDC 选型) 或 PWR_EN 没拉高
# 2. 枚举成功但无 ttyUSB: CONFIG_USB_SERIAL_OPTION 没开,
#    或模组 PID 不在 option 白名单 --- echo "2c7c 0125" >
#    /sys/bus/usb-serial/drivers/option1/new_id 临时验证
# 3. 有 ttyUSB 无 wwan0/usb0 网卡: qmi_wwan/cdc_mbim 没开 (firefly-linux.config)
# 4. PPP 拨号失败: defconfig 里 PPP 没开, 6.12 上推荐 QMI/MBIM 通道
# 5. 温度上升后掉线: 模组过温, 检查散热和供电余量
# 6. 休眠唤醒后模组失联: regulator-state-mem 断电后重新枚举需时间,
#    唤醒后等 5-10s, 或改 regulator-on-in-suspend
```

## 3. 方式二: PCIe 型 4G/5G 模组

　　参考板: itx-3588j (FF_4G_5G_MODULE)。

　　部分 5G 模组 (RM520N 等 PCIe 版) 走 PCIe x1。itx 的模组座在
pcie2x1l1 上, PHY 是 combphy2_psu (与 USB3 host3/SATA2 三选一复用,
见引脚冲突速查表)。

### 3.1 硬件连接

```
5G 模组 (PCIe 通路, itx-3588j):
  PCIe 差分对   ====> pcie2x1l1 (fe190000, RK3588S 无此控制器则换路)
  PHY           ====> combphy2_psu
  模组供电 3.8V ====> vcc3v8_4g, 使能 PCA9555 IO0_0 (4G_PWR_EN),
                      输入 vcc12v_dcin
```

### 3.2 设备树配置 (完整可复制)

```
/ {
	vcc3v8_4g: vcc3v8-4g {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v8_4g";
		regulator-min-microvolt = <3800000>;
		regulator-max-microvolt = <3800000>;
		regulator-boot-on;
		regulator-always-on;
		enable-active-high;
		gpio = <&pca9555 PCA_IO0_0 GPIO_ACTIVE_HIGH>;   // 4G_PWR_EN
		vin-supply = <&vcc12v_dcin>;
	};
};

&combphy2_psu {
	status = "okay";                 // pcie2x1l1 的 PHY
};

&pcie2x1l1 {
	status = "okay";
	vpcie3v3-supply = <&vcc3v8_4g>;  // 模组电源挂到 PCIe 电源
	// itx 原厂 dts 只有 status = "okay" (模组复位由模组电路自理);
	// 自研板建议显式接管复位 (引脚按自己原理图):
	// reset-gpios = <&gpioX RK_PXX GPIO_ACTIVE_HIGH>;
	// rockchip,perst-inactive-ms = <500>;   // 模组上电慢, 加大复位前等待
};
```

　　无 PCA9555 的自研板把 gpio 换成普通 GPIO。sjd4 板电源使能脚是
PCA9555 IO1_4 (节点名 vcc_4g_pwren), 结构相同。

　　控制器驱动与 PHY 驱动 (defconfig 已开): CONFIG_PCIE_DW_ROCKCHIP=y +
CONFIG_PHY_ROCKCHIP_NANENG_COMBO_PHY=y, 无需额外内核配置。

　　注意 combphy2_psu 三选一: 本模组座 / USB3.0 A 口 (usbhost3_0) /
SATA2, 同一时刻只能给一个用 (板上同时要 USB3 口和 4G 模组时, 模组改走
USB 型方式一, 或换用其他 pcie2x1lN 路由)。

### 3.3 验证测试

```
# PCIe 枚举
lspci | grep -i -E "2c7c|2cb7|wireless|network"
# RM520N: 2c7c:0801 (PCIe)

# MHI 通道 (PCIe 5G 模组走 MHI, 内核需 CONFIG_MHI_BUS + 模组驱动)
dmesg | grep -i -E "mhi|pci.*quectel"
ls /dev/mhi*                      # MHI 通道设备

# 后续 AT/数据通道同方式一 (PCIe 版模组的 AT 口在 /dev/mhi* 或 ttyUSB)

# 常见问题:
# 1. lspci 扫不到: combphy2_psu 归属冲突 (USB3/SATA 占了),
#    见 pcie 模块复用矩阵
# 2. 扫到但 MHI 不起: CONFIG_MHI_BUS 及模组 MHI 驱动未开,
#    PCIe 5G 依赖的 mhi_pci 通用驱动按模组选配
# 3. 上电时序: 模组 PWR_EN 到 PCIe link up 可达 10s,
#    pcie reset 延时不足会 link 不上
```

## 4. 方式三: 通话音频 (i2s1_8ch + bt_sco 声卡)

　　参考板: aio-3588q / itx-3588j。

　　模组的模拟通话音频 (PCM/I2S) 接到 i2s1_8ch, 复用 BT SCO 声卡结构。
q 板/itx 板的 FF_4G_5G_MODULE 都带这段。

### 4.1 硬件连接

```
模组 PCM/I2S 音频 (q/itx 板, i2s1m0 组, 引脚已从 pinctrl 核实):
  I2S SCLK/BCLK ====> i2s1m0_sclk = GPIO4_A1
  I2S LRCK/FS   ====> i2s1m0_lrck = GPIO4_A2
  模组 -> 主控  ====> i2s1m0_sdi0 = GPIO4_A5
  主控 -> 模组  ====> i2s1m0_sdo0 = GPIO4_B1
```

**与 SG 板 BT SCO 的差异**: SG 板 wireless BT 走 i2s1m0_sdi2
(GPIO4_A7)/sdo3 (GPIO4_B4), 4G 模组走 sdi0 (GPIO4_A5)/sdo0
(GPIO4_B1) --- 同一 i2s1 控制器不同 slot 引脚, 按硬件接线选组,
同一时刻只能用一路。

### 4.2 设备树配置 (完整可复制)

```
/ {
	/* codec 节点: 复用 BT SCO 声卡的通用 codec */
	bt_sco: bt-sco {
		status = "okay";
		compatible = "delta,dfbmcs320";
		#sound-dai-cells = <1>;
	};

	bt_sound: bt-sound {
		status = "okay";
		compatible = "simple-audio-card";
		simple-audio-card,format = "dsp_a";
		simple-audio-card,bitclock-inversion = <0>;
		simple-audio-card,mclk-fs = <256>;
		simple-audio-card,name = "rockchip,bt";
		simple-audio-card,cpu {
			sound-dai = <&i2s1_8ch>;
		};
		simple-audio-card,codec {
			sound-dai = <&bt_sco 1>;
		};
	};
};

&i2s1_8ch {
	status = "okay";
	pinctrl-0 = <&i2s1m0_lrck &i2s1m0_sclk &i2s1m0_sdi0 &i2s1m0_sdo0>;
	rockchip,bclk-fs = <32>;
};
```

　　供电部分 (vcc_4g / vcc3v8_4g) 见方式一/二, 与音频段同开。

### 4.3 验证测试

```
# 声卡注册
cat /proc/asound/cards            # 应有 rockchip,bt
aplay -l | grep bt

# PCM 通路 (模组 AT 口开通话后测)
# ATD10086; 拨号后:
arecord -D hw:rockchipbt -f S16_LE -r 8000 -c 1 /tmp/dl.wav   # 下行
aplay  -D hw:rockchipbt -f S16_LE -r 8000 -c 1 /tmp/ul.wav   # 上行放音

# 常见问题:
# 1. 无 rockchip,bt 卡: bt_sco/bt_sound 节点与 i2s1_8ch 使能缺一
# 2. 有卡但无声: bclk-fs 与模组 PCM 配置不符 (多数模组 8k/16k,
#    主从模式要对: 模组做从机时 sclk/lrck 由主控供)
# 3. 与 BT SCO 冲突: i2s1 同时接 BT 和 4G 时只能用一个
#    (引脚组 sdi0/sdo0 vs sdi2/sdo3 别混写)
```

## 5. 模块间引脚冲突速查

| 资源 | 模块 A | 模块 B |
|---|---|---|
| combphy2_psu | pcie2x1l1 (PCIe 5G 模组) | USB3 host3 / SATA2 |
| i2s1_8ch (sdi0/sdo0) | 4G 模组通话音频 | (BT SCO 若走 sdi2/sdo3 可共存控制器, 不能同时用) |
| PCA9555 IO0_0 | 4G_PWR_EN (itx/q) | (q 板无冲突, 按板核对) |
