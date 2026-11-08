/**
 * @file  basic_timer_gd32.c
 * @brief GD32F10x 基本定时器驱动 (TIMER5/6) —— 实例表由设备树生成
 *
 * 匹配条件: CONFIG_DRIVER_BASIC_TIMER=y 且设备树存在 basic-timers 节点
 * (DT_BASIC_TIMERS_COUNT > 0)。
 *
 * 基本定时器只有 16 位向上计数 + 溢出(更新)事件, 没有 GPIO 通道。
 * 典型用途: 周期时基/系统节拍/给 DAC 提供触发。驱动提供:
 *   - 周期溢出中断: 设备树 irq-mode=<1> (默认), 应用覆盖 weak 回调
 *       void basic_timer_callback(uint8_t idx)   (idx = 实例下标)
 *   - 纯计数模式:   irq-mode=<0>, 应用 basic_timer_start/stop/
 *       basic_timer_count 自行查询 (无中断)
 *
 * 寄存器直写 (fwlib 无 timer 模块, 与 EXTI 驱动同思路), 位定义与偏移
 * 对照完整版 gd32f10x_timer.h (BIT 定义见下方宏):
 *   CTL0=0x00 (CEN=bit0)   DMAINTEN=0x0C (UPIE=bit0)   INTF=0x10 (UPDF=bit0)
 *   SWEVG=0x14 (UPG=bit0)  CNT=0x24  PSC=0x28  CAR=0x2C
 * 更新中断使能是 UPIE (bit0); bit8 的 UPDEN 是更新 DMA 请求使能, 别混淆。
 * UPDF 清除: 向 INTF 对应位写 0 (GD32 定时器惯例, 与 EXTI 的写 1 清除相反)。
 *
 * 注意 APB1 定时器时钟: APB1 分频 != 1 时定时器时钟自动 x2。
 * 108M 主频下 APB1=54MHz -> 定时器时钟 108MHz, 设备树 clock-hz 应写 108000000。
 * 溢出周期 = (PSC+1)*(CAR+1)/clock-hz。
 */
#include "basic_timer.h"

#include <stddef.h>

#include "gd32f10x.h"
#include "devicetree_generated.h"
#include "init_fn_macros.h"
#include "gd32f10x_misc.h"
#include "gd32f10x_rcu.h"

#if DT_BASIC_TIMERS_COUNT > 0

/* TIMER5/6 基址 (APB1: TIMER5=0x40001000, TIMER6=0x40001400) */
static const uint32_t btimer_base[] = { 0x40001000U, 0x40001400U };
static const rcu_periph_enum btimer_rcu[] = { RCU_TIMER5, RCU_TIMER6 };
static const IRQn_Type btimer_irqn[] = { TIMER5_IRQn, TIMER6_IRQn };

/* 寄存器偏移 + 位定义 (对照 GD32F10x 用户手册 / 完整版 fwlib 头文件) */
#define BT_CTL0(base)       (*(__IO uint32_t *)((base) + 0x00U))
#define BT_DMAINTEN(base)   (*(__IO uint32_t *)((base) + 0x0CU))
#define BT_INTF(base)       (*(__IO uint32_t *)((base) + 0x10U))
#define BT_SWEVG(base)      (*(__IO uint32_t *)((base) + 0x14U))
#define BT_CNT(base)        (*(__IO uint32_t *)((base) + 0x24U))
#define BT_PSC(base)        (*(__IO uint32_t *)((base) + 0x28U))
#define BT_CAR(base)        (*(__IO uint32_t *)((base) + 0x2CU))

#define BT_CTL0_CEN         (1U << 0)      /* 计数器使能 */
#define BT_INTF_UPDF        (1U << 0)      /* 更新标志 (写 0 清除) */
#define BT_DMAINTEN_UPIE    (1U << 0)      /* 更新中断使能 (UPIE=bit0!) */
#define BT_SWEVG_UPG        (1U << 0)      /* 软件更新事件 */

/* 设备树生成的实例表 */
static const struct gd32_btimer_cfg dt_btimers[DT_BASIC_TIMERS_COUNT] = {
    DT_BASIC_TIMERS_INSTANCES
};

/* 实例 -> 硬件号映射 (irq 分发反查用) */
static uint8_t btimer_hw_of[DT_BASIC_TIMERS_COUNT];

static inline const struct gd32_btimer_cfg *btimer_cfg(uint8_t idx)
{
    return (idx < DT_BASIC_TIMERS_COUNT) ? &dt_btimers[idx] : NULL;
}

static inline uint32_t btimer_reg_base(uint8_t hw)
{
    return btimer_base[hw - 5U];
}

/* ---------------------------------------------------------------------- */
/* 初始化 (DEVICE_INIT, main 之前自动跑)                                    */
/* ---------------------------------------------------------------------- */

