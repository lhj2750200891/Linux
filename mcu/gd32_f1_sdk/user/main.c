/**
 * @file  main.c
 * @brief 应用入口 —— 硬件初始化全部由设备树 + 驱动自动完成
 *
 * 驱动匹配条件: Kconfig CONFIG_DRIVER_xxx 启用 + 设备树存在对应节点。
 * 匹配成功的驱动经 DEVICE_INIT 在 main 之前自动初始化(类似 Linux probe),
 * 应用层只管调用 API, 不需要(也不应该)调用任何 xxx_init()。
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

#ifdef CONFIG_DRIVER_UART
#include "uart_gd32.h"
#endif

#ifdef CONFIG_DRIVER_UART
/* UART 接收回调 (weak 覆盖, 在中断上下文执行, 应尽量短):
 * - uart_rx_callback:   每收到 1 字节 (int-mode 含 RX 时)
 * - uart_idle_callback: 一帧结束 (int-mode 含 IDLE 时), 不定长协议帧处理入口
 * 用户层只需要在这些回调里写应用即可, 标志位清零由驱动完成。 */
void uart_idle_callback(uint8_t idx, uint16_t len)
{
    /* 示例: 收到一帧后原样回显 (查询方式读, 也可以在主循环里处理) */
    (void)idx; (void)len;
}
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

#ifdef CONFIG_DRIVER_UART
    /* 串口初始化已在 main 之前由 DEVICE_INIT 完成 (设备树 uarts 节点) */
#if defined(DT_UART1_IDX) && (DT_UART1_IDX < UART_COUNT)
    /* console=1 的实例已可 printf; 发送也可显式调 uart_send(DT_UART1_IDX, ...) */
    printf("\r\nGD32F103RE UART driver ready (from devicetree)\r\n");
#endif
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

#ifdef CONFIG_DRIVER_UART
        /* 串口接收处理: 三种模式统一从环形缓冲区读 (驱动已把数据放好)
         * 轮询模式也可用 uart_read()/uart_available() 主动查询 */
#if defined(DT_UART1_IDX) && (DT_UART1_IDX < UART_COUNT)
        uint16_t frame = uart_idle_frame(DT_UART1_IDX);   /* IDLE 帧完成查询 */
        if (frame > 0) {
            /* 一帧结束 (uart_idle_callback 之后应用侧再做慢处理也行):
             * 例: 回显本帧 */
            uint8_t echo[32];
            uint16_t n = 0;
            while (uart_available(DT_UART1_IDX) > 0 && n < sizeof(echo)) {
                int16_t c = uart_read(DT_UART1_IDX);
                if (c < 0) {
                    break;
                }
                echo[n++] = (uint8_t)c;
            }
            uart_send(DT_UART1_IDX, echo, n);   /* DMA 模式自动走 DMA 发送 */
        }
#endif
#endif
    }
}
