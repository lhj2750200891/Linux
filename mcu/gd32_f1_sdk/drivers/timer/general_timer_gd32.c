/**
 * @file  general_timer_gd32.c
 * @brief GD32F10x 通用定时器驱动 (TIMER1~4) —— 实例表由设备树生成
 *
 * 匹配条件: CONFIG_DRIVER_TIMER=y 且设备树存在 general-timers 节点
 * (DT_GENERAL_TIMERS_COUNT > 0)。
 *
 * 四种模式 (设备树 mode 属性):
 *   TIMEBASE  周期更新中断, 同基本定时器 (弱回调 general_timer_callback)
 *   PWM       1~4 通道 PWM 输出, PWM0 模式 (占空 = CHxCV/(CAR+1), 高有效)
 *   FREQ      单通道输入捕获测频 (上升/下降沿可选, 软件轮询即可用)
 *   PWMCAP    相邻双通道测频+占空比: 低号通道直连上升沿,
 *             高号通道交叉到同一引脚下降沿 (引脚只需配低号通道的)
 *
 * 寄存器直写 (fwlib 无 timer 模块), 位定义对照完整版 gd32f10x_timer.h:
 *   CTL0=0x00 (CEN=bit0)  CTL1=0x04  SMCFG=0x08  DMAINTEN=0x0C (UPIE=bit0!)
 *   INTF=0x10 (写 0 清除)  SWEVG=0x14 (UPG=bit0)  CHCTL0=0x18  CHCTL1=0x1C
 *   CHCTL2=0x20  CNT=0x24  PSC=0x28  CAR=0x2C  CH0CV=0x34 +0x04*n
 * CHCTL0 管 CH0/CH1, CHCTL1 管 CH2/CH3; 每通道 8 位一段 (高位奇数通道):
 *   CHxMS=bit0-1 (out: 10b 输出比较 / in: 01b 直连 CIx 10b 交叉)  COMCTL=bit4-6
 *   PWM0=110b  CAPPSC=bit2-3  CAPFLT=bit4-7
 * CHCTL2: CHxEN=bit(4n)  CHxP=bit(4n+1) (输入捕获 1=下降沿)
 * 中断使能位: DMAINTEN bit0=UPIE bit1~4=CH0IE..CH3IE (UPIE=更新中断, 别写成
 * bit8 UPDEN —— 那是 DMA 请求, 参考 basic_timer 的教训)
 *
 * remap: 引脚重映射走 vendor fwlib gpio_pin_remap_config (AFIO PCF0)。
 */
#include "general_timer.h"

#include <stddef.h>

#include "gd32f10x.h"
#include "devicetree_generated.h"
#include "init_fn_macros.h"
#include "gd32f10x_misc.h"
#include "gd32f10x_rcu.h"
#include "gd32f10x_gpio.h"
#include "gpio_gd32.h"
#include <dt-bindings/timer/gd32f10x-timer.h>

#if DT_GENERAL_TIMERS_COUNT > 0

/* TIMER1~4 基址 (APB1: 0x40000000/0x40000400/0x40000800/0x40000C00) */
static const uint32_t gtimer_base[] = {
    0x40000000U, 0x40000400U, 0x40000800U, 0x40000C00U
};
static const rcu_periph_enum gtimer_rcu[] = { RCU_TIMER1, RCU_TIMER2, RCU_TIMER3, RCU_TIMER4 };
static const IRQn_Type gtimer_irqn[] = { TIMER1_IRQn, TIMER2_IRQn, TIMER3_IRQn, TIMER4_IRQn };

