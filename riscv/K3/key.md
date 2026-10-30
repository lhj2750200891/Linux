# 按键

　　K3 平台按键适配笔记: GPIO 按键 (gpio-keys) 与 SoC 内置 RPMI 电源键两条
路径。以 Firefly AIBOX-PRO-K3 为参考板, 覆盖按键引脚、去抖、长按监测与内核
配置陷阱。K3 **无 ADC 按键** (k3.dtsi 无 saradc 节点), RK3588 上的 ADC 方案
在此平台无对应物。

## 1. 原理

### 1.1 gpio-keys 框架

　　内核 `drivers/input/keyboard/gpio-keys.c` (CONFIG_KEYBOARD_GPIO, 匹配
compatible "gpio-keys") 把设备树 `gpio-keys` 节点下每个子节点注册成
`/dev/input/eventN` 按键事件。每个子节点:

- `linux,code`: 上报的键值 (KEY_POWER、KEY_F12 等, 定义在
  `dt-bindings/input/input.h`), 用户态 evdev 按键值分发动作。
- `gpios`: 按键引脚与有效电平; 按下接地 (对地短接) 的常规接法配
  `GPIO_ACTIVE_LOW`。
- `debounce-interval`: 去抖毫秒数, 内核在驱动内软件去抖 (对机械按键 30-100ms
  都常见, 参考板取 50)。

### 1.2 KEY_POWER 的特殊地位

　　KEY_POWER 不是普通键: systemd / Android 侧对它有专门处理链 (短按亮屏/
休眠, 长按触发 poweroff 流程), 内核 input 事件也会唤醒 suspend 中的系统
(子节点加 `wakeup-source` 后)。自研板若只要"长按 5 秒关机", 用户态可直接监听
KEY_POWER 长按, 或用 4.2 节 SoC 电源键方案。

### 1.3 SoC 内置电源键 (RPMI)

　　K3 的电源管理在 RCPU (RPMI 固件侧), k3.dtsi 已内置:

```c
rpmi_pwrkey: rpmi_pwrkey@0 {
	compatible = "riscv,rpmi-pwrkey";
	mboxes = <&mpxy_mbox 0xf 0x0>;      /* RPMI mailbox 通道 0xf = 电源服务 */
	interrupt-parent = <&saplic>;
	interrupts = <64 IRQ_TYPE_LEVEL_HIGH>;
	interrupt-names = "rpmi pwrkey";
	status = "okay";                    /* 基座默认开 */
};
```

　　驱动 `drivers/input/misc/pwrkey-rpmi.c` (CONFIG_INPUT_DRV_RPMI_PWRKEY,
k3_defconfig 已 =y), 上报的同样是电源键事件, 来源是 SoC 的 PWRBTN 引脚而非
GPIO。旁边还有一个配套节点 `pwrkey_monitor` (compatible
"spacemit,k3-pwrkey-monitor", 驱动 `drivers/soc/spacemit/pwrkey_monitor.c`,
CONFIG_SPACEMIT_POWERKEY_MONITOR, 基座默认 disabled): 对电源键做长按监测/
强制复位类扩展, 自研板按需打开。

## 2. 硬件连接

　　参考板: AIBOX-PRO-K3。两颗按键均为"一脚接 GPIO、一脚接地"的轻触开关,
按下拉低; 注意两脚在**不同的 IO 电压域** (pinctrl power-source 分别 1800 与
3300)。

| 按键 | 键值 | 全局 GPIO | 换算 bank-pin | 有效电平 | IO 域 | 去抖 |
|---|---|---|---|---|---|---|
| boot (复位/升级键) | KEY_F12 (118) | GPIO69 | bank1_5 | 低电平=按下 | 1.8V | 50ms |
| power (电源键) | KEY_POWER (116) | GPIO84 | bank2_20 | 低电平=按下 | 3.3V | 50ms |
| SoC PWRBTN (RPMI) | KEY_POWER | SoC 专用脚 | - | 固件判定 | - | 固件侧 |

接线核对要点:

- 按键未按下时 GPIO 应读到稳定高电平 (板上拉); 若悬空读数乱跳, 说明板上无
  上拉, 需把 pinctrl 的 `bias-disable` 改 `bias-pull-up` (或硬件加上拉电阻),
  否则去抖也救不了。
- KEY_F12 是".boot 键"借用的普通键值, 只在 bootloader/恢复流程有特殊语义;
  自研板自定义功能键时换任意 KEY_ 值即可, 配合 udev/input 规则或应用层监听。

## 3. 内核配置

　　`arch/riscv/configs/k3_defconfig` 现状: `CONFIG_INPUT_EVDEV=y` (evdev 事件
接口)、`CONFIG_INPUT_DRV_RPMI_PWRKEY=y` (SoC 电源键)。**缺 gpio-keys 驱动**,
必须补:

```
# k3_defconfig 需追加:
CONFIG_KEYBOARD_GPIO=y             # gpio-keys 驱动 (缺省未开! 只开了 CROS_EC)

# 可选:
CONFIG_SPACEMIT_POWERKEY_MONITOR=y # k3-pwrkey-monitor 长按监测 (基座节点默认 disabled)
```

## 4. 设备树配置

