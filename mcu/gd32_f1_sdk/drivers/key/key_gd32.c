/**
 * @file  key_gd32.c
 * @brief 独立按键驱动实现 —— 实例表由设备树生成 (DT_KEYS_INSTANCES)
 *
 * 两种工作方式由设备树 keys 容器的 key-mode 属性选择:
 *   KEY_MODE_IRQ  (默认) EXTI 外部中断: 引脚边沿触发, 免主循环轮询,
 *                  每键触发类型 trigger 属性可配(上升/下降/双沿),
 *                  置 Key_Num 并调用弱回调 key_callback(idx)
 *   KEY_MODE_POLL        纯轮询: 应用周期调用 key_scan()(与旧版行为一致),
 *                  消抖时间容器属性 debounce-ms 可配(默认 20ms)
 *
 * 两种模式 API 完全兼容: key_scan() 在中断模式下从事件标志取键值,
 * 应用代码不用关心模式。key_read() 始终读实时电平。
 *
 * EXTI 说明: fwlib V2.6.0 未带 gd32f10x_exti.c, 这里直接操作 EXTI
 * 寄存器 (IMR/RTSR/FTSR/PR 偏移 0/4/8/14, GD32F10x 与 STM32F1 相同),
 * AFIO 信号源选择用 fwlib 的 gpio_exti_source_select()。
 */
#include "key.h"

#include "systick.h"
#include "gpio_gd32.h"
#include "init_fn_macros.h"

#include "gd32f10x.h"

#if DT_KEYS_COUNT > 0

/* 设备树编译期生成的按键实例表 (含按下电平 level 与中断触发类型 trigger) */
static const struct gd32_gpio_cfg dt_keys[DT_KEYS_COUNT] = { DT_KEYS_INSTANCES };
uint8_t Key_Num = 0;

__attribute__((weak)) void key_callback(uint8_t idx) { (void)idx; }    /* 弱回调, 应用可覆盖 */

/* 按下状态 = 电平与设备树 active-level 一致 */
static uint8_t key_is_pressed(uint8_t idx)
{
    return gd32_gpio_read(&dt_keys[idx]) == dt_keys[idx].level;
}

uint8_t key_read(uint8_t idx)
{
    if (idx >= DT_KEYS_COUNT) {
        return 0;
    }
    return gd32_gpio_read(&dt_keys[idx]);
}

/* EXTI 寄存器 (基地址 EXTI_BASE, 按字节偏移直取):
 * IMR=0x00 EMR=0x04 RTSR=0x08 FTSR=0x0C SWIER=0x10 PR=0x14
 * (注意 EMR 在 IMR 之后, 别把 RTSR 算到 0x04 上) */
#define EXTI_REG(off)   (*(__IO uint32_t *)(EXTI_BASE + (off)))
#define EXTI_IMR        EXTI_REG(0x00)
#define EXTI_RTSR       EXTI_REG(0x08)
#define EXTI_FTSR       EXTI_REG(0x0C)
#define EXTI_PR         EXTI_REG(0x14)
#define EXTI_LINE(pin)  (1U << (pin))

/* ================================================================== */
/* 模式一: EXTI 中断 (key-mode = KEY_MODE_IRQ, 默认)                   */
/* ================================================================== */
#if DT_KEYS_MODE == 0

/* 事件标志: bit i = 第 i 个键触发过(已消抖), 等应用 key_scan() 取走 */
static volatile uint8_t key_event_flags;

/* EXTI 线号 == 引脚号 (Px_n 都走 EXTI_n): 找回按下按键的下标 */
static uint8_t key_idx_by_pin(uint8_t pin)
{
    for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
        if (dt_keys[i].pin == pin) {
            return i;
        }
    }
    return 0xFF;
}

static void key_exti_trig(uint8_t pin)
{
    /* 清挂起标志: PR 写 1 清零 (写 0 无效, 不影响其他线) */
    EXTI_PR = EXTI_LINE(pin);

    uint8_t idx = key_idx_by_pin(pin);
    if (idx == 0xFF) {
        return;                        /* 本线没配按键(其他模块占用) */
    }

    /* 电平二次确认 = 消抖: 边沿过后引脚应稳定在按下电平。
     * 抖动毛刺在几 us 内会弹回松开电平, 被这里滤掉 */
    if (key_is_pressed(idx)) {
        key_event_flags |= (uint8_t)(1U << idx);
        Key_Num = (uint8_t)(idx + 1);  /* 与轮询版 Key_Num 语义一致 */
        key_callback(idx);             /* 中断上下文, 应用覆盖时应短小 */
    }
}

