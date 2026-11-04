# GD32F10x 固件框架 (Kconfig + 编译期设备树 + 多板卡)

在原 `007_GD32F10x_gpio` 裸机工程基础上重构:引入 **Kconfig 配置系统**(控制驱动裁剪)、
**编译期设备树**(描述硬件引脚连接,编译时读入固件,无运行时解析开销)
和 **make lunch 多板卡支持**(同一颗芯片对应多块板卡,共用一套工程和驱动)。

## 目录结构

```
├── Makefile                        # 构建入口: lunch 选板 -> config -> 设备树 -> 编译 -> 链接
├── Kconfig                         # 顶层配置菜单
├── .board                          # 当前选择的板卡(make lunch 写入)
├── .config                         # 当前配置(make lunch 写入, 可手改, 变更后 make 即生效)
├── configs/
│   ├── gd32f103re_defconfig        # 板卡 gd32f103re 的默认配置(内含 CONFIG_BOARD_DTS 指定设备树)
│   └── gd32f103re_demo_defconfig   # 板卡 gd32f103re_demo 的默认配置(另一块板)
├── boards/
│   ├── gd32f103re/
│   │   └── gd32f103re.dts          # 板 gd32f103re 的设备树: LED/按键/矩阵键盘引脚
│   └── gd32f103re_demo/
│       └── gd32f103re_demo.dts     # 板 gd32f103re_demo 的设备树(2 LED / 1 按键)
├── dts/
│   ├── gd32f103re.dtsi             # SoC 级设备树: GPIO 控制器(GPIOA~GPIOE) + SysTick(CPU 时钟)
│   └── include/dt-bindings/gpio/
│       └── gd32f10x-gpio.h         # dt-bindings: GD32_MODE_* 模式编码(与 fwlib 一致)
├── scripts/
│   ├── kconfigconf.py              # 极简 Kconfig 引擎 -> autoconf.h + .config 补全
│   └── gen_devicetree.py           # DTB 解析器 -> devicetree_generated.h
├── drivers/                        # 驱动层(按 .config 裁剪编译)
│   ├── Kconfig
│   ├── gpio/                       # 核心: gd32_gpio_configure/read/write/toggle
│   ├── systick/                    # SysTick: systick_init/sys_delay_us/ms (时钟来自 DT)
│   ├── led/                        # LED:  led_init_all/led_set/led_toggle (LED_COUNT)
│   ├── key/                        # 按键: key_scan/key_read/Key_Num (KEY_COUNT)
│   └── matrix_key/                 # 矩阵键盘: matrix_key_scan
├── vendor/                         # 芯片厂提供内容(按层级摆放, 基本不动)
│   ├── cmsis/
│   │   ├── core/                   # ARM Cortex-M3 内核头文件
│   │   └── device/                 # GD32F10x 设备层: gd32f10x.h/启动文件/中断模板/链接脚本
│   └── fwlib/
│       ├── include/  source/       # GD32 外设固件库
├── user/                           # 应用层 main.c
└── build/                          # 构建产物(含 generated/ 生成头文件)
```

## 构建流程

```
make lunch: configs/<板卡>_defconfig ──复制──> .config      (.board 记住板卡名)
                                                     │
                       .config 中的 CONFIG_BOARD_DTS ─┘─> 找到该板的设备树
.config ──kconfigconf.py──> build/generated/autoconf.h            (CONFIG_xxx, 强制包含进所有C文件)
                                        │
<CONFIG_BOARD_DTS 指定的>.dts           │
   │ cpp(展开dtsi/bindings)             │
   ▼                                    ▼
build/dts/<板卡>.dtb ──gen_devicetree.py──> build/generated/devicetree_generated.h
                                        │ (DT_LEDS_INSTANCES / DT_KEYS_INSTANCES / ...)
   Makefile include .config 决定 obj-y ─┴──> arm-none-eabi-gcc 编译驱动 -> 链接 -> bin/hex
```

## 常用命令

