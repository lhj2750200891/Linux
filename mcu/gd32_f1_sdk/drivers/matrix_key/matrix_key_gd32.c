/**
 * @file  matrix_key_gd32.c
 * @brief 矩阵键盘驱动实现 —— 行/列表由设备树生成 (DT_MATRIX_KEYS_ROW/COL_INSTANCES)
 */
#include "matrix_key.h"

#include "systick.h"
#include "gpio_gd32.h"

#if DT_MATRIX_KEYS_ROW_COUNT > 0 && DT_MATRIX_KEYS_COL_COUNT > 0

/* 设备树编译期生成的行列实例表 (原硬编码驱动中的 button_row/button_col) */
static const struct gd32_gpio_cfg dt_rows[DT_MATRIX_KEYS_ROW_COUNT] = { DT_MATRIX_KEYS_ROW_INSTANCES };
static const struct gd32_gpio_cfg dt_cols[DT_MATRIX_KEYS_COL_COUNT] = { DT_MATRIX_KEYS_COL_INSTANCES };

void matrix_key_init(void)
{
    for (uint8_t i = 0; i < DT_MATRIX_KEYS_ROW_COUNT; i++) {
        gd32_gpio_configure(&dt_rows[i]);
    }
    for (uint8_t i = 0; i < DT_MATRIX_KEYS_COL_COUNT; i++) {
        gd32_gpio_configure(&dt_cols[i]);
    }
}

/* 与原 button_scan() 行为一致: 逐行拉低扫描, 键值在松开时返回 */
uint8_t matrix_key_scan(void)
{
    static uint8_t last_button = 0;
    uint8_t current_button = 0;
    uint8_t button_value = 0;

    for (uint8_t i = 0; i < DT_MATRIX_KEYS_ROW_COUNT; i++) {
        gd32_gpio_write(&dt_rows[i], 0);                 /* 拉低当前行 */
        sys_delay_ms(CONFIG_MATRIX_ROW_DELAY_MS);
        for (uint8_t j = 0; j < DT_MATRIX_KEYS_COL_COUNT; j++) {
            if (gd32_gpio_read(&dt_cols[j]) == 0) {
                current_button = (uint8_t)(i * DT_MATRIX_KEYS_COL_COUNT + j + 1);
            }
        }
        gd32_gpio_write(&dt_rows[i], 1);                 /* 释放当前行(空闲为高) */
    }

    if (current_button != 0) {
        last_button = current_button;
        return 0;
    } else if (last_button != 0) {
        button_value = last_button;
        last_button = 0;
        return button_value;
    }
    return 0;
}

#else /* 设备树中没有 matrix-keys 节点: 提供空实现 */

void matrix_key_init(void) {}
uint8_t matrix_key_scan(void) { return 0; }

#endif
