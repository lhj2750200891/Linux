/**
 * @file  main.c
 * @brief 应用入口 —— 硬件初始化全部由设备树 + 驱动完成, 按配置裁剪
 *
 * 应用层只使用设备树描述的"个数 + 索引", 不点名任何具体外设:
 *   LED_COUNT / led_set(i, x)   : i = 设备树 leds 子节点顺序
 *   KEY_COUNT / key_scan()      : 键值 = 设备树 keys 子节点顺序 + 1
 * 需要点名某个具体外设时, 用设备树生成的宏, 如 led_set(DT_LED1_IDX, 1)。
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

#ifdef CONFIG_DRIVER_MATRIX_KEY
#include "matrix_key.h"
#endif

/* 键值用 LED 按二进制位显示 (旧版驱动的演示函数) */
void LED_Display_Button_Value(uint8_t button_value)
{
#if defined(CONFIG_DRIVER_LED) && (LED_COUNT > 0)
    uint8_t binary_value = (uint8_t)(button_value - 1);

    /* 设备树有几个 LED 就显示几位 */
    for (uint8_t i = 0; i < LED_COUNT; i++) {
        led_set(i, (binary_value >> i) & 0x01);
    }
#else
    (void)button_value;
#endif
}

int main(void)
{
    SCB->VTOR = FLASH_START;
#ifdef CONFIG_DRIVER_SYSTICK
    systick_init();          /* CPU 时钟频率来自设备树 systick 节点 */
#endif

#ifdef CONFIG_DRIVER_LED
    led_init_all();          /* 个数/引脚来自设备树 leds 节点 */
#endif
#ifdef CONFIG_DRIVER_KEY
    key_init_all();          /* 个数/引脚来自设备树 keys 节点 */
#endif
#ifdef CONFIG_DRIVER_MATRIX_KEY
    matrix_key_init();       /* 行列来自设备树 matrix-keys 节点 */
#endif

    while (1) {
#ifdef CONFIG_DRIVER_SYSTICK
        sys_delay_ms(20);    /* 主循环节拍 */
#endif

#ifdef CONFIG_DRIVER_KEY
        Key_Num = key_scan();
        if (Key_Num != 0) {
            /* Key_Num: 1 ~ KEY_COUNT, 对应设备树 keys 子节点顺序, 在此处理按键事件 */
        }
#endif

#ifdef CONFIG_DRIVER_MATRIX_KEY
        /* 需要矩阵键盘演示时打开:
         * uint8_t btn = matrix_key_scan();
         * if (btn != 0) {
         *     LED_Display_Button_Value(btn);
         * }
         */
#endif
    }
}
