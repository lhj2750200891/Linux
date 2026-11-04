/**
 * @file  key.h
 * @brief 独立按键驱动 (设备树 keys 节点)
 *
 * 驱动不关心按键的名字与个数 —— 个数、引脚、按下电平全部来自设备树:
 *   KEY_COUNT          设备树 keys 节点的 count 属性
 *   key_scan() 返回值  1 ~ KEY_COUNT (下标+1), 0 = 无按键
 *   key_read(0..N-1)   下标 = 设备树子节点顺序 (key1->0, key2->1, ...)
 *
 * 需要按名字访问某个按键时, 使用设备树生成的宏: key1 节点 -> DT_KEY1_IDX
 *   例: key_read(DT_KEY1_IDX);
 */
#ifndef DRIVERS_KEY_KEY_H
#define DRIVERS_KEY_KEY_H

#include <stdint.h>

#include "devicetree_generated.h"

/* 按键个数(设备树描述, 驱动中不写死) */
#define KEY_COUNT   DT_KEYS_COUNT

extern uint8_t Key_Num;    /**< 最近一次 key_scan() 的键值 (1~KEY_COUNT, 0=无) */

/* 初始化由 DEVICE_INIT 自动完成 (main 之前), 应用层直接使用下面的 API */
uint8_t key_read(uint8_t idx);    /**< 读原始电平: 0/1 */
uint8_t key_scan(void);           /**< 带消抖扫描, 返回键值(下标+1), 无按键返回 0 */

#endif