static void basic_timer_init_all(void)
{
    for (uint8_t i = 0; i < DT_BASIC_TIMERS_COUNT; i++) {
        const struct gd32_btimer_cfg *cfg = &dt_btimers[i];
        uint8_t hw = cfg->timer_idx;
        uint32_t base;

        btimer_hw_of[i] = hw;
        rcu_periph_clock_enable(btimer_rcu[hw - 5U]);
        base = btimer_reg_base(hw);

        BT_CTL0(base) = 0U;                    /* 停止计数, 清配置 */
        BT_PSC(base)  = cfg->psc_reg;          /* 预分频 */
        BT_CAR(base)  = cfg->arr_reg;          /* 重装值 */

        /* 软件更新事件: 把 PSC/CAR 从影子寄存器装入生效。
         * 副作用是会置位 UPDF, 所以放在开中断之前 + 随后清标志。 */
        BT_DMAINTEN(base) = 0U;                /* 中断使能先关 */
        BT_SWEVG(base) = BT_SWEVG_UPG;
        BT_INTF(base) = ~BT_INTF_UPDF;         /* 清 UPDF (写 0) */

        if (cfg->irq_mode) {
            /* 更新中断使能 = UPIE (DMAINTEN bit0)。
             * 注意 bit8 是 UPDEN (更新 DMA 请求使能), 不要混淆 ——
             * 写成 0x100 会出现计数正常/UPDF 置位但 NVIC 永不 pending。 */
            BT_DMAINTEN(base) = BT_DMAINTEN_UPIE;
            nvic_irq_enable(btimer_irqn[hw - 5U], 2, 0);
        }

        /* 启动计数 (初始化完即运行, 要后启动的应用可先 basic_timer_stop) */
        BT_CTL0(base) = BT_CTL0_CEN;
    }
}
DEVICE_INIT(basic_timer, basic_timer_init_all, GD_INIT_DEVICE);

/* ---------------------------------------------------------------------- */
/* 运行控制 API                                                             */
/* ---------------------------------------------------------------------- */

void basic_timer_start(uint8_t idx)
{
    const struct gd32_btimer_cfg *cfg = btimer_cfg(idx);
    if (cfg == NULL) { return; }
    BT_CTL0(btimer_reg_base(cfg->timer_idx)) |= BT_CTL0_CEN;
}

void basic_timer_stop(uint8_t idx)
{
    const struct gd32_btimer_cfg *cfg = btimer_cfg(idx);
    if (cfg == NULL) { return; }
    BT_CTL0(btimer_reg_base(cfg->timer_idx)) &= ~BT_CTL0_CEN;
}

uint32_t basic_timer_count(uint8_t idx)
{
    const struct gd32_btimer_cfg *cfg = btimer_cfg(idx);
    if (cfg == NULL) { return 0; }
    return BT_CNT(btimer_reg_base(cfg->timer_idx)) & 0xFFFFU;
}

void basic_timer_reload(uint8_t idx)
{
    const struct gd32_btimer_cfg *cfg = btimer_cfg(idx);
    if (cfg == NULL) { return; }
    BT_SWEVG(btimer_reg_base(cfg->timer_idx)) = BT_SWEVG_UPG;
}

/* ---------------------------------------------------------------------- */
/* 中断服务: 更新事件 -> 按硬件号反查实例 + weak 回调                        */
/* ---------------------------------------------------------------------- */

void gd32_btimer_irq_handler(uint8_t hw)
{
    uint32_t base = btimer_reg_base(hw);

    for (uint8_t i = 0; i < DT_BASIC_TIMERS_COUNT; i++) {
        if (btimer_hw_of[i] != hw) { continue; }
        if (BT_INTF(base) & BT_INTF_UPDF) {
            BT_INTF(base) = ~BT_INTF_UPDF;     /* 写 0 清除 UPDF */
            basic_timer_callback(i);
        }
        return;
    }
    /* 设备树没配的硬件中断 (不该到这): 清标志防止挂死 */
    BT_INTF(base) = 0U;
}

void TIMER5_IRQHandler(void) { gd32_btimer_irq_handler(5); }
void TIMER6_IRQHandler(void) { gd32_btimer_irq_handler(6); }

#else /* CONFIG 开但设备树没有 basic-timers 节点: 空实现保证编译 */

void basic_timer_start(uint8_t idx) { (void)idx; }
void basic_timer_stop(uint8_t idx) { (void)idx; }
uint32_t basic_timer_count(uint8_t idx) { (void)idx; return 0; }
void basic_timer_reload(uint8_t idx) { (void)idx; }

#endif

/* weak 回调默认实现 (两种编译路径都要有) */
__attribute__((weak)) void basic_timer_callback(uint8_t idx) { (void)idx; }
