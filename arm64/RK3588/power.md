# 电源

　　从 12V DC 输入到 RK3588 每一颗核心的完整供电树: 硬件分级原理、RK806 PMIC +
RK860x 分立 DCDC 的设备树完整适配、always-on 与挂起策略、运行时验证。参考板
AIO-3588SG, 其余 AIO/ITX/LGA 板同架构 (轨名/电压/门控脚以各板原理图为准)。
充放电 (电池/充电芯片/PD) 是另一套系统, 见 charging.md 与 typec.md。

## 1. 原理: 12V 进来之后发生了什么

### 1.1 整板供电树

　　12V 不是直接进 SoC, 而是逐级降压; 每一级在 dts 里都有对应节点, 全树的
"父子关系"靠 vin-supply 属性串起来:

```
12V DC 输入座
  │
  ▼
vcc12v_dcin (12V 软件记账轨, 无驱动控制)
  ├─────────► 板级硬 DCDC (12V→5V, 纯硬件, dts 只记账)
  │              ▼
  │           vcc5v0_sys ──┬─► RK806 全部 buck/LDO 的输入 (vcc1~10/vcc12/vcca)
  │                        └─► RK860x 大电流 buck ×3 的输入 (vin)
  ├─► vcc5v0_usbdcin ─► vcc5v0_usb ─► vcc5v0_usb20_host0/1 (GPIO 门控 USB VBUS)
  ├─► vcc12v_bp        (背光 12V, GPIO 门控, SG)
  ├─► vcc3v3_pcie30 / vcc3v3_pcie3x2_0/1 / vcc3v3_pcie20_1l2 / vcc3v3_sata0
  │        (板级 3.3V 电源, GPIO 门控, 12V 直入, 不经过 PMIC)
  └─► SC8886 充电芯片 (仅 SG 电池板: 12V/PD → SYS → 整板, 见 charging.md)

RK806 (spi2, 1MHz)                          RK860x (I2C)
  ├─ DCDC1  vdd_gpu_s0       GPU 核心        ├─ i2c0 0x42  vdd_cpu_big0_s0  A76 簇0 (cpu_b0/b1)
  ├─ DCDC2  vdd_cpu_lit_s0   A55 四核        ├─ i2c0 0x43  vdd_cpu_big1_s0  A76 簇1 (cpu_b2/b3)
  ├─ DCDC3  vdd_log_s0       SoC 逻辑域      └─ i2c1 0x42  vdd_npu_s0       NPU
  ├─ DCDC4  vdd_vdenc_s0     视频编解码域        (RK3588S 板为 i2c2 0x42)
  ├─ DCDC5  vdd_ddr_s0       DDR 主电压 (DDR blob 专管)
  ├─ DCDC6  vdd2_ddr_s3      DDR (S3 保留轨)
  ├─ DCDC7  vcc_2v0_pldo_s3  2.0V, 兼作 PMIC 自供 (vcc11)
  ├─ DCDC8  vcc_3v3_s3       3.3V 常开域 (SD/RTC/CEC...)
  ├─ DCDC9  vddq_ddr_s0      DDR (DDR blob 专管)
  ├─ DCDC10 vcc_1v8_s3       1.8V 常开域
  ├─ PLDO1~6  avcc_1v8_s0 / vcc_1v8_s0 / avdd_1v2_s0 / vcc_3v3_s0 /
  │           vccio_sd_s0 / pldo6_s3
  ├─ NLDO1~5  vdd_0v75_s3 / vdd_ddr_pll_s0 / avdd_0v75_s0 / vdd_0v85_s0 / vdd_0v75_s0
  └─ 硬件接口: GPIO0_A7 中断 + GPIO0_A2/A3/C1/C2/C3/D6 六根 sleep 控制线
```

　　注意分层: PCIe/SATA/背光这类 GPIO 门控电源直接从 12V 降压, 只受 enable 脚
控制, 不经过 PMIC —— PMIC 管的是"电压对不对", enable 脚管的是"给不给电",
两套机制别混。

### 1.2 RK806 输入的级联

