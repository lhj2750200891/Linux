# 充放电

　　CW2017 电量计 + SC8886 充电芯片 + FUSB302 PD 三芯片协同的完整充放电系统,
含原理/联动链路/完整设备树/驱动移植/验证。参考板 AIO-3588SG (Firefly RK3588
板中唯一带电池充放电的板型)。

## 1. 原理: 三芯片充放电系统

　　先读这节再动 dts: 充放电不是"一个驱动 + 一个节点", 而是三颗芯片通过
power_supply 框架互链, 少一条链接就少一个功能。

### 1.1 系统架构 (物理链路)

```
适配器 (PD / BC1.2 / DC)
  │ VBUS 5~12V (PD 协商档位)
  ▼
┌───────────────────────────────┐
│ SC8886 充电芯片 (I2C4, 0x6b)    │  功率级: buck-boost 充电
│   VBUS ──► SYS ──► BAT (NVDC)  │──► SYS: 整板供电 (VSYS≥6.144V 保底)
│   OTG 反向: BAT ──► VBUS 5V    │──► BAT: 2S 电池充电 (≤8.4V/2A)
└───────────────────────────────┘
  ▲ I2C 控制/状态/中断        ▲ 电池电压采样
┌──────────┐            ┌──────────────┐
│ FUSB302  │            │ CW2017 电量计 │
│ CC/PD    │            │ (I2C4, 0x63) │──► SOC%/电压/温度/状态
│ (I2C2)   │            └──────────────┘
└──────────┘              电池组侧
```

　　充电主路径是 NVDC (Nominal Voltage DC) 架构: 适配器电压先进 SC8886 降到
系统电压 SYS, 电池挂 SYS 与 BAT 之间。好处是适配器插入瞬间系统不闪断
(VSYS_MIN 兜底), 电池深放时系统照常工作, OTG 时电池反向升压输出 5V。

### 1.2 为什么是"电量计 + 充电芯片"两颗芯片

　　职责完全正交, 谁也替代不了谁:

- SC8886 (南芯, 兼容 TI bq25703): 只管功率。充/放电开关、电流电压调节、
  输入限流 (IINDPM) / 输入欠压 (VINDPM)、故障保护。它内部有 ADC 能量
  电池电压和电流, 但**没有容量算法**——不知道"还剩多少电"
- CW2017 (赛微 CellWise): 只管感知。挂在电池侧持续采样电池电压, 用 80 字节
  电池特性曲线换算出 SOC 百分比、温度、状态。**没有任何功率能力**,
  开不了充电路径, 也感知不到 VBUS
- FUSB302: 只管协议。CC 线检测插拔/方向, PD 协商出"用多少伏多少安"
  的合同, 自己也没有功率路径

　　所以"充"靠 SC8886, "显示还剩多少电"靠 CW2017, "跟适配器谈条件"靠
FUSB302。三者在软件层互为输入输出 (见 1.4)。

### 1.3 内核软件框架: power_supply class 三设备

　　三颗芯片在 /sys/class/power_supply/ 下注册三个电源设备:

| 设备 | 驱动 | type | 关键属性 |
|---|---|---|---|
| cw2017-battery | cw2017_battery.c | BATTERY | capacity/status/voltage_now/temp/charge_full_design |
| bq25700-charger | bq25700_charger.c | USB | online/status/constant_charge_current/input_current_limit |
| tcpm-source-psy-* | tcpm (fusb302) | USB | PD 合同的 voltage_now/current_now/online |

　　用户态 (UPower / Android healthd / 桌面电池图标) 只看这三个节点,
所有联动都在内核 power_supply 框架内完成。

### 1.4 三条联动链路 (源码依据 → 为什么 dts 要那几个 phandle)

　　**链路 1 — PD 联动 (高压快充):**

```
fusb302 probe → tcpm 状态机 → PD 协商完成 (9V/12V) → psy 属性更新
  → power_supply_changed 广播 → bq2570x_pd_notifier_call (bq25700 驱动)
  → 按 ti,usb-charger-detection 过滤出事件源 → 读合同电压/电流
  → 写寄存器 INPUT_CURRENT / INPUT_VOLTAGE / CHARGE_CURRENT
```

- 为什么必须 `ti,usb-charger-detection = <&usbc0>`: power_supply 事件是
  全局广播的, 驱动靠这个 phandle 比对 `psy->dev.parent->of_node` 过滤
  "是不是我的 Type-C 口发的"; probe 时还读该 psy 的 CURRENT_MAX/VOLTAGE_MAX
  预设初始输入。没这条, PD 只跑 5V 默认输入, 高压档全废