/* 寄存器访问 (base 为基址, off 随宏) */
#define GT_REG(base, off)      (*(__IO uint32_t *)((base) + (off)))
#define GT_CTL0(base)          GT_REG((base), 0x00U)
#define GT_DMAINTEN(base)      GT_REG((base), 0x0CU)
#define GT_INTF(base)          GT_REG((base), 0x10U)
#define GT_SWEVG(base)         GT_REG((base), 0x14U)
#define GT_CHCTL0(base)        GT_REG((base), 0x18U)      /* CH0/CH1 */
#define GT_CHCTL1(base)        GT_REG((base), 0x1CU)      /* CH2/CH3 */
#define GT_CHCTL2(base)        GT_REG((base), 0x20U)
#define GT_CNT(base)           GT_REG((base), 0x24U)
#define GT_PSC(base)           GT_REG((base), 0x28U)
#define GT_CAR(base)           GT_REG((base), 0x2CU)

#define GT_CEN                 (1U << 0)      /* 计数器使能 */
#define GT_UPDF                (1U << 0)      /* 更新标志 (写 0 清除) */
#define GT_UPIE                (1U << 0)      /* 更新中断使能 */
#define GT_UPG                 (1U << 0)      /* 软件更新事件 */

/* INTF 通道捕获标志 bit1~4 = CH0IF..CH3IF (与 DMAINTEN CHxIE 位号同步) */
#define GT_CHIF(ch)            (1U << (1U + (ch)))

/* 每通道 CHCTL 配置位段 (CHCTL0 低 8 位=CH0 高 8 位=CH1; CHCTL1 同理 CH2/CH3) */
#define GT_CHCTL_SHIFT(ch)     (((ch) & 1U) * 8U)

/* 输出比较: CHxMS=10b (输出), COMCTL=110b (PWM0) */
#define GT_OCCTL_PWM0          0x60U          /* 0110 0000b: MS=10 COMCTL=PWM0 */
#define GT_OCCTL_PWM1          0x70U          /* 0111 0000b: MS=10 COMCTL=PWM1 */

/* 输入捕获: CHxMS=01b (直连 CIx) / 10b (交叉 CIy), CAPPSC=00 CAPFLT=0000 */
#define GT_ICCTL_DIRECT_RISE   0x01U          /* 0000 0001b */
#define GT_ICCTL_INDIRECT_FALL 0x02U          /* 0000 0010b: MS=10b 交叉 + 下降沿(CHCTL2) */

/* CHCTL2: 通道使能 bit(4n), 极性 bit(4n+1), 1=下降沿/低有效 */
#define GT_CHEN(ch)            (1U << ((ch) * 4U))
#define GT_CHP(ch)             (1U << ((ch) * 4U + 1U))

/* remap: fwlib 的 gpio_pin_remap_config 编码值 (仅 APB1 TIMER1~3 支持) */
static const uint32_t gtimer_remap_cfg[4][3] = {
    /* TIMER1 */ { 0, GPIO_TIMER1_PARTIAL_REMAP0, GPIO_TIMER1_FULL_REMAP },
    /* TIMER2 */ { 0, GPIO_TIMER2_PARTIAL_REMAP, GPIO_TIMER2_FULL_REMAP },
    /* TIMER3 */ { 0, GPIO_TIMER3_REMAP, 0 },
    /* TIMER4 */ { 0, 0, 0 },
};

/* 设备树生成的实例表 */
static const struct gd32_gtimer_cfg dt_gtimers[DT_GENERAL_TIMERS_COUNT] = {
    DT_GENERAL_TIMERS_INSTANCES
};

/* 实例 -> 硬件号映射 (irq 分发反查用) */
static uint8_t gtimer_hw_of[DT_GENERAL_TIMERS_COUNT];

/* freq/pwmcap 捕获模式: ISR 内计算的最新结果 (volatile, 主循环轮询读) */
static volatile struct {
    uint16_t last_rise;     /* 上一次上升沿捕获值 (周期差计算基准) */
    uint16_t last_fall;     /* 最近一次下降沿捕获值 */
    uint32_t period_clk;    /* 最新周期 (计数时钟数), 0=尚未有两个上升沿 */
    uint32_t high_clk;      /* 最新高电平时长 (pwmcap, freq 为 0) */
} gtimer_cap[DT_GENERAL_TIMERS_COUNT];

