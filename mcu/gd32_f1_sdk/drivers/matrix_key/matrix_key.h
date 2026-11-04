/**
 * @file  matrix_key.h
 * @brief 矩阵键盘驱动 (设备树 matrix-keys 节点 -> 逐行扫描)
 */
#ifndef DRIVERS_MATRIX_KEY_MATRIX_KEY_H
#define DRIVERS_MATRIX_KEY_MATRIX_KEY_H

#include <stdint.h>

#include "devicetree_generated.h"

/* 初始化由 DEVICE_INIT 自动完成 (main 之前), 应用层直接使用下面的 API */
uint8_t matrix_key_scan(void);    /**< 扫描矩阵键盘, 松开时返回键值(1~行x列), 无返回 0 */

#endif
