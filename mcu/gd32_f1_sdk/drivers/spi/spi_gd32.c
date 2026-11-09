/**
 * @file  spi_gd32.c
 * @brief GD32F10x SPI 主机驱动实现 —— 实例/从机表由设备树生成
 *
 * 匹配条件: CONFIG_DRIVER_SPI=y 且设备树存在 spi-buses 节点 (DT_SPI_BUSES_COUNT > 0)。
 *
 * 工作方式: 主机模式 + 全双工轮询 + 超时保护, 软件片选。
 *   - 波特率: PCLK (SPI0=CK_APB2, SPI1/2=CK_APB1) / 2^(psc+1), 取不超过
 *     baud-hz 的最高档; dts 里只写目标频率, 换算在驱动初始化时完成
 *   - 片选: 每个从机一个 GPIO (cs-gpios), 传输前拉低、完成后拉高;
 *     一主多从 = 从机表里多条目指向同一 bus, 轮询传输天然互斥
 *   - 16 位帧: len 以帧为单位, DATA 寄存器按 16 位读写
 *
 * 注意: PA15/PB3/PB4 复用为 JTAG (JTDO/NJTRST/JTDI), SPI0 重映射组与 SPI2
 * 固定组都落在这些脚上 —— 驱动检测到后自动禁 JTAG 保留 SWD (PA13/PA14)。
 */
#include "spi_gd32.h"

#include <stddef.h>

#include "gd32f10x.h"
#include "devicetree_generated.h"
#include "init_fn_macros.h"
#include "gd32f10x_rcu.h"
#include "gd32f10x_gpio.h"
#include "gd32f10x_spi.h"

/* dt-bindings 编码 (帧长/极性相位/移位方向), 设备树与驱动共用同一份定义 */
#include "dt-bindings/spi/gd32f10x-spi.h"

#if DT_SPI_BUSES_COUNT > 0

/* 设备树生成的实例表 / 从机表 */
static const struct gd32_spi_cfg dt_spi_buses[DT_SPI_BUSES_COUNT] = { DT_SPI_BUSES_INSTANCES };
#if DT_SPI_SLAVES_COUNT > 0
static const struct gd32_spi_slave dt_spi_slaves[DT_SPI_SLAVES_COUNT] = { DT_SPI_SLAVES };
#endif

/* 每条总线的传输重入保护 (主循环与中断同时访问同一总线时拒绝后者) */
static volatile uint8_t spi_busy[DT_SPI_BUSES_COUNT];

/* GPIO 端口基址/时钟表 (与 uart 驱动 port-idx 约定一致: A=0..E=4) */
static const uint32_t spi_port_base[] = { GPIOA, GPIOB, GPIOC, GPIOD, GPIOE };
static const rcu_periph_enum spi_port_rcu[] = {
    RCU_GPIOA, RCU_GPIOB, RCU_GPIOC, RCU_GPIOD, RCU_GPIOE
};

/* spi-idx -> 外设时钟 */
static const rcu_periph_enum spi_rcu[] = { RCU_SPI0, RCU_SPI1, RCU_SPI2 };

/* spi-idx -> AFIO 重映射码 (0 = 不重映射) */
static const uint32_t spi_remap_code[] = {
    GPIO_SPI0_REMAP,                   /* SPI0: PA5/PA6/PA7 -> PB3/PB4/PB5 */
    0U,                                /* SPI1: PB13/PB14/PB15 固定 */
    0U,                                /* SPI2: PB3/PB4/PB5 固定 (无独立重映射) */
};

/* 等标志超时: 轮询循环次数 (108MHz 下约数十 ms, 正常传输远小于此) */
#define SPI_TMO_LOOPS  0x20000U

/* ---------------------------------------------------------------------- */
/* 内部工具                                                                */
/* ---------------------------------------------------------------------- */

static inline const struct gd32_spi_cfg *bus_cfg(uint8_t bus)
{
    return (bus < DT_SPI_BUSES_COUNT) ? &dt_spi_buses[bus] : NULL;
}

/* 从机下标 -> 从机表项; disabled/未挂载 (DT_IDX_DISABLED) 及越界返回 NULL */
static inline const struct gd32_spi_slave *slave_get(uint8_t slave)
{
#if DT_SPI_SLAVES_COUNT > 0
    return (slave < DT_SPI_SLAVES_COUNT) ? &dt_spi_slaves[slave] : NULL;
#else
    (void)slave;
    return NULL;
#endif
}