static inline const struct gd32_gtimer_cfg *gtimer_cfg(uint8_t idx)
{
    return (idx < DT_GENERAL_TIMERS_COUNT) ? &dt_gtimers[idx] : NULL;
}

static inline uint32_t gtimer_reg_base(uint8_t hw)
{
    return gtimer_base[hw - 1U];
}

/* ---------------------------------------------------------------------- */
/* 通道配置                                                                */
/* ---------------------------------------------------------------------- */

static void gtimer_chan_gpio(const struct gd32_gtimer_cfg *cfg,
                             const struct gd32_gtim_chan *ch)
{
    struct gd32_gpio_cfg gpio = {
        .port = ch->port, .pin = ch->pin, .mode = ch->pinmode,
        .level = 0, .trigger = 0,
    };
    gd32_gpio_configure(&gpio);
}

/* ---------------------------------------------------------------------- */
/* 初始化 (DEVICE_INIT, main 之前自动跑)                                    */
/* ---------------------------------------------------------------------- */

static void general_timer_init_all(void)
{
    for (uint8_t i = 0; i < DT_GENERAL_TIMERS_COUNT; i++) {
        const struct gd32_gtimer_cfg *cfg = &dt_gtimers[i];
        uint8_t hw = cfg->timer_idx;
        uint32_t base = gtimer_reg_base(hw);

        gtimer_hw_of[i] = hw;
        rcu_periph_clock_enable(gtimer_rcu[hw - 1U]);
        if (cfg->remap) {
            rcu_periph_clock_enable(RCU_AF);      /* AFIO 时钟 */
            gpio_pin_remap_config(gtimer_remap_cfg[hw - 1U][cfg->remap - 1U], ENABLE);
        }

        /* 时基公共部分 */
        GT_CTL0(base) = 0U;                       /* 停止计数 */
        GT_PSC(base) = cfg->psc_reg;

        if (cfg->mode == GD32_TIMER_MODE_TIMEBASE ||
            cfg->mode == GD32_TIMER_MODE_PWM) {
            GT_CAR(base) = cfg->arr_reg;
        } else {
            /* 捕获模式: 全速自由跑, 16 位最大余量, PSC 由 prescaler 决定 */
            GT_CAR(base) = 0xFFFFU;
        }

        /* 通道配置 */
        GT_CHCTL0(base) = 0U;
        GT_CHCTL1(base) = 0U;
        GT_CHCTL2(base) = 0U;
        for (uint8_t c = 0; c < 4U; c++) {
            const struct gd32_gtim_chan *ch = &cfg->chans[c];
            if (ch->ch == 0xFFU) { continue; }
            uint32_t shift = GT_CHCTL_SHIFT(ch->ch);
            __IO uint32_t *chreg = (ch->ch < 2U) ? &GT_CHCTL0(base) : &GT_CHCTL1(base);

            if (cfg->mode == GD32_TIMER_MODE_PWM) {
                /* PWM 输出: AF_PP 引脚已由 gtimer_chan_gpio 配, 设 PWM0/PWM1 */
                gtimer_chan_gpio(cfg, ch);
                *chreg &= ~(0xFFU << shift);
                *chreg |= (uint32_t)(ch->aux ? GT_OCCTL_PWM1 : GT_OCCTL_PWM0) << shift;
                /* 比较值: CHxCV 偏移 0x34 + 4*ch */
                GT_REG(base, 0x34U + 4U * ch->ch) = ch->val;
                GT_CHCTL2(base) |= GT_CHEN(ch->ch);           /* 使能输出, 高有效 */
            } else if (cfg->mode == GD32_TIMER_MODE_FREQ) {
                /* 测频: 直连捕获, 上升/下降沿由 polarity */
                gtimer_chan_gpio(cfg, ch);
                *chreg &= ~(0xFFU << shift);
                *chreg |= (uint32_t)GT_ICCTL_DIRECT_RISE << shift;
                GT_CHCTL2(base) |= GT_CHEN(ch->ch);
                if (ch->aux) { GT_CHCTL2(base) |= GT_CHP(ch->ch); }
            } else if (cfg->mode == GD32_TIMER_MODE_PWMCAP) {
                /* 双通道: 低号通道直连上升沿, 高号通道交叉到低号引脚下降沿
                 * —— 两个通道引脚相同, 高号通道的 gpio 配置被忽略 */
                if ((ch->ch & 1U) == 0U) {
                    /* 低号通道 (CH0/CH2): 引脚配输入, 直连捕获上升沿 */
                    gtimer_chan_gpio(cfg, ch);
                    *chreg &= ~(0xFFU << shift);
                    *chreg |= (uint32_t)GT_ICCTL_DIRECT_RISE << shift;
                    GT_CHCTL2(base) |= GT_CHEN(ch->ch);           /* CHxP=0 上升沿 */
                } else {
                    /* 高号通道 (CH1/CH3): 交叉输入低号引脚, 下降沿极性 */
                    *chreg &= ~(0xFFU << shift);
                    *chreg |= (uint32_t)GT_ICCTL_INDIRECT_FALL << shift;
                    GT_CHCTL2(base) |= GT_CHEN(ch->ch) | GT_CHP(ch->ch); /* 下降沿 */
                }
            }
        }

        /* 软件更新事件装入 PSC/CAR, 清标志, 按需开中断 */
        GT_DMAINTEN(base) = 0U;
        GT_SWEVG(base) = GT_UPG;
        GT_INTF(base) = 0U;                       /* 清配置期间置位的全部标志 */

        if (cfg->mode == GD32_TIMER_MODE_TIMEBASE && cfg->irq_mode) {
            GT_DMAINTEN(base) = GT_UPIE;
            nvic_irq_enable(gtimer_irqn[hw - 1U], 2, 0);
        } else if (cfg->mode == GD32_TIMER_MODE_PWM && cfg->irq_mode) {
            /* pwm 模式默认不开中断; irq-mode=1 时开更新中断 */
            GT_DMAINTEN(base) = GT_UPIE;
            nvic_irq_enable(gtimer_irqn[hw - 1U], 2, 0);
        } else if (cfg->mode == GD32_TIMER_MODE_FREQ || cfg->mode == GD32_TIMER_MODE_PWMCAP) {
            /* 捕获模式: 必须开通道中断 —— 周期差值必须在 ISR 内算,
             * 轮询间隔大于信号周期时读到的是轮询间隔的模值 (错误结果) */
            uint32_t chie = 0U;
            for (uint8_t c = 0; c < 4U; c++) {
                if (cfg->chans[c].ch != 0xFFU) { chie |= GT_CHIF((cfg->chans[c].ch)); }
            }
            GT_DMAINTEN(base) = chie;
            nvic_irq_enable(gtimer_irqn[hw - 1U], 2, 0);
        }

        GT_CTL0(base) = GT_CEN;                   /* 启动 */
    }
}
DEVICE_INIT(general_timer, general_timer_init_all, GD_INIT_DEVICE);

