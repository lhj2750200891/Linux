# 其他模块

　　风扇 / G-Sensor / 蜂鸣器 / INA226 / SD 卡座 / SPI / RTL8126 5G 网口 / SW3203 / WOL / M.2 SSD 小模块合集。

　　单模块体量不大的外设集中在此文档, 每个模块独立三段式 (硬件连接/设备树/
验证), 相互无依赖, 按需取用。
(4G/5G 蜂窝模组体量较大, 已单独成文, 见 [4g-5g-module.md](4g-5g-module.md))

## 1. 风扇 (PWM 散热风扇)

　　两种玩法: 纯手控 (pwm-fan 无温控表) / 温控自动调速 (cooling-levels +
rockchip,temp-trips, Firefly 私有属性, 6.12 firefly 内核已带)。

### 1.1 硬件连接

```
SG 板 (AIO-3588SG):
  风扇 PWM   ====> PWM15_M2 = GPIO1_C6, 20ms 周期
  风扇电源   ====> vcc12v_dcin (12V, 板上供电常开, 无使能脚)

jd4 板 (AIO-3588JD4):
  风扇 PWM   ====> PWM5_M1 = GPIO3_B3, 20ms 周期
  风扇电源   ====> vcc5v0_sys (5V)

l-qua 板 (多风扇时):
  fan_sub1: PWM3  + FG 转速反馈 GPIO1_C3
  fan_sub2: PWM11 + FG 转速反馈 GPIO1_C6
  fan_sub3: PWM0  + FG 转速反馈 GPIO1_A3
```

### 1.2 设备树配置

**方式一: 纯手控 — AIO-3588SG (无温控表, 用户态 echo pwm)**

```
/ {
	fan: pwm-fan {
		status = "okay";
		compatible = "pwm-fan";
		#cooling-cells = <2>;
		fan-supply = <&vcc12v_dcin>;          // 12V 供电
		pwms = <&pwm15 0 50000 0>;            // 20ms 周期, 无反相
	};
};

&pwm15 {
	status = "okay";
	pinctrl-0 = <&pwm15m2_pins>;             // PWM15_M2 = GPIO1_C6
};
```

**方式二: 温控自动调速 — aio-3588jd4 / itx-3588j (temp-trips 表)**

```
/ {
	fan: pwm-fan {
		compatible = "pwm-fan";
		#cooling-cells = <2>;
		fan-supply = <&vcc5v0_sys>;           // jd4 5V (itx 用 vcc12v_dcin)
		pwms = <&pwm5 0 50000 0>;
		cooling-levels = <50 50 100 150 200 255>;   // 6 档 PWM 值
		                                          // (itx 首档为 0)
		rockchip,temp-trips = <               // Firefly 私有: 温度->档位
			50000   1                         // 50C -> 档1
			55000   2                         // 55C -> 档2
			60000   3                         // 60C -> 档3
			65000   4                         // 65C -> 档4
			70000   5                         // 70C -> 档5
		>;
	};
};

&pwm5 {
	pinctrl-0 = <&pwm5m1_pins>;              // PWM5_M1 = GPIO3_B3
	status = "okay";
};
```

**方式三: 带 FG 转速反馈的多风扇 — aio-3588l-qua (fan_sub1 为例)**

```
/ {
	fan_sub1: pwm-fan-sub1 {
		compatible = "pwm-fan";
		#cooling-cells = <2>;
		fan-supply = <&vcc5v0_sys>;
		pwms = <&pwm3 0 50000 0>;
		pinctrl-names = "default";
		pinctrl-0 = <&fan_sub1_tach>;
		interrupt-parent = <&gpio1>;
		interrupts = <RK_PC3 IRQ_TYPE_EDGE_FALLING>;   // FG 脉冲
		pulses-per-revolution = <2>;                   // 每转 2 脉冲
	};
};
```

　　(需自行补 fan_subN_tach 及对应 &pwmN 的 pinctrl, 引脚见 1.1)

### 1.3 验证测试

