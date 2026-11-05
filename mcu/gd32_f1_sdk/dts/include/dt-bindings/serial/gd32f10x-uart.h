/*
 * dt-bindings: GD32F10x UART/USART 扩展参数编码
 *
 * pinctrl 引脚复用(Remux)标志 (加在 GPIO 引脚模式值上, 位[7:6]):
 *   uart 驱动在设备树中写 pinctrl-0 = <&uart1 ...PA9 组合...> 之外,
 *   还支持用户手动组合引脚(rx 上拉/浮空可选)。
 *
 * 数据位/停止位/校验位编码 (uart 节点 line-ctl 属性):
 *   DATA_8/9      : 数据位 8 或 9 (9 位含校验位场合)
 *   STOP_1/0_5/2  : 停止位
 *   PM_NONE/EVEN/ODD : 校验 无/偶/奇
 *
 * 在 .dts/.dtsi 中使用, 由 cpp 预处理器展开 (与 gd32f10x-gpio.h 同一机制)。
 */

#ifndef DT_BINDINGS_SERIAL_GD32F10X_UART_H
#define DT_BINDINGS_SERIAL_GD32F10X_UART_H

/* 数据位 (USART_CTL0 WL 位) */
#define GD32_UART_DATA_8       0    /* 8 个数据位 */
#define GD32_UART_DATA_9       1    /* 9 个数据位 */

/* 停止位 (USART_CTL1 STB 位域) */
#define GD32_UART_STOP_1       0    /* 1 个停止位 */
#define GD32_UART_STOP_0_5     1    /* 0.5 个停止位 (智能卡模式) */
#define GD32_UART_STOP_2       2    /* 2 个停止位 */

/* 校验 (USART_CTL0 PM 位域) */
#define GD32_UART_PM_NONE      0    /* 无校验 */
#define GD32_UART_PM_EVEN      2    /* 偶校验 */
#define GD32_UART_PM_ODD       3    /* 奇校验 */

/* 中断使能标志 (uart 节点errupts 属性的标志单元, 可组合) */
#define GD32_UART_INT_NONE     0    /* 纯轮询 */
#define GD32_UART_INT_RX       1    /* RBNE 接收中断(每字节) */
#define GD32_UART_INT_IDLE     2    /* IDLE 空闲中断(不定长帧) */
#define GD32_UART_INT_RX_IDLE  3    /* RBNE + IDLE (常用组合) */

#endif
