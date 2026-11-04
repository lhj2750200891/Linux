/**
 * @file  systick_gd32.c
 * @brief SysTick 延时驱动 —— CPU 时钟来自设备树, 查询 COUNTFLAG 实现阻塞延时
 *
 * 设备树 (SoC dtsi, 板级可覆写 clock-frequency):
 *   systick: systick@e000e010 {
 *       compatible = "gd,cortex-m-systick";
 *       clock-frequency = <108000000>;    // CPU 时钟, 延时基准
 *   };
 *
 * 滴答时钟源 = CPU 时钟 / 8 (外部时钟, 与 vendor 库例程一致)。
 * 换算用 64 位中间值, 精确到 tick, 无累计误差。
 */
#include "gd32f10x.h"
#include "systick.h"
#include "devicetree_generated.h"
#include "init_fn_macros.h"

#if DT_SYSTICK_CLOCK_FREQUENCY == 0
#error "设备树缺少 systick 节点(gd,cortex-m-systick)或未配置 clock-frequency"
#endif

/* 滴答时钟源 = CPU 时钟 / 8 */
#define SYSTICK_FREQ   (DT_SYSTICK_CLOCK_FREQUENCY / 8U)

static void systick_init(void)
{
    SysTick->CTRL &= ~SysTick_CTRL_CLKSOURCE_Msk;    /* CLKSOURCE=0: 外部时钟 CPU/8 */
}
DEVICE_INIT(systick, systick_init, GD_INIT_EARLY);

/* 装入计数值, 查询等待计数完成; 单次最大 (2^24-1) 个 tick */
static void systick_delay_ticks(uint32_t ticks)
{
    uint32_t ctrl;

    SysTick->LOAD = ticks;
    SysTick->VAL  = 0;
    SysTick->CTRL |= SysTick_CTRL_ENABLE_Msk;
    do {
        ctrl = SysTick->CTRL;                        /* 先读寄存器再判断, 避免误差 */
    } while (!(ctrl & SysTick_CTRL_COUNTFLAG_Msk) && (ctrl & SysTick_CTRL_ENABLE_Msk));
    SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
}

void sys_delay_us(uint32_t us)
{
    systick_delay_ticks((uint32_t)((uint64_t)us * SYSTICK_FREQ / 1000000U));
}

void sys_delay_ms(uint32_t ms)
{
    systick_delay_ticks((uint32_t)((uint64_t)ms * SYSTICK_FREQ / 1000U));
}