- 寄存器编码细节: VINDPM 阈值 = PD 合同电压 − 1.28V (预留线损),
  代码里 `find_idx(voltage − 1280000 − 3200000, TBL_INPUTVOL)` 的
  −1.28V 即此意, −3.2V 是寄存器基准偏移

　　**链路 2 — BC1.2 联动 (普通 USB 口 / 充电头):**

```
u2phy0 (USB2 PHY 自带 BC1.2 检测) → extcon 事件 SDP/DCP/CDP
  → bq25700_charger_evt_handel → 按 ti,input-current-sdp/dcp/cdp
  写 INPUT_CURRENT + CHARGE_CURRENT → 启动充电
```

- 为什么 `extcon = <&u2phy0>`: RK 平台的 BC1.2 (SDP=PC 口 / DCP=充电头 /
  CDP=带数据充电口) 由 USB2 PHY 实现, SC8886 芯片本身不做 BC1.2
- **have_battery 守门**: evt_handel 开头 `if (!have_battery) goto no_battery`
  —— 无电池的板插充电器不启用充电路径。have_battery 是 cw2017 驱动
  probe 时用 TEMP_MIN 奇偶校验测出并导出的全局变量, 是两个驱动之间
  唯一的直接耦合
- `pd-charge-only = <1>` 时整条 BC1.2 链路被跳过 (只认 PD), 口子上没有
  USB2 数据线/不需要 BC1.2 的板子用它

　　**链路 3 — 状态上报 (电量显示):**

```
cw2017 轮询 work (monitor-interval-ms, 默认 8s)
  → power_supply_am_i_supplied → 沿 power-supplies phandle 找到
    bq25700-charger → 读其 ONLINE (=寄存器 AC_STAT, 适配器在位)
  → charger_attached → status = CHARGING / DISCHARGING / FULL (soc≥100)
  → power_supply_changed → 用户态 uevent
```

- 为什么 cw2017 节点要 `power-supplies = <&sc8886>`: cw2017 自己感知不到
  VBUS, 靠电源框架查充电芯片的 ONLINE 得出"插没插充电器"
  (power_supply_core.c 解析 power-supplies 建立 supplied_to 关系)
- bq25700-charger 的 ONLINE 不用任何软件状态, 直接来自芯片 AC_STAT
  寄存器位, 插拔事件由 INT 中断 (GPIO4_C1) 驱动刷新

　　**四条 phandle 汇总 (改错一处断一链):**

| 属性 | 挂在哪 | 指向 | 作用 | 6.12 驱动是否解析 |
|---|---|---|---|---|
| ti,usb-charger-detection | sc8886 | &usbc0 | PD 事件源过滤 (链路 1) | 是 |
| extcon | sc8886 | &u2phy0 | BC1.2 事件源 (链路 2) | 是 |
| power-supplies | cw2017 | &sc8886 | 查充电器在位 (链路 3) | 是 |
| vbus-supply | fusb302 | otg-vbus regulator | OTG 时开 5V VBUS | 是 (tcpm) |
| charge-dev | fusb302 | &sc8886 | 关联充电芯片 | **否 (遗留属性)** |

### 1.5 compatible 对比: 为什么 SC8886 写 "ti,bq25703"

　　SC8886 是南芯对 TI bq25703 的引脚兼容芯片, 寄存器布局相同。
bq25700_charger.c 一套驱动支持四个 compatible:

```
ti,bq25700  /  ti,bq25703  /  southchip,sc8885  /  southchip,sc8886
```

- 寄存器 map 选择 (probe 开头): 全设备树搜 `ti,bq25700` 或 `sc8885` 节点,
  搜到用 bq25700 map (寄存器 0x12/0x14/0x15 起, 最大 0xFF);
  搜不到用 bq25703 map (寄存器 0x00/0x02/0x04 起, 最大 0x3B)。
  SG 板只有一颗 sc8886 且 compatible = ti,bq25703 → 走 bq25703 map ✓
- chip id 校验: DEVICE_ID 寄存器 bq25700=0x59 / bq25703=0x58, 仅读取记录
- 写 `southchip,sc8886` 与 `ti,bq25703` 的唯一功能差异
  (bq25700_fw_read_u32_props): OTG 电压表换成 sc8886 专属档
  {1.28V–20.8V, 步进 128mV}, 且强校验 ti,otg-voltage ≥ 4.28V。
  两者寄存器 map 相同, 常规 5V OTG 配置下效果一致

