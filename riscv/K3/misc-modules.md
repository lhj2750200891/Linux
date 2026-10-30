# 杂项模块 (PWM/SPI/IR/温控/风扇等)

　　K3 平台小模块合集: PWM (20 路 APBC + 6 路 RCPU)、SPI/QSPI 与
SPI-NOR、红外接收、温控、PWM 风扇、efuse、eSPI、EtherCAT 主站, 以及
VPU/RCPU 等大块头的索引入口。每项独立成节, 按需取用。

## 1. PWM

### 1.1 控制器总表

| 组 | 控制器 | 基址 | 归属 |
|---|---|---|---|
| APBC 域 | pwm0-pwm19 (20 路) | 0xd401a000 起, 步进 0x400 | k3.dtsi 基座 |
| RCPU 域 | rpwm0-rpwm5 (6 路) | 0xc088d100 起 | k3-rdomain.dtsi 基座 |

- compatible = "spacemit,k1-pwm", "marvell,pxa910-pwm", 驱动走
  **CONFIG_PWM_PXA** (defconfig 已 =y)。
- 已有实装参考: DSI 背光 pwm1 (mipi-dsi.md)、eDP 背光 pwm18
  (edp.md)、风扇 rpwm6 (见本篇 3 节)。

### 1.2 使能写法

```dts
&pwm5 {
	pinctrl-names = "default";
	pinctrl-0 = <&pwm5_X_cfg>;         /* 基座组按 pad 选, k3-pinctrl 有多档 */
	status = "okay";
};
/* pwms = <&pwm5 0 <period_ns> 0>;  引用格式与 RK3588 相同 */
```

## 2. SPI / QSPI / SPI-NOR

### 2.1 普通 SPI (spi0-3)

| 控制器 | 基址 | 引脚组 (k3-pinctrl, 多档) | 实装参考 |
|---|---|---|---|
| spi0 | 0xd4040000 | ssp0_0/1/2_cfg (53-55 / 81-83 / 104-106) | - |
| spi1 | 0xd4040800 | ssp1_0/1_cfg (32-34 / 111-113) | - |
| spi2 | 0xf0613000 | ssp2_0_cfg (28-30) | - |
| spi3 | 0xd401c000 | ssp3_0/1_cfg (68-70 / 99-101) | bananapi-f3 |

- compatible = "spacemit,k3-spi" (CONFIG_SPI_SPACEMIT_K1=y 已编),
  spi-max-frequency 51.2MHz; 组名是 **sspN** 不是 spiN (grep 别找错)。
- 用户态访问: CONFIG_SPI_SPIDEV=y 已编, 从设备加 compatible
  "rohm,dh2228fv" (或 linux,spidev) 挂 spidev。

```dts
&spi3 {                                    /* bananapi-f3 参考 */
	pinctrl-names = "default";
	pinctrl-0 = <&ssp3_0_cfg>;         /* pad68 tx / 69 rx / 70 clk func6 */
	status = "okay";
};
```

### 2.2 QSPI + SPI-NOR (itx FF_SPI_NOR, 实装)

　　qspi @0xd420c000 (irq117), NOR 映射窗 0xb8000000 (12MB); 引脚组
qspi_cfg (pads138-141/144 func0) + qspi_cs0_cfg (pad142):

```dts
&qspi {
	pinctrl-names = "default";
	pinctrl-0 = <&qspi_cfg>, <&qspi_cs0_cfg>;
	status = "okay";

	flash@0 {
		compatible = "jedec,spi-nor";
		reg = <0>;
		spi-max-frequency = <26500000>;
		m25p,fast-read;
		broken-flash-reset;            /* 参考板标志; 复位中断恢复问题才加 */
		status = "okay";
	};
};

&pinctrl {
	qspi-cfg   { qspi-pins    { power-source = <1800>; }; };
	qspi-cs0-cfg { qspi-cs0-pins { power-source = <1800>; }; };
};
```

**双驱动陷阱**: 两个驱动都 match "spacemit,k3-qspi" —
`spi-fsl-qspi.c` (CONFIG_SPI_FSL_QUADSPI, **defconfig 已编 =y**) 与
`spi-k1-qspi.c` (CONFIG_SPI_K1_QSPI, **未编**)。保持默认 (只用
fsl-qspi) 即可, **别双开**, 同时编会抢同一设备。

### 2.3 eSPI

　　espi0 @0xcac8c000 (K3 少见的 eSPI 从/主控), 引脚组 espi0_0/1/2_cfg
(pad0-7 func5)。参考板无实装, 有 x86 生态对接需求再展开。

## 3. PWM 风扇 (spcda400 FF_PWM_FAN, 实装)

　　风扇走 **RCPU 域 rpwm6** (pad33 func3), 40kHz, 标准 pwm-fan 驱动
(CONFIG_SENSORS_PWM_FAN=y 已编) + 温控联动 cooling-levels:

