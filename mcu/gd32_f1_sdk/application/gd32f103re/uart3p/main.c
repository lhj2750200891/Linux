/**
 * @file  main.c
 * @brief uart3p 应用 —— 三串口测试 (接哪个口测哪个口)
 *
 * 板级 dts: arm/boards/gd32f103re/gd32f103re.dts (uarts count=3, 全 DMA+IDLE)
 *   DT_UART1_IDX = USART0 PA9/PA10   (console, printf 默认口)
 *   DT_UART2_IDX = USART1 PA2/PA3
 *   DT_UART3_IDX = USART2 PB10/PB11
 *
 * 用法: USB 转串口想测哪个口就接哪个口的 TX 引脚 (共地):
 *   接 PA9  -> 应看到 [USART0] 开机横幅 + 每秒播报
 *   接 PA2  -> 应看到 [USART1] 开机横幅 + 每秒播报 (uart_printf 指定输出)
 *   接 PB10 -> 应看到 [USART2] 开机横幅 + 每秒播报 (uart_printf 指定输出)
 * 向任一口发数据会被该口原样回显 (DMA 收 + IDLE 判帧)。
 *
 * 所有输出都用 uart_printf(实例下标, ...) 显式指定串口,
 * printf(...) 本身仍走设备树 console=1 的 USART0。
 */
#include "main.h"

#include "uart_gd32.h"
#include "systick.h"

/* 单口测试循环体: 播报 + 回显 (哪个口接了 USB 转串口, 哪个口就有现象) */
static void port_report(uint8_t idx, const char *name, uint32_t tick)
{
    uart_printf(idx, "[%s] tick=%lu\r\n", name, (unsigned long)tick);
}

static void port_echo(uint8_t idx, const char *name)
{
    if (uart_idle_frame(idx) > 0) {
        uint16_t n = uart_available(idx);
        uart_printf(idx, "[%s] got %u bytes: ", name, n);
        int16_t c;
        while ((c = uart_read(idx)) >= 0) {
            uart_send(idx, (const uint8_t *)&c, 1);
        }
        uart_printf(idx, "\r\n");
    }
}

int main(void)
{
    SCB->VTOR = FLASH_START;

    uart_printf(DT_UART1_IDX, "\r\n=== uart3p: 3x UART (DMA+IDLE) ===\r\n[USART0] PA9/PA10  ready\r\n");
    uart_printf(DT_UART2_IDX, "\r\n=== uart3p: 3x UART (DMA+IDLE) ===\r\n[USART1] PA2/PA3   ready (uart_printf)\r\n");
    uart_printf(DT_UART3_IDX, "\r\n=== uart3p: 3x UART (DMA+IDLE) ===\r\n[USART2] PB10/PB11 ready (uart_printf)\r\n");

    uint32_t tick = 0;

    while (1) {
        sys_delay_ms(1000);
        tick++;

        port_report(DT_UART1_IDX, "USART0", tick);
        port_report(DT_UART2_IDX, "USART1", tick);
        port_report(DT_UART3_IDX, "USART2", tick);

        port_echo(DT_UART1_IDX, "USART0");
        port_echo(DT_UART2_IDX, "USART1");
        port_echo(DT_UART3_IDX, "USART2");
    }
}