　　结论: 写哪个都能跑。SG 用 `ti,bq25703`; 若芯片确认是 SC8886 且需要
更细的 OTG 电压档, 写 `southchip,sc8886`。不要写 `ti,bq25700`
(寄存器 map 完全不同, 必然 probe 失败)。

### 1.6 cw2017 与 sc8886 全方位对比

| 维度 | CW2017 (电量计) | SC8886 (充电芯片) |
|---|---|---|
| 芯片角色 | fuel gauge, 只采样 | charger, 功率路径 |
| 功率能力 | 无 | buck-boost, 充电 ≤8.128A / OTG ≤6.35A |
| I2C 地址 | 0x63 | 0x6b |
| 内核驱动 | cw2017_battery.c (715 行) | bq25700_charger.c (2174 行) |
| compatible | cellwise,cw2017 | ti,bq25703 (或 southchip,sc8886) |
| Kconfig | BATTERY_CW2017 | CHARGER_BQ25700 |
| power_supply 名 | cw2017-battery | bq25700-charger |
| power_supply 类型 | BATTERY | USB |
| 上报属性 | capacity/voltage/temp/status | online/status/charge_current/limits |
| 关键寄存器 | VCELL/SOC/BATINFO(80B) | CHARGE_CURRENT/MAX_CHARGE_VOLTAGE/INPUT_* |
| 中断 | 无 (纯轮询) | INT GPIO4_C1 (AC_STAT 变化触发) |
| 输入来源 | 电池电压采样 | VBUS (PD/BC1.2/DC) |
| 与对方联动 | power-supplies 查 ONLINE | have_battery 守门 |
| 配置重心 | 电池特性曲线 (profile) | 充电参数 (8 个 ti,* 属性) |

### 1.7 CW2017 SOC 算法要点 (为什么 profile 不能抄错)

- `cellwise,battery-profile` 80 字节 = 电池特性曲线 (batinfo), 由
  CellWise 官方工具按电池型号生成, probe 时烧进芯片。cw_init 会对比
  寄存器内已有内容, 不一致就重传并重新使能
- 换电池规格 (容量/化学体系/内阻) 必须换 profile, 否则 SOC 跳变或不准;
  不写 profile 时驱动沿用芯片 flash 已有内容并告警 (首次贴片芯片是空的)
- `cellwise,dual-cell`: 2S 双节时芯片按单节采样, 驱动电压读数 ×2 上报
- SOC 迟滞滤波 (cw_get_soc): 充电中突降 >3% 丢弃 (电压跌落假象),
  放电中突升 >3% 丢弃; SOC 连续无效 >40s 或充电中卡死 >30min 自动复位电量计
- 容量上报优先级: monitored-battery 节点的 charge_full_design_uah >
  `cellwise,design-capacity-amh` × 1000 (µAh); SG 无 monitored-battery
  节点, 走后者 (5000mAh)
- 6.12 驱动不使用中断: INT/ALERT 引脚可以不接, 纯轮询
  (monitor-interval-ms)。5.10 老驱动用 alert 中断, 移植时别照搬
- 无电池的板 (have_battery=0): SOC 强制报 100%, 这是正常现象

## 2. 硬件连接

　　参考板: AIO-3588SG。

```
SC8886 (I2C4_M3, 地址 0x6b):
  I2C SCL/SDA  ====> I2C4_M3: SCL GPIO1_A3 / SDA GPIO1_A2
  INT          ====> GPIO4_C1 (低有效, 上拉, AC_STAT 变化中断)
  OTG_EN       ====> GPIO4_C0 (otg-mode-en, 高有效, OTG 硬件使能脚)
  放电脚       ====> GPIO1_A5 (typec0-discharge, 高有效,
                     断开适配器时 20ms 脉冲泄放 VBUS 残压)
  VBUS OTG 5V  ====> Type-C 口 VBUS (OTG 对外放电 5V/1.5A)
  BAT±         ====> 2S 锂电池组 (标称 7.4V, 满充 8.4V, 截止 6.0V,
                     设计容量 5000mAh)
  SYS 输出     ====> 板级各路 DCDC 输入 (VSYS ≥ 6.144V 保底)

CW2017 (同一 I2C4_M3, 地址 0x63):
  I2C          ====> 与 SC8886 共总线 (GPIO1_A3 / GPIO1_A2)
  电池电压采样 ====> 电池组侧 (dual-cell: 按单节采样, 上报 ×2)
  INT/ALERT    ====> 未接 (6.12 驱动纯轮询, 不用中断)

FUSB302 (I2C2_M0, 地址 0x22) —— PD 协商, 与 Type-C 模块共用:
  I2C SCL/SDA  ====> I2C2_M0: SCL GPIO0_B7 / SDA GPIO0_C0
  INT          ====> GPIO0_C4 (低有效)
```

