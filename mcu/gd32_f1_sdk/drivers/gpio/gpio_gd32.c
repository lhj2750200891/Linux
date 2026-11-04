/**
 * @file  gpio_gd32.c
 * @brief GD32 GPIO 核心驱动实现
 */
#include "gpio_gd32.h"

#include "gd32f10x.h"

/* 端口序号 -> 外设基址 / RCU 时钟 (与 dtsi 中 port-idx 对应) */
static const uint32_t port_base[] = { GPIOA, GPIOB, GPIOC, GPIOD, GPIOE };
static const rcu_periph_enum port_rcu[] = {
    RCU_GPIOA, RCU_GPIOB, RCU_GPIOC, RCU_GPIOD, RCU_GPIOE
};

/* fwlib 模式编码的 bit4 = 输出类型(推挽/开漏/复用) */
#define GPIO_MODE_OUTPUT_BIT   0x10U

static inline uint32_t pin_mask(uint8_t pin)
{
    return (uint32_t)1U << pin;
}

void gd32_gpio_configure(const struct gd32_gpio_cfg *cfg)
{
    if (cfg == NULL || cfg->port >= (sizeof(port_base) / sizeof(port_base[0]))) {
        return;
    }

    rcu_periph_clock_enable(port_rcu[cfg->port]);
    gpio_init(port_base[cfg->port], cfg->mode, GPIO_OSPEED_50MHZ, pin_mask(cfg->pin));

    /* 输出类引脚: 按设备树 init-level 写入初始电平 */
    if ((cfg->mode & GPIO_MODE_OUTPUT_BIT) == GPIO_MODE_OUTPUT_BIT) {
        gpio_bit_write(port_base[cfg->port], pin_mask(cfg->pin), cfg->level ? SET : RESET);
    }
}

void gd32_gpio_write(const struct gd32_gpio_cfg *cfg, uint8_t level)
{
    if (cfg == NULL || cfg->port >= (sizeof(port_base) / sizeof(port_base[0]))) {
        return;
    }
    gpio_bit_write(port_base[cfg->port], pin_mask(cfg->pin), level ? SET : RESET);
}

uint8_t gd32_gpio_read(const struct gd32_gpio_cfg *cfg)
{
    if (cfg == NULL || cfg->port >= (sizeof(port_base) / sizeof(port_base[0]))) {
        return 0;
    }
    return gpio_input_bit_get(port_base[cfg->port], pin_mask(cfg->pin)) ? 1U : 0U;
}

void gd32_gpio_toggle(const struct gd32_gpio_cfg *cfg)
{
    if (cfg == NULL || cfg->port >= (sizeof(port_base) / sizeof(port_base[0]))) {
        return;
    }
    bit_status level = gpio_output_bit_get(port_base[cfg->port], pin_mask(cfg->pin));
    gpio_bit_write(port_base[cfg->port], pin_mask(cfg->pin), !level);
}
