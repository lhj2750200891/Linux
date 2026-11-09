/**
 * @file  main.c
 * @brief I2C 主机驱动 + SSD1306 OLED 从机设备验证应用
 *
 * 设备树配置 (gd32f103re.dts i2c-buses 节点):
 *   i2c0: PB6=SCL / PB7=SDA, 100kHz 标准模式
 *     oled0@3c: SSD1306 OLED 128x64 (status = "okay")
 *     sensor1@48: LM75 温度传感器示例 (已注释, 打开即验证一主多从)
 *
 * 验证方法:
 *   1. OLED 模块 (SSD1306 I2C 0x3C) 接 PB6=SCL / PB7=SDA, VCC=3.3V
 *   2. 烧录后看串口: i2c_probe 探测 + 初始化结果
 *   3. 看屏幕: 显示板名/I2C 状态/运行秒数, LED1 同步闪烁
 *
 * 预期串口输出 (115200, USART0 PA9):
 *   === oled_test: i2c0 (PB6/PB7 100kHz) + ssd1306 oled0@3c ===
 *   [I2C] probe 0x3C ... ACK
 *   [OLED] init ok
 *   [OLED] run sec=1 ...
 *
 * 从机节点从设备树摘除 (status="disabled" 或删除) 时的编译行为:
 *   DT_OLED0_IDX 变为 DT_IDX_DISABLED -> 本应用走 #else 分支, 仅串口提示,
 *   编译不报错, 运行不挂死。
 */
#include "main.h"

#include "systick.h"
#include "led.h"
#include "i2c_gd32.h"
#include "oled.h"
#include "devicetree_generated.h"

int main(void)
{
    SCB->VTOR = FLASH_START;
    uint32_t sec = 0;

    printf("=== oled_test: i2c0 (PB6/PB7 100kHz) + ssd1306 oled0@3c ===\r\n");

#if defined(DT_OLED0_IDX) && DT_OLED0_IDX != DT_IDX_DISABLED
    /* 设备树挂载了 oled0 从机: 探测 -> 初始化 -> 显示 */
    printf("[I2C] probe 0x%02X (bus DT_I2C0_IDX=%u) ... ",
           (unsigned)DT_OLED0_ADDR, (unsigned)DT_I2C0_IDX);
    int rc = i2c_probe(DT_OLED0_BUS, DT_OLED0_ADDR);
    if (rc != GD_I2C_OK) {
        printf("no ACK (rc=%d, 接线? SCL=PB6 SDA=PB7 上拉?)\r\n", rc);
    } else {
        printf("ACK\r\n");
    }

    rc = oled_init(DT_OLED0_IDX);
    if (rc != GD_I2C_OK) {
        printf("[OLED] init FAIL rc=%d (仅串口输出)\r\n", rc);
    } else {
        printf("[OLED] init ok\r\n");
        oled_show_string(1, 1, "GD32F103RE");
        oled_show_string(2, 1, "I2C+OLED OK!");
        oled_show_string(4, 1, "Run:");
    }
#else
    /* 设备树未挂载 oled0: 编译期降级, 不引用任何 OLED 宏 */
    printf("[OLED] 设备树未挂载 oled0 从机 (DT_OLED0_IDX 不存在/禁用)\r\n");
    printf("[OLED] 本应用只做 i2c 主机空载运行 + LED 闪烁\r\n");
#endif

    while (1) {
        sys_delay_ms(1000);
        sec++;
#if defined(DT_OLED0_IDX) && DT_OLED0_IDX != DT_IDX_DISABLED
        oled_show_num(4, 5, sec, 5);
#endif
        printf("[OLED] run sec=%lu\r\n", (unsigned long)sec);
        if (LED_COUNT > 0) {
            led_toggle(DT_LED1_IDX);
        }
    }
}