/* 向量名与启动文件 startup_gd32f10x_hd.S 一致 */
void EXTI0_IRQHandler(void)  { key_exti_trig(0); }
void EXTI1_IRQHandler(void)  { key_exti_trig(1); }
void EXTI2_IRQHandler(void)  { key_exti_trig(2); }
void EXTI3_IRQHandler(void)  { key_exti_trig(3); }
void EXTI4_IRQHandler(void)  { key_exti_trig(4); }

void EXTI5_9_IRQHandler(void)
{
    for (uint8_t pin = 5; pin <= 9; pin++) {
        if (EXTI_PR & EXTI_LINE(pin)) {
            key_exti_trig(pin);
        }
    }
}

void EXTI10_15_IRQHandler(void)
{
    for (uint8_t pin = 10; pin <= 15; pin++) {
        if (EXTI_PR & EXTI_LINE(pin)) {
            key_exti_trig(pin);
        }
    }
}

/* 中断模式 key_scan: 取走事件标志, 返回语义与轮询版一致 (下标+1, 一次性) */
uint8_t key_scan(void)
{
    uint8_t flags = key_event_flags;
    if (flags) {
        for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
            if (flags & (1U << i)) {
                key_event_flags &= (uint8_t)~(1U << i);
                return (uint8_t)(i + 1);
            }
        }
    }
    return 0;
}

static void key_init_all(void)
{
    /* 同引脚号不同端口的键会互相顶掉 AFIO EXTI 源 (Px_n 只有一个源),
     * 这里直接拒绝初始化并停住, 提示改设备树 */
    for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
        for (uint8_t j = (uint8_t)(i + 1); j < DT_KEYS_COUNT; j++) {
            if (dt_keys[i].pin == dt_keys[j].pin) {
                return;                /* 引脚冲突: 两键都失效, 需改 dts */
            }
        }
    }

    rcu_periph_clock_enable(RCU_AF);
    for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
        const struct gd32_gpio_cfg *k = &dt_keys[i];
        uint32_t line = EXTI_LINE(k->pin);

        gd32_gpio_configure(k);

        /* AFIO: EXTI 线 k->pin 的信号源 = 本按键端口 */
        gpio_exti_source_select(k->port, k->pin);

        /* 触发类型 trigger: 0=上升 1=下降(默认) 2=双沿 */
        if (k->trigger == 0 || k->trigger == 2) {
            EXTI_RTSR |= line;
        }
        if (k->trigger == 1 || k->trigger == 2) {
            EXTI_FTSR |= line;
        }
        EXTI_PR    = line;             /* 清历史挂起再开中断 */
        EXTI_IMR  |= line;             /* 开放该线中断请求 */

        /* NVIC: 线 0~4 独立向量, 5~9 / 10~15 共享向量 */
        if (k->pin < 5) {
            NVIC_EnableIRQ((IRQn_Type)(EXTI0_IRQn + k->pin));
        } else if (k->pin < 10) {
            NVIC_EnableIRQ(EXTI5_9_IRQn);
        } else {
            NVIC_EnableIRQ(EXTI10_15_IRQn);
        }
    }
}
DEVICE_INIT(key, key_init_all, GD_INIT_DEVICE);

/* ================================================================== */
/* 模式二: 纯轮询 (key-mode = KEY_MODE_POLL)                           */
/* ================================================================== */
#else   /* DT_KEYS_MODE == 1 */

static uint8_t key_any_pressed(void)
{
    for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
        if (key_is_pressed(i)) {
            return 1;
        }
    }
    return 0;
}

/* 与旧版 key_scan() 行为一致: 松开状态首次检测到按下 -> 消抖 -> 键值(下标+1) */
uint8_t key_scan(void)
{
    static uint8_t key_up = 1;    /* 松开标志 */

    if (key_up && key_any_pressed()) {
        key_up = 0;
        sys_delay_ms(DT_KEYS_DEBOUNCE_MS);    /* 消抖时间来自设备树(默认 20ms) */

        for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
            if (key_is_pressed(i)) {
                Key_Num = (uint8_t)(i + 1);
                return (uint8_t)(i + 1);
            }
        }
    }

    if (!key_any_pressed()) {
        key_up = 1;
    }
    return 0;
}

static void key_init_all(void)
{
    for (uint8_t i = 0; i < DT_KEYS_COUNT; i++) {
        gd32_gpio_configure(&dt_keys[i]);
    }
}
DEVICE_INIT(key, key_init_all, GD_INIT_DEVICE);

#endif  /* DT_KEYS_MODE */

#else /* 设备树中没有 key 节点: 提供空实现, 保证编译通过 */

uint8_t Key_Num = 0;
uint8_t key_read(uint8_t idx) { (void)idx; return 0; }
uint8_t key_scan(void) { return 0; }

#endif