```
# 驱动注册 (对应 CONFIG_SENSORS_PWM_FAN=y, firefly-linux.config)
ls /sys/class/hwmon/
cat /sys/class/hwmon/hwmon*/name            # 应有 pwmfan

# 手控风扇: 直接设置 PWM占空比 (thermal cooling device 方式)
cat /sys/class/thermal/cooling_device*/type          # pwm-fan
echo 255 > /sys/class/thermal/cooling_device*/cur_state   // 最大转速
echo 0   > /sys/class/thermal/cooling_device*/cur_state   // 停转

# 温控表生效确认 (方式二)
cat /sys/class/thermal/thermal_zone*/temp
# 温度升过 50C 后风扇应自动升档, 降回后延迟降档

# FG 转速 (方式三)
cat /sys/class/hwmon/hwmon*/fan1_input     # RPM 读数

# 常见问题:
# 1. 风扇不转: 先量 PWM 引脚波形; pinctrl 复用组选错 (PWM15 有 m0/m2 等)
# 2. cooling-levels 第一档不为 0 时开机会有基础转速, 不想要改首档为 0
# 3. temp-trips 不生效: 这是 Firefly 私有属性, 须用 SDK 内核
#    (drivers/hwmon/pwm-fan.c 带 rockchip 扩展), 主线内核只有 cooling-levels
```

## 2. G-Sensor (MC3230 加速度计)

### 2.1 硬件连接

```
MC3230 (AIO-3588SG):
  I2C SCL/SDA ====> I2C4_M3: SCL GPIO4_C3 / SDA GPIO4_C4 (地址 0x4c)
  (SG 板与 PCA9555 同挂 i2c4)
  INT 不接 (irq_enable = 0, 轮询模式)
```

### 2.2 设备树配置

```
&i2c4 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c4m3_xfer>;

	mc3230: mc3230@4c {
		status = "okay";
		compatible = "gs_mc3230";
		reg = <0x4c>;
		type = <SENSOR_TYPE_ACCEL>;        // 传感器类型宏
		irq_enable = <0>;                  // 0=轮询, 1=中断
		poll_delay_ms = <30>;              // 轮询周期
		layout = <6>;                      // 安装方向 (坐标映射), 按整机姿态调 1-8
	};
};
```

　　需要 #include <dt-bindings/sensor-dev.h> (SENSOR_TYPE_ACCEL)。

　　内核配置: CONFIG_GS_MC3230=m (firefly-linux.config, 驱动在
kernel-6.12/drivers/input/sensors/accel/mc3230.c, Firefly 移植的
rk29 系 sensor 框架)。

### 2.3 验证测试

```
# 模块加载
lsmod | grep mc3230
dmesg | grep -i mc3230

# 输入设备
cat /proc/bus/input/devices | grep -A4 mc3230
cat /sys/class/input/input*/name     # 应有 gs_mc3230

# 读数据 (evtest 或直接读)
evtest /dev/input/eventN              # 移动板子应看到三轴数据变化

# 常见问题:
# 1. 挂不上: i2cdetect -y 4 看 0x4c 在不在 (总线号按实际)
# 2. 坐标方向不对: layout 属性换 1-8 试
# 3. 驱动框架差异: gs_mc3230 是 Firefly 移植的旧 sensor 框架,
#    与主线 iio/inv-mpu 体系不通用
```

## 3. 蜂鸣器 (PWM 无源蜂鸣器)

### 3.1 硬件连接

```
无源蜂鸣器 (aio-3588l-qua):
  驱动 PWM ====> PWM13_M1, 20ms 周期
  (蜂鸣器频率由 PWM 占空比/频率决定, 无源需方波驱动)
```

### 3.2 设备树配置

```
/ {
	pwm_beeper: pwm-beeper {
		status = "okay";
		compatible = "pwm-beeper";
		pwms = <&pwm13 0 50000 0>;
	};
};

&pwm13 {
	pinctrl-0 = <&pwm13m1_pins>;
	status = "okay";
};
```

