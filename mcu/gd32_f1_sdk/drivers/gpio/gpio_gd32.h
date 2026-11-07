/**
 * @file  gpio_gd32.h
 * @brief GD32 GPIO 核心驱动 —— 引脚信息来自设备树生成的实例表
 *
 * 设备树生成的每个 GPIO 实例都对应本结构体
 * (见 build/generated/devicetree_generated.h 的 DT_xxx_INSTANCES 宏):
 */
#ifndef DRIVERS_GPIO_GPIO_GD32_H
#define DRIVERS_GPIO_GPIO_GD32_H

#include <stddef.h>
#include <stdint.h>

#include "gd32f10x_rcu.h"
#include "gd32f10x_gpio.h"

struct gd32_gpio_cfg {
	uint8_t port;    /**< 端口序号: A=0 B=1 C=2 D=3 E=4 (设备树 port-idx) */
	uint8_t pin;     /**< 引脚号 0~15 */
	uint8_t mode;    /**< GD32 模式编码, 与 fwlib GPIO_MODE_* 一致 (dt-bindings 定义) */
	uint8_t level;   /**< 语义由上层驱动解释:
			  *   输出类(LED/矩阵行) -> 上电初始电平
			  *   输入类(按键/矩阵列) -> 按下时的有效电平 */
	uint8_t trigger; /**< 仅按键驱动使用: EXTI 触发类型 KEY_TRIG_* (其他实例为 0) */
};

void gd32_gpio_configure(const struct gd32_gpio_cfg *cfg);
void gd32_gpio_write(const struct gd32_gpio_cfg *cfg, uint8_t level);
uint8_t gd32_gpio_read(const struct gd32_gpio_cfg *cfg);
void gd32_gpio_toggle(const struct gd32_gpio_cfg *cfg);

#endif
