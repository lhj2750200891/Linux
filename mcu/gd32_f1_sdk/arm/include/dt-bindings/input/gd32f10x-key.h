/*
 * dt-bindings: GD32F10x 独立按键扩展参数编码
 *
 * keys 容器属性 key-mode 与子节点属性 trigger 在 .dts 中使用,
 * 由 cpp 预处理器展开 (与 gd32f10x-gpio.h 同一机制)。
 */

#ifndef DT_BINDINGS_INPUT_GD32F10X_KEY_H
#define DT_BINDINGS_INPUT_GD32F10X_KEY_H

/* keys 容器: key-mode 属性 (工作方式) */
#define KEY_MODE_IRQ     0    /* EXTI 外部中断 (默认): 按键触发中断, 免轮询 */
#define KEY_MODE_POLL    1    /* 轮询: 主循环周期调用 key_scan(), 免中断 */

/* 按键子节点: trigger 属性 (中断触发类型, 仅 key-mode=<KEY_MODE_IRQ> 有效) */
#define KEY_TRIG_RISING  0    /* 上升沿触发 (active-level=1 的按键按下瞬间) */
#define KEY_TRIG_FALLING 1    /* 下降沿触发 (active-level=0 的按键按下瞬间, 默认) */
#define KEY_TRIG_BOTH    2    /* 双沿触发 (按下和松开都进中断, 配合状态判断) */

#endif
