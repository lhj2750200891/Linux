# 裸 GPIO (gpio)

基础层驱动,LED/按键/UART 引脚都由它配置。**应用一般不直接用**,
只有设备树没覆盖的外设(如单总线传感器、软件 SPI)才需要。

**头文件**: `#include "gpio_gd32.h"`(开关: `CONFIG_DRIVER_GPIO_GD32`)

## API

| 函数 | 说明 |
|---|---|
| `void gd32_gpio_configure(const struct gd32_gpio_cfg *cfg)` | 配置引脚(方向/模式) |
| `void gd32_gpio_write(const struct gd32_gpio_cfg *cfg, uint8_t level)` | 写电平 0/1 |
| `uint8_t gd32_gpio_read(const struct gd32_gpio_cfg *cfg)` | 读电平 0/1 |
| `void gd32_gpio_toggle(const struct gd32_gpio_cfg *cfg)` | 翻转 |

配置结构体(应用自行填,不走设备树):

```c
struct gd32_gpio_cfg {
    uint8_t port;    /* 端口: A=0 B=1 C=2 D=3 E=4 */
    uint8_t pin;     /* 引脚 0~15 */
    uint8_t mode;    /* GD32_MODE_* (见下表) */
    uint8_t level;   /* 初始电平(输出用) */
};
```

`mode` 常量(与 fwlib `GPIO_MODE_*` 数值一致,
定义于 `arm/include/dt-bindings/gpio/gd32f10x-gpio.h`):

| 常量 | 含义 |
|---|---|
| `GD32_MODE_AIN` / `GD32_MODE_IN_FLOATING` | 模拟输入 / 浮空输入 |
| `GD32_MODE_IPD` / `GD32_MODE_IPU` | 下拉 / 上拉输入 |
| `GD32_MODE_OUT_PP` / `GD32_MODE_OUT_OD` | 推挽 / 开漏输出 |
| `GD32_MODE_AF_PP` / `GD32_MODE_AF_OD` | 复用推挽 / 复用开漏(UART TX 等) |

## 示例(软件控制一个蜂鸣器)

```c
#include "gpio_gd32.h"

static const struct gd32_gpio_cfg buzzer = {
    .port = 1, .pin = 4,             /* PB4 (A=0 B=1 C=2 D=3 E=4) */
    .mode = GD32_MODE_OUT_PP, .level = 0,
};

int main(void)
{
    SCB->VTOR = FLASH_START;
    gd32_gpio_configure(&buzzer);
    gd32_gpio_write(&buzzer, 1);          /* 响 */
    /* ... */
}
```

提示: 如果该外设是固定硬件(焊死在板上),更好的做法是在设备树
加节点 + 写一个小驱动(见根 README「如何添加一个新驱动」),
`gpio_gd32.h` 留给真正动态/一次性的引脚操作。
