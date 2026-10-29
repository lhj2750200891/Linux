# SATA

　　直连 SATA (combphy 与 USB3/PCIe 复用) 与 USB3 HUB 一扩四转 SATA (GL3321G, 需移植驱动)。

## 1. RK3588 SATA 控制器全景

| 控制器 | 地址 | PHY | 互斥 | Firefly 使用 |
|---|---|---|---|---|
| sata0 | fe210000 | combphy0_ps | pcie2x1l2 (M.2 复用) | roc-rk3588s-pc-sata/ext, itx-3588j |
| sata1 | fe220000 | combphy1_ps | pcie2x1l0, USB3 OTG1 | (Firefly 板均未用) |
| sata2 | fe230000 | combphy2_psu | pcie2x1l1 | roc-rk3588-rt |

　　内核配置:

```
CONFIG_SATA_AHCI=y
CONFIG_AHCI_DWC=y
CONFIG_SATA_AHCI_PLATFORM=y
```

　　注意:
- RK3588 每个原生 SATA 只支持 1 个口 (ports-implemented = <0x1>),
  多盘需求要走多控制器或 USB 一扩四方案
- combphy 为多路复用 PHY, 与 PCIe/USB3 互斥, 同一组只能选一个功能

## 2. 方式一: 直连 SATA0

　　参考板: roc-rk3588s-pc-sata / itx-3588j。

### 2.1 硬件连接

```
M.2 B key SATA SSD:
  3.3V 电源使能 ====> GPIO1_D7 (vcc3v3_sata0)
  itx-3588j 板: 电源使能 ====> PCA9555 IO1_2 (扩展 IO)

PHY: SATA0 与 PCIe2x1l2 (M.2 E key WiFi) 共享 combphy0_ps, 硬件二选一
```

### 2.2 设备树配置

```
/ {
	vcc3v3_sata0: vcc3v3-sata0 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_sata0";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		regulator-boot-on;
		enable-active-high;
		gpio = <&gpio1 RK_PD7 GPIO_ACTIVE_HIGH>;
		startup-delay-us = <5000>;
		vin-supply = <&vcc12v_dcin>;
	};
};

&combphy0_ps {
	status = "okay";
};

&sata0 {
	status = "okay";
	target-supply = <&vcc3v3_sata0>;   // SATA 电源经此属性关联
};
```

　　注意:
- FF_SATA0 与 FF_PCIE2_1L2 宏互斥 (同一 M.2 槽复用), 板卡 dts 中
  二者只能定义其一
- itx-3588j 电源用 PCA9555 扩展 IO, 覆盖为:
  &vcc3v3_sata0 { gpio = <&pca9555 PCA_IO1_2 GPIO_ACTIVE_HIGH>; };

## 3. 方式二: 直连 SATA2

　　参考板: roc-rk3588-rt。

### 3.1 硬件连接

```
M.2 SATA SSD:
  3.3V 电源使能 ====> GPIO2_B5 (vcc3v3_sata2)

PHY: SATA2 与 PCIe2x1l1 共享 combphy2_psu, 硬件二选一
```

### 3.2 设备树配置

```
/ {
	vcc3v3_sata2: vcc3v3-sata2 {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_sata2";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		regulator-boot-on;
		enable-active-high;
		gpio = <&gpio2 RK_PB5 GPIO_ACTIVE_HIGH>;
		startup-delay-us = <5000>;
		vin-supply = <&vcc3v3_sys>;
	};
};

&combphy2_psu {
	status = "okay";
};

&sata2 {
	status = "okay";
	target-supply = <&vcc3v3_sata2>;
};
```

## 4. 方式三: USB3 一扩四转 SATA

　　参考板: aio-3588sjd4。

### 4.1 硬件拓扑 (非原生 SATA 控制器)

```
USB3.0 主机口 ====> GL33121 USB3 HUB (一扩四) ====> 4 x GL3321G USB转SATA桥 ====> 4 个 SATA 硬盘口

  HUB 复位   ====> PCA9555 IO0_6 (vcc_hub3_reset, 内核启动 2.5s 后复位)
  SATA 桥 3.0V 电源 ====> PCA9555 IO0_0 (vcc_3v0_sata)
  GL3321G 电源/复位 ====> PCA9555 IO1_5 (上电延时 500ms)
```

　　内核无需 SATA 设备树节点, 4 个盘通过 USB 枚举为 /dev/sda ~ /dev/sdd。

### 4.2 驱动移植 (瑞芯微原厂 SDK 无此驱动!)

