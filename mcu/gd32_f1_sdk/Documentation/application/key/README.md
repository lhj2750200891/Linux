# 独立按键 (key)

两种工作方式由**设备树** `keys` 节点的 `key-mode` 属性选择,
**应用层 API 完全一致**,不用关心是中断还是轮询:

- `KEY_MODE_IRQ`(默认):EXTI 外部中断,按下即触发,主循环爱干嘛干嘛
- `KEY_MODE_POLL`:纯轮询,主循环周期调 `key_scan()`(5~20ms 一次)

**头文件**: `#include "key.h"`(开关: `CONFIG_DRIVER_KEY`)

## API

| 函数/变量 | 说明 |
|---|---|
| `KEY_COUNT` | 按键总数(设备树 `count` 属性) |
| `uint8_t key_scan(void)` | 取按键事件。返回 `1~KEY_COUNT`,无返回 0。**两种模式下行为一致**:中断模式取走事件标志,轮询模式现场扫描消抖 |
| `uint8_t Key_Num` | 全局变量,最近一次按键的键值(中断模式下事件发生时就更新,不等 key_scan) |
| `uint8_t key_read(uint8_t idx)` | 读引脚实时电平 0/1(不走消抖,两种模式都可用) |
| `void key_callback(uint8_t idx)` | **弱回调,仅中断模式触发**:按键事件在中断上下文调用,应用可覆盖;应尽量短,只置标志别做重活 |

## 用法 1: 主循环查询(两种模式通用,最简单)

```c
#include "key.h"
#include "led.h"

int main(void)
{
    SCB->VTOR = FLASH_START;
    while (1) {
        uint8_t k = key_scan();
        if (k > 0) {
            led_toggle(k - 1);      /* 第 k 个键翻第 k 个灯 */
        }
        /* 中断模式下这里不需要延时; 轮询模式建议 5~20ms 一圈 */
    }
}
```

## 用法 2: 中断回调(仅 key-mode=<KEY_MODE_IRQ>,实时性最好)

```c
volatile uint8_t key_event = 0;

void key_callback(uint8_t idx)      /* 中断上下文: 只置标志 */
{
    key_event = (uint8_t)(idx + 1);
}

int main(void)
{
    SCB->VTOR = FLASH_START;
    while (1) {
        if (key_event) {
            uint8_t k = key_event;
            key_event = 0;
            led_toggle(k - 1);
        }
        /* 主循环完全空闲, 可做别的重活 */
    }
}
```

## 设备树配置(选模式的地方)

```dts
keys {
    compatible = "gd,gpio-keys";
    count = <4>;
    key-mode = <KEY_MODE_IRQ>;    /* 中断(默认) | KEY_MODE_POLL 轮询 */

    key1 {
        gpios = <&gpioa 7 GD32_MODE_IPU>;
        active-level = <GD32_LEVEL_LOW>;      /* 按下 = 低电平 */
        trigger = <KEY_TRIG_FALLING>;         /* 中断模式: 下降沿触发 */
    };
    /* active-level 和 trigger 都可省略, 缺省按引脚上下拉自动推导:
     *   IPU 上拉 -> 低有效 + 下降沿      IPD 下拉 -> 高有效 + 上升沿
     * 只有浮空输入或不规则电路才需要显式写。 */
};
```

轮询模式把 `key-mode` 改成 `KEY_MODE_POLL`,消抖时间用容器属性
`debounce-ms` 配(默认 20),此时 `trigger` 不生效。

## 中断模式注意事项

- **同引脚号冲突**:EXTI 线号 = 引脚号,两个按键用了相同引脚号
  (即使在不同端口)时中断模式不可用,需改轮询或换引脚;
- 消抖方式为"边沿后电平二次确认",对绝大部分机械按键足够;
  极端干扰场合再考虑轮询模式 + RC 滤波;
- 回调里别做延时/printf,重活放主循环(置标志模式,见用法 2)。