```dts
/ {
	fan_pwm6: pwm-fan {
		compatible = "pwm-fan";
		pwms = <&rpwm6 0 25000 0>;     /* 25us = 40kHz; rpwm6 在 rdomain */
		cooling-levels = <64 96 128 192 255>;
		#cooling-cells = <2>;
	};
};

&rpwm6 { status = "okay"; };

&pinctrl {
	spcda400_rpwm6_cfg: spcda400-rpwm6-cfg {
		spcda400-rpwm6-pins {
			pinmux = <K3_PADCONF(33, 3)>;
			bias-pull-up;
			drive-strength = <25>;
			power-source = <3300>;
		};
	};
};
```

　　与 thermal zone 联动: 在 thermal-zones 里给 cooling-maps 挂
&fan_pwm6 (k3-tsensor 见 4 节)。

## 4. 温控 (tsensor)

　　k3.dtsi 基座 "spacemit,k3-tsensor" + CONFIG_K3_THERMAL=y
(CONFIG_THERMAL/CPU_THERMAL/DEVFREQ_THERMAL 同已编), GPU 侧另有
POWERVR_THERMAL=y。基座已带 thermal-zones 骨架, 板级一般零改动;
做风扇联动才需要补 cooling-maps (3 节)。

## 5. 红外接收 (IR)

　　两路接收器: ircrx0 @0xd4017e00 (irq69) / ircrx1 @0xd4017f00
(irq20), compatible "spacemit-k1,irc", 驱动 CONFIG_IR_SPACEMIT_K1=y
(已编) + CONFIG_IR_NEC_DECODER=y:

```dts
&ircrx0 {
	pinctrl-names = "default";
	pinctrl-0 = <&ircrx0_X_cfg>;       /* 按板 pad 选组 */
	status = "okay";
};
```

　　验证: `ir-keytable -t` (或 cat /dev/lirc0 后按遥控) — 出键值即
通。键位映射用 ir-keytable 协议/键表配置。

## 6. efuse / socinfo

　　"spacemit,efuse" ×2 (基座), 芯片 UID/校准值读取; socinfo 出
/sys 属性。无板级适配工作, 排查启动日志异常时当读数工具用。

## 7. EtherCAT 主站 (itx 默认开启!)

　　`ec_master` ("spacemit,igh-ec-master", **CONFIG_EC_MASTER=y 已
编**) — IgH EtherCAT 主站, itx-k3l 板级直接
`&ec_master { status = "okay"; };` (无 pinctrl, 绑定网口工作)。
工业场景自研板按需使能; 不用则保持基座 disabled 即可, 无副作用。

## 8. 大块头索引入口 (按需再深挖)

| 模块 | 入口 | 说明 |
|---|---|---|
| VPU 视频编解码 | drivers/media/platform/spacemit/vpu_k3/ | H.264/HEVC 硬解; 需 v4l2 用户态配合 |
| 2D 加速 (v2d) | "spacemit,v2d" (k3.dtsi) | blitter 类; 图形栈用 |
| RCPU 远程核 | "spacemit,k3-rproc" ×2 + hwspinlock + k3-mailbox ×7 | RPMsg/共享内存 (resmem 的 rcpu0/1 段); rdomain 外设都挂在它后面 |
| NPU | SDK 单独组件 (不在内核 dts 主线) | RK1828 场景关联 pcie.md 的 EP 口 |
| hibernation | resmem: hibernation_nomap 等 | 休眠到 RAM 保留段, 动内存布局先看 resmem 全图 |

　　这些模块参考板未给板级级联实例 (VPU/RCPU 是平台级功能), 自研板
默认"基座什么样就什么样", 出问题先查固件/库配套而不是 dts。

## 9. 验证测试 (合集)

```bash
# PWM: sysfs 导出看波形
ls /sys/class/pwm/                  # pwmchipX 数量 = 已使能路数
echo 0 > /sys/class/pwm/pwmchip5/export && cat /sys/class/pwm/pwmchip5/pwm0/period

# SPI-NOR
ls /dev/mtd* ; cat /proc/mtd        # NOR 分区 (qspi 枚举)
dmesg | grep -iE "spi-nor|qspi"     # 器件 JEDEC ID

# spidev
ls /dev/spidev*                     # spi3 挂 spidev 后出现
spidev_test -D /dev/spidev3.0 -v    # 回环 (MOSI 接 MISO 时)

# 风扇
cat /sys/class/hwmon/*/name | grep -B1 -A1 fan
echo 128 > /sys/class/hwmon/*/pwm1  # 降速听声音变化 (hwmon 号按实际)

# IR
ir-keytable -r                      # 列协议/键表
ir-keytable -t                      # 按遥控看事件

# 温度
cat /sys/class/thermal/thermal_zone*/temp

# EtherCAT
ls /dev/EtherCAT* ; dmesg | grep -i ec_master

# CAN / 音频 / SD 另见各专篇
```
