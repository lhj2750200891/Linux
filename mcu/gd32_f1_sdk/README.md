# GD32F10x 固件框架 (Kconfig + 编译期设备树 + 多板卡 + 多应用)

在裸机工程基础上重构:引入 **Kconfig 配置系统**(控制驱动裁剪)、
**编译期设备树**(描述硬件引脚连接,编译时读入固件,无运行时解析开销)、
**make lunch 两级选择**(先版型后应用)和 **Linux 风格子 Makefile 嵌套**
(驱动/应用各自目录的 Makefile,顶层统一收集)。

## 目录结构

```
├── Makefile                        # 构建入口: lunch 选版型+应用 -> config -> 设备树 -> 编译
├── Kconfig                         # 顶层配置菜单
├── .board / .app                   # 当前选择的版型 / 应用 (make lunch 写入)
├── .config                         # 当前配置 (make lunch 写入, 可手改, 变更后 make 即生效)
├── configs/
│   ├── gd32f103re_defconfig        # 版型 gd32f103re 的默认配置 (含 CONFIG_BOARD_DTS 指定设备树)
│   └── gd32f103re_demo_defconfig   # 版型 gd32f103re_demo 的默认配置
├── arm/                            # 设备树树 (借鉴 Linux arch/arm 布局)
│   ├── boards/
│   │   ├── gd32f103re/gd32f103re.dts       # 板级设备树: LED/按键/矩阵键盘/串口实例
│   │   └── gd32f103re_demo/gd32f103re_demo.dts
│   ├── core/
│   │   ├── gd32f10x.dtsi           # 家族级: SysTick / GPIOA~E / USART0~UART4 / DMA 外设节点
│   │   └── gd32f103re.dtsi         # 型号级: 用 &soc overlay 增补本型号的 UART 引脚分组
│   └── include/dt-bindings/
│       ├── gpio/gd32f10x-gpio.h    # GD32_MODE_* 模式编码 (与 fwlib 一致)
│       ├── serial/gd32f10x-uart.h  # GD32_UART_* (数据位/停止位/校验/中断模式)
│       └── ...
├── application/                    # 应用层 (两级: 版型/应用)
│   ├── gd32f103re/
│   │   ├── blink/                  # LED 流水灯 + 按键 (Makefile, main.c, main.h)
│   │   └── uart_echo/              # 串口回显 (Makefile, main.c, defconfig 覆盖板级配置)
│   └── gd32f103re_demo/
│       └── hello/                  # 按键翻转 LED 最小应用
├── scripts/
│   ├── kconfigconf.py              # 极简 Kconfig 引擎 -> autoconf.h + .config 补全
│   └── gen_devicetree.py           # DTB 解析器 -> devicetree_generated.h
├── drivers/                        # 驱动层 (按 .config 裁剪编译, 各自目录含子 Makefile)
│   ├── Kconfig
│   ├── gpio/  systick/  led/  key/  matrix_key/
│   └── uart/                       # UART: 轮询/中断(RBNE+IDLE)/DMA 三模式, printf 重定向
├── Documentation/devicetree/bindings/  # 绑定文档 (DTSchema YAML, 对应各 compatible)
├── vendor/                         # 芯片厂提供内容 (cmsis + fwlib, 基本不动)
└── build/                          # 构建产物 (bin/ 固件按 <版型>_<应用> 命名)
```

## 构建流程

```
make lunch: configs/<版型>_defconfig (或应用 defconfig) ──复制──> .config
                                                    (.board/.app 记住选择)
                                                       │
                      .config 中的 CONFIG_BOARD_DTS ───┘──> 找到该板的设备树 (arm/boards/)
.config ──kconfigconf.py──> build/generated/autoconf.h      (CONFIG_xxx, 强制包含进所有 C 文件)
                                        │
<CONFIG_BOARD_DTS 指定的>.dts           │
   │ cpp(展开 arm/core/*.dtsi + arm/include/dt-bindings)
   ▼                                    ▼
build/dts/<版型>.dtb ──gen_devicetree.py──> build/generated/devicetree_generated.h
                                        │ (DT_LEDS_INSTANCES / DT_UARTS_INSTANCES / ...)
   顶层 Makefile 收集 drivers/*/Makefile 与 application/<版型>/<应用>/Makefile 的 obj-y
   └──> arm-none-eabi-gcc 编译 -> 链接 -> build/bin/<版型>_<应用>.bin
```

