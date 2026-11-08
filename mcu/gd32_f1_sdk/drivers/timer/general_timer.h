/**
 * @file  general_timer.h
 * @brief 通用定时器 (TIMER1~4) 驱动接口 —— PWM 输出 / 输入捕获测频 / 双通道测频测占空比 / 定时中断
 *
 * 实例信息全部来自设备树 (general-timers 节点, mode 四选一):
 *   GD32_TIMER_MODE_TIMEBASE  纯定时中断 (同基本定时器, 无引脚)
 *   GD32_TIMER_MODE_PWM       PWM 输出, 1~4 通道独立占空比
 *   GD32_TIMER_MODE_FREQ      单通道输入捕获测频 (上升或下降沿)
 *   GD32_TIMER_MODE_PWMCAP    相邻双通道测频+占空比 (低号通道上升沿直连,
 *                             高号通道下降沿交叉, 共用一个引脚!)
 *
 * 设备树宏:
 *   DT_GENERAL_TIMERS_COUNT            实例个数
 *   DT_GTIMx_IDX                       按子节点名访问实例下标
 *
 * 设备树示例:
 *   general-timers {
 *       compatible = "gd,gd32-general-timer";
 *       count = <2>;
 *       gtim1 {                                   // TIMER2: PWM 1kHz, CH2 -> PB0
 *           timer-idx = <2>;
 *           mode = <GD32_TIMER_MODE_PWM>;
 *           clock-hz = <108000000>;
 *           prescaler = <108>;                    // 1MHz, 1tick=1us
 *           period-us = <1000>;                   // 1kHz
 *           irq-mode = <0>;
 *           ch2 { channel = <2>; gpios = <&gpiob 0 GD32_MODE_AF_PP>;
 *                 duty-tenk = <5000>; }           // 50%
 *       };
 *       gtim2 {                                   // TIMER3: 测 TIMER2 的 PWM
 *           timer-idx = <3>;
 *           mode = <GD32_TIMER_MODE_PWMCAP>;
 *           prescaler = <1>;                      // 108MHz 全速计数
 *           ch2 { channel = <2>; gpios = <&gpiob 8 GD32_MODE_IPU>; }
 *           ch3 { channel = <3>; gpios = <&gpiob 9 GD32_MODE_IPU>; }
 *       };
 *   };
 *
 * 双通道测频原理 (PWMCAP, 例 CH2/CH3 共用 PB8):
 *   CH2 直连上升沿 + CH3 交叉(CH2 引脚, 下降沿)同时配置 -> 一个 PWM 周期内
 *   CH2 捕获周期起点, CH3 捕获下降沿:
 *     周期   = (CH2 本次 - CH2 上次) * (prescaler / clock-hz)
 *     高电平 = (CH3 - CH2 上次)   * (prescaler / clock-hz)
 *     频率 = 1 / 周期,  占空比 = 高电平 / 周期
 *
 * 注意: pwmcap 模式高号通道 (如 ch3) 只用 channel 属性选极性方向,
 * gpios 引脚属性被忽略 (与低号通道共用同一引脚)。
 */
#ifndef DRIVERS_TIMER_GENERAL_TIMER_H
#define DRIVERS_TIMER_GENERAL_TIMER_H

#include <stdint.h>

#include "devicetree_generated.h"

/* 设备树生成的通道槽 (每实例固定 4 个, ch=0xFF 表示未用) */
struct gd32_gtim_chan {
    uint8_t  ch;        /* 通道号 0~3, 0xFF=未用 */
    uint8_t  port;      /* GPIO 端口序号 A=0 */
    uint8_t  pin;       /* 引脚号 */
    uint8_t  pinmode;   /* GD32_MODE_* (pwm=AF_PP, 捕获=浮空/IPU/IPD) */
    uint8_t  aux;       /* pwm: PWM0/PWM1; freq: 0=上升沿 1=下降沿 */
    uint16_t val;       /* pwm: 比较值 tick; 其他 0 */
};

/* 设备树生成的实例配置 (字段由 scripts/gen_devicetree.py 输出) */
struct gd32_gtimer_cfg {
    uint8_t  timer_idx;     /* 硬件号 1~4 */
    uint32_t clock_hz;      /* 输入时钟 (APB1 定时器时钟) */
    uint16_t psc_reg;       /* 预分频装入值 */
    uint16_t arr_reg;       /* 重装值 (freq/pwmcap 模式全速计数, arr=0xFFFF) */
    uint8_t  mode;          /* GD32_TIMER_MODE_* */
    uint8_t  irq_mode;      /* 1=中断 0=查询 */
    uint8_t  remap;         /* 0=默认 1=部分 2=完全 */
    struct gd32_gtim_chan chans[4];
};

/* 以下 API 的 idx 都是设备树实例下标 (DT_GTIMx_IDX) */

/* 运行控制 */
void     general_timer_start(uint8_t idx);   /* 计数开始 */
void     general_timer_stop(uint8_t idx);    /* 计数暂停 */
uint32_t general_timer_count(uint8_t idx);   /* 当前计数值 */

/* 只读访问实例配置 (换算函数要用, 越界返回 NULL) */
const struct gd32_gtimer_cfg *general_timer_cfg_get(uint8_t idx);

/* PWM 占空比 (千分比 1~1000) —— 正弦可当调光; 千分比 0/1000 直接拉常电平 */
void general_timer_pwm_duty(uint8_t idx, uint8_t chan, uint16_t duty_milli);

/* 输入捕获查询 (freq/pwmcap 模式, 无需中断, 软件读最新两次捕获差算) */
struct gtim_cap {
    uint32_t period_clk;    /* 一个信号周期 = N 个计数时钟 (0=尚无两次捕获) */
    uint32_t high_clk;      /* 高电平时长 = N 个计数时钟 (仅 pwmcap; freq 为 0) */
};
struct gtim_cap general_timer_cap_read(uint8_t idx);

/* 便捷换算: 捕获原始计数 -> 频率 Hz / 占空比万分比 (整型运算) */
uint32_t gtim_cap_freq_hz(const struct gd32_gtimer_cfg *cfg, const struct gtim_cap *cap);
uint32_t gtim_cap_duty_tenk(const struct gd32_gtimer_cfg *cfg, const struct gtim_cap *cap);

/* 事件中断回调 (timebase 更新中断 / 捕获模式捕获中断, weak, 应用覆盖)
 * 中断上下文, 应短小 (置标志可以, printf 不行) */
void general_timer_callback(uint8_t idx);

#endif
