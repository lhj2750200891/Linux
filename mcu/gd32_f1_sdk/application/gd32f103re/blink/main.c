/**
 * @file  main.c
 * @brief blink 应用 —— LED 流水灯 + 独立按键
 *
 * 应用位于 application/<版型>/<应用>/, 只属于本版型;
 * 硬件初始化全部由设备树 + 驱动自动完成 (main 之前 DEVICE_INIT 自动 probe)。
 * 应用层只使用设备树描述的"个数 + 索引", 不点名具体引脚。
 */
#include "main.h"

#ifdef CONFIG_DRIVER_SYSTICK
#include "systick.h"
#endif

#ifdef CONFIG_DRIVER_LED
#include "led.h"
#endif

#ifdef CONFIG_DRIVER_KEY
#include "key.h"
#endif

int main(void)
{
    SCB->VTOR = FLASH_START;
    uint8_t step __attribute__((unused)) = 0;

    while (1) {
#ifdef CONFIG_DRIVER_SYSTICK
        sys_delay_ms(200);    /* 流水灯节拍 */
#endif

#ifdef CONFIG_DRIVER_KEY
        Key_Num = key_scan();
        if (Key_Num != 0) {
            /* 按键事件: 键值 1~KEY_COUNT, 对应设备树 keys 子节点顺序 */
        }
#endif

#if defined(CONFIG_DRIVER_LED) && (LED_COUNT > 0)
        /* 流水灯: 设备树有几个 LED 就跑几位 */
        for (uint8_t i = 0; i < LED_COUNT; i++) {
            led_set(i, (uint8_t)(i == step));
        }
        step = (uint8_t)((step + 1) % LED_COUNT);
#endif
    }
}