static int spi_wait_flag(uint32_t periph, uint32_t flag)
{
    uint32_t tmo = SPI_TMO_LOOPS;

    while (!(SPI_STAT(periph) & flag)) {
        if (--tmo == 0) {
            return GD_SPI_ERR_TIMEOUT;
        }
    }
    return GD_SPI_OK;
}

static inline uint32_t cs_base(const struct gd32_spi_slave *s)
{
    return spi_port_base[s->cs_port];
}

static inline uint32_t cs_mask(const struct gd32_spi_slave *s)
{
    return (uint32_t)1U << s->cs_pin;
}

/* PA15/PB3/PB4 复用 JTAG, 上电默认 JTAG-DP 使能, 直接配 GPIO 无效;
 * 检测到这三个脚时禁 JTAG 保留 SWD (PA13/PA14 仍可调试) */
static void spi_release_jtag_pins(const struct gd32_spi_cfg *cfg)
{
    uint8_t jtag = 0;

    jtag |= (cfg->sck_port == 0 && cfg->sck_pin == 15);
    jtag |= (cfg->miso_port == 0 && cfg->miso_pin == 15);
    jtag |= (cfg->mosi_port == 0 && cfg->mosi_pin == 15);
    jtag |= (cfg->sck_port == 1 && cfg->sck_pin <= 4 && cfg->sck_pin >= 3);
    jtag |= (cfg->miso_port == 1 && cfg->miso_pin <= 4 && cfg->miso_pin >= 3);
    jtag |= (cfg->mosi_port == 1 && cfg->mosi_pin <= 4 && cfg->mosi_pin >= 3);

    if (jtag) {
        rcu_periph_clock_enable(RCU_AF);
        gpio_pin_remap_config(GPIO_SWJ_SWDPENABLE_REMAP, ENABLE);
    }
}

/* ---------------------------------------------------------------------- */
/* 传输                                                                    */
/* ---------------------------------------------------------------------- */

/* 全双工核心: CS 由调用方控制。len = 帧数, 8/16 位帧统一按宽度访问 DATA */
static int spi_xfer_frames(uint8_t bus, const uint8_t *tx, uint8_t *rx, uint16_t len)
{
    const struct gd32_spi_cfg *cfg = bus_cfg(bus);
    uint32_t periph = cfg->periph;
    int wide = cfg->frame16;
    uint16_t i;
    int rc;

    for (i = 0; i < len; i++) {
        rc = spi_wait_flag(periph, SPI_STAT_TBE);
        if (rc != GD_SPI_OK) {
            return rc;
        }
        if (wide) {
            const uint16_t *tx16 = (const uint16_t *)(const void *)tx;
            uint16_t *rx16 = (uint16_t *)(void *)rx;
            uint16_t out = tx ? tx16[i] : 0xFFFFU;
            SPI_DATA(periph) = out;
            rc = spi_wait_flag(periph, SPI_STAT_RBNE);
            if (rc != GD_SPI_OK) {
                return rc;
            }
            if (rx) {
                rx16[i] = (uint16_t)SPI_DATA(periph);
            }
        } else {
            SPI_DATA(periph) = tx ? tx[i] : 0xFFU;
            rc = spi_wait_flag(periph, SPI_STAT_RBNE);
            if (rc != GD_SPI_OK) {
                return rc;
            }
            if (rx) {
                rx[i] = (uint8_t)SPI_DATA(periph);
            }
        }
    }
    /* 等最后一位彻底移出再让调用方抬 CS, 避免末帧被截断 */
    return spi_wait_flag(periph, SPI_STAT_TRANS);
}

/* 片选包裹的一次完整传输 (从机表驱动 CS, 无软片选则直接传输) */
static int spi_dev_xfer(uint8_t slave, const uint8_t *tx, uint8_t *rx, uint16_t len)
{
    const struct gd32_spi_slave *s = slave_get(slave);
    if (s == NULL || len == 0) {
        return GD_SPI_ERR_PARAM;
    }
    const struct gd32_spi_cfg *cfg = bus_cfg(s->bus);
    if (cfg == NULL || spi_busy[s->bus]) {
        return GD_SPI_ERR_BUSY;
    }
    spi_busy[s->bus] = 1;

    int rc = GD_SPI_OK;
    if (s->cs != 0xFFU) {
        rcu_periph_clock_enable(spi_port_rcu[s->cs_port]);
        gpio_bit_reset(cs_base(s), cs_mask(s));          /* 选中: CS 拉低 */
    }
    rc = spi_xfer_frames(s->bus, tx, rx, len);
    if (s->cs != 0xFFU) {
        gpio_bit_set(cs_base(s), cs_mask(s));            /* 释放: CS 抬高 */
    }

    spi_busy[s->bus] = 0;
    return rc;
}

