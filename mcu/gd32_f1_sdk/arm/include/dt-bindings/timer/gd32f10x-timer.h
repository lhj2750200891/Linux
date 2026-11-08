/**
 * @file  gd32f10x-timer.h
 * @brief 定时器 dt-bindings 公共常量 (设备树与驱动共用)
 *
 * GD32F10x 定时器分三类, 驱动各自独立:
 *   基本定时器 TIMER5/6   (gd,gd32-basic-timer): 只有无引脚的溢出计数,
 *                          常用做时基/触发 DAC; 驱动提供周期中断
 *   通用定时器 TIMER1~4   (gd,gd32-general-timer): PWM/输入捕获/编码器...
 *   高级定时器 TIMER0/7   (gd,gd32-advanced-timer): 死区互补 PWM/刹车...
 * 后两类各自实现后本文件继续扩充。
 */
#ifndef DT_BINDINGS_TIMER_GD32F10X_TIMER_H
#define DT_BINDINGS_TIMER_GD32F10X_TIMER_H

/* 常用分频比速记 (prescaler 属性直接填分频比 N: 计数时钟 = clock-hz/N)。
 * 108MHz 定时器时钟下的效果:
 *   PSC_108MHZ_TO_1MHZ   (108)  -> 1MHz,  1tick=1us,   16位最长 65.5ms
 *   PSC_108MHZ_TO_10KHZ  (10800)-> 10kHz, 1tick=100us, 16位最长 6.55s
 */
#define GD32_TIMER_PSC_108MHZ_TO_1MHZ     108U
#define GD32_TIMER_PSC_108MHZ_TO_10KHZ    10800U

/* 通用定时器工作模式 (gd,gd32-general-timer 节点 mode 属性) */
#define GD32_TIMER_MODE_TIMEBASE   0   /* 纯定时中断/计数 (无引脚) */
#define GD32_TIMER_MODE_PWM        1   /* PWM 输出 (1~4 通道) */
#define GD32_TIMER_MODE_FREQ       2   /* 输入捕获测频 (单通道) */
#define GD32_TIMER_MODE_PWMCAP     3   /* 双通道测频+占空比 (CH0+1 或 CH2+3) */

#endif /* DT_BINDINGS_TIMER_GD32F10X_TIMER_H */