　　内核配置: CONFIG_INPUT_PWM_BEEPER=y (firefly-linux.config)。

### 3.3 验证测试

```
# 事件设备
cat /proc/bus/input/devices | grep -A4 pwm-beeper

# 响一声 (标准蜂鸣事件)
evtest /dev/input/eventN          # SND_BELL/SND_TONE 事件
# 或用户态直接操作 (echo 8 > /dev/input/eventN 方式较隐晦, 一般用 evdev 测试)

# 常见问题:
# 1. 无源蜂鸣器不响: 频率不对, pwm-beeper 驱动用事件值当频率,
#    事件值为 0 时不响
# 2. 有源蜂鸣器 (自带振荡) 不适合此驱动, 直接 GPIO 拉高更简单 (见 led 模块)
```

## 4. INA226 电流/电压监测

### 4.1 硬件连接

```
INA226 (aio-3588l-qua, 两颗):
  芯片 0 I2C ====> I2C7_M0: SCL GPIO1_D0 / SDA GPIO1_D1 (地址 0x40)
  芯片 1 I2C ====> 同总线 (地址 0x41)
  供电   ====> vcc3v3_ac
  测量端 ====> 串入被测电源的采样电阻 (硬件决定测量对象)
```

### 4.2 设备树配置

```
&i2c7 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c7m0_xfer>;

	ina226_40: ina226@40 {
		status = "okay";
		compatible = "ti,ina226";
		reg = <0x40>;
		vcc-supply = <&vcc3v3_ac>;
	};

	ina226_41: ina226@41 {
		status = "okay";
		compatible = "ti,ina226";
		reg = <0x41>;
		vcc-supply = <&vcc3v3_ac>;
	};
};
```

　　可选属性 (按精度需求加, 不加用默认):
- shunt-resistor = <r欧姆> 采样电阻值 (默认 10000, 即 10mΩ 记 10000μΩ
  — 注意单位是微欧)
- 对齐: 主线驱动为 ina2xx, 采样电阻/唤醒时间等属性按
  Documentation/devicetree/bindings/hwmon/ti,ina2xx.yaml

　　内核配置: CONFIG_SENSORS_INA2XX=y (rockchip_linux_defconfig 已开)。

### 4.3 验证测试

```
# hwmon 注册
ls /sys/class/hwmon/
cat /sys/class/hwmon/hwmon*/name        # ina226

# 读数 (mv/uV/W)
cat /sys/class/hwmon/hwmon*/in0_input   # 总线电压 mV
cat /sys/class/hwmon/hwmon*/power1_input  # 功率 uW
cat /sys/class/hwmon/hwmon*/curr1_input  # 电流 mA (需 shunt-resistor 对)

# 常见问题:
# 1. 电流读数离谱: shunt-resistor 与硬件采样电阻不符
# 2. 两颗芯片地址要硬件 A0/A1 拉法区分 (0x40/0x41)
```

## 5. SD 卡 (TF 卡)

### 5.1 硬件连接

```
TF 卡座:
  DAT0-3/CLK/CMD ====> &sdmmc (fe2c0000), 4bit (硬件固定引脚, 无复用选项)
  卡电源 3.3V/1.8V (信号) ====> vccio_sd_s0 (PMIC 可调, SDR104 时切 1.8V)
  卡电源使能:
    SG 板: vcc3v3_sd_s0 = GPIO3_C6 (高有效)
    q 板:  PCA9555 IO1_5
    l-qua: GPIO1_D6
```

### 5.2 设备树配置 (SG 板完整版)

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
vqmmc-supply (vccio_sd_s0 是 PMIC rk806 的固定节点, 已在 base dtsi)。

### 5.3 验证测试

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

## 6. SPI (用户态 spidev)

### 6.1 硬件连接

```
SPI1 (aio-3588q, M2 复用组):
  CLK  ====> SPI1_CLK_M2  = GPIO1_D2
  MISO ====> SPI1_MISO_M2 = GPIO1_D0
  MOSI ====> SPI1_MOSI_M2 = GPIO1_D1
  CS0  ====> SPI1_CS0_M2  = GPIO1_D3
```