　　21 路输出 (10 DCDC + 6 PLDO + 5 NLDO) 的输入脚不是都接 5V, 有三处特例,
抄 dts 时最容易抄错:

| 输入脚 | 接的是什么 | 说明 |
|---|---|---|
| vcc1~10, vcc12, vcca | vcc5v0_sys | 正常情况, 全部接 5V |
| vcc11 (PLDO6 输入) | vcc_2v0_pldo_s3 | **接的是自己 DCDC7 的输出**, 芯片内部级联 |
| vcc13/vcc14 (NLDO 输入) | vcc_1v1_nldo_s3 | 板级 1.1V LDO (dts 里是 fixed regulator), 不是 PMIC 自产 |

　　另注意不同板卡的差异: 原厂 EVB 参考设计 DCDC10 输出 1.1V 直接兼作 vcc13/14,
Firefly 板 DCDC10 输出的是 vcc_1v8_s3, 1.1V 由板级 LDO 单独出 —— 对照原理图,
别跨板混抄。

### 1.3 大核为什么甩给 RK860x

　　PMIC 集成 buck 单路一般 3~5A, 4×A76 大核簇峰值电流 8A 以上, PMIC 顶不住;
RK8602/RK8603 是 I2C 可调的单路大电流同步 buck (同族不同电流档), 专喂大核与 NPU。
三颗芯片两条 I2C: big0/big1 在 i2c0 的 0x42/0x43, NPU 在 i2c1 的 0x42
(RK3588 全功能型号走 i2c1, RK3588S 走 i2c2 —— 源码里用 #ifdef rk3588 区分)。

　　驱动是 `drivers/regulator/rk860x-regulator.c`, compatible = "rockchip,rk8602"
/ "rockchip,rk8603", 节点里写 `regulator-compatible = "rk860x-reg"`。

### 1.4 轨名规律 (先读命名再读 dts)

　　dts 里几十条轨不是乱起的, 四条规律:

- 后缀 `_s0` / `_s3`: 电源状态域。s0 = 运行态才有电; s3 = 挂起 (SUSPEND/S3)
  时仍保持。例: vcc_1v8_s0 挂起时断, vcc_1v8_s3 挂起时保持 (RTC/唤醒源靠 s3 轨);
- `_mem` 伴生轨: 每个大功率域有主轨 (core) + mem 轨 (SRAM/缓存)。本板 mem 轨
  与主轨由同一颗 DCDC 输出, dts 用**双标签**表达 (一个节点两个 label);
- 前缀: `vdd_` = 数字核心电源; `vcc_` = 接口/IO 电源; `avcc_`/`avdd_` = 模拟电源;
  `vccio_` = IO 电平轨 (电压可切);
- 颜色不对劲先查命名: 看到 `*_s3` 就知道它是挂起也不断电的轨, 策略不敢乱动。

### 1.5 上电时序: 每个阶段谁在调压

| 阶段 | 调压者 | 干什么 |
|---|---|---|
| 上电瞬间 | RK806 内部 POR 硬件时序 | 按芯片固定顺序拉起各 buck/LDO, dts 不控制先后 |
| U-Boot TPL | rkbin DDR 初始化固件 | 直接 I2C 写 PMIC, 调好 DDR 三轨 (vdd_ddr/vddq/vdd2) |
| U-Boot proper | U-Boot regulator uclass | 解析 dts 的 `regulator-init-microvolt`, 把 CPU 大核调到安全起频电压 |
| 内核 probe | regulator 框架 | 按 dts 约束接管, boot-on/always-on 决定使能状态 |
| 运行时 | cpufreq/devfreq | 按 OPP 表调 cpu/gpu/npu 频率与电压 |

　　`regulator-init-microvolt` 是给 U-Boot 的属性 (已核实: U-Boot 的
regulator-uclass.c 解析它, 内核 rk806 驱动不解析), 含义是"进内核之前先站到
这个电压"。所以**改了它没在内核看到效果, 不是 bug**。

## 2. 设备树配置 (完整, 自包含)

　　按供电树自顶向下五层给全: 固定轨 → PMIC → 分立 DCDC → 消费者 → 门控轨。
自研板照抄后只改三样: GPIO 门控脚与极性、电压范围、门控轨的增删。
dts 片段放进自研板板级 dtsi (根级节点放 /{} 内, &xx 为对 SoC dtsi 已有节点的追加);
`GPIO_ACTIVE_HIGH`/`IRQ_TYPE_LEVEL_LOW`/`RK_Pxx` 依赖 dt-bindings 头, 板级 dtsi 已带。

### 2.1 第一层: 12V / 5V / 1.1V 固定轨

```
vcc12v_dcin: vcc12v-dcin {
    compatible = "regulator-fixed";
    regulator-name = "vcc12v_dcin";
    regulator-always-on;
    regulator-boot-on;
    regulator-min-microvolt = <12000000>;
    regulator-max-microvolt = <12000000>;
};

vcc5v0_sys: vcc5v0-sys {
    compatible = "regulator-fixed";
    regulator-name = "vcc5v0_sys";
    regulator-always-on;
    regulator-boot-on;
    regulator-min-microvolt = <5000000>;
    regulator-max-microvolt = <5000000>;
    vin-supply = <&vcc12v_dcin>;        /* 5V 从 12V 降下来, 层级在这里体现 */
};

vcc5v0_usbdcin: vcc5v0-usbdcin {
    compatible = "regulator-fixed";
    regulator-name = "vcc5v0_usbdcin";
    regulator-always-on;
    regulator-boot-on;
    regulator-min-microvolt = <5000000>;
    regulator-max-microvolt = <5000000>;
    vin-supply = <&vcc12v_dcin>;
};

vcc5v0_usb: vcc5v0-usb {
    compatible = "regulator-fixed";
    regulator-name = "vcc5v0_usb";
    regulator-always-on;
    regulator-boot-on;
    regulator-min-microvolt = <5000000>;
    regulator-max-microvolt = <5000000>;
    vin-supply = <&vcc5v0_usbdcin>;     /* USB VBUS 的上游链 */
};

vcc_1v1_nldo_s3: vcc-1v1-nldo-s3 {
    compatible = "regulator-fixed";
    regulator-name = "vcc_1v1_nldo_s3";
    regulator-always-on;
    regulator-boot-on;
    regulator-min-microvolt = <1100000>;
    regulator-max-microvolt = <1100000>;
    vin-supply = <&vcc5v0_sys>;         /* 板级 1.1V LDO, 供 PMIC 的 vcc13/vcc14 */
};
```

　　理解点: `regulator-fixed` 没有驱动控制能力, 它只是把硬件上"必然存在的
电源"登记进 regulator 框架 —— 价值在 vin-supply 层级链 (regulator_summary
里能看到整棵树) 和给下游做 supply 引用。12V→5V 的实际降压是板级硬 DCDC,
效率和时序问题查硬件, 别在 dts 里找。

