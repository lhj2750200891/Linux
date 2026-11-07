/**
 * @file  main.c
 * @brief uart_echo 应用 —— 串口收发回显 (设备树 uarts 节点驱动)
 *
 * 演示接收模式的统一用法:
 *   - 中断/DMA 模式: 数据已入环形缓冲区, 主循环查 uart_idle_frame() 处理帧
 *   - 回调方式: 覆盖 weak 的 uart_rx_callback / uart_idle_callback
 * printf 重定向到设备树 console=1 的实例 (Kconfig CONFIG_DRIVER_UART_PRINTF)。
 */
#include "main.h"

#include "uart_gd32.h"
#include "systick.h"

/* UART 接收回调 (weak 覆盖, 在中断上下文执行, 应尽量短):
 * 需要逐字节/帧事件驱动的应用在此写业务, 否则用主循环查询方式 */
void uart_idle_callback(uint8_t idx, uint16_t len)
{
    (void)idx; (void)len;    /* 本例用主循环查询, 回调留空 */
}

int main(void)
{
    SCB->VTOR = FLASH_START;

    printf("\r\nGD32F103RE uart_echo ready (from devicetree)\r\n");

    while (1) {
        /* IDLE 帧完成查询: 一帧结束 (不定长) 后原样回显 */
        if (uart_idle_frame(DT_UART1_IDX) > 0) {
            uint8_t echo[64];
            uint16_t n = 0;
            while (uart_available(DT_UART1_IDX) > 0 && n < sizeof(echo)) {
                int16_t c = uart_read(DT_UART1_IDX);
                if (c < 0) {
                    break;
                }
                echo[n++] = (uint8_t)c;
            }
            uart_send(DT_UART1_IDX, echo, n);    /* DMA 模式自动走 DMA 发送 */
        }

        sys_delay_ms(10);
    }
}
