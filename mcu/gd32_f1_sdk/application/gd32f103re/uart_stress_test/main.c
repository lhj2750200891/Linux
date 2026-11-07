/**
 * @file  main.c
 * @brief uart_stress_test 应用 —— 串口连续压力测试 (配合 VOFA+ 等工具灌数据)
 *
 * 板级 dts: arm/boards/gd32f103re/gd32f103re.dts (uarts count=3, 全 DMA+IDLE)
 *   DT_UART1_IDX = USART0 PA9/PA10, DT_UART2_IDX = USART1 PA2/PA3,
 *   DT_UART3_IDX = USART2 PB10/PB11 —— 三个口同时收, 哪个口接了就回哪个口。
 *
 * 行为: 主循环全速轮询 (无延时, 无 tick 播报), 任一口收到帧(IDLE 判界)立即回
 *   [口名] got <本帧字节数> bytes: <原始内容>
 * 字节数与内容都是板子实际收到的, 可用来核对发送端发了多少、内容对不对。
 *
 * 上位机建议 (VOFA+):
 *   - 持续发送定长帧, 间隔拉到 10ms 级测试吞吐/丢帧
 *   - 每帧固定帧头(序号)时, 看 returned 报告的字节数与帧头是否连续
 */
#include "main.h"

#include "uart_gd32.h"

/* 每口帧计数: 收到一帧 +1, 回显带序号 —— 发送端数次数, 接收端看最后序号
 * 是否相等、中间有无跳号, 丢没丢帧一眼可见 */
static uint32_t rx_count[3];

/* 收到一帧: 回显 [序号] 字节数 + 原始内容 (帧边界由 IDLE 空闲中断判定) */
static void port_echo(uint8_t idx, const char *name)
{
    if (uart_idle_frame(idx) > 0) {
        rx_count[idx]++;
        uart_printf(idx, "[%s] #%lu got %u bytes: ", name,
                    (unsigned long)rx_count[idx], uart_available(idx));
        int16_t c;
        while ((c = uart_read(idx)) >= 0) {
            uart_send(idx, (const uint8_t *)&c, 1);    /* 逐字节透传 */
        }
        uart_printf(idx, "\r\n");
    }
}

int main(void)
{
    SCB->VTOR = FLASH_START;

    uart_printf(DT_UART1_IDX, "\r\n=== uart_stress_test (DMA+IDLE) ===\r\n[USART0] PA9/PA10  ready\r\n");
    uart_printf(DT_UART2_IDX, "\r\n=== uart_stress_test (DMA+IDLE) ===\r\n[USART1] PA2/PA3   ready\r\n");
    uart_printf(DT_UART3_IDX, "\r\n=== uart_stress_test (DMA+IDLE) ===\r\n[USART2] PB10/PB11 ready\r\n");

    while (1) {                          /* 全速轮询: 收到即回, 无节拍 */
        port_echo(DT_UART1_IDX, "USART0");
        port_echo(DT_UART2_IDX, "USART1");
        port_echo(DT_UART3_IDX, "USART2");
    }
}