/* ---------------------------------------------------------------------- */
/* 运行控制 API                                                            */
/* ---------------------------------------------------------------------- */

void general_timer_start(uint8_t idx)
{
    const struct gd32_gtimer_cfg *cfg = gtimer_cfg(idx);
    if (cfg == NULL) { return; }
    GT_CTL0(gtimer_reg_base(cfg->timer_idx)) |= GT_CEN;
}

void general_timer_stop(uint8_t idx)
{
    const struct gd32_gtimer_cfg *cfg = gtimer_cfg(idx);
    if (cfg == NULL) { return; }
    GT_CTL0(gtimer_reg_base(cfg->timer_idx)) &= ~GT_CEN;
}

uint32_t general_timer_count(uint8_t idx)
{
    const struct gd32_gtimer_cfg *cfg = gtimer_cfg(idx);
    if (cfg == NULL) { return 0; }
    return GT_CNT(gtimer_reg_base(cfg->timer_idx)) & 0xFFFFU;
}

const struct gd32_gtimer_cfg *general_timer_cfg_get(uint8_t idx)
{
    return gtimer_cfg(idx);
}

void general_timer_pwm_duty(uint8_t idx, uint8_t chan, uint16_t duty_milli)
{
    const struct gd32_gtimer_cfg *cfg = gtimer_cfg(idx);
    uint32_t arr;

    if (cfg == NULL || cfg->mode != GD32_TIMER_MODE_PWM || chan > 3U) { return; }
    if (cfg->chans[chan].ch == 0xFFU) { return; }
    arr = cfg->arr_reg;
    /* 千分比 -> 比较值, 限制到 [1, arr] 保证波形有效 */
    uint32_t cval = ((uint32_t)duty_milli * (arr + 1U)) / 1000U;
    if (cval < 1U) { cval = 1U; }
    if (cval > arr) { cval = arr; }
    GT_REG(gtimer_reg_base(cfg->timer_idx), 0x34U + 4U * chan) = cval;
}

