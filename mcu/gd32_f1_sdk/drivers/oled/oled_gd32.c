/**
 * @file  oled_gd32.c
 * @brief SSD1306 OLED 驱动实现 —— 走 i2c 驱动的从机句柄 (设备树挂载)
 *
 * 匹配条件: CONFIG_DRIVER_OLED=y。总线与地址来自应用传入的设备树从机下标
 * (DT_OLED0_IDX), 驱动本身不引用具体节点名, 设备树增删从机不影响编译。
 *
 * I2C 字节协议 (SSD1306):
 *   控制字节 0x00 = 后续为命令; 0x40 = 后续为显存数据
 *   数据批量发送: 控制字节 0x40 + 连续数据流 (同一事务, 比逐字节快一个数量级)
 */
#include "oled.h"

#include <stddef.h>
#include <string.h>

#include "i2c_gd32.h"
#include "systick.h"
#include "oled_font.h"

/* 从机句柄 (oled_init 时记录, 单屏使用; 多屏可扩展为实例数组) */
static uint8_t oled_slave = 0xFFU;

/* ---------------------------------------------------------------------- */
/* 底层                                                                    */
/* ---------------------------------------------------------------------- */

int oled_write_cmd(uint8_t cmd)
{
    const uint8_t buf[2] = { 0x00, cmd };        /* 控制字节 0x00: 命令 */
    return i2c_write(oled_slave, buf, 2);
}

int oled_write_data(const uint8_t *buf, uint16_t len)
{
    /* 控制字节 0x40 + 数据流一次事务发出; SSD1306 页宽 128 字节 + 1 控制字节 */
    static uint8_t stage[129];
    uint16_t off = 0;

    while (off < len) {
        uint16_t n = (uint16_t)(len - off);
        if (n > 128) {
            n = 128;
        }
        stage[0] = 0x40;
        memcpy(&stage[1], &buf[off], n);
        int rc = i2c_write(oled_slave, stage, (uint16_t)(n + 1));
        if (rc != GD_I2C_OK) {
            return rc;
        }
        off = (uint16_t)(off + n);
    }
    return GD_I2C_OK;
}

/* ---------------------------------------------------------------------- */
/* 显示                                                                    */
/* ---------------------------------------------------------------------- */

void oled_set_cursor(uint8_t page, uint8_t col)
{
    oled_write_cmd(0xB0 | (page & 0x07));                    /* 页地址 */
    oled_write_cmd(0x10 | ((col >> 4) & 0x0F));              /* 列高 4 位 */
    oled_write_cmd(0x00 | (col & 0x0F));                     /* 列低 4 位 */
}

void oled_clear(void)
{
    static const uint8_t zeros[16] = { 0 };

    for (uint8_t page = 0; page < 8; page++) {
        oled_set_cursor(page, 0);
        for (uint8_t i = 0; i < 8; i++) {                    /* 128 = 16x8 */
            oled_write_data(zeros, 16);
        }
    }
}

void oled_display(uint8_t on)
{
    oled_write_cmd(on ? 0xAF : 0xAE);
}

void oled_show_char(uint8_t line, uint8_t column, char ch)
{
    if (ch < ' ' || ch > '~') {
        ch = ' ';                                            /* 越界字符按空格显示 */
    }
    uint8_t idx = (uint8_t)(ch - ' ');
    uint8_t col = (uint8_t)((column - 1) * 8);

    oled_set_cursor((uint8_t)((line - 1) * 2), col);         /* 上半格 */
    oled_write_data(&OLED_F8x16[idx][0], 8);
    oled_set_cursor((uint8_t)((line - 1) * 2 + 1), col);     /* 下半格 */
    oled_write_data(&OLED_F8x16[idx][8], 8);
}

void oled_show_string(uint8_t line, uint8_t column, const char *str)
{
    for (uint8_t i = 0; str[i] != '\0'; i++) {
        oled_show_char(line, (uint8_t)(column + i), str[i]);
    }
}