### 2.2 PMIC RK806 完整节点 (spi2)

　　挂在 spi2 (m2 引脚组), 中断 GPIO0_A7 低电平有效; `pmic_pins` 引脚组在
rk3588s-pinctrl.dtsi 里已定义, 板级直接引用:

| 引脚 | 功能 |
|---|---|
| GPIO0_A7 | pmic_int_l (PMIC 中断, 上拉, 低有效) |
| GPIO0_A2/A3/C1/C2/C3/D6 | pmic_sleep1~6 (挂起电平控制线, 与 1.4 节 s3 策略配套) |

```
&spi2 {
    status = "okay";
    assigned-clocks = <&cru CLK_SPI2>;
    assigned-clock-rates = <200000000>;
    pinctrl-names = "default";
    pinctrl-0 = <&spi2m2_cs0 &spi2m2_pins>;
    num-cs = <1>;

    rk806single: rk806single@0 {
        compatible = "rockchip,rk806";
        spi-max-frequency = <1000000>;
        reg = <0x0>;

        interrupt-parent = <&gpio0>;
        interrupts = <7 IRQ_TYPE_LEVEL_LOW>;      /* GPIO0_A7, 低有效 */
        pinctrl-names = "default";
        pinctrl-0 = <&pmic_pins>;

        /* 电压/温度保护阈值, 单位 mV/°C */
        low_voltage_threshold = <3000>;           /* 低压告警, 合法 2800~3500 */
        shutdown_voltage_threshold = <2700>;      /* 低压关机, 合法 2700~3400 */
        shutdown_temperture_threshold = <160>;    /* 关机温度 (驱动源码就拼错为 temperture) */
        hotdie_temperture_threshold = <115>;      /* 高温告警 */

        /* 0: 重启 PMU; 1: 清 power off 寄存器转 ACTIVE;
         * 2: 同 1 且拉低 RESETB 5ms 再释放 */
        pmic-reset-func = <1>;

        vcc1-supply  = <&vcc5v0_sys>;             /* DCDC1~10 + vcca + vcc12 全接 5V */
        vcc2-supply  = <&vcc5v0_sys>;
        vcc3-supply  = <&vcc5v0_sys>;
        vcc4-supply  = <&vcc5v0_sys>;
        vcc5-supply  = <&vcc5v0_sys>;
        vcc6-supply  = <&vcc5v0_sys>;
        vcc7-supply  = <&vcc5v0_sys>;
        vcc8-supply  = <&vcc5v0_sys>;
        vcc9-supply  = <&vcc5v0_sys>;
        vcc10-supply = <&vcc5v0_sys>;
        vcc12-supply = <&vcc5v0_sys>;
        vcca-supply  = <&vcc5v0_sys>;
        vcc11-supply = <&vcc_2v0_pldo_s3>;        /* 自产 2.0V 自供 (DCDC7) */
        vcc13-supply = <&vcc_1v1_nldo_s3>;        /* 板级 1.1V LDO */
        vcc14-supply = <&vcc_1v1_nldo_s3>;

        pwrkey {
            status = "okay";                      /* PMIC 电源键 MFD 子设备 */
        };

        regulators {
            /* 双标签: 一颗 DCDC 出 core+mem 两路同名电源 */
            vdd_gpu_s0: vdd_gpu_mem_s0: DCDC_REG1 {
                regulator-boot-on;
                regulator-min-microvolt = <550000>;
                regulator-max-microvolt = <950000>;
                regulator-ramp-delay = <12500>;       /* 调压斜率 uV/us */
                regulator-enable-ramp-delay = <400>;
                regulator-name = "vdd_gpu_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;         /* 挂起时关 (GPU 挂起无用) */
                };
            };

            vdd_cpu_lit_s0: vdd_cpu_lit_mem_s0: DCDC_REG2 {
                regulator-always-on;
                regulator-boot-on;
                regulator-init-microvolt = <800000>;  /* 给 U-Boot 的初值, 见 1.5 */
                regulator-min-microvolt = <550000>;
                regulator-max-microvolt = <950000>;
                regulator-ramp-delay = <12500>;
                regulator-name = "vdd_cpu_lit_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            vdd_log_s0: DCDC_REG3 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <675000>;
                regulator-max-microvolt = <800000>;
                regulator-ramp-delay = <12500>;
                regulator-name = "vdd_log_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                    regulator-suspend-microvolt = <750000>;
                };
            };

            vdd_vdenc_s0: vdd_vdenc_mem_s0: DCDC_REG4 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <550000>;
                regulator-max-microvolt = <950000>;
                regulator-init-microvolt = <750000>;
                regulator-ramp-delay = <12500>;
                regulator-name = "vdd_vdenc_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            /* DDR 轨: 不写 min/max —— 电压由 DDR blob 专管, 内核不动 (见 4 号坑) */
            vdd_ddr_s0: DCDC_REG5 {
                regulator-always-on;
                regulator-boot-on;
                regulator-ramp-delay = <12500>;
                regulator-name = "vdd_ddr_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                    regulator-suspend-microvolt = <850000>;
                };
            };

            vdd2_ddr_s3: DCDC_REG6 {
                regulator-always-on;
                regulator-boot-on;
                regulator-name = "vdd2_ddr_s3";       /* S3 保留: 内存自刷新 */
                regulator-state-mem {
                    regulator-on-in-suspend;
                };
            };

            vcc_2v0_pldo_s3: DCDC_REG7 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <2000000>;
                regulator-max-microvolt = <2000000>;
                regulator-name = "vdd_2v0_pldo_s3";
                regulator-state-mem {
                    regulator-on-in-suspend;
                    regulator-suspend-microvolt = <2000000>;
                };
            };

            vcc_3v3_s3: DCDC_REG8 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <3300000>;
                regulator-max-microvolt = <3300000>;
                regulator-name = "vcc_3v3_s3";
                regulator-state-mem {
                    regulator-on-in-suspend;
                    regulator-suspend-microvolt = <3300000>;
                };
            };

            vddq_ddr_s0: DCDC_REG9 {
                regulator-always-on;
                regulator-boot-on;
                regulator-name = "vddq_ddr_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            vcc_1v8_s3: DCDC_REG10 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <1800000>;
                regulator-max-microvolt = <1800000>;
                regulator-name = "vcc_1v8_s3";
                regulator-state-mem {
                    regulator-on-in-suspend;
                    regulator-suspend-microvolt = <1800000>;
                };
            };

            avcc_1v8_s0: PLDO_REG1 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <1800000>;
                regulator-max-microvolt = <1800000>;
                regulator-name = "avcc_1v8_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            vcc_1v8_s0: PLDO_REG2 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <1800000>;
                regulator-max-microvolt = <1800000>;
                regulator-name = "vcc_1v8_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                    regulator-suspend-microvolt = <1800000>;
                };
            };

            avdd_1v2_s0: PLDO_REG3 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <1200000>;
                regulator-max-microvolt = <1200000>;
                regulator-name = "avdd_1v2_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            vcc_3v3_s0: PLDO_REG4 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <3300000>;
                regulator-max-microvolt = <3300000>;
                regulator-name = "vcc_3v3_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            /* SD 卡 IO 电平轨: 1.8~3.3V 可切, 供 sdmmc 的 vqmmc (UHS-I 用) */
            vccio_sd_s0: PLDO_REG5 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <1800000>;
                regulator-max-microvolt = <3300000>;
                regulator-name = "vccio_sd_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            pldo6_s3: PLDO_REG6 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <1800000>;
                regulator-max-microvolt = <1800000>;
                regulator-name = "pldo6_s3";
                regulator-state-mem {
                    regulator-on-in-suspend;
                    regulator-suspend-microvolt = <1800000>;
                };
            };

            vdd_0v75_s3: NLDO_REG1 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <750000>;
                regulator-max-microvolt = <750000>;
                regulator-name = "vdd_0v75_s3";
                regulator-state-mem {
                    regulator-on-in-suspend;
                    regulator-suspend-microvolt = <750000>;
                };
            };

            vdd_ddr_pll_s0: NLDO_REG2 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <850000>;
                regulator-max-microvolt = <850000>;
                regulator-name = "vdd_ddr_pll_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                    regulator-suspend-microvolt = <850000>;
                };
            };

            avdd_0v75_s0: NLDO_REG3 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <837500>;
                regulator-max-microvolt = <837500>;
                regulator-name = "avdd_0v75_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            vdd_0v85_s0: NLDO_REG4 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <850000>;
                regulator-max-microvolt = <850000>;
                regulator-name = "vdd_0v85_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };

            vdd_0v75_s0: NLDO_REG5 {
                regulator-always-on;
                regulator-boot-on;
                regulator-min-microvolt = <750000>;
                regulator-max-microvolt = <750000>;
                regulator-name = "vdd_0v75_s0";
                regulator-state-mem {
                    regulator-off-in-suspend;
                };
            };
        };
    };
};
```

