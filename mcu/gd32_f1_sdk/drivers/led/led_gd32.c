/**
 * @file  led_gd32.c
 * @brief LED 驱动实现 —— 实例表由设备树生成 (DT_LEDS_INSTANCES)
 */
#include "led.h"

#include "gpio_gd32.h"

#if DT_LEDS_COUNT > 0

/* 设备树编译期生成的 LED 实例表 (原硬编码驱动中的 led1~led3) */
static const struct gd32_gpio_cfg dt_leds[DT_LEDS_COUNT] = { DT_LEDS_INSTANCES };

void led_init_all(void)
{
    for (uint8_t i = 0; i < DT_LEDS_COUNT; i++) {
        gd32_gpio_configure(&dt_leds[i]);
    }
}

void led_set(uint8_t idx, uint8_t on)
{
    if (idx >= DT_LEDS_COUNT) {
        return;
    }
    gd32_gpio_write(&dt_leds[idx], on ? 1U : 0U);
}

void led_toggle(uint8_t idx)
{
    if (idx >= DT_LEDS_COUNT) {
        return;
    }
    gd32_gpio_toggle(&dt_leds[idx]);
}

#else /* 设备树中没有 led 节点: 提供空实现, 保证编译通过 */

void led_init_all(void) {}
void led_set(uint8_t idx, uint8_t on) { (void)idx; (void)on; }
void led_toggle(uint8_t idx) { (void)idx; }

#endif
