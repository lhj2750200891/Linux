/**
 * @file  basic_timer.h
 * @brief 基本定时器 (TIMER5/6) 驱动接口
 *
 * 实例信息全部来自设备树 (basic-timers 节点):
 *   DT_BASIC_TIMERS_COUNT                 实例个数
 *   DT_BTIM1_IDX / DT_BTIM2_IDX / ...     按子节点名字访问下标
 *
 * 设备树示例 (arm/boards/<板型>/<板型>.dts):
 *   basic-timers {
 *       compatible = "gd,gd32-basic-timer";
 *       count = <1>;
 *       btim1 {                  // TIMER5: 500ms 周期中断
 *           timer-idx = <5>;
 *           clock-hz = <108000000>;   // APB1 定时器时钟 (自动倍频后)
 *           prescaler = <10800>;      // 分频比: 108MHz/10800 = 10kHz (1tick=100us)
 *           period-us = <500000>;     // 500ms = 5000 tick
 *           irq-mode = <1>;
 *       };
 *   };
 *
 * 周期换算: period-us = (CAR+1)*prescaler*1e6/clock-hz。
 * 16 位限制: PSC/CAR 都 <= 65535, 周期过长就加大 prescaler
 * (108MHz + prescaler=10800 时最长 6.55s, 速记常量见
 *  arm/include/dt-bindings/timer/gd32f10x-timer.h)。
 * 回调在中断上下文执行, 应尽量短 (置标志/翻转 GPIO 可以, printf 不行)。
 */
#ifndef DRIVERS_TIMER_BASIC_TIMER_H
#define DRIVERS_TIMER_BASIC_TIMER_H

#include <stdint.h>

#include "devicetree_generated.h"

/* 设备树生成的实例配置 (字段由 scripts/gen_devicetree.py 输出) */
struct gd32_btimer_cfg {
    uint8_t  timer_idx;      /* 硬件号: 5 或 6 */
    uint32_t clock_hz;       /* 输入时钟 (APB1 定时器时钟) */
    uint16_t psc_reg;        /* 预分频装入值 (实际分频 = psc_reg+1) */
    uint16_t arr_reg;        /* 重装值 (溢出周期 = (arr_reg+1) tick) */
    uint8_t  irq_mode;       /* 1=溢出中断 0=纯计数 */
};

/* 以下 API 的 idx 都是设备树实例下标 (DT_BTIMx_IDX) */

void     basic_timer_start(uint8_t idx);    /* 计数开始 */
void     basic_timer_stop(uint8_t idx);     /* 计数暂停 (保留当前计数值) */
uint32_t basic_timer_count(uint8_t idx);    /* 当前计数值 (无符号 16 位) */
void     basic_timer_reload(uint8_t idx);   /* 软件触发一次更新 (计数清零重装) */

/* 溢出中断回调 (irq-mode=1 时每个周期进一次, weak, 应用覆盖)
 * 参数 idx = 触发的实例下标; 中断上下文, 应短小 */
void basic_timer_callback(uint8_t idx);

#endif
