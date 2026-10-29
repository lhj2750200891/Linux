# LED

　　K3 平台 GPIO 指示灯适配笔记: 通过内核标准 gpio-leds 框架驱动板上的电源/用户
LED。以 Firefly AIBOX-PRO-K3 (k3-firefly-aibox-pro.dts) 为参考板, 覆盖 LED 的
GPIO 编号换算、pinctrl 电气配置、内核配置陷阱与验证方法。

## 1. 原理

### 1.1 gpio-leds 框架

　　内核 `drivers/leds/leds-gpio.c` (驱动名 leds-gpio, 匹配 compatible
"gpio-leds") 把设备树 `gpio-leds` 节点下的每个子节点注册成一个 LED 类设备,
出现在 `/sys/class/leds/<label>/`。每个子节点两个关键属性:

- `gpios`: 引用的 GPIO 及极性 (`GPIO_ACTIVE_HIGH` 高电平点亮 /
  `GPIO_ACTIVE_LOW` 低电平点亮), 内核自动做极性翻转, 用户态只管写 0/1。
- `linux,default-trigger`: 触发器 (heartbeat 心跳闪 / timer 定时闪 /
  default-on 开机亮等), 控制灯的自动行为; 不写则纯手动控制。

### 1.2 K3 的 GPIO 编号体系 (与 RK3588 最大的差异)

　　K3 全 SoC 只有 **一个** GPIO 控制器 (`gpio: gpio@d4019000`, compatible
"spacemit,k3-gpio", 位于 k3.dtsi), 4 组 × 32 个 = **128 个全局编号的 GPIO**。
设备树引用时用 `K3_GPIO(x)` 宏把全局编号拆成 `<bank pin>` 两格:

```c
/* k3.dtsi 顶部定义 */
#define K3_GPIO(x) ((x) / 32) ((x) % 32)
```

| 全局编号 | K3_GPIO(x) 展开值 | 含义 |
|---|---|---|
| 45 | `<1 13>` | bank1 第 13 脚 |
| 75 | `<2 11>` | bank2 第 11 脚 |
| 122 | `<3 26>` | bank3 第 26 脚 |

　　设备树写法 `<&gpio K3_GPIO(45) GPIO_ACTIVE_HIGH>`, 宏在 dts 编译期展开,
`#gpio-cells = <3>` (bank + pin + 标志)。裸写 `<&gpio 1 13 ...>` 等价但难读,
推荐统一用宏。

### 1.3 引脚复用与电气配置

　　K3 的 pinctrl 控制器是 `pinctrl: pinctrl@d401e000` (k3.dtsi), 驱动
`drivers/pinctrl/spacemit/pinctrl-k1.c` (CONFIG_PINCTRL_SPACEMIT_K1, 随
ARCH_SPACEMIT 默认 y, 无需手动开)。板级 pinctrl 组写在 `&pinctrl {}` 包装下,
每个引脚一个子节点:

```c
K3_PADCONF(pad, func) = ((pad) << 16) | (func)   /* k3-pinctrl.dtsi 定义 */
```

- `pad` = 全局引脚号 (与 GPIO 全局编号同一编号空间), `func` = 复用功能号,
  **0 即 GPIO 功能**。
- 同节点可带的电气属性 (pinctrl-k1.c 解析): `bias-disable` (关上下拉)、
  `bias-pull-up/pull-down`、`drive-strength = <25>` (驱动能力档位)、
  `power-source = <3300>` (IO 电压域 3.3V) 或 `<1800>` (1.8V 域)。
- **power-source 必须与硬件实际接的 IO 域一致**, 配 1800 而引脚物理在 3.3V 域
  会驱动异常; 照抄参考板前先确认自己板子的 bank 供电。

## 2. 硬件连接

　　参考板: AIBOX-PRO-K3。三颗 LED 均为 GPIO 直接推灯 (串联限流电阻在板上),
高电平点亮, 无需外部供电使能脚。

| 功能 | 颜色/标号 | 全局 GPIO | 换算 bank-pin | 复用功能号 | 极性 | 默认态 |
|---|---|---|---|---|---|---|
| 电源指示 | 蓝色 power | GPIO45 | bank1_13 | func 0 (GPIO) | 高电平亮 | 上电常亮 |
| 用户灯 | 绿色 user | GPIO75 | bank2_11 | func 0 (GPIO) | 高电平亮 | 灭 |
| 用户灯 2 | 红色 user1 | GPIO122 | bank3_26 | func 0 (GPIO) | 高电平亮 | 灭 |
| RS485 方向指示 | - | GPIO51 | bank1_19 | func 0 (GPIO) | 高电平亮 | 灭 |

