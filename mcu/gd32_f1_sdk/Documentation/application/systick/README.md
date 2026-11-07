# SysTick 延时 (systick)

最常用的驱动,两个函数,阻塞延时。

**头文件**: `#include "systick.h"`(开关: `CONFIG_DRIVER_SYSTICK`)

## API

| 函数 | 说明 |
|---|---|
| `void sys_delay_us(uint32_t us)` | 微秒级阻塞延时 |
| `void sys_delay_ms(uint32_t ms)` | 毫秒级阻塞延时 |

- 无需手动初始化(DEVICE_INIT 自动完成)。
- 时钟基准来自设备树 `systick` 节点的 `clock-frequency`
  (默认 108 MHz, 与 PLL 配置一致;改主频时在板级 dts 同步改)。

## 示例

```c
#include "systick.h"

int main(void)
{
    SCB->VTOR = FLASH_START;
    while (1) {
        sys_delay_ms(100);      /* 100ms 亮灭节拍 */
        led_toggle(0);
    }
}
```

精度说明: `sys_delay_us` 基于 SysTick 24 位递减计数器,
长延时(秒级)内部自动分段,直接 `sys_delay_ms(5000)` 即可。