### 6.2 设备树配置

```
&spi1 {
	status = "okay";
	pinctrl-0 = <&spi1m2_cs0 &spi1m2_pins>;
	num-cs = <1>;
	max-freq = <50000000>;              // 50MHz 控制器上限

	spi_dev: spi-dev@0 {
		status = "okay";
		compatible = "rockchip,spidev";
		reg = <0x0>;                     // 片选 0
		spi-max-frequency = <50000000>;  // 设备侧限频 (按外设规格降)
	};
};
```

　　注意: RK SDK 里 spidev 的 compatible 写 "rockchip,spidev" (主线为
"spidev"/无, 主线对 spidev-compatible 有校验, 本 SDK 已放开)。

### 6.3 验证测试

```
# 设备节点
ls /dev/spidev1.0                      // 总线1 片选0

# 环回测试 (MOSI 短接 MISO)
spidev_test -D /dev/spidev1.0 -v -p "\x01\x02\x03"

# Python 测试也广泛可用 (spidev 模块)

# 常见问题:
# 1. /dev/spidev* 不出现: 节点 reg 与 num-cs 不配, 或 compatible 写错
# 2. 波形不对: spi-cpha/spi-cpol 按外设时序加到 spi-dev@0 节点
# 3. spi1m2 与 i2s 引脚冲突 (GPIO1_D0/D1 同为 i2s7 m0), 同板互斥时二选一
```

## 7. RTL8126 5G 网口 (PCIe 5G PHY 网卡)

### 7.1 硬件连接

```
RTL8126 (aio-3588l-qua):
  PCIe 差分对 ====> pcie2x1l2 (combphy0_ps)
  隔离脚 isolateb ====> GPIO4_B0 (高电平启用, 默认上拉)
  唤醒脚 WAKEN    ====> GPIO0_C0 (配合 WOL)
```

### 7.2 设备树配置

```
&pinctrl {
	rtl8126 {
		rtl8126_isolateb: rtl8126-isolateb {
			rockchip,pins = <4 RK_PB0 RK_FUNC_GPIO &pcfg_pull_up>;
		};
		net5g_waken: net5g-waken {
			rockchip,pins = <0 RK_PC0 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};

&pcie2x1l2 {
	pinctrl-names = "default";
	pinctrl-0 = <&rtl8126_isolateb>;     // isolateb 拉高 = 芯片不隔离
};

&combphy0_ps {
	status = "okay";                      // pcie2x1l2 的 PHY
};
```

　　rtl8126 驱动: 5.10/6.1 SDK 用 r8126 (Realtek out-of-tree), 6.12 主线
r8125/r8126 逐步合入; SDK defconfig 按 CONFIG_R8126 处理, 编译时确认
驱动存在 (make menuconfig 搜 8126)。

### 7.3 验证测试

```
lspci | grep -i net                     # 应看到 Realtek 5G 网卡
lspci -vvv -s <bdf> | grep Lnk          // LnkSta 应 x2/x4 5GT/s 以上

ip link                                 // eth1 (5G 口) 出现
ethtool eth1                            // Speed: 5000Mb/s
iperf3 -c <server> -t 10                // 峰值应是千兆的 3-5 倍

# 常见问题:
# 1. 枚举到但速率只有 2.5G: PHY 模式没切 pcie (combphy0_ps 被 USB3 占用),
#    看 combphy 归属 (引脚冲突速查表)
# 2. isolateb 被拉低芯片隔离, lspci 扫不到 --- 检查 pinctrl-0 是否挂对
# 3. 驱动: r8126 装了吗 (dmesg | grep r8126)
```

## 8. SW3203 电能计量芯片 (Firefly 私有驱动)

### 8.1 硬件连接

```
SW3203 (itx-3588j):
  I2C ====> 挂在 codec 同总线 (i2c3), 地址 0x3c
  采样端串入被测电源回路 (硬件决定)
```

### 8.2 设备树配置

