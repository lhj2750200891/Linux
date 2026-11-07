/**
 * @file  main.c
 * @brief hello 应用 —— gd32f103re_demo 演示板最小应用
 *
 * 仅点灯 + 按键计数, 演示同一套 SDK 下"版型不同 -> 应用不同"的组织方式。
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

    while (1) {
#ifdef CONFIG_DRIVER_SYSTICK
        sys_delay_ms(300);
#endif

#ifdef CONFIG_DRIVER_KEY
        Key_Num = key_scan();
        if (Key_Num != 0) {
#ifdef CONFIG_DRIVER_LED
            /* 按一下翻转一个 LED (demo 板设备树只配了部分 LED/按键) */
            led_toggle((uint8_t)(Key_Num - 1));
#endif
        }
#endif
    }
}
