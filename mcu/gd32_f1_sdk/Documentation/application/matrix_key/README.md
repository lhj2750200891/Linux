# 矩阵键盘 (matrix_key)

行列扫描键盘,一个扫描函数。

**头文件**: `#include "matrix_key.h"`(开关: `CONFIG_DRIVER_MATRIX_KEY`)

## API

| 函数 | 说明 |
|---|---|
| `uint8_t matrix_key_scan(void)` | 扫描(**松开时**返回键值)。返回 `1 ~ 行数×列数`,无按键返回 0 |

- 行/列引脚来自设备树 `matrix-keys` 节点(`row-gpios` / `col-gpios`),
  行列数不需要应用关心。
- 键值编号按行列展平:第 r 行第 c 列 = `r * 列数 + c + 1`(r/c 从 0 计)。
- 与独立按键 `key_scan()` 一样,依赖主循环周期性调用(5~20ms)。

## 示例

```c
#include "matrix_key.h"
#include "led.h"
#include "systick.h"

int main(void)
{
    SCB->VTOR = FLASH_START;
    while (1) {
        uint8_t k = matrix_key_scan();
        if (k > 0) {
            led_toggle((k - 1) % LED_COUNT);   /* 键值 -> 灯 */
        }
        sys_delay_ms(10);
    }
}
```

需要"键值 -> 字符"映射(如 4x3 电话键盘)时,在应用里建一张
`const char keymap[]` 查表即可,驱动不掺和键义。