## 常用命令

| 命令 | 说明 |
|---|---|
| `make lunch` | 交互式两级选择: 先版型, 后该版型下的应用 |
| `make lunch BOARD=<版型>` | 只指定版型, 仍交互选应用 |
| `make lunch BOARD=<版型> APP=<应用>` | 全免交互 (脚本/CI 用) |
| `make` | 编译 -> `build/bin/<版型>_<应用>.bin` |
| `make defconfig` | 从当前 版型+应用 的 defconfig 恢复默认配置 |
| `make clean` / `make distclean` | 清理 build/ / 另清理 .config + .board + .app |
| `make download` | OpenOCD + J-Link 烧录当前固件 |
| `make PYTHON=python3.x` | 指定 Python 解释器 (默认 python3) |

## 版型与应用 (make lunch 两级选择)

**一个版型 = 一个 defconfig + 它指定的板级设备树**;**一个应用 =
`application/<版型>/<应用>/` 目录 (Makefile 必需, defconfig 可选)**。
驱动代码与版型无关, 应用与版型绑定:

```sh
make lunch BOARD=gd32f103re APP=uart_echo   # 选版型+应用
make                                         # -> build/bin/gd32f103re_uart_echo.bin
make lunch APP=blink                         # 只换应用 (返回交互)
make                                         # -> build/bin/gd32f103re_blink.bin
```

交互菜单(先选版型, 再选该版型下的应用, 直接回车=保持当前):

```
current board: gd32f103re
     1. gd32f103re
   * 2. gd32f103re_demo   <- current
select board [1-2] (default 1): <回车>
board: gd32f103re
     1. blink
   * 2. uart_echo   <- current
select app [1-2] (default 2): 1

board:   gd32f103re
app:     blink
config:  configs/gd32f103re_defconfig
devicetree: arm/boards/gd32f103re/gd32f103re.dts
```

约定与保护:
- 切换版型/应用必须走 `make lunch`;`make BOARD=xxx`(或 `APP=xxx`)
  与当前选择不一致会直接报错提示用 lunch 切换。
- 版型下有一个应用, 或工程里只有一块板时, `make` 自动选中, 免 lunch。
- 应用目录自带 `defconfig` 时**整体覆盖**板级默认(如 uart_echo 只开
  SYSTICK/GPIO/UART);否则沿用 `configs/<版型>_defconfig`。
- 某驱动启用但该板设备树没有对应节点: 生成器补 `DT_xxx_COUNT 0`,
  驱动走空实现, 不会编译失败。

## 如何新增: 应用 / 底板 / 芯片型号

三者完全解耦,由目录约定自动发现,**不需要改任何构建文件(Makefile/Kconfig)**:

```
新增应用     只动 application/<版型>/<新应用>/           (1 步)
新增底板     复制三处: arm/boards/ + configs/ + application/  (3 步)
新增芯片型号 只动 arm/core/<新型号>.dtsi (+ 容量宏, 见注意)      (2 步)
跨芯片家族   vendor/ + Makefile MCU 配置, 属大改(见末尾说明)
```

### 1. 新增一块底板(版型)—— 最常用

一块底板 = 三处联动复制,复制后 `make lunch` 菜单里**自动出现**,选完直接编译:

```sh
# (a) 复制板级设备树, 目录和 .dts 都改成新底板名, 然后改里面的引脚
cp -r arm/boards/gd32f103re arm/boards/myboard
mv arm/boards/myboard/gd32f103re.dts arm/boards/myboard/myboard.dts
#     编辑 myboard.dts: LED/按键引脚、uart 实例个数与引脚组、console 指向
#     (include 的 arm/core/gd32f103re.dtsi 是芯片型号, 换芯片才需要动)

# (b) 复制 defconfig, 改第一行的 CONFIG_BOARD_DTS 指向新 dts, 再按需裁剪驱动
sed 's#arm/boards/gd32f103re/gd32f103re.dts#arm/boards/myboard/myboard.dts#' \
    configs/gd32f103re_defconfig > configs/myboard_defconfig

# (c) 给新底板建应用(至少一个, 复制现有应用改内容即可)
cp -r application/gd32f103re/blink application/myboard/blink

# (d) 选择并编译
make lunch            # 菜单里自动出现 myboard, 选它再选 blink
make                  # -> build/bin/myboard_blink.bin
```