| 命令 | 说明 |
|---|---|
| `make lunch` | 交互式选择板卡(输入序号,直接回车=默认当前板卡) |
| `make lunch BOARD=<板卡名>` | 直接选择板卡(免交互) |
| `make` | 编译当前板卡固件 -> `build/bin/<板卡名>.bin` |
| `make defconfig` | 从当前板卡的 defconfig 恢复默认配置 |
| `make clean` / `make distclean` | 清理 build/ / 清理 build/ + .config + .board |
| `make download` | OpenOCD + J-Link 烧录当前板卡固件 |
| `make PYTHON=python3.x` | 指定 Python 解释器(默认 python3) |

## 多板卡支持 (make lunch)

**一块板 = 一个 defconfig + 它指定的设备树**,驱动代码完全共用,切换板卡不用新建工程:

- `configs/<板卡名>_defconfig`:板卡的"身份",里面 **必须用 `CONFIG_BOARD_DTS=<设备树路径>`
  指定这块板的设备树**(板卡与硬件描述在此绑定),其余是驱动裁剪/参数差异。
- `CONFIG_BOARD_DTS` 指向的 `.dts`:这块板的全部硬件描述(外设个数、引脚、模式)。

```sh
make lunch BOARD=gd32f103re_demo   # 切到 demo 板: 写入 .board + 复制其 defconfig 为 .config
make                               # 编译 -> build/bin/gd32f103re_demo.bin (固件按板卡命名)
make lunch                         # 或交互式: 输入序号回车即可(直接回车=当前板卡)
```

交互菜单(借鉴瑞芯微 SDK 的 `build.sh lunch`,按序号选择,不用记板卡名):

```
================================================
 当前板卡: gd32f103re_demo
 可选板卡 (configs/ 下有对应 _defconfig 的板):
     1. gd32f103re
   * 2. gd32f103re_demo   <- 当前
================================================
请选择板卡序号 [2] (回车=默认): 1

已选择板卡: gd32f103re
设备树    : boards/gd32f103re/gd32f103re.dts  (由 defconfig 的 CONFIG_BOARD_DTS 指定)
配置就绪  : 运行 make 编译, 固件输出 build/bin/gd32f103re.bin
```

默认序号始终指向当前板卡,直接回车即保持不变;`BOARD=` 参数保留给脚本/CI 免交互使用。

约定与保护:
- 切换板卡必须走 `make lunch`;`make BOARD=xxx` 与当前板卡不一致会直接报错提示。
- 工程里只有一块板时,直接 `make` 会自动选中它;多于一块时必须先 lunch。
- 某驱动在 defconfig 中启用但该板设备树没有对应节点:生成器补 `DT_xxx_COUNT 0`,
  驱动自动走空实现,不会编译失败。

**添加一块新板(3 步,不动任何驱动/应用代码)**:
1. `boards/<新板名>/` 下写这块板的 `.dts`(复制现有板改引脚即可);
2. `configs/<新板名>_defconfig`,第一行内容就是 `CONFIG_BOARD_DTS=boards/<新板名>/xxx.dts`,
   再按需裁剪驱动;
3. `make lunch BOARD=<新板名>` → `make`。

改配置: 直接编辑 `.config`(如把 `CONFIG_DRIVER_MATRIX_KEY=y` 改成
`# CONFIG_DRIVER_MATRIX_KEY is not set`),然后 `make`,会自动只编译启用的驱动。

## 设备树使用方式

硬件描述写在各板卡自己的 `.dts` 中(由该板 defconfig 的 `CONFIG_BOARD_DTS` 指定)。
**外设的个数、引脚全部在设备树中描述,
驱动只提供按索引的通用接口, 代码里不写死任何外设名字和个数**:

