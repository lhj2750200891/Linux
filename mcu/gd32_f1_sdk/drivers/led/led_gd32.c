/**
 * @file  led_gd32.c
 * @brief LED 驱动实现 —— 实例表由设备树生成 (DT_LEDS_INSTANCES)
 *
 * 匹配条件: CONFIG_DRIVER_LED=y 且设备树存在 leds 节点 (DT_LEDS_COUNT > 0)。
 * 满足时经 DEVICE_INIT 自动注册初始化, 应用层无需调用 led_init_all()。
 */
#include "led.h"

#include "gpio_gd32.h"
#include "init_fn_macros.h"

#if DT_LEDS_COUNT > 0

/* 设备树编译期生成的 LED 实例表 (原硬编码驱动中的 led1~led3) */
static const struct gd32_gpio_cfg dt_leds[DT_LEDS_COUNT] = { DT_LEDS_INSTANCES };

static void led_init_all(void)
{
    for (uint8_t i = 0; i < DT_LEDS_COUNT; i++) {
        gd32_gpio_configure(&dt_leds[i]);
    }
}
DEVICE_INIT(led, led_init_all, GD_INIT_DEVICE);

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

void led_set(uint8_t idx, uint8_t on) { (void)idx; (void)on; }
void led_toggle(uint8_t idx) { (void)idx; }

#endif