　　同一 I2C 总线挂两颗充电芯片是常规布线, 地址 0x63/0x6b 不冲突;
两者都挂在电池/VBUS 域, 注意 I2C 上拉电平域与隔离要求按芯片手册。

## 3. 内核配置

　　SDK rockchip_linux_defconfig 已全部包含, 沿用该 defconfig 不用改;
从零裁剪内核时按此清单核对:

```
CONFIG_BATTERY_CW2017=y            # 电量计 (drivers/power/supply/Kconfig)
CONFIG_CHARGER_BQ25700=y           # 充电芯片 (同一 Kconfig 文件)
CONFIG_TYPEC_TCPM=y                # PD 状态机 (链路 1 的事件源)
CONFIG_TYPEC_FUSB302=y             # CC/PD 芯片
CONFIG_EXTCON=y                    # extcon 框架 (链路 2)
CONFIG_PHY_ROCKCHIP_INNO_USB2=y    # u2phy0 = BC1.2 检测提供者
CONFIG_REGMAP_I2C=y                # 两驱动共同依赖 (Kconfig 自动选)
```

　　为什么 TYPEC_TCPM/FUSB302 也算充电源件: PD 联动链路 1 的事件源就是
tcpm 注册的 power supply。关掉它们 PD 高压协商不工作, SC8886 只能按
BC1.2 默认电流充电。

## 4. 设备树配置

　　参考: rk3588-firefly-aio-3588sg.dtsi (FF_TYPEC0_FULL 段)。三个节点
强耦合 (四个 phandle 互指), 必须一起配。下面 fusb302 给的是"纯充电口"
版 (无 DP altmode / USB 数据角色, 编译零外部引用, 直接可复制);
若整板要全功能 Type-C, USB/PHY/DP 部分用 typec.md 的完整版, 充电三节点
完全一致。

### 4.1 第一步: FUSB302 节点 (PD 协商, 纯充电版)

