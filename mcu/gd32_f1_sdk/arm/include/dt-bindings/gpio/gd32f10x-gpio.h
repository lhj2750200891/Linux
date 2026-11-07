/*
 * dt-bindings: GD32F10x GPIO 模式编码
 *
 * 数值与 fwlib 的 GPIO_MODE_* 完全一致 (fwlib/Include/gd32f10x_gpio.h),
 * 因此设备树里的模式值可以原样传给 gpio_init()。
 * 在 .dts/.dtsi 中使用, 由 cpp 预处理器展开。
 */

#ifndef DT_BINDINGS_GPIO_GD32F10X_GPIO_H
#define DT_BINDINGS_GPIO_GD32F10X_GPIO_H

#define GD32_MODE_AIN              0x00   /* 模拟输入 */
#define GD32_MODE_IN_FLOATING      0x04   /* 浮空输入 */
#define GD32_MODE_IPD              0x28   /* 下拉输入 */
#define GD32_MODE_IPU              0x48   /* 上拉输入 */
#define GD32_MODE_OUT_OD           0x14   /* 开漏输出 */
#define GD32_MODE_OUT_PP           0x10   /* 推挽输出 */
#define GD32_MODE_AF_OD            0x1C   /* 复用开漏 */
#define GD32_MODE_AF_PP            0x18   /* 复用推挽 */

/* 电平约定: 0 = 低电平, 1 = 高电平 */
#define GD32_LEVEL_LOW             0
#define GD32_LEVEL_HIGH            1

#endif
