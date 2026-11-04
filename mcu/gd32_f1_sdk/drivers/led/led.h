/**
 * @file  led.h
 * @brief LED 驱动 (设备树 leds 节点)
 *
 * 驱动不关心 LED 的名字与个数 —— 个数、引脚全部来自设备树:
 *   LED_COUNT          设备树 leds 节点的 count 属性
 *   led_set(0..N-1)    下标 = 设备树子节点顺序 (led1->0, led2->1, ...)
 *
 * 需要按名字访问某个 LED 时, 使用设备树生成的宏: led1 节点 -> DT_LED1_IDX
 *   例: led_set(DT_LED1_IDX, 1);
 */
#ifndef DRIVERS_LED_LED_H
#define DRIVERS_LED_LED_H

#include <stdint.h>

#include "devicetree_generated.h"

/* LED 个数(设备树描述, 驱动中不写死) */
#define LED_COUNT   DT_LEDS_COUNT

/* 初始化由 DEVICE_INIT 自动完成 (main 之前), 应用层直接使用下面的 API */
void led_set(uint8_t idx, uint8_t on);       /* idx: 0 ~ LED_COUNT-1 */
void led_toggle(uint8_t idx);

#endif