```
sw3203@3c {
	status = "okay";
	compatible = "ismartware,sw3203";
	reg = <0x3c>;
	startup-delay-ms = <2500>;           // 上电稳定 2.5s 再访问
	reg-0x20 = <0x05>;                   // 寄存器 0x20 初值 (开关频率配置)
};
```

　　内核配置: CONFIG_FIREFLY_SW3203 (SDK 带 Firefly 私有驱动
kernel-6.12/drivers/misc/firefly/sw3203/, 默认未开, 需手动开)。

### 8.3 验证测试

```
# 驱动加载
dmesg | grep -i sw3203
ls /sys/bus/i2c/drivers/ | grep sw3203

# i2c 通信 (读寄存器 0x20)
i2cget -y 3 0x3c 0x20

# 常见问题: 计量值异常 → 采样电阻/量程与驱动参数匹配问题, 看
# drivers/misc/firefly/sw3203/sw3203.c 的寄存器语义
```

## 9. WOL 网络唤醒 (PCIe 唤醒源)

### 9.1 硬件连接

```
唤醒链路 (aio-3588l-qua):
  RTL8126 WAKEN 脚 ====> GPIO3_D0 (PCIE20X1_2_WAKEN_M0, 低有效)
  (GMAC PHY 唤醒走另一路: gmac0_int = GPIO0_B7, 见 gmac 模块)
```

### 9.2 设备树配置

```
/ {
	wol_wake: wol-wake {
		compatible = "gpio-keys";
		pinctrl-names = "default";
		pinctrl-0 = <&pcie20x1_2_waken_pin>;

		pcie-wake {
			label = "pcie-wake";
			gpios = <&gpio3 RK_PD0 GPIO_ACTIVE_LOW>;   // 低有效
			linux,code = <KEY_WAKEUP>;
			wakeup-source;                              // 是唤醒源
		};
	};
};

&pinctrl {
	pcie-wol {
		pcie20x1_2_waken_pin: pcie20x1-2-waken-pin {
			rockchip,pins = <3 RK_PD0 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

　　需要 #include <dt-bindings/input/input.h> (KEY_WAKEUP)。

### 9.3 验证测试

```
# 唤醒源注册
cat /proc/interrupts | grep pcie-wake
grep . /sys/class/input/input*/capabilities/  # 按键能力

# 挂起并验证
echo mem > /sys/power/state
# 远端发魔术包 (wakeonlan <MAC>), 板子应唤醒

# 常见问题:
# 1. 唤不醒: PCI 设备侧 WOL 也要开 (ethtool -s eth1 wol g),
#    唤醒信号是网卡拉低 WAKEN, 只配 gpio-keys 不够
# 2. 休眠即醒: 引脚悬空漂移, pcfg_pull_up 拉住
```

## 10. M.2 SSD (NVMe 槽位使能)

### 10.1 硬件连接

```
M.2 NVMe (lga-3588l-mini-duo, 双槽):
  slot0 (M.2 M key) ====> pcie3x4, 2 lane, PERST# GPIO1_B2, WAKE GPIO1_B1
  slot1 (M.2 M key) ====> pcie3x2, 2 lane, PERST# GPIO1_B7, WAKE GPIO1_B6
  参考时钟使能 ====> GPIO4_B6 (pcie_refclk_en, 高有效)
  槽电源 3.3V  ====> GPIO4_B5 (vcc3v3_ac1, 高有效)
