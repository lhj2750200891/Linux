/**
 * @file  systick.h
 * @brief SysTick 延时驱动 (驱动接口)
 *
 * CPU 时钟频率来自设备树 systick 节点的 clock-frequency 属性,
 * 滴答时钟源 = CPU 时钟 / 8 (外部时钟)。
 * 单次延时上限约 1.2s (SysTick LOAD 为 24 位)。
 */
#ifndef __SYSTICK_H_
#define __SYSTICK_H_

#include <stdint.h>

/* 初始化由 DEVICE_INIT 自动完成 (main 之前), 应用层直接使用下面的 API */
void sys_delay_us(uint32_t us);
void sys_delay_ms(uint32_t ms);

#endif