/* 十进制无符号数: 固定 len 位, 高位补 0 */
void oled_show_num(uint8_t line, uint8_t column, uint32_t num, uint8_t len)
{
    uint32_t pow = 1;
    for (uint8_t i = 0; i < len - 1; i++) {
        pow *= 10;
    }
    for (uint8_t i = 0; i < len; i++) {
        oled_show_char(line, (uint8_t)(column + i),
                       (char)('0' + (num / pow) % 10));
        pow /= 10;
    }
}

/* 十进制带符号数: 符号 + len 位数字 */
void oled_show_signed_num(uint8_t line, uint8_t column, int32_t num, uint8_t len)
{
    uint32_t mag;
    if (num >= 0) {
        oled_show_char(line, column, '+');
        mag = (uint32_t)num;
    } else {
        oled_show_char(line, column, '-');
        mag = (uint32_t)(-num);
    }
    oled_show_num(line, (uint8_t)(column + 1), mag, len);
}

/* 十六进制: 固定 len 位 (1~8), 大写 */
void oled_show_hex_num(uint8_t line, uint8_t column, uint32_t num, uint8_t len)
{
    uint32_t pow = 1;
    for (uint8_t i = 0; i < len - 1; i++) {
        pow *= 16;
    }
    for (uint8_t i = 0; i < len; i++) {
        uint8_t digit = (uint8_t)((num / pow) % 16);
        oled_show_char(line, (uint8_t)(column + i),
                       (char)(digit < 10 ? '0' + digit : 'A' + digit - 10));
        pow /= 16;
    }
}

/* 二进制: 固定 len 位 (1~16) */
void oled_show_bin_num(uint8_t line, uint8_t column, uint32_t num, uint8_t len)
{
    uint32_t pow = 1;
    for (uint8_t i = 0; i < len - 1; i++) {
        pow *= 2;
    }
    for (uint8_t i = 0; i < len; i++) {
        oled_show_char(line, (uint8_t)(column + i),
                       (char)('0' + (num / pow) % 2));
        pow /= 2;
    }
}

/* ---------------------------------------------------------------------- */
/* 初始化 (标准 SSD1306 128x64 序列)                                        */
/* ---------------------------------------------------------------------- */

int oled_init(uint8_t slave)
{
    int rc;

    oled_slave = slave;
    sys_delay_ms(120);                           /* 上电稳定 (厂商要求 >100ms) */

    static const uint8_t init_cmds[] = {
        0xAE,   /* 关显示 (配置期间) */
        0xD5, 0x80,   /* 时钟分频/振荡频率 */
        0xA8, 0x3F,   /* 多路复用 1/64 */
        0xD3, 0x00,   /* 显示偏移 0 */
        0x40,         /* 显示起始行 0 */
        0xA1,         /* 段重映射: 列 127 -> SEG0 (左右方向) */
        0xC8,         /* COM 扫描方向: 逆向 (上下方向) */
        0xDA, 0x12,   /* COM 引脚配置 (128x64 用 0x12) */
        0x81, 0xCF,   /* 对比度 */
        0xD9, 0xF1,   /* 预充电周期 */
        0xDB, 0x30,   /* VCOMH 电平 */
        0xA4,         /* 显示跟随显存 (非全亮) */
        0xA6,         /* 正常显示 (非反色) */
        0x8D, 0x14,   /* 充电泵使能 (模块内置升压必须开) */
        0x20, 0x02,   /* 页寻址模式 (0xB0/列地址三条命令定位) */
        0xAF,   /* 开显示 */
    };

    for (uint8_t i = 0; i < sizeof(init_cmds); i++) {
        rc = oled_write_cmd(init_cmds[i]);
        if (rc != GD_I2C_OK) {
            oled_slave = 0xFFU;                      /* 初始化失败, 后续 API 空操作 */
            return rc;
        }
    }

    oled_clear();
    return GD_I2C_OK;
}