```

### 10.2 设备树配置 (完整可复制)

　　参考板: lga-3588l-mini-duo-rk182x。pcie30phy 拆 NANBNB 模式,
pcie3x4/pcie3x2 各带 2 lane 跑一个 M.2 槽:

```
/ {
	pcie_refclk_en: pcie-refclk-en {          // PCIe 参考时钟缓冲使能
		compatible = "regulator-fixed";
		regulator-name = "pcie_refclk_en";
		regulator-boot-on;
		regulator-always-on;
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio4 RK_PB6 GPIO_ACTIVE_HIGH>;
		pinctrl-names = "default";
		pinctrl-0 = <&pcie_refclk_en_pin>;
	};

	vcc3v3_ac1: vcc3v3-ac1 {                  // M.2 槽 3.3V 供电
		compatible = "regulator-fixed";
		regulator-name = "vcc3v3_ac1";
		regulator-boot-on;
		regulator-always-on;
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		enable-active-high;
		gpio = <&gpio4 RK_PB5 GPIO_ACTIVE_HIGH>;
		pinctrl-names = "default";
		pinctrl-0 = <&pcie_m2_power_en>;
		vin-supply = <&vcc12v_dcin>;
	};
};

&pcie30phy {
	rockchip,pcie30-phymode = <PHY_MODE_PCIE_NANBNB>;  // 拆 2+2 lane
	status = "okay";
};

/* M.2 SSD 槽 0 */
&pcie3x4 {
	num-lanes = <2>;
	reset-gpios = <&gpio1 RK_PB2 GPIO_ACTIVE_HIGH>;    // PERST#
	vpcie3v3-supply = <&vcc3v3_ac1>;
	pinctrl-names = "default";
	pinctrl-0 = <&pcie30x4m3_pins &pcie_ssd0_wake_pin>;
	status = "okay";
};

/* M.2 SSD 槽 1 */
&pcie3x2 {
	num-lanes = <2>;
	reset-gpios = <&gpio1 RK_PB7 GPIO_ACTIVE_HIGH>;    // PERST#
	vpcie3v3-supply = <&vcc3v3_ac1>;
	pinctrl-names = "default";
	pinctrl-0 = <&pcie30x2m3_pins &pcie_ssd1_wake_pin>;
	status = "okay";
};

&pinctrl {
	pcie {
		pcie_refclk_en_pin: pcie-refclk-en-pin {
			rockchip,pins = <4 RK_PB6 RK_FUNC_GPIO &pcfg_output_low>;
		};
		pcie_m2_power_en: pcie-m2-power-en {
			rockchip,pins = <4 RK_PB5 RK_FUNC_GPIO &pcfg_output_low>;
		};
		pcie_ssd0_wake_pin: pcie-ssd0-wake-pin {
			rockchip,pins = <1 RK_PB1 RK_FUNC_GPIO &pcfg_pull_up>;
		};
		pcie_ssd1_wake_pin: pcie-ssd1-wake-pin {
			rockchip,pins = <1 RK_PB6 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

　　只接一个槽就只留对应 &pcie3xN 段; num-lanes 按槽实际 lane 数改
(单 lane M.2 改 <1>, pcie30phy 模式跟着换成 NANBNB 拆法或保持默认)。

### 10.3 验证测试

```
lspci | grep -i nvme
ls /dev/nvme*                           // nvme0 + nvme0n1

# 读写测速
dd if=/dev/nvme0n1 of=/dev/null bs=1M count=100 iflag=direct
hdparm -t /dev/nvme0n1

# 常见问题:
# 1. 盘扫不到: pcie_refclk_en 没拉高 (时钟缓冲芯片不输出refclk),
#    示波器量槽上 100MHz; 或 pcie3x2 拆分模式配错 (见 pcie 模块)
# 3. 速度只有 8GT/s (PCIe2): lane 数/PHY 复用配置问题, lspci -vvv 看 LnkSta
```

## 11. 模块间引脚冲突速查 (本文档内)

| 引脚 | 模块 A | 模块 B |
|---|---|---|
| GPIO1_C6 | pwm15m2 (风扇 SG) | fan_sub2 FG (l-qua) |
| GPIO1_D0/D1 | spi1m2 MISO/MOSI | i2s7m0 (SG) / i2s1 |
| GPIO4_B0 | RTL8126 isolateb | (can0m0 TX 附近区域) |
| GPIO4_B5/B6 | M.2 电源/时钟使能 | usb30 host en (l-qua 同区) |
| PWM3 | fan_sub1 (l-qua) | pwm3m1/m3 屏背光 (见 mipi-dsi) |
