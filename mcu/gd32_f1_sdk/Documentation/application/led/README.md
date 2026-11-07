# LED (led)

两个函数,按下标控制。个数、引脚全部来自设备树 `leds` 节点。

**头文件**: `#include "led.h"`(开关: `CONFIG_DRIVER_LED`)

## API

| 函数/宏 | 说明 |
|---|---|
| `LED_COUNT` | LED 总数(设备树 `count` 属性) |
| `void led_set(uint8_t idx, uint8_t on)` | 点亮/熄灭。`idx: 0 ~ LED_COUNT-1`,`on: 1=亮 0=灭`(引脚极性由设备树处理,应用不用管) |
| `void led_toggle(uint8_t idx)` | 翻转 |

设备树子节点顺序即下标:`led1 → 0, led2 → 1, ...`;
按名字访问用 `led_set(DT_LED1_IDX, 1)`。

## 示例

```c
#include "led.h"
#include "systick.h"

int main(void)
{
    SCB->VTOR = FLASH_START;
    uint8_t i = 0;
    while (1) {
        led_set(i, 1);                      /* 流水灯 */
        sys_delay_ms(200);
        led_set(i, 0);
        i = (i + 1) % LED_COUNT;            /* 个数变了代码不用改 */
    }
}
```

设备树加一个 `led4` 并把 `count` 改成 4,上面代码一行不动,
重新 make 即自动生效。
