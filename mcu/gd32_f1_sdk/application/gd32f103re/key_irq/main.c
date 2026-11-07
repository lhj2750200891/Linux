/**
 * @file  main.c
 * @brief key_irq 应用 —— 中断方式按键点灯
 *
 * 现象: 灯平时全灭, 按 key_k 翻转第 k 个 LED,
 * 按哪个亮哪个, 松手不灭, 再按同键熄灭; 无需主循环扫描。
 *
 * 工作方式由板级 dts keys 容器的 key-mode = <KEY_MODE_IRQ> 决定,
 * 应用层零改动可切到轮询 (改成 KEY_MODE_POLL + debounce-ms 即可)。
 * 板级 dts: arm/boards/gd32f103re/gd32f103re.dts (KEY_MODE_IRQ)
 */
#include "main.h"

#include "led.h"
#include "key.h"

/* 按键事件标志 (中断置位, 主循环取走), bit k = 第 k 键待处理 */
static volatile uint8_t key_events;

/* 按键中断回调 (弱回调覆盖, EXTI 中断上下文, 只置标志) */
void key_callback(uint8_t idx)
{
    key_events |= (uint8_t)(1U << idx);
}

int main(void)
{
    SCB->VTOR = FLASH_START;

    while (1) {
        uint8_t ev = key_events;
        if (ev) {
            key_events = 0;
            for (uint8_t i = 0; i < KEY_COUNT; i++) {
                if (ev & (1U << i)) {
                    led_toggle(i);        /* 按 key_k 翻转第 k 个灯 */
                }
            }
        }
        /* 主循环空闲: 中断模式下无事可做, 等待按键事件 */
        __WFI();                          /* 睡到下次中断, 现象不受影响 */
    }
}