### 2.3 大核 / NPU: RK860x 分立 DCDC

```
&i2c0 {
    status = "okay";
    pinctrl-0 = <&i2c0m2_xfer>;

    /* 双标签: cpu-supply 与 mem-supply 引用同一颗芯片 */
    vdd_cpu_big0_s0: vdd_cpu_big0_mem_s0: rk8602@42 {
        compatible = "rockchip,rk8602";
        reg = <0x42>;
        vin-supply = <&vcc5v0_sys>;
        regulator-compatible = "rk860x-reg";
        regulator-name = "vdd_cpu_big0_s0";
        regulator-min-microvolt = <550000>;
        regulator-max-microvolt = <1050000>;
        regulator-ramp-delay = <2300>;
        rockchip,suspend-voltage-selector = <1>;  /* 挂起走硬件电压档 1 */
        regulator-boot-on;
        regulator-always-on;
        regulator-state-mem {
            regulator-off-in-suspend;
        };
    };

    vdd_cpu_big1_s0: vdd_cpu_big1_mem_s0: rk8603@43 {
        compatible = "rockchip,rk8603";
        reg = <0x43>;
        vin-supply = <&vcc5v0_sys>;
        regulator-compatible = "rk860x-reg";
        regulator-name = "vdd_cpu_big1_s0";
        regulator-min-microvolt = <550000>;
        regulator-max-microvolt = <1050000>;
        regulator-ramp-delay = <2300>;
        rockchip,suspend-voltage-selector = <1>;
        regulator-boot-on;
        regulator-always-on;
        regulator-state-mem {
            regulator-off-in-suspend;
        };
    };
};

&i2c1 {
    status = "okay";
    pinctrl-0 = <&i2c1m2_xfer>;

    vdd_npu_s0: vdd_npu_mem_s0: rk8602@42 {
        compatible = "rockchip,rk8602";
        reg = <0x42>;
        vin-supply = <&vcc5v0_sys>;
        regulator-compatible = "rk860x-reg";
        regulator-name = "vdd_npu_s0";
        regulator-min-microvolt = <550000>;
        regulator-max-microvolt = <950000>;       /* NPU 上限比 CPU 低 100mV */
        regulator-ramp-delay = <2300>;
        rockchip,suspend-voltage-selector = <1>;
        regulator-boot-on;
        regulator-always-on;
        regulator-state-mem {
            regulator-off-in-suspend;
        };
    };
};
```

