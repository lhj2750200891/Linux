# 应用层 API 使用文档索引

面向应用开发者(写 `application/<版型>/<应用>/main.c` 的人),
按驱动组织,每个驱动一份使用文档,说明应用层可见的 API。

| 文档 | 驱动 | 覆盖内容 |
|---|---|---|
| [common/README.md](common/README.md) | — | 公共约定: 设备树下标、初始化机制、按名字访问宏 |
| [systick/README.md](systick/README.md) | `drivers/systick/` | `sys_delay_us/ms` 延时 |
| [led/README.md](led/README.md) | `drivers/led/` | `led_set/led_toggle` |
| [key/README.md](key/README.md) | `drivers/key/` | `key_scan/key_read/Key_Num` |
| [matrix_key/README.md](matrix_key/README.md) | `drivers/matrix_key/` | `matrix_key_scan` |
| [uart/README.md](uart/README.md) | `drivers/uart/` | 收发/帧处理/回调/printf 重定向 |

GPIO 驱动(`drivers/gpio/`)是 LED/按键/UART 的基础层,
应用一般不直接调用;如需裸 GPIO 操作(如传感器单总线)见
[gpio/README.md](gpio/README.md)。

## 快速上手

最小应用(`application/<版型>/hello/main.c`):

```c
#include "main.h"
#include "systick.h"
#include "led.h"

int main(void)
{
    SCB->VTOR = FLASH_START;      /* 中断向量表重定位, 必写 */
    while (1) {
        led_toggle(0);            /* 下标来自设备树 leds 子节点顺序 */
        sys_delay_ms(500);
    }
}
```

编译选择见仓库根 [README.md](../../README.md) 的
「如何新增: 应用 / 底板 / 芯片型号」章节。