注意: (b) 的 `CONFIG_BOARD_DTS` 路径是**唯一容易漏的一处**,目录名或文件名
对不上会直接报错提示。

### 2. 新增一个应用

应用与版型绑定,建目录即被发现:

```
application/<版型>/<新应用>/
├── Makefile     # 必需: obj-y += $(app-dir)/main.c   ($(app-dir) 顶层自动注入,
│                #   多文件就多写几行 obj-y += $(app-dir)/xxx.c)
├── main.c       # 应用入口
├── main.h       # 必需: vendor 的 gd32f10x_it.c 会 include 它(编译硬依赖)
└── defconfig    # 可选: 整体覆盖板级默认配置(如只开 UART 关掉 LED/按键)
```

然后 `make lunch` 选它(或 `make lunch APP=<新应用>` 只换应用)。
应用内多个 .c 文件照常拆分,头文件互 include 即可,无需登记。

### 3. 新增一个芯片型号(如 103RC / 103RB, 仍属 GD32F10x 家族)

型号差异 = 引脚分组 + 容量,设备树已经分层,只需加一个 dtsi:

```
(a) 复制 arm/core/gd32f103re.dtsi -> arm/core/gd32f103rc.dtsi
    按 103RC 封装(如 LQFP48/64)的数据手册 2.6 节裁剪引脚组:
    - 引出脚才保留对应 GPIO/USART 引脚组
    - 没有引出的引脚(如小封装没有 PD 口)直接删掉引脚组单元
    家族公共部分 gd32f10x.dtsi(GPIO 控制器/USART 外设/DMA)不用动。

(b) 该型号的底板 dts 改 include:
    #include "gd32f103rc.dtsi"     // 原来 include "gd32f103re.dtsi"
```

**已知限制(型号相关, 当前需改 Makefile)**:
- `Makefile:171` 硬编码 `-DGD32F10X_HD`(高密度),换中/极大密度型号
  需改为 `GD32F10X_MD` / `GD32F10X_XD` 等(fwlib 启动文件按此裁剪 Flash/RAM);
- 不同容量 Flash/RAM 大小不同,需核对链接脚本
  `vendor/cmsis/device/gd32f10x_flash.ld` 的分区;
- 主频不同时在板级 dts 覆写 systick 的 `clock-frequency`。

### 4. 跨芯片家族(如 GD32F30x / GD32F4xx)—— 当前不支持直接扩展

需要: 新 vendor 固件库与 CMSIS 内核文件、`MCU_CPU`(cortex-m4 等)与编译
宏按家族参数化、`arm/core/` 新建家族 dtsi。属框架级大改,不在本 README
的"复制即用"范围内。

## 设备树使用方式

分层结构(借鉴 Linux):

- `arm/core/gd32f10x.dtsi` — **家族级**:SysTick、GPIOA~E 控制器、
  USART0~UART4 外设节点(`gd,gd32-uart-periph`)、DMA0/1。
- `arm/core/gd32f103re.dtsi` — **型号级**:`&soc` overlay 增补该型号
  可用的 UART 引脚分组(`gd,gd32-uart-pingroup`, 借鉴 Linux pinctrl):
  每组 = 组号 + tx 引脚 + rx 引脚 + 是否重映射。
- `arm/boards/<版型>/<版型>.dts` — **板级**:LED/按键/矩阵键盘/串口实例。

```dts
leds         { compatible = "gd,gpio-leds";         count = <3>; };  /* 子节点: gpios / init-level */
keys         { compatible = "gd,gpio-keys";         count = <4>; };  /* 子节点: gpios / active-level */
matrix-keys  { compatible = "gd,gpio-matrix-keys";  row-count = <4>; col-count = <3>; };

uarts {
    compatible = "gd,gd32-uart";
    count = <1>;
    uart1 {                      /* 预定义引脚组: USART0 的 m0 组 (PA9/PA10) */
        pgroup   = <&usart0 0>;
        baud-rate = <115200>;
        dma-mode = <1>;                        /* DMA 收 + IDLE 判帧 */
        int-mode = <GD32_UART_INT_IDLE>;
        console  = <1>;                        /* printf 重定向到本实例 */
    };
    /* 或手动组合引脚 (数据手册 2.6 节标了复用功能的引脚均可):
     * uart2 { tx-gpios = <&gpioc 10 GD32_MODE_AF_PP>;
     *         rx-gpios = <&gpioc 11 GD32_MODE_IN_FLOATING>;
     *         uart-idx = <2>; remap = <1>; } */
};
```

