/*
 * dt-bindings: GD32F10x I2C 扩展参数编码
 *
 * 在 .dts/.dtsi 中使用, 由 cpp 预处理器展开 (与 gd32f10x-gpio.h 同一机制),
 * 驱动 (drivers/i2c/i2c_gd32.c) 与设备树共用同一份定义。
 */

#ifndef DT_BINDINGS_I2C_GD32F10X_I2C_H
#define DT_BINDINGS_I2C_GD32F10X_I2C_H

/* SCL 速率档位 (i2c 实例节点 speed 属性)
 * GD32F10x 硬件 I2C 支持标准/快速两档, 对应 fwlib i2c_clock_config() 的 clkspeed */
#define GD32_I2C_SPEED_STANDARD  0    /* 标准模式 100 kHz (默认) */
#define GD32_I2C_SPEED_FAST      1    /* 快速模式 400 kHz (总线须有足够上拉) */

/* 从机地址书写约定 (仿 Linux i2c 设备):
 *   从机节点 reg = <0x3C>  即 7 位地址, 不含读写位
 *   (驱动内部发送时 addr<<1 | 方向位)
 * 合法范围 0x08 ~ 0x77, 生成脚本会校验 */

#endif