接线核对要点:

- 万用表量 LED 阳极应能对地看到 GPIO 翻转电平; 若灯常亮不受控, 优先查
  power-source 电压域配错或极性写反。
- 三颗灯不在同一 bank (1/2/3 各一颗), 自研板换脚时注意各 bank 的 IO 电压域可能
  不同 (AIBOX-PRO 三灯均配 1800)。

## 3. 内核配置

　　`arch/riscv/configs/k3_defconfig` 现状: `CONFIG_NEW_LEDS=y`、
`CONFIG_LEDS_CLASS=y`、`CONFIG_LEDS_TRIGGERS=y`、
`CONFIG_LEDS_TRIGGER_NETDEV=y`。**缺 gpio-leds 驱动本体**, 不补则设备树配了
也不出 LED 设备:

```
# k3_defconfig 需追加:
CONFIG_LEDS_GPIO=y                 # gpio-leds 驱动 (drivers/leds/leds-gpio.c), 缺省未开!

# 常用触发器 (缺省只开了 NETDEV, 按需补):
CONFIG_LEDS_TRIGGER_HEARTBEAT=y    # 心跳闪, 最常用的"系统活着"指示
CONFIG_LEDS_TRIGGER_TIMER=y        # timer 触发器 (delay_on/delay_off 可调)
CONFIG_LEDS_TRIGGER_DEFAULT_ON=y   # 开机常亮
CONFIG_LEDS_TRIGGER_CPU=y          # CPU 活动指示
```

　　pinctrl 驱动 (CONFIG_PINCTRL_SPACEMIT_K1) 与 GPIO 控制器驱动随 SoC 默认
使能, 无需额外配置。

## 4. 设备树配置

　　以下 dts 为**完整自包含版**: 板级文件 (k3-firefly-common.dtsi /
k3-firefly-aibox-pro.dtsi) 的相关内容已全部展开为 `/ {}` 全定义, 不依赖任何
Firefly 板级 include。SoC 基座 include 四件套 `k3.dtsi` + `k3-rdomain.dtsi` +
`k3-pinctrl.dtsi` + `k3_opp_table.dtsi` 保留 (GPIO/pinctrl/RCPU 域/CPU OPP
在其中, 与 RK3588 笔记中 rk3588s.dtsi 的处理同级), 你的 dts 顶部写法见
key.md 4.1 节模板。

### 4.1 方式一: 三色指示灯 (电源/用户/用户 2)

　　参考板: AIBOX-PRO-K3 (FF_LEDS 分支)。加到你的板级 dts (aibox-pro.dts
同级新建的 xxx.dts, 已 include k3.dtsi + k3-pinctrl.dtsi):

```dts
/ {
	leds {
		compatible = "gpio-leds";
		pinctrl-names = "default";
		pinctrl-0 = <&leds_gpio_cfg>;

		power_led: power {
			label = "blue:power";
			default-state = "on";
			/* ir-power-click 是 Firefly 自定义触发器, 6.18 内核不存在,
			 * 自研板换标准触发器, 见 4.3 陷阱说明 */
			linux,default-trigger = "heartbeat";
			gpios = <&gpio K3_GPIO(45) GPIO_ACTIVE_HIGH>;
		};

		user_led: user {
			label = "green:user";
			default-state = "off";
			linux,default-trigger = "timer";
			gpios = <&gpio K3_GPIO(75) GPIO_ACTIVE_HIGH>;
		};

		user1_led: user1 {
			label = "red:user1";
			default-state = "off";
			/* 不写 default-trigger = 纯手动控制 */
			gpios = <&gpio K3_GPIO(122) GPIO_ACTIVE_HIGH>;
		};
	};
};

&pinctrl {
	leds_gpio_cfg: leds-gpio-cfg {
		leds-gpio-pins {
			pinmux = <K3_PADCONF(45, 0)>, <K3_PADCONF(75, 0)>,
				 <K3_PADCONF(122, 0)>;
			bias-disable;		/* 关上下拉, 推挽直驱 */
			drive-strength = <25>;
			power-source = <1800>;	/* 三脚同在 1.8V 域, 按你板子改 */
		};
	};
};
```