struct gtim_cap general_timer_cap_read(uint8_t idx)
{
    /* 纯读取: 结果由捕获 ISR 维护 (差值必须在每个沿的中断里计算,
     * 轮询周期大于信号周期时直接读 CHxCV 差是错的) */
    struct gtim_cap cap = { 0, 0 };
    if (idx >= DT_GENERAL_TIMERS_COUNT) { return cap; }
    cap.period_clk = gtimer_cap[idx].period_clk;
    cap.high_clk = gtimer_cap[idx].high_clk;
    return cap;
}

uint32_t gtim_cap_freq_hz(const struct gd32_gtimer_cfg *cfg, const struct gtim_cap *cap)
{
    /* freq = clock_hz / prescaler / period_clk; 整型: 先乘后除 */
    if (cap->period_clk == 0U) { return 0; }
    return cfg->clock_hz / ((uint32_t)(cfg->psc_reg + 1U) * cap->period_clk);
}

uint32_t gtim_cap_duty_tenk(const struct gd32_gtimer_cfg *cfg, const struct gtim_cap *cap)
{
    (void)cfg;
    if (cap->period_clk == 0U) { return 0; }
    return cap->high_clk * 10000U / cap->period_clk;
}

/* ---------------------------------------------------------------------- */
/* 中断服务: 捕获模式通道中断 -> 最新捕获值已锁存, 只需清标志通知回调        */
/* ---------------------------------------------------------------------- */