　　注意: RK3588S 板 NPU 在 i2c2 (源码用 `#ifdef rk3588` 区分, 0x42 地址不变);
big0/big1 的 max 1050000 比 GPU/NPU 的 950000 高 —— 大核 OPP 表上限更高,
范围写小了 cpufreq 会报电压不支持。

### 2.4 消费者: cluster / GPU / NPU 的供电链接

　　调频调压的驱动通过 "xxx-supply" 属性找到自己的电源; 没有这一层, PMIC 配得
再对也不会被动态调压:

```
&cpu_l0 {                       /* A55 四核簇的代表核 (l0~l3 同轨) */
    cpu-supply = <&vdd_cpu_lit_s0>;
    mem-supply = <&vdd_cpu_lit_mem_s0>;
};

&cpu_b0 {                       /* A76 簇 0 代表核 (b0/b1 同轨) */
    cpu-supply = <&vdd_cpu_big0_s0>;
    mem-supply = <&vdd_cpu_big0_mem_s0>;
};

&cpu_b2 {                       /* A76 簇 1 代表核 (b2/b3 同轨) */
    cpu-supply = <&vdd_cpu_big1_s0>;
    mem-supply = <&vdd_cpu_big1_mem_s0>;
};

&gpu {
    mali-supply = <&vdd_gpu_s0>;
    mem-supply  = <&vdd_gpu_mem_s0>;
    status = "okay";
};

&rknpu {
    rknpu-supply = <&vdd_npu_s0>;
    mem-supply   = <&vdd_npu_mem_s0>;
    status = "okay";
};
```

