/**
 * @file  main.c
 * @brief btimer_test 应用 —— 基本定时器 TIMER5/6 验证
 *
 * 板级 dts (arm/boards/gd32f103re/gd32f103re.dts):
 *   btim1 = TIMER5, 500ms 周期中断 -> 翻转 led1 (DT_LED1_IDX)
 *   btim2 = TIMER6, 1s    周期中断 -> 置标志, 主循环 printf 报时
 *
 * 现象:
 *   led1 (PC13) 以 1Hz 周期闪烁 (500ms 翻转一次)
 *   console 串口每秒打印一次 [TIMER6] sec=N (N 连续递增)
 *
 * 注意: printf 不能放中断上下文 —— TIMER6 回调只置 volatile 标志,
 * 打印在主循环做 (中断里打 printf 会阻塞串口发送, 拖垮中断响应)。
 */
#include "main.h"

#include "basic_timer.h"
#include "led.h"

/* TIMER6 秒标志 (中断置位, 主循环取走) */
static volatile uint8_t sec_flag;

/* 基本定时器回调 (weak 覆盖, 中断上下文, 只做最短的事) */
void basic_timer_callback(uint8_t idx)
{
    if (idx == DT_BTIM1_IDX) {
        led_toggle(DT_LED1_IDX);              /* TIMER5: 500ms 翻转 LED */
    } else if (idx == DT_BTIM2_IDX) {
        sec_flag = 1;                          /* TIMER6: 只置标志 */
    }
}

int main(void)
{
    SCB->VTOR = FLASH_START;

    printf("\r\n=== btimer_test: TIMER5 LED + TIMER6 printf ===\r\n");
    printf("[TIMER5] 500ms period -> toggle led1\r\n");
    printf("[TIMER6] 1s    period -> printf report\r\n");

    uint32_t sec = 0;

    while (1) {
        if (sec_flag) {
            sec_flag = 0;
            sec++;
            printf("[TIMER6] sec=%lu\r\n", (unsigned long)sec);
        }
    }
}