void gd32_gtimer_irq_handler(uint8_t hw)
{
    uint32_t base = gtimer_reg_base(hw);

    for (uint8_t i = 0; i < DT_GENERAL_TIMERS_COUNT; i++) {
        if (gtimer_hw_of[i] != hw) { continue; }
        const struct gd32_gtimer_cfg *cfg = &dt_gtimers[i];
        uint32_t intena = GT_DMAINTEN(base);
        uint32_t flags = GT_INTF(base);

        if ((flags & GT_UPDF) && (intena & GT_UPIE)) {
            GT_INTF(base) = ~GT_UPDF;
            general_timer_callback(i);
        }
        /* 捕获模式: 通道中断里读 CHxCV 计算周期/高电平差值 */
        if (cfg->mode == GD32_TIMER_MODE_FREQ) {
            uint8_t ch = 0xFFU;
            for (uint8_t c = 0; c < 4U; c++) {
                if (cfg->chans[c].ch != 0xFFU) { ch = cfg->chans[c].ch; break; }
            }
            if (ch != 0xFFU && (flags & GT_CHIF(ch))) {
                uint16_t now = (uint16_t)(GT_REG(base, 0x34U + 4U * ch) & 0xFFFFU);
                uint16_t last = gtimer_cap[i].last_rise;
                if (now != last) {
                    gtimer_cap[i].period_clk = (last < now) ? (now - last)
                                                            : (0x10000U + now - last);
                }
                gtimer_cap[i].last_rise = now;
                GT_INTF(base) = ~GT_CHIF(ch);
            }
        } else if (cfg->mode == GD32_TIMER_MODE_PWMCAP) {
            /* 低号通道=上升沿直连, 高号=交叉下降沿 (引脚共用) */
            uint8_t lo = 0xFFU, hi = 0xFFU;
            for (uint8_t c = 0; c < 4U; c++) {
                uint8_t getch = cfg->chans[c].ch;
                if (getch == 0xFFU) { continue; }
                if (lo == 0xFFU || getch < lo) { lo = getch; }
                if (hi == 0xFFU || getch > hi) { hi = getch; }
            }
            if (flags & GT_CHIF(hi)) {
                /* 下降沿: 记录, 高电平 = fall - 上一上升沿 */
                gtimer_cap[i].last_fall =
                    (uint16_t)(GT_REG(base, 0x34U + 4U * hi) & 0xFFFFU);
                GT_INTF(base) = ~GT_CHIF(hi);
            }
            if (flags & GT_CHIF(lo)) {
                /* 上升沿: 周期 = 本次 - 上次上升沿; 高电平用最近下降沿算 */
                uint16_t rise = (uint16_t)(GT_REG(base, 0x34U + 4U * lo) & 0xFFFFU);
                uint16_t last = gtimer_cap[i].last_rise;
                if (rise != last) {
                    uint16_t fall = gtimer_cap[i].last_fall;
                    gtimer_cap[i].period_clk = (rise > last) ? (rise - last)
                                                             : (0x10000U + rise - last);
                    /* 高电平 = 下降沿 - 上次上升沿 (同一周期内: fall >= last) */
                    gtimer_cap[i].high_clk = (fall >= last) ? (fall - last)
                                                            : (0x10000U + fall - last);
                }
                gtimer_cap[i].last_rise = rise;
                GT_INTF(base) = ~GT_CHIF(lo);
            }
        }
        return;
    }
    /* 设备树没配的硬件中断 (不该到这): 清全部标志防挂死 */
    GT_INTF(base) = 0U;
}

void TIMER1_IRQHandler(void) { gd32_gtimer_irq_handler(1); }
void TIMER2_IRQHandler(void) { gd32_gtimer_irq_handler(2); }
void TIMER3_IRQHandler(void) { gd32_gtimer_irq_handler(3); }
void TIMER4_IRQHandler(void) { gd32_gtimer_irq_handler(4); }

#else /* 设备树没有 general-timers 节点: 空实现保证编译 */

void general_timer_start(uint8_t idx) { (void)idx; }
void general_timer_stop(uint8_t idx) { (void)idx; }
uint32_t general_timer_count(uint8_t idx) { (void)idx; return 0; }
const struct gd32_gtimer_cfg *general_timer_cfg_get(uint8_t idx)
{ (void)idx; return NULL; }
void general_timer_pwm_duty(uint8_t idx, uint8_t chan, uint16_t duty_milli)
{ (void)idx; (void)chan; (void)duty_milli; }
struct gtim_cap general_timer_cap_read(uint8_t idx)
{ (void)idx; struct gtim_cap cap = {0, 0}; return cap; }
uint32_t gtim_cap_freq_hz(const struct gd32_gtimer_cfg *cfg, const struct gtim_cap *cap)
{ (void)cfg; (void)cap; return 0; }
uint32_t gtim_cap_duty_tenk(const struct gd32_gtimer_cfg *cfg, const struct gtim_cap *cap)
{ (void)cfg; (void)cap; return 0; }

#endif

/* weak 回调默认实现 (两种编译路径都要有) */
__attribute__((weak)) void general_timer_callback(uint8_t idx) { (void)idx; }