/* ---------------------------------------------------------------------- */
/* 初始化                                                                  */
/* ---------------------------------------------------------------------- */

static void spi_init_one(uint8_t idx)
{
    const struct gd32_spi_cfg *cfg = &dt_spi_buses[idx];
    spi_parameter_struct init;

    /* 引脚: SCK/MOSI 复用推挽, MISO 浮空输入 */
    rcu_periph_clock_enable(spi_port_rcu[cfg->sck_port]);
    rcu_periph_clock_enable(spi_port_rcu[cfg->miso_port]);
    rcu_periph_clock_enable(spi_port_rcu[cfg->mosi_port]);
    if (cfg->remap) {
        rcu_periph_clock_enable(RCU_AF);
        gpio_pin_remap_config(spi_remap_code[cfg->spi_idx], ENABLE);
    }
    spi_release_jtag_pins(cfg);

    gpio_init(spi_port_base[cfg->sck_port],  GPIO_MODE_AF_PP, GPIO_OSPEED_50MHZ,
              (uint32_t)1U << cfg->sck_pin);
    gpio_init(spi_port_base[cfg->mosi_port], GPIO_MODE_AF_PP, GPIO_OSPEED_50MHZ,
              (uint32_t)1U << cfg->mosi_pin);
    gpio_init(spi_port_base[cfg->miso_port], GPIO_MODE_IN_FLOATING, GPIO_OSPEED_50MHZ,
              (uint32_t)1U << cfg->miso_pin);

    rcu_periph_clock_enable(spi_rcu[cfg->spi_idx]);
    spi_i2s_deinit(cfg->periph);

    /* 波特率: SCLK = PCLK / 2^(psc+1), 取不超过 baud-hz 的最高档
     * (SPI0 挂 APB2, SPI1/2 挂 APB1) */
    uint32_t pclk = (cfg->spi_idx == 0) ? rcu_clock_freq_get(CK_APB2)
                                        : rcu_clock_freq_get(CK_APB1);
    uint32_t psc = 0;
    while (psc < 7 && (pclk >> (psc + 1)) > cfg->baud_hz) {
        psc++;
    }

    spi_struct_para_init(&init);
    init.device_mode          = SPI_MASTER;
    init.trans_mode           = SPI_TRANSMODE_FULLDUPLEX;
    init.frame_size           = cfg->frame16 ? SPI_FRAMESIZE_16BIT : SPI_FRAMESIZE_8BIT;
    init.nss                  = SPI_NSS_SOFT;       /* 软片选, NSS 引脚不参与 */
    init.endian               = cfg->lsb_first ? SPI_ENDIAN_LSB : SPI_ENDIAN_MSB;
    init.clock_polarity_phase = ((cfg->cpol ? SPI_CTL0_CKPL : 0U) |
                                 (cfg->cpha ? SPI_CTL0_CKPH : 0U));
    init.prescale             = CTL0_PSC(psc);
    spi_init(cfg->periph, &init);
    spi_enable(cfg->periph);

    spi_busy[idx] = 0;

    /* 从机片选上电即置空闲 (高), 避免意外选中 */
#if DT_SPI_SLAVES_COUNT > 0
    for (uint8_t s = 0; s < DT_SPI_SLAVES_COUNT; s++) {
        const struct gd32_spi_slave *sl = &dt_spi_slaves[s];
        if (sl->bus == idx && sl->cs != 0xFFU) {
            rcu_periph_clock_enable(spi_port_rcu[sl->cs_port]);
            gpio_init(cs_base(sl), sl->cs_mode, GPIO_OSPEED_50MHZ, cs_mask(sl));
            gpio_bit_set(cs_base(sl), cs_mask(sl));
        }
    }
#endif
}

static void spi_init_all(void)
{
    for (uint8_t i = 0; i < DT_SPI_BUSES_COUNT; i++) {
        spi_init_one(i);
    }
}
DEVICE_INIT(spi, spi_init_all, GD_INIT_DEVICE);

/* ---------------------------------------------------------------------- */
/* 设备级 API                                                              */
/* ---------------------------------------------------------------------- */