```
&i2c2 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c2m0_xfer>;

	usbc0: fusb302@22 {
		compatible = "fcs,fusb302";
		reg = <0x22>;
		interrupt-parent = <&gpio0>;
		interrupts = <RK_PC4 IRQ_TYPE_LEVEL_LOW>;   // INT GPIO0_C4 低有效
		int-n-gpios = <&gpio0 RK_PC4 GPIO_ACTIVE_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&usbc0_int>;
		vbus-supply = <&vbus5v0_typec_charge>; // OTG VBUS 由 SC8886 供
		charge-dev = <&sc8886>;                // 关联充电芯片 (6.12 未解析, 见 4.2)
		suspend-disable-irq;                   // 遗留属性, 6.12 驱动未解析
		status = "okay";

		usb_con: connector {
			compatible = "usb-c-connector";
			label = "USB-C";
			data-role = "dual";
			power-role = "dual";
			try-power-role = "sink";        // 上电默认受电
			op-sink-microwatt = <1000000>;  // 低于 1W 的档放弃
			// PD sink 能力, 档位必须落在 SC8886 输入窗口
			// (3.2~19.52V) 与整板功率预算内
			sink-pdos =
				<PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)
				 PDO_FIXED(9000, 3000, PDO_FIXED_USB_COMM)
				 PDO_FIXED(12000, 2000, PDO_FIXED_USB_COMM)>;
			// OTG 对外放电能力 (source)
			source-pdos =
				<PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)>;
			// 纯充电口: 无 mode-switch/altmodes/ports。
			// USB 数据角色切换 + DP altmode 见 Type-C 模块
		};
	};
};

&pinctrl {
	typec0 {
		usbc0_int: usbc0-int {
			rockchip,pins = <0 RK_PC4 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

　　sink-pdos 为什么最高 12V/2A: 必须落在充电芯片输入窗口
(TBL_INPUTVOL 上限 19.52V) 内, 且按整板输入电容/线损留量; 声明了
20V 而 VINDPM 跟不上会在高压档过流重启。

　　sink-pdos 与 ti,input-current-* 互不覆盖: PD 场景输入电流由合同
动态写入 (链路 1), ti,input-current-sdp/dcp/cdp 只管 BC1.2 场景
(链路 2)。

### 4.2 第二步: SC8886 充电芯片节点

```
&i2c4 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c4m3_xfer>;

	sc8886: sc8886@6b {
		status = "okay";
		compatible = "ti,bq25703";            // SC8886 兼容 bq25703 (见 1.5)
		reg = <0x6b>;
		ti,usb-charger-detection = <&usbc0>; // PD 事件源 (链路 1, 必需)
		interrupt-parent = <&gpio4>;
		interrupts = <RK_PC1 IRQ_TYPE_LEVEL_LOW>;  // INT GPIO4_C1
		otg-mode-en-gpios = <&gpio4 RK_PC0 GPIO_ACTIVE_HIGH>;
		pinctrl-names = "default";
		pinctrl-0 = <&charger_int>;
		extcon = <&u2phy0>;                  // BC1.2 事件源 (链路 2)
		/* ---- 8 个必填 ti,* 属性 (缺一个/超值域 probe 直接失败) ---- */
		ti,charge-current = <2000000>;       // 充电电流 2A (≤0.5C 看电芯)
		ti,max-charge-voltage = <8400000>;   // 2S 满充 8.4V (4.2V/节)
		ti,input-current-sdp = <2500000>;    // BC1.2: PC USB 口
		ti,input-current-dcp = <2500000>;    // BC1.2: 充电头
		ti,input-current-cdp = <2500000>;    // BC1.2: CDP 口
		ti,minimum-sys-voltage = <6144000>;  // VSYS 下限, 深放不掉电
		ti,otg-voltage = <5000000>;          // OTG 输出 5V
		ti,otg-current = <1500000>;          // OTG 输出 1.5A
		/* ---- 行为开关 ---- */
		pd-charge-only = <0>;                // 0=BC1.2 链路也启用
		typec0-discharge-gpios = <&gpio1 RK_PA5 GPIO_ACTIVE_HIGH>;

		regulators {
			// OTG 5V 输出注册为 regulator, 供 fusb302 vbus-supply
			vbus5v0_typec_charge: vbus5v0-typec-charge {
				regulator-compatible = "otg-vbus";
				regulator-name = "vbus5v0_typec_charge";
			};
		};
	};
};