　　Firefly 私有驱动共 2 个, 移植文件清单:
- drivers/regulator/fixed-firefly.c           (带 kernel-reset-ms 延时复位特性)
- drivers/regulator/Kconfig:  config REGULATOR_FIXED_VOLTAGE_FIREFLY
- drivers/regulator/Makefile: obj-$(CONFIG_REGULATOR_FIXED_VOLTAGE_FIREFLY) += fixed-firefly.o
- drivers/gpio/gpio-firefly-gl3321g.c         (GL3321G 上电时序)
- drivers/gpio/Kconfig:  config GPIO_FIREFLY_GL3321G
- drivers/gpio/Makefile: obj-$(CONFIG_GPIO_FIREFLY_GL3321G) += gpio-firefly-gl3321g.o

　　内核配置 (在 firefly-linux.config 片段中, 主 defconfig 没有):

```
CONFIG_REGULATOR_FIXED_VOLTAGE_FIREFLY=y
CONFIG_GPIO_FIREFLY_GL3321G=y
```

### 4.3 设备树配置

```
/ {
	/* USB3 HUB 复位, 内核启动后延时 2.5s 复位, 保证盘序稳定 */
	vcc_hub3_reset: vcc-hub3-reset {
		status = "okay";
		compatible = "regulator-fixed-firefly", "regulator-fixed-firefly-uboot";
		regulator-name = "vcc_hub3_reset";
		enable-active-high;
		enable-active-low-uboot;               // U-Boot 阶段低有效
		regulator-always-on;
		regulator-fixed-kernel-reset-ms = <2500>;   // 延时复位(毫秒)
		gpio = <&pca9555 PCA_IO0_6 GPIO_ACTIVE_HIGH>;
	};

	/* 4 个 GL3321G 桥芯片 3.0V 供电 */
	vcc_3v0_sata: vcc-3v0-sata-regulator {
		compatible = "regulator-fixed";
		regulator-name = "vcc_3v0_sata";
		regulator-always-on;
		enable-active-high;
		status = "okay";
		gpio = <&pca9555 PCA_IO0_0 GPIO_ACTIVE_HIGH>;
	};

	/* GL3321G 电源时序: 上电后延时 500ms */
	gl3321g: gl3321g-pwr-gpio {
		compatible = "firefly,gl3321g-gpio";
		firefly-mdelay = <500>;
		firefly-gl3321g-gpio = <&pca9555 PCA_IO1_5 GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
};
```

　　USB3 一扩四跑在 USB3 主机口 usbhost3_0 上, 控制器必须配 (jd4 的
VBUS 是常供无 GPIO):

```
/ {
	/* VBUS 5V (jd4 常供无 GPIO; 自研板有使能脚时加 gpio 属性) */
	vcc5v0_usb_host: vcc5v0-usb-host {
		status = "okay";
		compatible = "regulator-fixed";
		regulator-name = "vcc5v0_usb_host";
		enable-active-high;
		regulator-boot-on;
		regulator-always-on;
		regulator-min-microvolt = <5000000>;
		regulator-max-microvolt = <5000000>;
		vin-supply = <&vcc5v0_usb>;
	};
};

&u2phy3 {                               // USB2 伴生 PHY
	status = "okay";
};

&u2phy3_host {
	status = "okay";
	phy-supply = <&vcc5v0_usb_host>;
};

&combphy2_psu {                         // USB3 PHY
	status = "okay";
};

&usbhost3_0 {
	status = "okay";
};

&usbhost_dwc3_0 {
	status = "okay";
	dr_mode = "host";
};
```

### 4.4 时序说明

```
上电 -> U-Boot: HUB 复位脚低 (enable-active-low-uboot),
              HUB/桥芯片保持复位
内核启动: vcc_3v0_sata 供电 -> GL3321G 上电
kernel 启动 + 2.5s: vcc_hub3_reset 释放 HUB 复位
释放 + 500ms: gl3321g 节点完成桥芯片时序
之后 USB 枚举 4 个 SATA 盘
```

## 5. 验证测试

```
# 原生 SATA (方式一/二)
dmesg | grep -i -E "ahci|sata"
# 应看到: ahci fe210000.sata: AHCI 0001.0301 32 slots 1 ports ...

lsblk                   # 应出现 sda
cat /sys/class/sata/.../link_speed 或:
dmesg | grep -i "SATA link up"    # SATA3 6.0 Gbps 为正常

# USB 一扩四 (方式三)
lsusb                    # 应看到 GL33121 HUB + 4 个 GL3321G 桥
lsblk                    # 应出现 sda ~ sdd (插满 4 盘时)
dmesg | grep -i -E "usb-storage|gl33|SuperSpeed"

# 读写测速
dd if=/dev/sda of=/dev/null bs=1M count=1000 iflag=direct
# 原生 SATA3 应接近 550MB/s (SSD 本身限制), USB3 桥方案约 400MB/s
```
