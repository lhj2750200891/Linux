/**
 * @file  main.c
 * @brief 通用定时器 TIMER1~4 驱动验证应用
 *
 * 设备树配置 (gd32f103re.dts general-timers 节点):
 *   gtim1: TIMER1  1s 时基定时中断          (无引脚)
 *   gtim2: TIMER2  PWM 1kHz 50% 输出 CH2->PB0
 *   gtim3: TIMER3  双通道测频+占空比  CH2/CH3->PB8 (共用, CH3 交叉)
 *
 * 验证方法:
 *   1. 用跳线帽把 PB0 (PWM 输出) 接到 PB8 (捕获输入)
 *   2. 烧录后看串口: 每 500ms 打印捕获到的频率/占空比 (应为 ~1000Hz / ~50%)
 *      并且每秒打印一次 TIMER1 时基计数
 *   3. PB0 的 PWM 也可用示波器/万用表直接观察
 *
 * 预期串口输出 (115200, USART0 PA9):
 *   === gtimer_test: TIMER1 timebase + TIMER2 pwm + TIMER3 pwmcap ===
 *   [CAP] f=1000Hz duty=50.0% (period=108000 high=54000 clk)
 *   [TIME1] sec=1
 *   [CAP] f=1000Hz duty=50.0% ...
 */
#include "main.h"
#include "general_timer.h"
#include "devicetree_generated.h"

volatile uint8_t time1_flag = 0;
volatile uint32_t time1_sec = 0;

/* TIMER1 时基 1s 中断回调 */
void general_timer_callback(uint8_t idx)
{
    if (idx == DT_GTIM1_IDX) {
        time1_flag = 1;
    }
}

int main(void)
{
    uint32_t report_cnt = 0;

    printf("=== gtimer_test: TIMER1 timebase + TIMER2 pwm + TIMER3 pwmcap ===\r\n");
    printf("[PWM] TIMER2 CH2 -> PB0, 1kHz 50%%\r\n");
    printf("[CAP] TIMER3 CH2+CH3 -> PB8 (pwmcap)\r\n");
    printf("请用跳线连接 PB0 -> PB8\r\n");

    while (1) {
        /* TIMER1 时基: 每秒报数 */
        if (time1_flag) {
            time1_flag = 0;
            time1_sec++;
            printf("[TIME1] sec=%lu\r\n", (unsigned long)time1_sec);
        }

        /* TIMER3 双通道捕获: 每 500ms 读一次 (轮询模式) */
        report_cnt++;
        if (report_cnt >= 500000U) {
            struct gtim_cap cap = {0, 0};
            report_cnt = 0;
            cap = general_timer_cap_read(DT_GTIM3_IDX);
            if (cap.period_clk != 0U) {
                const struct gd32_gtimer_cfg *cfg = general_timer_cfg_get(DT_GTIM3_IDX);
                uint32_t freq = gtim_cap_freq_hz(cfg, &cap);
                uint32_t duty = gtim_cap_duty_tenk(cfg, &cap);
                printf("[CAP] f=%luHz duty=%lu.%lu%% (period=%lu high=%lu clk)\r\n",
                       (unsigned long)freq,
                       (unsigned long)(duty / 10U), (unsigned long)(duty % 10U),
                       (unsigned long)cap.period_clk,
                       (unsigned long)cap.high_clk);
            } else {
                printf("[CAP] no edge yet (PB0->PB8 connected?)\r\n");
            }
        }
    }
}
