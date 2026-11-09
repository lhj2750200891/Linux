/**
 * @file  oled.h
 * @brief SSD1306 OLED 驱动 (I2C 从机设备, 挂载在设备树 i2c-buses 下)
 *
 * 匹配条件: CONFIG_DRIVER_OLED=y 且设备树 i2c 总线上挂了 ssd1306 从机节点。
 * 驱动不写死地址/总线 —— 从机句柄来自设备树生成的宏:
 *   oled0@3c 节点 -> DT_OLED0_IDX (DT_I2C_SLAVES 表下标)
 *   应用调用 oled_init(DT_OLED0_IDX); 从机未挂载时 DT_OLED0_IDX =
 *   DT_IDX_DISABLED(0xFF), i2c 层越界校验, API 返回错误不挂死。
 *
 * 屏幕坐标: 128x64, 8x16 字库
 *   Line   1~4 (每行 16 像素高)
 *   Column 1~16 (每列 8 像素宽)
 *
 * 初始化不是自动的: 应用在 main 里显式 oled_init() (先于首次显示即可),
 * 便于控制上电时序和失败处理 (OLED 未接时返回错误, 不影响系统启动)。
 */
#ifndef DRIVERS_OLED_OLED_H
#define DRIVERS_OLED_OLED_H

#include <stdint.h>

/* 初始化: slave = DT_OLED0_IDX。返回 0 成功; 负数 = i2c 层错误码
 * (从机未接/未挂载 -> GD_I2C_ERR_NACK 或 GD_I2C_ERR_PARAM) */
int oled_init(uint8_t slave);

void oled_clear(void);
void oled_display(uint8_t on);                    /* 1=开显示 0=熄屏 (内容保持) */

void oled_set_cursor(uint8_t page, uint8_t col);  /* page 0~7, col 0~127 */
void oled_show_char(uint8_t line, uint8_t column, char ch);
void oled_show_string(uint8_t line, uint8_t column, const char *str);

void oled_show_num(uint8_t line, uint8_t column, uint32_t num, uint8_t len);
void oled_show_signed_num(uint8_t line, uint8_t column, int32_t num, uint8_t len);
void oled_show_hex_num(uint8_t line, uint8_t column, uint32_t num, uint8_t len);
void oled_show_bin_num(uint8_t line, uint8_t column, uint32_t num, uint8_t len);

/* 底层: 命令/数据直写 (特殊显示效果用, 如滚动/翻转) */
int oled_write_cmd(uint8_t cmd);
int oled_write_data(const uint8_t *buf, uint16_t len);

#endif