　　mem-supply 与主轨由同一颗 DCDC 出 (双标签), 驱动调压时两轨同步 —— 硬件上
就是一组电感, 软件上必须两个名字都给, 少一个该模块调压链装配不上。

### 2.5 板级 GPIO 门控轨

　　四个代表性写法, 覆盖全部常见形态:

```
/* 形态 1: 普通 GPIO 门控 (PCIE 3.3V, 12V 直入) */
vcc3v3_pcie30: vcc3v3-pcie30 {
    compatible = "regulator-fixed";
    regulator-name = "vcc3v3_pcie30";
    regulator-min-microvolt = <3300000>;
    regulator-max-microvolt = <3300000>;
    enable-active-high;
    gpio = <&gpio2 RK_PC5 GPIO_ACTIVE_HIGH>;
    vin-supply = <&vcc12v_dcin>;
};

/* 形态 2: SD 卡座供电, 上游是 PMIC 的 3.3V s3 轨, 还要给 sdmmc 当 vmmc */
vcc3v3_sd_s0: vcc3v3-sd-s0 {
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
        regulator-off-in-suspend;
    };
};
/* 对应的消费者 (sdmmc 节点里):
     vmmc-supply = <&vcc3v3_sd_s0>;     卡座供电
     vqmmc-supply = <&vccio_sd_s0>;     IO 电平 1.8/3.3 切换 (UHS-I) */

/* 形态 3: USB host VBUS 5V 门控 (给外设供电, 上游 5V 链) */
vcc5v0_usb_host: vcc5v0-usb-host {
    compatible = "regulator-fixed";
    regulator-name = "vcc5v0_usb_host";
    regulator-boot-on;
    regulator-always-on;
    enable-active-high;
    regulator-min-microvolt = <5000000>;
    regulator-max-microvolt = <5000000>;
    gpio = <&gpio4 RK_PB5 GPIO_ACTIVE_HIGH>;
    vin-supply = <&vcc5v0_usb>;
};

/* 形态 4: 扩展芯片 GPIO (pca9555) 门控的屏供电, 与背光 12V 分开 */
vcc3v3_mipi: vcc3v3-mipi {
    compatible = "regulator-fixed";
    regulator-name = "vcc3v3_mipi";
    regulator-boot-on;
    regulator-always-on;
    enable-active-high;
    gpio = <&pca9555 PCA_IO0_6 GPIO_ACTIVE_HIGH>;
};

vcc12v_bp: vcc12v-bp {
    compatible = "regulator-fixed";
    regulator-name = "vcc12v_bp";
    regulator-boot-on;
    regulator-always-on;
    enable-active-high;
    gpio = <&gpio1 RK_PB3 GPIO_ACTIVE_HIGH>;
};
```