```dts
systick      { compatible = "gd,cortex-m-systick"; clock-frequency = <108000000>; };  /* SoC dtsi */
leds         { compatible = "gd,gpio-leds";        count = <3>;  /* 子节点: gpios / init-level */ };
keys         { compatible = "gd,gpio-keys";        count = <4>;  /* 子节点: gpios / active-level */ };
matrix-keys  { compatible = "gd,gpio-matrix-keys"; row-count = <4>; col-count = <3>;  /* row-gpios / col-gpios */ };
```

- `count` 等个数属性: 必须与实际子节点/引脚列表个数一致, 生成器编译期校验, 不一致直接报错。
- `gpios = <&gpioc 13 GD32_MODE_OUT_PP>` 即:GPIOC 端口、13 脚、推挽输出。
- 端口通过 `&gpioc` 标签引用(SoC dtsi 中定义了 `port-idx`:A=0 ~ E=4)。
- 每个子节点名(如 `led1`)生成下标宏 `DT_LED1_IDX`, 应用层需要点名某个外设时使用。

编译后生成 `build/generated/devicetree_generated.h`,例如:

```c
#define DT_LEDS_COUNT 3               /* 来自设备树 count 属性 */
#define DT_LEDS_INSTANCES \
	{ .port = 2, .pin = 13, .mode = 0x10, .level = 1 }, ...
#define DT_LED1_IDX 0                 /* 节点名 led1 -> 实例下标 */
```

### 驱动 API(全部按索引, 个数来自设备树)

| 驱动 | 接口 |
|---|---|
| SysTick 延时 | `systick_init()`, `sys_delay_us(us)`, `sys_delay_ms(ms)`(CPU 时钟来自 DT `clock-frequency`) |
| LED | `LED_COUNT`, `led_init_all()`, `led_set(idx, on)`, `led_toggle(idx)` |
| 按键 | `KEY_COUNT`, `key_init_all()`, `key_read(idx)`, `key_scan()`(返回 1~KEY_COUNT), `Key_Num` |
| 矩阵键盘 | `matrix_key_init()`, `matrix_key_scan()` |

按索引遍历: `for (i = 0; i < LED_COUNT; i++) led_set(i, 1);`
按名字点名: `led_set(DT_LED1_IDX, 1);` / `key_read(DT_KEY1_IDX);`
设备树加一个 `led4` 并把 `count` 改成 4, 应用遍历代码一行都不用改, 重新 make 即生效。

## 如何添加一个新驱动

以 " buzzer" 蜂鸣器为例:

1. **Kconfig**: 在 `drivers/Kconfig` 添加
   ```
   config DRIVER_BUZZER
       bool "蜂鸣器驱动"
       default y
       depends on DRIVER_GPIO_GD32
   ```
2. **Makefile**: 添加 `obj-$(CONFIG_DRIVER_BUZZER) += drivers/buzzer/buzzer.c`
3. **设备树**: 在板级 dts 添加节点(复用已有类型可免改脚本):
   ```dts
   buzzers { compatible = "gd,gpio-leds";   /* 或在 scripts/gen_devicetree.py 增加新类型 */
       count = <1>;
       buzzer { gpios = <&gpiob 4 GD32_MODE_OUT_PP>; init-level = <0>; };
   };
   ```
4. **驱动代码**: `#include "devicetree_generated.h"`,用 `DT_xxx_INSTANCES` 生成实例表。
5. `make` — 设备树/配置任何变动都会自动重新生成并只重编译受影响的文件。

## 生成脚本说明(零第三方依赖)

- `scripts/kconfigconf.py`: 支持 Kconfig 语法子集(config/bool/int/string/default/depends on/
  menu/if/source/help),表达式支持 `! && || ()`。求值规则:用户值 > default > 类型默认值,
  依赖不满足强制关闭。string 在 `.config` 中不带引号存储(make 可直接用),
  在 autoconf.h 中带引号输出。以后如需 menuconfig 等,可无缝换用 kconfiglib(语法兼容)。
- `scripts/gen_devicetree.py`: 解析 dtc 生成的 FDT(DTB)二进制,按 compatible 识别节点,
  解析 phandle 引用与 `#gpio-cells`,生成 C 宏。
