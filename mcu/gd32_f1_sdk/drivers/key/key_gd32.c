/**
 * @file  key_gd32.c
 * @brief 独立按键驱动实现 —— 实例表由设备树生成 (DT_KEYS_INSTANCES)
 */
#include "key.h"

#include "systick.h"
#include "gpio_gd32.h"

uint8_t Key_Num = 0;

#if DT_KEYS_COUNT > 0

/* 设备树编译期生成的按键实例表 (原硬编码驱动中的 key1~key4) */
static const struct gd32_gpio_cfg dt_keys[DT_KEYS_COUNT] = { DT_KEYS_INSTANCES };

void key_init_all(void)
{
    for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
        gd32_gpio_configure(&dt_keys[i]);
    }
}

uint8_t key_read(uint8_t idx)
{
    if (idx >= DT_KEYS_COUNT) {
        return 0;
    }
    return gd32_gpio_read(&dt_keys[idx]);
}

/* 按下状态 = 电平与设备树 active-level 一致 */
static uint8_t key_is_pressed(uint8_t idx)
{
    return key_read(idx) == dt_keys[idx].level;
}

static uint8_t key_any_pressed(void)
{
    for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
        if (key_is_pressed(i)) {
            return 1;
        }
    }
    return 0;
}

/* 与原 key_scan() 行为一致: 松开状态首次检测到按下 -> 消抖 -> 返回键值(下标+1) */
uint8_t key_scan(void)
{
    static uint8_t key_up = 1;    /* 松开标志 */

    if (key_up && key_any_pressed()) {
        key_up = 0;
        sys_delay_ms(CONFIG_KEY_DEBOUNCE_MS);

        for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
            if (key_is_pressed(i)) {
                return (uint8_t)(i + 1);
            }
        }
    }

    if (!key_any_pressed()) {
        key_up = 1;
    }
    return 0;
}

#else /* 设备树中没有 key 节点: 提供空实现, 保证编译通过 */

uint8_t Key_Num = 0;
void key_init_all(void) {}
uint8_t key_read(uint8_t idx) { (void)idx; return 0; }
uint8_t key_scan(void) { return 0; }

#endif