　　两个细节: ①同一条物理轨可以拆成多个 dts 节点用同一个 enable 脚
(如 vcc3v3_sata0 与 vcc3v3_pcie20_1l2 共用 GPIO1_D7) —— 多个消费者各引各的
label, 实际是一个开关; ②屏的 VBUS 供电 (vbus5v0_typec_charge) 在 SG 板来自
SC8886 的 otg-vbus 子节点, 不在本节范围, 见 charging.md。

### 2.6 三种"常开"语义与挂起策略

| 属性 | 语义 | 缺了会怎样 |
|---|---|---|
| regulator-always-on | probe 时使能且**永不许关**, 无消费者也不关 | 轨在启动后期被当 unused 关掉, 外设莫名失电 |
| regulator-boot-on | 保持上电时状态, 但无人用时启动末期会被回收 | 单用它撑常开轨 = 埋雷 |
| regulator-state-mem + on/off-in-suspend | 挂起 (S3) 时该轨开/关 | 策略与硬件 sleep 线不一致时挂起/唤醒异常 |
| regulator-suspend-microvolt | 挂起期间的电压 (配合 on-in-suspend) | — |
| regulator-init-microvolt | **U-Boot 专用**初值, 内核不解析 | 无内核影响, 改了没反应属正常 |

　　判断口诀: 常开域 (DDR/RTC/3.3V s3) 一律 always-on + boot-on 双标;
能挂起断电的域 (GPU/NPU/大核) 只 boot-on + state-mem 关。

## 3. 验证测试

```
# 1. 全树一眼: 层级/电压/状态/消费者数, 缩进即 vin-supply 父子链
cat /sys/kernel/debug/regulator/regulator_summary

# 2. 单轨状态与实时电压
for f in /sys/class/regulator/regulator.*; do
    n=$(cat $f/name); [ "$n" = "vdd_cpu_big0_s0" ] && echo $f && cat $f/state $f/microvolts
done

# 3. 启动期注册/回收日志 (unused 关轨在这里现形)
dmesg | grep -iE "rk806|rk860|regulator"

# 4. cpufreq 联动: 拉高 cpu4 (大核) 频率, 回看 summary 里 vdd_cpu_big0_s0 电压变化
cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_cur_freq
cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_available_frequencies
```