&pinctrl {
	typec0 {
		charger_int: charger-int {
			rockchip,pins = <4 RK_PC1 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

　　8 个必填属性 → 寄存器值域对照 (驱动 bq25700_fw_read_u32_props,
值超上限返回 -ENODEV, probe 失败):

| 属性 | 寄存器 | 值域 | 步进 | SG 取值 |
|---|---|---|---|---|
| ti,charge-current | CHARGE_CURRENT | 0–8128mA | 64mA | 2000000 (2A) |
| ti,max-charge-voltage | MAX_CHARGE_VOLTAGE | 0–19200mV | 16mV | 8400000 (8.4V) |
| ti,input-current-sdp/dcp/cdp | INPUT_CURRENT | 0–6350mA | 50mA | 2500000 |
| ti,minimum-sys-voltage | MIN_SYS_VOTAGE | 1024–16182mV | 256mV | 6144000 |
| ti,otg-voltage | OTG_VOLTAGE | 4480–20800mV (sc8886 compatible: 1280 起/128 步进) | 64mV | 5000000 |
| ti,otg-current | OTG_CURRENT | 0–6350mA | 50mA | 1500000 |

　　各 GPIO 的作用 (为什么有这三个脚):
- otg-mode-en (GPIO4_C0): SC8886 硬件 OTG 使能脚, 驱动 set_otg_vbus
  同时拉 GPIO + 写 EN_OTG 寄存器位, 双保险
- typec0-discharge (GPIO1_A5): 拔掉适配器时驱动输出 20ms 脉冲, 泄放
  Type-C VBUS 残压, 否则再次插拔可能识别不到新插入
- charger INT (GPIO4_C1): AC_STAT 变化中断。驱动按当前电平动态翻转
  触发方式 (AC 在位=低触发, 拔出=高触发), pinctrl 固定配上拉即可

　　**驱动不解析的遗留属性** (SG dtsi 里有, 写不写都不生效, 保留只为
对照原理图/老内核):
- charge-dev (fusb302 上): 6.12 全内核无任何驱动解析
- suspend-disable-irq (fusb302 上): 无解析 (4.19/5.10 老驱动用)
- ti,max-input-voltage / ti,max-input-current / ti,input-current
  (sc8886 上): 6.12 驱动的属性表里没有
- firefly,battery-max-voltage / battery-min-voltage / max-temp / min-temp
  (cw2017 上): 内核不读

　　**可选属性与全树陷阱**:
- ti,battery = <&cw2017>: 写上后 probe 时检查电池是否在线, 不在线则
  -EPROBE_DEFER 等电量计就绪。SG 未用; 装电池的板建议写, 更稳
- 全树不要有名为 usb_bc 的节点: 驱动会全树搜索该节点名, 搜到即改走
  rk_bc_detect 旧通道并忽略 extcon 配置 (从别的板型抄 USB 配置时
  容易误抄进来)
- typec0-enable-gpios / typec1-enable-gpios: 双 Type-C 口充电路径
  切换才需要 (驱动原生支持双口), 单口板不写

### 4.3 第三步: CW2017 电量计节点

```
	cw2017: cw2017@63 {
		status = "okay";
		compatible = "cellwise,cw2017";
		reg = <0x63>;
		// 80 字节电池特性曲线, CellWise 工具按电池型号生成。
		// 下面是 SG 板 2S/5000mAh 电池的 profile
		cellwise,battery-profile = /bits/ 8
			<
			0x3C 0x00 0x00 0x00 0x00 0x00 0x00 0x00
			0xB0 0xC4 0xBF 0xB9 0x9B 0x97 0xE0 0xCF
			0xC1 0xCD 0xBB 0x9D 0x88 0x7C 0x65 0x56
			0x52 0x50 0x4E 0x97 0x79 0xD2 0xDE 0xFF
			0xE5 0xB4 0x71 0x7C 0xB0 0xC5 0xAE 0x93
			0x9D 0xB5 0xCF 0xD5 0xC6 0xB0 0x99 0x89
			0x82 0x85 0x91 0xA8 0xC1 0xC9 0xB0 0x43
			0x00 0x00 0x90 0x02 0x00 0x00 0x00 0x00
			0x00 0x00 0x64 0x00 0x00 0x00 0x00 0x00
			0x00 0x00 0x00 0x00 0x00 0x00 0x00 0xA2
			>;
		cellwise,dual-cell;                    // 2S 双节 (电压上报 ×2)
		cellwise,monitor-interval-ms = <5000>; // 轮询周期 5s (默认 8s)
		cellwise,alert-level = <10>;           // <10% 低电告警阈值
		cellwise,design-capacity-amh = <5000>; // 设计容量 5000mAh
		power-supplies = <&sc8886>;            // 查充电器在位 (链路 3)
	};
```

　　profile 必须正好 80 字节 (驱动 CW2017_SIZE_BATINFO=80), 数量不对
probe 报 -EINVAL。换电池型号必须重新生成 (见 1.7), profile 不写时驱动
沿用芯片 flash 内容并告警——首次贴片的芯片 flash 是空的, 强烈建议写。

　　**profile 怎么拿 (从 0 定制电池)**: 找 CellWise FAE 或电池厂, 按电池
datasheet (容量/内阻/放电曲线/温度特性) 用 CellWise 配套工具生成,
产物即 80 字节十六进制, 直接填入。实在拿不到: 先不写 profile, 系统
可跑但 SOC 不准; 后续拿到再补——驱动 probe 时对比 dts 与芯片 flash
内容, 不一致自动重烧, 换 profile 不需要额外操作。

　　**cw2017 节点要排在 sc8886 之前**: 同一 I2C 总线按节点顺序依次
probe, 电量计先 probe 才能先完成 have_battery 判定; 若充电芯片先
probe, 会走 "no battery" 分支跳过输入电流初始化, BC1.2 路径直到
下一次插拔充电器才正常。

### 4.4 第四步: u2phy0 使能 (BC1.2 依赖)

　　`extcon = <&u2phy0>` 的事件由 USB2 PHY 的 BC1.2 检测产生, PHY 不
使能就没有 SDP/DCP/CDP 事件:

```
&u2phy0 {
	status = "okay";
};

&u2phy0_otg {
	status = "okay";
};
```

　　纯充电口 (USB 数据线没接 dwc3) 也必须做这一步——BC1.2 检测在
PHY 里实现, 与 USB 控制器无关。u2phy0_otg 的完整配置 (typec-vbus-det、
dwc3 role switch 等) 属 Type-C 模块, 纯充电口不需要——不加
typec-vbus-det 时 PHY 用硬件 BVALID 引脚检测 VBUS, BC1.2 自行工作;
SG 加它是因为 vbus 状态要与 TCPM 联动 (改由软件 GRF 位驱动)。

### 4.5 属性速查 (照板改)

　　cw2017:

| 属性 | 说明 |
|---|---|
| cellwise,battery-profile | 80 字节, 按电池型号生成, 必填 80 字节整 |
| cellwise,dual-cell | 2S 电池写, 电压 ×2 上报 |
| cellwise,monitor-interval-ms | 轮询周期, 默认 8000 |
| cellwise,alert-level | 低电告警阈值 %, 0–127 |
| cellwise,design-capacity-amh | 设计容量 mAh, 默认 4000 |
| power-supplies | 指向充电芯片, 断链则 status 永远 Discharging |

　　sc8886:

| 属性 | 说明 |
|---|---|
| ti,usb-charger-detection | PD 事件源 phandle, 断链则 PD 高压失效 |
| extcon | BC1.2 事件源 phandle (u2phy0) |
| ti,charge-current | 充电电流, 按电芯 0.5C 以内定 |
| ti,max-charge-voltage | 满充电压, 节数 ×4.2V (按电芯规格) |
| ti,input-current-sdp/dcp/cdp | BC1.2 三类口输入限流 |
| ti,minimum-sys-voltage | VSYS 保底, 防深放重启 |
| ti,otg-voltage / ti,otg-current | OTG 输出规格 |
| pd-charge-only | 1=只认 PD (跳过 BC1.2) |
| otg-mode-en-gpios | OTG 硬件使能脚 |
| typec0-discharge-gpios | 拔线泄放 VBUS 残压脚 |

## 5. 驱动移植

　　原厂 SDK 已自带两个驱动且 defconfig 已开, **自研板通常零移植**,
只做第 4 节 dts。以下供换内核 / 从零合入时使用:

```
1. 确认源文件
   ls drivers/power/supply/bq25700_charger.c cw2017_battery.c
   # 缺文件时从本 SDK 对应版本拷贝 (文件头有 Rockchip 版权)

2. Kconfig / Makefile 条目 (SDK 均已含)
   drivers/power/supply/Kconfig:   BATTERY_CW2017 / CHARGER_BQ25700
   drivers/power/supply/Makefile:  obj-$(CONFIG_BATTERY_CW2017)  += cw2017_battery.o
                                   obj-$(CONFIG_CHARGER_BQ25700) += bq25700_charger.o

3. defconfig
   CONFIG_BATTERY_CW2017=y
   CONFIG_CHARGER_BQ25700=y
   # 依赖: CONFIG_TYPEC_TCPM / TYPEC_FUSB302 / EXTCON /
   #       PHY_ROCKCHIP_INNO_USB2 / REGMAP_I2C (见第 3 节)

4. 编译验证
   make ARCH=arm64 rockchip_linux_defconfig
   make ARCH=arm64 -j$(nproc)
   # 两个 .o 应编出: drivers/power/supply/cw2017_battery.o
   #                 drivers/power/supply/bq25700_charger.o
```

　　**为什么不能用上游内核驱动**:
- 上游 bq25700 驱动是 bq25700 专用的 charger+fuel-gauge 复合驱动, 没有
  bq25703/sc8886 寄存器 map, 没有 RK 的 PD (ti,usb-charger-detection)
  与 BC1.2 (extcon=u2phy0) 联动, 也没有 otg-vbus regulator —— 换上游
  等于链路 1/2 全断
- 上游 cw2015_battery.c 是 CW2015 单节老驱动, 没有 dual-cell /
  design-capacity-amh / have_battery / 充电迟滞, 与 bq25700 驱动的
  无电池保护也对不上
- RK 版两驱动的耦合点 (have_battery) 是 5.10 商用验证过的无电池保护,
  6.12 SDK 原样保留 —— 移植时不要"顺手清理"这个全局变量

## 6. 验证测试

```
# 1. 驱动 probe
dmesg | grep -E "cw2017|bq25700"
# 期望:
#   cw2017 4-0063: IC version: 0x..
#   cw2017 4-0063: have battery (TEMP_MIN=0x..)     <- have_battery=1
#   Battery profile updated                          <- profile 烧录成功
#   bq25700 4-006b: INPUT_CURRENT:.. INPUT_VOLTAGE:.. CHARGE_CURRENT:..
# 装电池但报 "no battery" → 见问题 2

# 2. I2C 在位
i2cdetect -y 4
# 应见 0x63 与 0x6b 两个 U (cw2017 需电池在位才有电, 不装电池探测不到属正常)

# 3. 电量上报 (用户态视角)
cat /sys/class/power_supply/cw2017-battery/capacity     # SOC %
cat /sys/class/power_supply/cw2017-battery/status       # Charging/Discharging/Full
cat /sys/class/power_supply/cw2017-battery/voltage_now  # 2S: 6000~8400 mV
cat /sys/class/power_supply/cw2017-battery/temp         # 0.1°C
cat /sys/class/power_supply/cw2017-battery/charge_full_design  # 5000000 µAh

# 4. 充电芯片状态
cat /sys/class/power_supply/bq25700-charger/online      # 1=适配器在位(AC_STAT)
cat /sys/class/power_supply/bq25700-charger/status
cat /sys/class/power_supply/bq25700-charger/constant_charge_current
cat /sys/class/power_supply/bq25700-charger/input_current_limit

# 5. 寄存器级调试 (bq25700 专用 sysfs)
echo 1 > /sys/module/bq25700_charger/parameters/dbg_level
cat /sys/bus/i2c/devices/4-006b/charge_info             # dump 全部寄存器到 dmesg
dmesg | tail -40
# 重点看: AC_STAT=1, IN_FCHRG/IN_PCHRG (充电状态位),
#         SET CHARGE_CURRENT 是否为配置值, F_* 故障位是否全 0

# 6. PD 高压联动 (插 PD 适配器)
cat /sys/class/typec/port0/power_role                   # sink
# 协商 9V/12V 后:
dmesg | grep -E "negotiated|INPUT_CURRENT"
cat /sys/class/power_supply/bq25700-charger/voltage_max # 应为协商电压

# 7. 插拔事件 (链路 3 通畅性)
udevadm monitor --kernel --subsystem-match=power_supply
# 插/拔充电器, 应看到 cw2017-battery 与 bq25700-charger 的 CHANGE 事件

# 8. OTG 对外放电 (板子当 source 给外设供电)
# 触发方式: Type-C 口接 sink 设备 (如手机) — tcpm 按 CC 检测自动进
# source 角色并使能 otg-vbus regulator; regulator 的 sysfs state 是
# 只读的, 不能手动 echo 开启, 用观察法:
grep -rl otg-vbus /sys/class/regulator/*/name    # 找到 regulator 目录
cat <上一步目录>/state                            # 触发后应显示 enabled
# 量 Type-C VBUS 应有 5V/1.5A; 拔掉 sink 后 state 回 disabled

# 9. 充电电流确认
# 插适配器: constant_charge_current ≈ ti,charge-current (2A 档 64mA 步进取整)
# 充满: status=Full 且 capacity=100

常见问题:
1. capacity 一直 0 或 100 → profile 没写/不对 (芯片 flash 空),
   dmesg 看 "No battery-profile found"; 无电池板报 100% 属正常 (have_battery=0)
2. 装了电池但报 "no battery" → TEMP_MIN 奇偶校验失败, 实质是 I2C 不通/
   芯片未上电; 先 i2cdetect -y 4 看 0x63
3. 不充电且 online=1 → ti,charge-current=0, 或电池保护板切断;
   charge_info 看 IN_FCHRG/IN_PCHRG 位
4. PD 只协商 5V → ti,usb-charger-detection 没指向 usbc0, 或
   CONFIG_TYPEC_TCPM/FUSB302 没开; 检查 dmesg "automode supported"
5. bq25700 probe 报 -ENODEV → 8 个 ti,* 属性缺一个, 或值超 4.2 节值域表
6. 插充电器系统重启 → 无电池板写了输入电流导致功率路径异常
   (have_battery 守门防的就是它); 检查 cw2017 是否 probe 成功,
   且节点排在 sc8886 之前
7. SOC 跳变 → profile 与电池不匹配, 或 monitor-interval-ms 过短
   电压未稳 (建议 ≥5000)
8. status 永远 Discharging → power-supplies phandle 断了 (链路 3),
   cw2017 查不到充电芯片 ONLINE
9. 纯 DC 输入口 (不走 USB): 去掉 fusb302 节点与链路 1/2, 充电芯片
   只剩默认输入限流 (ti,input-current-sdp); extcon 可不接, dmesg
   "Invalid or missing extcon dev0" 告警可忽略, 充电功能不受影响
```