绑定文档见 `Documentation/devicetree/bindings/`(DTSchema YAML 格式, 各
compatible 一份, 含属性约束与完整示例)。

编译后生成 `build/generated/devicetree_generated.h`,例如:

```c
#define DT_LEDS_COUNT 3                /* 来自设备树 count 属性 */
#define DT_LEDS_INSTANCES \
    { .port = 2, .pin = 13, .mode = 0x10, .level = 1 }, ...
#define DT_LED1_IDX 0                  /* 节点名 led1 -> 实例下标 */
#define DT_UARTS_COUNT 1
#define DT_UARTS_INSTANCES { .periph = ..., .baud_rate = 115200, ... }
```

### 驱动 API(全部按索引, 个数来自设备树)

| 驱动 | 接口 |
|---|---|
| SysTick 延时 | `systick_init()`, `sys_delay_us(us)`, `sys_delay_ms(ms)`(时钟来自 DT) |
| LED | `LED_COUNT`, `led_init_all()`, `led_set(idx, on)`, `led_toggle(idx)` |
| 按键 | `KEY_COUNT`, `key_init_all()`, `key_read(idx)`, `key_scan()` |
| 矩阵键盘 | `matrix_key_init()`, `matrix_key_scan()` |
| UART | `uart_send(idx, buf, len)`, `uart_printf(idx, fmt, ...)`(指定串口 printf 语法输出), `uart_read(idx)`, `uart_available(idx)`, `uart_idle_frame(idx)`, `uart_poll_read(idx)`(纯轮询模式) |

UART 三种工作模式由设备树组合决定(应用层只需写回调):
- `dma-mode=<1>` + `int-mode=<GD32_UART_INT_IDLE>`:DMA 循环收 + 空闲中断判帧;
- `dma-mode=<0>` + `int-mode=<GD32_UART_INT_RX_IDLE>`:RBNE 每字节入环形
  缓冲区 + IDLE 帧结束, 覆盖弱回调 `uart_rx_callback` / `uart_idle_callback` 即可;
- 两者皆关: 纯轮询。
- 注意 UART3 的 DMA 只有 RX=DMA1_CH2/TX=CH4, **UART4 无 DMA**(驱动自动退化为中断)。

## 如何添加一个新驱动

以 "buzzer" 蜂鸣器为例:

1. **Kconfig**: `drivers/Kconfig` 添加
   ```
   config DRIVER_BUZZER
       bool "蜂鸣器驱动"
       default y
       depends on DRIVER_GPIO_GD32
   ```
2. **子 Makefile**: `drivers/buzzer/Makefile` 写
   `obj-$(CONFIG_DRIVER_BUZZER) += $(drv-dir)/buzzer.c`(顶层自动收集);
3. **设备树**: 板级 dts 添加节点(复用已有类型可免改脚本);
4. **驱动代码**: `#include "devicetree_generated.h"`, 用 `DT_xxx_INSTANCES` 生成实例表;
5. **绑定文档**: `Documentation/devicetree/bindings/` 下加对应 `.yaml`;
6. `make` — 设备树/配置任何变动都会自动重新生成并只重编译受影响的文件。

## 生成脚本说明(零第三方依赖)

- `scripts/kconfigconf.py`: 支持 Kconfig 语法子集(config/bool/int/string/default/
  depends on/menu/if/source/help),表达式支持 `! && || ()`。求值规则:用户值 >
  default > 类型默认值,依赖不满足强制关闭。string 在 `.config` 中不带引号存储,
  在 autoconf.h 中带引号输出。以后如需 menuconfig,可无缝换 kconfiglib。
- `scripts/gen_devicetree.py`: 解析 dtc 生成的 FDT(DTB)二进制,按 compatible
  识别节点,解析 phandle 引用与 `#gpio-cells`/`#pin-group-cells`,生成 C 宏。