万用表点位对照 (软件认为 vs 实测, 上电逐级量):

| 测点 | 期望值 | 对不上时先查 |
|---|---|---|
| DC 输入座 | 12V | 适配器/保险丝 |
| PMIC 附近 5V (vcc5v0_sys) | 5.0V | 板级 12V→5V DCDC (硬件) |
| 大核供电电感 | 0.6~1.0V 随频变 | rk860x I2C 地址 / cpu-supply 链接 |
| DDR 供电电感 | 按 DDR 类型定 | 别查 dts, 查 DDR blob 配置 |
| vcc_3v3_s3 / vcc_1v8_s3 | 3.3V / 1.8V 常在 | PMIC DCDC8/10 |
| GPIO 门控轨 (如 pcie30) | 使能后 3.3V | GPIO 脚/极性/上游 12V |

挂起验证: `echo mem > /sys/power/state` 前后各打一次 regulator_summary,
对照各轨 on/off 是否与 state-mem 策略一致, 唤醒后全部恢复。

## 4. 排障与坑

| 现象 | 根因 | 处理 |
|---|---|---|
| 某外设启动后期莫名失电, dmesg 有 `disabling unused regulator` | 轨漏标 always-on, 或只有 boot-on 且无消费者 | 常开域补 always-on (见 2.6 口诀) |
| 大核不调频不调压, cpufreq 报 supply 错误 | cpu-supply/mem-supply 链接缺失, 或 rk860x 没 probe (I2C 地址/引脚错) | 先 `dmesg | grep rk860` 看 probe, 再查 2.4 |
| 编译报 undefined label (vdd_cpu_big0_mem_s0) | 双标签只写了一个 | mem 与主轨标签写同一节点 (见 2.3) |
| 改了 regulator-init-microvolt 内核没反应 | 该属性是 U-Boot 用的, 内核 rk806 驱动不解析 | 属预期; 要改进内核初值走 boot-on + OPP |
| DDR 轨电压异常/随机死机 | 给 vdd_ddr_s0 加了 min/max 或手调电压 | DDR 电压由 DDR blob 专管, dts 不写范围不动它 |
| GPIO 门控轨永远没电压 | 极性反了 (enable-active-high 与硬件不符) 或上游 12V 没进 | 先量上游, 再量 enable 脚电平, 最后看极性 |
| 两块板抄同一轨电压范围, 一块报错 | EVB 与 Firefly 的 DCDC10/1.1V LDO 级联方式不同 (见 1.2) | 以本板原理图为准, 不跨板混抄 |
| SG 电池板无电池黑屏重启 | 供电源其实是 SC8886 SYS, 不是 12V 直入 | 见 charging.md (U-Boot 电源初始化已修, PD 坑在 typec.md) |
| 挂起后唤醒源失效/RTC 掉电 | 动了 s3 轨的 state-mem 策略 | s3 轨策略与硬件 sleep 线配套, 改前想清挂起需求 |
| spi2 引脚被占 | PMIC 占用 spi2m2, 别再配给其他外设 | 引脚冲突按 README 方法论反查 |

## 5. 职责边界

　　本篇只管"电从哪来到哪去"与 PMIC/DCDC 适配。以下话题在各自文档:

- 电池充放电 (CW2017/SC8886/PD 三芯片联动) → charging.md;
- Type-C PD 协商与 DP 复用 → typec.md;
- RTC (hym8563, 32K 输出给 WiFi/BT) → rtc.md;
- WiFi/BT 的 reg_on/时钟使能 → wifi-bt.md;
- 屏幕背光 PWM (backlight_1 节点) → mipi-dsi.md / edp.md / lvds.md;
- SD 卡完整链路 (vmmc/vqmmc 之外的部分) → sdcard.md。
