/*
 * dt-bindings: GD32F10x SPI 扩展参数编码
 *
 * 在 .dts/.dtsi 中使用, 由 cpp 预处理器展开 (与 gd32f10x-gpio.h 同一机制),
 * 驱动 (drivers/spi/spi_gd32.c) 与设备树共用同一份定义。
 * CPOL/CPHA 组合即 SPI 四种模式: 0/0=MODE0, 0/1=MODE1, 1/0=MODE2, 1/1=MODE3
 */

#ifndef DT_BINDINGS_SPI_GD32F10X_SPI_H
#define DT_BINDINGS_SPI_GD32F10X_SPI_H

/* 帧长 (spi 实例节点 frame-size 属性) */
#define GD32_SPI_FRAME_8BIT    0    /* 8 位帧 (默认, 绝大多数设备) */
#define GD32_SPI_FRAME_16BIT   1    /* 16 位帧 */

/* 时钟空闲电平 CPOL (cpol 属性) */
#define GD32_SPI_CPOL_LOW      0    /* 空闲低电平 (默认) */
#define GD32_SPI_CPOL_HIGH     1    /* 空闲高电平 */

/* 采样边沿 CPHA (cpha 属性) */
#define GD32_SPI_CPHA_1EDGE    0    /* 第一个边沿采样 (默认) */
#define GD32_SPI_CPHA_2EDGE    1    /* 第二个边沿采样 */

/* 移位方向 (first-bit 属性) */
#define GD32_SPI_FIRST_MSB     0    /* 高位在前 (默认, 绝大多数设备) */
#define GD32_SPI_FIRST_LSB     1    /* 低位在前 */

#endif
