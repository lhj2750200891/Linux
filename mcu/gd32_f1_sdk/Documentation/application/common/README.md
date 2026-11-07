# 公共约定

所有驱动 API 遵循同一套约定,看懂这页其他文档就不用重复解释。

## 1. 一切按"下标"访问,个数来自设备树

驱动的 API 全部是 `xxx_func(idx, ...)`,**代码里不写死外设名字和个数**:

```c
led_set(0, 1);          /* 第 1 个 LED */
led_set(DT_LED1_IDX, 1);  /* 按名字: 设备树子节点 led1 */
```

| 宏 | 含义 | 生成来源 |
|---|---|---|
| `LED_COUNT` / `KEY_COUNT` | LED / 按键个数 | 设备树 `count` 属性 |
| `DT_LED1_IDX` / `DT_KEY2_IDX` ... | 节点名 -> 实例下标 | 设备树子节点顺序 |
| `DT_UART1_IDX` ... | 串口实例下标 | 设备树 `uarts` 子节点顺序 |

## 2. 初始化是自动的,main 里不用调

所有驱动用 `DEVICE_INIT` 机制注册进 `.init_array` 段,
**`main()` 执行之前**由启动代码自动完成 probe(按
`GD_INIT_EARLY → PREINIT → DEVICE → APPLICATION` 四级)。

```c
int main(void)
{
    SCB->VTOR = FLASH_START;   /* 唯一必写: 向量表重定位 */
    led_set(0, 1);             /* 不需要 led_init_all(), 已自动完成 */
}
```

条件包含时注意成对写 `#ifdef`:

```c
#ifdef CONFIG_DRIVER_LED
#include "led.h"
#endif
...
#ifdef CONFIG_DRIVER_LED
led_toggle(0);
#endif
```

(.config 裁掉某驱动后代码仍能编译,见 uart_echo/blink 示例应用。)

## 3. 中断上下文准则(回调函数)

覆盖 weak 回调(如 `uart_rx_callback`)时,代码**运行在中断上下文**:

- 只做置标志 / 拷数据,不做延时、不调 printf、不做长循环;
- 想做重活: 回调置标志,主循环轮询标志再处理(见 uart 文档示例)。

## 4. 找到某个驱动的头文件

| 驱动 | 头文件 | Kconfig 开关 |
|---|---|---|
| 延时 | `#include "systick.h"` | `CONFIG_DRIVER_SYSTICK` |
| LED | `#include "led.h"` | `CONFIG_DRIVER_LED` |
| 按键 | `#include "key.h"` | `CONFIG_DRIVER_KEY` |
| 矩阵键盘 | `#include "matrix_key.h"` | `CONFIG_DRIVER_MATRIX_KEY` |
| 串口 | `#include "uart_gd32.h"` | `CONFIG_DRIVER_UART` |
| printf 重定向 | 自动, 无需 include | `CONFIG_DRIVER_UART_PRINTF` |
| 裸 GPIO | `#include "gpio_gd32.h"` | `CONFIG_DRIVER_GPIO_GD32` |