int spi_transfer(uint8_t slave, const uint8_t *tx, uint8_t *rx, uint16_t len)
{
    return spi_dev_xfer(slave, tx, rx, len);
}

int spi_write(uint8_t slave, const uint8_t *buf, uint16_t len)
{
    if (buf == NULL) {
        return GD_SPI_ERR_PARAM;
    }
    return spi_dev_xfer(slave, buf, NULL, len);
}

int spi_read(uint8_t slave, uint8_t *buf, uint16_t len)
{
    if (buf == NULL) {
        return GD_SPI_ERR_PARAM;
    }
    return spi_dev_xfer(slave, NULL, buf, len);
}

int spi_write_then_read(uint8_t slave, const uint8_t *wr, uint16_t wlen,
                        uint8_t *rd, uint16_t rlen)
{
    if (wr == NULL || rd == NULL || wlen == 0 || rlen == 0) {
        return GD_SPI_ERR_PARAM;
    }
    const struct gd32_spi_slave *s = slave_get(slave);
    if (s == NULL) {
        return GD_SPI_ERR_PARAM;
    }
    const struct gd32_spi_cfg *cfg = bus_cfg(s->bus);
    if (cfg == NULL || spi_busy[s->bus]) {
        return GD_SPI_ERR_BUSY;
    }
    spi_busy[s->bus] = 1;

    /* CS 全程有效: 手动选中 -> 两段传输 -> 释放 */
    int rc = GD_SPI_OK;
    if (s->cs != 0xFFU) {
        rcu_periph_clock_enable(spi_port_rcu[s->cs_port]);
        gpio_bit_reset(cs_base(s), cs_mask(s));
    }
    for (uint16_t i = 0; i < wlen && rc == GD_SPI_OK; i++) {
        rc = spi_wait_flag(cfg->periph, SPI_STAT_TBE);
        if (rc == GD_SPI_OK) {
            SPI_DATA(cfg->periph) = wr[i];
            rc = spi_wait_flag(cfg->periph, SPI_STAT_RBNE);
            if (rc == GD_SPI_OK) {
                (void)SPI_DATA(cfg->periph);     /* 写段的回读丢弃 */
            }
        }
    }
    for (uint16_t i = 0; i < rlen && rc == GD_SPI_OK; i++) {
        rc = spi_wait_flag(cfg->periph, SPI_STAT_TBE);
        if (rc == GD_SPI_OK) {
            SPI_DATA(cfg->periph) = 0xFFU;
            rc = spi_wait_flag(cfg->periph, SPI_STAT_RBNE);
            if (rc == GD_SPI_OK) {
                rd[i] = (uint8_t)SPI_DATA(cfg->periph);
            }
        }
    }
    if (rc == GD_SPI_OK) {
        rc = spi_wait_flag(cfg->periph, SPI_STAT_TRANS);
    }
    if (s->cs != 0xFFU) {
        gpio_bit_set(cs_base(s), cs_mask(s));
    }
    spi_busy[s->bus] = 0;
    return rc;
}

void spi_cs_set(uint8_t slave, uint8_t level)
{
    const struct gd32_spi_slave *s = slave_get(slave);
    if (s == NULL || s->cs == 0xFFU) {
        return;
    }
    if (level) {
        gpio_bit_set(cs_base(s), cs_mask(s));
    } else {
        gpio_bit_reset(cs_base(s), cs_mask(s));
    }
}

#else /* 设备树中没有 spi-buses 节点: 提供空实现, 保证编译通过 */

int spi_transfer(uint8_t slave, const uint8_t *tx, uint8_t *rx, uint16_t len)
    { (void)slave; (void)tx; (void)rx; (void)len; return GD_SPI_ERR_PARAM; }
int spi_write(uint8_t slave, const uint8_t *buf, uint16_t len)
    { (void)slave; (void)buf; (void)len; return GD_SPI_ERR_PARAM; }
int spi_read(uint8_t slave, uint8_t *buf, uint16_t len)
    { (void)slave; (void)buf; (void)len; return GD_SPI_ERR_PARAM; }
int spi_write_then_read(uint8_t slave, const uint8_t *wr, uint16_t wlen, uint8_t *rd, uint16_t rlen)
    { (void)slave; (void)wr; (void)wlen; (void)rd; (void)rlen; return GD_SPI_ERR_PARAM; }
void spi_cs_set(uint8_t slave, uint8_t level) { (void)slave; (void)level; }

#endif