　　以下 dts 为**完整自包含版**: 板级公共文件的内容已展开; 注意
`<dt-bindings/input/input.h>` 原本在 k3-firefly-common.dtsi 里 include, 公共
文件禁用后**必须写进你自己的 dts**, 否则 KEY_F12/KEY_POWER 宏未定义编译报错。

### 4.1 方式一: GPIO 按键 (boot + power)

　　参考板: AIBOX-PRO-K3 (FF_KEY 分支)。dts 头部 include 与节点:

```dts
/dts-v1/;

/* SoC 基座四件套 (原本由 k3-firefly-common.dtsi 统一 include, 现自带) */
#include "k3.dtsi"
#include "k3-rdomain.dtsi"
#include "k3-pinctrl.dtsi"
#include "k3_opp_table.dtsi"
#include <dt-bindings/gpio/gpio.h>
#include <dt-bindings/input/input.h>      /* KEY_* 宏, 原在 common.dtsi, 必须自带 */

/ {
	model = "xxx board";
	compatible = "xxx,your-board";

	gpio_keys: gpio-keys {
		compatible = "gpio-keys";
		pinctrl-names = "default";
		pinctrl-0 = <&boot_key_cfg>, <&power_key_cfg>;

		button-boot {
			label = "boot";
			linux,code = <KEY_F12>;
			gpios = <&gpio K3_GPIO(69) GPIO_ACTIVE_LOW>;
			debounce-interval = <50>;
		};

		button-power {
			label = "power";
			linux,code = <KEY_POWER>;
			gpios = <&gpio K3_GPIO(84) GPIO_ACTIVE_LOW>;
			debounce-interval = <50>;
			/* 按键唤醒 suspend 中的系统时加:
			 * wakeup-source; */
		};
	};
};

&pinctrl {
	boot_key_cfg: boot-key-cfg {
		boot-key-pin {
			pinmux = <K3_PADCONF(69, 0)>;
			bias-disable;		/* 板上有上拉时关内部上下拉 */
			drive-strength = <25>;
			power-source = <1800>;	/* GPIO69 在 1.8V 域 */
		};
	};

	power_key_cfg: power-key-cfg {
		power-key-pin {
			pinmux = <K3_PADCONF(84, 0)>;
			bias-disable;
			drive-strength = <25>;
			power-source = <3300>;	/* GPIO84 在 3.3V 域, 两脚不同! */
		};
	};
};
```

### 4.2 方式二: SoC 内置电源键 (RPMI) + 长按监测

　　rpmi_pwrkey 在 k3.dtsi 已 `status = "okay"`, **零设备树改动即有电源键**,
适合整机面板只留一个电源键的形态。要长按监测/看门狗式强制动作时, 打开
monitor 节点:

```dts
/* k3.dtsi 基座中默认 disabled, 覆盖打开即可 */
&pwrkey_monitor {
	status = "okay";
};
```

　　配套内核配置 `CONFIG_SPACEMIT_POWERKEY_MONITOR=y` (3 节), 驱动与
rpmi_pwrkey 通过同一电源键事件联动, 详见
`drivers/soc/spacemit/pwrkey_monitor.c`。

### 4.3 属性速查与陷阱

| 属性 | 值域 | 说明 |
|---|---|---|
| linux,code | KEY_* (input.h) | 上报键值 |
| gpios | `<&gpio K3_GPIO(N) flag>` | N=0..127; 按下接地用 ACTIVE_LOW |
| debounce-interval | 毫秒 | 0 时驱动取默认 5ms, 机械键建议 30-100 |
| wakeup-source | bool | 允许该键唤醒 suspend |
| autorepeat | bool | 长按连发 (gpio-keys 节点级属性) |

陷阱清单:

- **KEYBOARD_GPIO 未编入内核**时, gpio-keys 节点无驱动匹配, /dev/input 下不
  出现且不报错 — 自查第一步是 3 节配置。
- KEY_F12/KEY_POWER 宏未定义 (dts 编译报 `undefined identifier`): 头文件
  `dt-bindings/input/input.h` 忘了 include (原由公共文件提供)。
- 两颗按键 GPIO69/84 的 power-source 一个 1800 一个 3300, 照抄时别顺手统一;
  配错电压域的脚读不到稳定电平。
- 按键常报"按下"不松: 硬件无上拉 + pinctrl 配了 bias-disable — 改
  bias-pull-up。

## 5. 验证测试

```bash
# 1. 输入设备出现与否 (应有 rpmi pwrkey 与 gpio-keys 两类)
cat /proc/bus/input/devices | grep -A4 "gpio-keys\|pwrkey"

# 2. 原始事件监听 (按下/松开各报一条, 键值 116=KEY_POWER 118=KEY_F12)
evtest                      # 选 gpio-keys 对应 eventN, 或:
cat /dev/input/event0 | hexdump &   # 按键观察输出

# 3. 无设备时的排查顺序
#    a) zcat /proc/config.gz | grep KEYBOARD_GPIO   -> 未编入 (最常见)
#    b) dmesg | grep -i "gpio-keys"                 -> probe 报错
#    c) 引脚电平: 未按下应读 1
cat /sys/kernel/debug/pinctrl/*/pinmux-pins | grep -E "69|84"

# 4. 电源键功能链验证 (KEY_POWER 事件 -> 系统响应)
#    短按: 桌面/systemd-logind 亮屏或休眠; 长按: 触发关机菜单
journalctl -f | grep -i power       # 另开终端看用户态是否收到
```