　　说明: 参考板原版 `firefly_leds: leds { status = "okay"; ... }` 是给节点
挂了 label 并带 status 字段, 但 k3.dtsi 中**并不存在** leds 基础节点, 这是
Firefly 的冗余写法; 上面已简化为干净的全定义版, 功能完全一致。

### 4.2 方式二: RS485 收发方向指示灯

　　参考板: AIBOX-PRO-K3 (FF_RS485_UART6 分支)。复用 gpio-leds 框架把收发方向
控制脚同时做成指示灯: RS485 半双工的 DE/\RE 方向脚拉高 = 发送态, 灯亮即"正在
发送"。方向由 uart 驱动控制 (此处只给灯节点, uart 部分见对应串口文档):

```dts
/ {
	rs485_direction_leds: rs485-direction-leds {
		compatible = "gpio-leds";
		pinctrl-names = "default";
		pinctrl-0 = <&rs485_direction_cfg>;

		rs485_direction: rs485-direction {
			label = "RS485_H_SEND_L_RECV";
			gpios = <&gpio K3_GPIO(51) GPIO_ACTIVE_HIGH>;
			default-state = "off";
		};
	};
};

&pinctrl {
	rs485_direction_cfg: rs485-direction-cfg {
		rs485-direction-pin {
			pinmux = <K3_PADCONF(51, 0)>;	/* RS485 /RE+DE 方向脚 */
			bias-disable;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};
};
```

### 4.3 属性速查与陷阱

| 属性 | 值域 | 说明 |
|---|---|---|
| gpios | `<&gpio K3_GPIO(N) flag>` | N=0..127 全局编号; flag 高有效/低有效 |
| label | 任意 | 决定 /sys/class/leds/ 目录名 |
| default-state | on / off / keep | keep 保留 bootloader 留下的状态 |
| linux,default-trigger | 内核已编入的触发器名 | 见下方陷阱 |
| retain-state-suspended | bool | suspend 期间保持状态 |
| panic-indicator | bool | kernel panic 时闪烁标记 |

陷阱清单 (参考板存在但内核不认的写法, 自研板勿照抄):

- `linux,default-trigger = "ir-power-click"/"ir-user-click"/"ir-user1-click"`:
  **6.18 内核无此触发器** (grep 全 drivers/ 无匹配), 是 Firefly 用户态约定名;
  设备树照抄不报错但触发器不会绑定, 灯保持 default-state。自研板用
  heartbeat/timer/default-on 等标准触发器, 且注意 3 节所述对应 CONFIG_ 要开。
- `compatible = "firefly,led"` (FF_LEDS 未定义时的 #else 分支): 内核**无此驱动**,
  是遗留写法, 勿用。
- LEDS_GPIO 没编进内核时, 设备树完全正确但 `/sys/class/leds` 下什么都没有,
  dmesg 也不会报错 (节点无人匹配) — 排查先查 3 节配置。

## 5. 验证测试

```bash
# 1. LED 设备是否注册 (三个 label 应在列)
ls /sys/class/leds/

# 2. 手动点亮/熄灭 (不留触发器的红绿灯)
echo 255 > /sys/class/leds/red\:user1/brightness   # 亮
cat    /sys/class/leds/red\:user1/brightness       # 读回状态
echo 0   > /sys/class/leds/red\:user1/brightness   # 灭

# 3. 触发器验证 (蓝灯心跳闪)
cat /sys/class/leds/blue\:power/trigger            # 当前触发器带[]的是激活项
echo heartbeat > /sys/class/leds/blue\:power/trigger

# 4. timer 触发器自定义闪烁周期 (毫秒)
echo timer > /sys/class/leds/green\:user/trigger
echo 200 > /sys/class/leds/green\:user/delay_on
echo 800 > /sys/class/leds/green\:user/delay_off

# 5. 引脚复用状态核实 (确认 func 已切 GPIO 且方向输出)
cat /sys/kernel/debug/pinctrl/*/pinmux-pins | grep -E "45|75|122"
# 输出应显示对应 pin 处于 leds_gpio_cfg 组、function 为 gpio

# 6. 无 LED 设备时的排查顺序
#    a) zcat /proc/config.gz | grep LEDS_GPIO   -> 未编入 (最常见)
#    b) ls /sys/bus/platform/devices/ | grep d4019000   -> GPIO 控制器没起来
#    c) dmesg | grep -i "led"                   -> probe 报错
```
