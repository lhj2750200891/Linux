/**
 * @file  i2c_gd32.c
 * @brief GD32F10x I2C 主机驱动实现 —— 实例/从机表由设备树生成
 *
 * 匹配条件: CONFIG_DRIVER_I2C=y 且设备树存在 i2c-buses 节点 (DT_I2C_BUSES_COUNT > 0)。
 *
 * 工作方式: 主机模式 + 轮询 + 超时保护 (不依赖中断, 可安全用于任意上下文;
 * 从机不在线时也不会挂死, 超时返回错误码)。
 *
 * 时序要点 (GD32F10x I2C = STM32F1 同源外设):
 *   - SBSEND 清除: 读 STAT0 后写 DATA (地址)
 *   - ADDSEND 清除: 读 STAT0 后读 STAT1
 *   - 收 N>=1 字节的经典序列 (参考 UM "master receiver"):
 *       N=1: 先关 ACK, 地址阶段后等 RBNE -> STOP -> 读 DATA
 *       N=2: POAP=1 + 关 ACK (作用于下一字节), 等 BTC -> STOP -> 读两次
 *       N>2: 连读 N-2 字节 -> 关 ACK -> 等 BTC -> STOP -> 读两次
 *   - 写读组合 (write_then_read): 写段不发 STOP, 直接重复起始位 (Sr) 转读段
 *
 * 总线恢复: 从机热插拔/复位过程中可能把 SDA 拉死 (BUSY 恒置位),
 * 参照 Linux i2c 总线恢复, 切回 GPIO 模式打 9 个 SCL 脉冲 + 产生 STOP。
 */
#include "i2c_gd32.h"

#include <stddef.h>

#include "gd32f10x.h"
#include "devicetree_generated.h"
#include "init_fn_macros.h"
#include "gd32f10x_rcu.h"
#include "gd32f10x_gpio.h"
#include "gd32f10x_i2c.h"

/* dt-bindings 编码 (速率档位), 设备树与驱动共用同一份定义 */
#include "dt-bindings/i2c/gd32f10x-i2c.h"

#if DT_I2C_BUSES_COUNT > 0

/* 设备树生成的实例表 / 从机表 */
static const struct gd32_i2c_cfg dt_i2c_buses[DT_I2C_BUSES_COUNT] = { DT_I2C_BUSES_INSTANCES };
#if DT_I2C_SLAVES_COUNT > 0
static const struct gd32_i2c_slave dt_i2c_slaves[DT_I2C_SLAVES_COUNT] = { DT_I2C_SLAVES };
#endif

/* 每条总线的事务重入保护 (主循环与中断同时访问同一总线时拒绝后者) */
static volatile uint8_t i2c_busy[DT_I2C_BUSES_COUNT];

/* GPIO 端口基址/时钟表 (与 uart 驱动 port-idx 约定一致: A=0..E=4) */
static const uint32_t i2c_port_base[] = { GPIOA, GPIOB, GPIOC, GPIOD, GPIOE };
static const rcu_periph_enum i2c_port_rcu[] = {
    RCU_GPIOA, RCU_GPIOB, RCU_GPIOC, RCU_GPIOD, RCU_GPIOE
};

/* i2c-idx -> 外设时钟 */
static const rcu_periph_enum i2c_rcu[] = { RCU_I2C0, RCU_I2C1 };

/* 超时: 轮询循环次数 (108MHz 主频下 1 次循环约 10~15 周期)
 * I2C_TMO_LOOPS   : 单个传输标志等待, 约 20~40ms (100kHz 传 1 字节约 90us, 余量充足)
 * I2C_TMO_BUSFREE : 等总线空闲, 期间失败会触发一次总线恢复 */
#define I2C_TMO_LOOPS     0x20000U
#define I2C_TMO_BUSFREE   0x80000U
/* 总线恢复时 SCL 脉冲半周期 (约 5us) */
#define I2C_RECOVERY_DELAY 600U

/* STAT0 中传输途中可能出现的错误标志 (出现即提前失败) */
#define I2C_ERR_MASK (I2C_STAT0_BERR | I2C_STAT0_LOSTARB | I2C_STAT0_AERR | \
                      I2C_STAT0_OUERR | I2C_STAT0_PECERR | I2C_STAT0_SMBTO | \
                      I2C_STAT0_SMBALT)

/* ---------------------------------------------------------------------- */
/* 内部工具                                                                */
/* ---------------------------------------------------------------------- */

static inline const struct gd32_i2c_cfg *bus_cfg(uint8_t bus)
{
    return (bus < DT_I2C_BUSES_COUNT) ? &dt_i2c_buses[bus] : NULL;
}

/* 从机下标 -> 从机表项; disabled/未挂载 (DT_IDX_DISABLED) 及越界返回 NULL */
static inline const struct gd32_i2c_slave *slave_get(uint8_t slave)
{
#if DT_I2C_SLAVES_COUNT > 0
    return (slave < DT_I2C_SLAVES_COUNT) ? &dt_i2c_slaves[slave] : NULL;
#else
    (void)slave;
    return NULL;
#endif
}

static void i2c_clear_errors(uint32_t periph)
{
    I2C_STAT0(periph) &= ~I2C_ERR_MASK;
}

/* 产生 STOP 并等硬件将其发出 (STOP 位自动清零), 顺带清残留错误标志 */
static void i2c_send_stop(uint32_t periph)
{
    uint32_t tmo = I2C_TMO_LOOPS;

    I2C_CTL0(periph) |= I2C_CTL0_STOP;
    while ((I2C_CTL0(periph) & I2C_CTL0_STOP) && tmo--) { }
    i2c_clear_errors(periph);
}

/* 等 STAT0 的 want 位出现; errmask 中任何错误标志出现则提前返回错误 */
static int i2c_wait_stat(uint32_t periph, uint32_t want, uint32_t tmo_loops)
{
    uint32_t tmo = tmo_loops;

    while (tmo--) {
        uint32_t st = I2C_STAT0(periph);
        if (st & I2C_ERR_MASK) {
            return (st & I2C_STAT0_AERR) ? GD_I2C_ERR_NACK : GD_I2C_ERR_TIMEOUT;
        }
        if (st & want) {
            return GD_I2C_OK;
        }
    }
    return GD_I2C_ERR_TIMEOUT;
}

/* 总线恢复: 外设脱开 -> SCL/SDA 切 GPIO 开漏 -> 9 个 SCL 脉冲让从机吐完
 * 当前字节释放 SDA -> 造一个 STOP -> 引脚切回复用开漏 -> 外设恢复 */
static void i2c_recovery_delay(void)
{
    volatile uint32_t n = I2C_RECOVERY_DELAY;
    while (n--) { }
}

static void i2c_bus_recover(const struct gd32_i2c_cfg *cfg)
{
    uint32_t scl = i2c_port_base[cfg->scl_port];
    uint32_t sda = i2c_port_base[cfg->sda_port];
    uint32_t scl_mask = (uint32_t)1U << cfg->scl_pin;
    uint32_t sda_mask = (uint32_t)1U << cfg->sda_pin;
    int i;

    I2C_CTL0(cfg->periph) &= ~I2C_CTL0_I2CEN;    /* 外设先脱开总线 */

    gpio_init(scl, GPIO_MODE_OUT_OD, GPIO_OSPEED_50MHZ, scl_mask);
    gpio_init(sda, GPIO_MODE_OUT_OD, GPIO_OSPEED_50MHZ, sda_mask);
    gpio_bit_set(scl, scl_mask);
    gpio_bit_set(sda, sda_mask);
    i2c_recovery_delay();

    for (i = 0; i < 9; i++) {
        if (gpio_input_bit_get(sda, sda_mask)) {
            break;                               /* SDA 已被从机释放 */
        }
        gpio_bit_reset(scl, scl_mask);           /* 拉低 SCL, 从机移一位 */
        i2c_recovery_delay();
        gpio_bit_set(scl, scl_mask);
        i2c_recovery_delay();
    }

    /* 造 STOP: SCL 高电平期间 SDA 低 -> 高 */
    gpio_bit_reset(sda, sda_mask);
    i2c_recovery_delay();
    gpio_bit_set(sda, sda_mask);
    i2c_recovery_delay();

    gpio_init(scl, GPIO_MODE_AF_OD, GPIO_OSPEED_50MHZ, scl_mask);
    gpio_init(sda, GPIO_MODE_AF_OD, GPIO_OSPEED_50MHZ, sda_mask);
    I2C_CTL0(cfg->periph) |= I2C_CTL0_I2CEN;
}

/* 等总线空闲; 超时则尝试一次总线恢复再等, 仍忙则报错
 * (循环条件短路: BUSY 先判断, tmo 减到 0 回绕成 0xFFFFFFFF 即超时印记) */
static int i2c_wait_bus_free(const struct gd32_i2c_cfg *cfg)
{
    uint32_t tmo = I2C_TMO_BUSFREE;

    while ((I2C_STAT1(cfg->periph) & I2C_STAT1_I2CBSY) && tmo--) { }
    if (tmo == 0xFFFFFFFFU) {
        i2c_bus_recover(cfg);
        tmo = I2C_TMO_BUSFREE;
        while ((I2C_STAT1(cfg->periph) & I2C_STAT1_I2CBSY) && tmo--) { }
        if (tmo == 0xFFFFFFFFU) {
            return GD_I2C_ERR_BUSY;
        }
    }
    return GD_I2C_OK;
}

/* ---------------------------------------------------------------------- */
/* 事务原语                                                                */
/* ---------------------------------------------------------------------- */

/* 事务边界: BUSY 重入保护 + 等总线空闲 + 清残留错误 + ACK 恢复使能 */
static int i2c_txn_begin(uint8_t bus)
{
    const struct gd32_i2c_cfg *cfg = bus_cfg(bus);
    if (cfg == NULL || i2c_busy[bus]) {
        return GD_I2C_ERR_PARAM;
    }
    int rc = i2c_wait_bus_free(cfg);
    if (rc != GD_I2C_OK) {
        return rc;
    }
    i2c_busy[bus] = 1;
    i2c_clear_errors(cfg->periph);
    I2C_CTL0(cfg->periph) |= I2C_CTL0_ACKEN;
    return GD_I2C_OK;
}

static void i2c_txn_end(uint8_t bus)
{
    i2c_busy[bus] = 0;
}

/* 起始位 + 地址阶段: 发 START -> SBSEND -> 写地址 -> ADDSEND -> 清标志。
 * 读方向 rd=1。失败时内部已补发 STOP。 */
static int i2c_tx_addr(uint8_t bus, uint8_t addr7, uint8_t rd)
{
    const struct gd32_i2c_cfg *cfg = bus_cfg(bus);
    uint32_t periph = cfg->periph;
    int rc;

    I2C_CTL0(periph) |= I2C_CTL0_START;
    rc = i2c_wait_stat(periph, I2C_STAT0_SBSEND, I2C_TMO_LOOPS);
    if (rc != GD_I2C_OK) {
        i2c_send_stop(periph);
        return rc;
    }

    I2C_DATA(periph) = (uint32_t)((addr7 << 1) | (rd ? 1U : 0U));   /* 写地址同时清 SBSEND */
    rc = i2c_wait_stat(periph, I2C_STAT0_ADDSEND, I2C_TMO_LOOPS);
    if (rc != GD_I2C_OK) {
        i2c_send_stop(periph);                   /* AERR -> 从机不应答 */
        return rc;
    }

    /* 清 ADDSEND 序列: 读 STAT0 后读 STAT1 */
    (void)I2C_STAT0(periph);
    (void)I2C_STAT1(periph);
    return GD_I2C_OK;
}

/* 数据阶段 (写): TBE 逐字节写入, 末字节等 BTC 完全移出。
 * no_stop=1 时不发 STOP (供 write_then_read 的重复起始位衔接)。 */
static int i2c_tx_data(uint8_t bus, const uint8_t *buf, uint16_t len, uint8_t no_stop)
{
    const struct gd32_i2c_cfg *cfg = bus_cfg(bus);
    uint32_t periph = cfg->periph;
    int rc;
    uint16_t i;

    for (i = 0; i < len; i++) {
        rc = i2c_wait_stat(periph, I2C_STAT0_TBE, I2C_TMO_LOOPS);
        if (rc != GD_I2C_OK) {
            i2c_send_stop(periph);
            return rc;
        }
        I2C_DATA(periph) = buf[i];
    }
    /* BTC: 最后一个字节完全移出 (TBE 只代表缓冲区空) */
    rc = i2c_wait_stat(periph, I2C_STAT0_BTC, I2C_TMO_LOOPS);
    if (rc != GD_I2C_OK) {
        i2c_send_stop(periph);
        return rc;
    }
    if (!no_stop) {
        i2c_send_stop(periph);
    }
    return GD_I2C_OK;
}

/* 数据阶段 (读): 按 N=1 / N=2 / N>2 三种经典序列保证末字节 NACK + STOP 时序 */
static int i2c_rx_data(uint8_t bus, uint8_t addr7, uint8_t *buf, uint16_t len)
{
    const struct gd32_i2c_cfg *cfg = bus_cfg(bus);
    uint32_t periph = cfg->periph;
    int rc;
    uint16_t i;

    if (len == 1) {
        /* N=1: 地址阶段前先关 ACK (收到即 NACK) */
        I2C_CTL0(periph) &= ~I2C_CTL0_ACKEN;
        rc = i2c_tx_addr(bus, addr7, 1);
        if (rc != GD_I2C_OK) {
            goto cleanup;
        }
        rc = i2c_wait_stat(periph, I2C_STAT0_RBNE, I2C_TMO_LOOPS);
        if (rc != GD_I2C_OK) {
            goto cleanup;
        }
        I2C_CTL0(periph) |= I2C_CTL0_STOP;
        buf[0] = (uint8_t)I2C_DATA(periph);      /* 读 DATA 同时清 RBNE */
        i2c_send_stop(periph);                   /* 等 STOP 位清零 */
    } else if (len == 2) {
        /* N=2: POAP=1 + 关 ACK -> ACKEN 作用于下一字节 (第 2 字节 NACK) */
        I2C_CTL0(periph) = (I2C_CTL0(periph) | I2C_CTL0_POAP) & ~I2C_CTL0_ACKEN;
        rc = i2c_tx_addr(bus, addr7, 1);
        if (rc != GD_I2C_OK) {
            goto cleanup;
        }
        rc = i2c_wait_stat(periph, I2C_STAT0_BTC, I2C_TMO_LOOPS);
        if (rc != GD_I2C_OK) {
            goto cleanup;
        }
        I2C_CTL0(periph) |= I2C_CTL0_STOP;
        buf[0] = (uint8_t)I2C_DATA(periph);
        buf[1] = (uint8_t)I2C_DATA(periph);
        i2c_send_stop(periph);
        I2C_CTL0(periph) &= ~I2C_CTL0_POAP;
    } else {
        /* N>2: ACK 使能连读 N-2 字节, 然后关 ACK 等 BTC -> STOP -> 读最后两次 */
        rc = i2c_tx_addr(bus, addr7, 1);
        if (rc != GD_I2C_OK) {
            goto cleanup;
        }
        for (i = 0; i + 2 < len; i++) {
            rc = i2c_wait_stat(periph, I2C_STAT0_RBNE, I2C_TMO_LOOPS);
            if (rc != GD_I2C_OK) {
                goto cleanup;
            }
            buf[i] = (uint8_t)I2C_DATA(periph);
        }
        I2C_CTL0(periph) &= ~I2C_CTL0_ACKEN;
        rc = i2c_wait_stat(periph, I2C_STAT0_BTC, I2C_TMO_LOOPS);
        if (rc != GD_I2C_OK) {
            goto cleanup;
        }
        I2C_CTL0(periph) |= I2C_CTL0_STOP;
        buf[len - 2] = (uint8_t)I2C_DATA(periph);
        buf[len - 1] = (uint8_t)I2C_DATA(periph);
        i2c_send_stop(periph);
    }

    I2C_CTL0(periph) |= I2C_CTL0_ACKEN;          /* 恢复 ACK, 供下一次接收 */
    return GD_I2C_OK;

cleanup:
    i2c_send_stop(periph);
    I2C_CTL0(periph) &= ~(I2C_CTL0_POAP);
    I2C_CTL0(periph) |= I2C_CTL0_ACKEN;
    return rc;
}

/* ---------------------------------------------------------------------- */
/* 初始化                                                                  */
/* ---------------------------------------------------------------------- */

static void i2c_init_one(uint8_t idx)
{
    const struct gd32_i2c_cfg *cfg = &dt_i2c_buses[idx];
    uint32_t scl_mask = (uint32_t)1U << cfg->scl_pin;
    uint32_t sda_mask = (uint32_t)1U << cfg->sda_pin;

    /* 引脚: 复用开漏 (总线上的上拉电阻由硬件提供) */
    rcu_periph_clock_enable(i2c_port_rcu[cfg->scl_port]);
    rcu_periph_clock_enable(i2c_port_rcu[cfg->sda_port]);
    if (cfg->remap) {
        rcu_periph_clock_enable(RCU_AF);
        gpio_pin_remap_config(GPIO_I2C0_REMAP, ENABLE);   /* I2C0 -> PB8/PB9 */
    }
    gpio_init(i2c_port_base[cfg->scl_port], GPIO_MODE_AF_OD, GPIO_OSPEED_50MHZ, scl_mask);
    gpio_init(i2c_port_base[cfg->sda_port], GPIO_MODE_AF_OD, GPIO_OSPEED_50MHZ, sda_mask);

    /* 外设: 时钟 -> 复位 -> 时序 (fwlib 内部读 RCU 取 PCLK1 算 CKCFG/RT) */
    rcu_periph_clock_enable(i2c_rcu[cfg->i2c_idx]);
    i2c_deinit(cfg->periph);
    i2c_clock_config(cfg->periph,
                     (cfg->speed == GD32_I2C_SPEED_FAST) ? 400000U : 100000U,
                     I2C_DTCY_2);
    i2c_mode_addr_config(cfg->periph, I2C_I2CMODE_ENABLE, I2C_ADDFORMAT_7BITS,
                         cfg->own_addr);
    i2c_ack_config(cfg->periph, I2C_ACK_ENABLE);
    i2c_enable(cfg->periph);

    i2c_busy[idx] = 0;

    /* 复位发生在一次传输中途时, 从机会拉住 SDA (BUSY 恒置位), 上电即恢复 */
    if (I2C_STAT1(cfg->periph) & I2C_STAT1_I2CBSY) {
        i2c_bus_recover(cfg);
    }
}

static void i2c_init_all(void)
{
    for (uint8_t i = 0; i < DT_I2C_BUSES_COUNT; i++) {
        i2c_init_one(i);
    }
}
DEVICE_INIT(i2c, i2c_init_all, GD_INIT_DEVICE);

/* ---------------------------------------------------------------------- */
/* 总线级 API                                                              */
/* ---------------------------------------------------------------------- */

/* 探测从机是否在位: 只发地址, 收到 ACK 即在位 (i2cdetect 的等价物) */
int i2c_probe(uint8_t bus, uint8_t addr7)
{
    if (bus_cfg(bus) == NULL || addr7 < 0x08U || addr7 > 0x77U) {
        return GD_I2C_ERR_PARAM;
    }
    int rc = i2c_txn_begin(bus);
    if (rc != GD_I2C_OK) {
        return rc;
    }
    rc = i2c_tx_addr(bus, addr7, 0);
    i2c_send_stop(bus_cfg(bus)->periph);         /* 只发地址, 应答后立即收尾 */
    i2c_txn_end(bus);
    return rc;
}

/* ---------------------------------------------------------------------- */
/* 设备级 API                                                              */
/* ---------------------------------------------------------------------- */

int i2c_write(uint8_t slave, const uint8_t *buf, uint16_t len)
{
    const struct gd32_i2c_slave *s = slave_get(slave);
    if (s == NULL || buf == NULL || len == 0) {
        return GD_I2C_ERR_PARAM;
    }
    int rc = i2c_txn_begin(s->bus);
    if (rc != GD_I2C_OK) {
        return rc;
    }
    rc = i2c_tx_addr(s->bus, s->addr, 0);
    if (rc == GD_I2C_OK) {
        rc = i2c_tx_data(s->bus, buf, len, 0);
    }
    i2c_txn_end(s->bus);
    return rc;
}

int i2c_read(uint8_t slave, uint8_t *buf, uint16_t len)
{
    const struct gd32_i2c_slave *s = slave_get(slave);
    if (s == NULL || buf == NULL || len == 0) {
        return GD_I2C_ERR_PARAM;
    }
    int rc = i2c_txn_begin(s->bus);
    if (rc != GD_I2C_OK) {
        return rc;
    }
    rc = i2c_rx_data(s->bus, s->addr, buf, len);
    i2c_txn_end(s->bus);
    return rc;
}

int i2c_write_then_read(uint8_t slave, const uint8_t *wr, uint16_t wlen,
                        uint8_t *rd, uint16_t rlen)
{
    const struct gd32_i2c_slave *s = slave_get(slave);
    if (s == NULL || wr == NULL || rd == NULL || wlen == 0 || rlen == 0) {
        return GD_I2C_ERR_PARAM;
    }
    int rc = i2c_txn_begin(s->bus);
    if (rc != GD_I2C_OK) {
        return rc;
    }
    /* 写段不发 STOP, 由 rx 的地址阶段产生重复起始位 (Sr) 衔接 */
    rc = i2c_tx_addr(s->bus, s->addr, 0);
    if (rc == GD_I2C_OK) {
        rc = i2c_tx_data(s->bus, wr, wlen, 1);
    }
    if (rc == GD_I2C_OK) {
        rc = i2c_rx_data(s->bus, s->addr, rd, rlen);
    }
    i2c_txn_end(s->bus);
    return rc;
}

int i2c_write_reg(uint8_t slave, uint8_t reg, uint8_t val)
{
    const uint8_t buf[2] = { reg, val };
    return i2c_write(slave, buf, 2);
}

int i2c_write_regs(uint8_t slave, uint8_t reg, const uint8_t *buf, uint16_t len)
{
    const struct gd32_i2c_slave *s = slave_get(slave);
    if (s == NULL || buf == NULL || len == 0) {
        return GD_I2C_ERR_PARAM;
    }
    int rc = i2c_txn_begin(s->bus);
    if (rc != GD_I2C_OK) {
        return rc;
    }
    /* 寄存器地址 + 数据在同一事务内连续写出 */
    rc = i2c_tx_addr(s->bus, s->addr, 0);
    if (rc == GD_I2C_OK) {
        rc = i2c_tx_data(s->bus, &reg, 1, 1);
    }
    if (rc == GD_I2C_OK) {
        rc = i2c_tx_data(s->bus, buf, len, 0);
    }
    i2c_txn_end(s->bus);
    return rc;
}

int i2c_read_reg(uint8_t slave, uint8_t reg, uint8_t *val)
{
    return i2c_read_regs(slave, reg, val, 1);
}

int i2c_read_regs(uint8_t slave, uint8_t reg, uint8_t *buf, uint16_t len)
{
    uint8_t r = reg;
    return i2c_write_then_read(slave, &r, 1, buf, len);
}

#else /* 设备树中没有 i2c-buses 节点: 提供空实现, 保证编译通过 */

int i2c_probe(uint8_t bus, uint8_t addr7) { (void)bus; (void)addr7; return GD_I2C_ERR_PARAM; }
int i2c_write(uint8_t slave, const uint8_t *buf, uint16_t len)
    { (void)slave; (void)buf; (void)len; return GD_I2C_ERR_PARAM; }
int i2c_read(uint8_t slave, uint8_t *buf, uint16_t len)
    { (void)slave; (void)buf; (void)len; return GD_I2C_ERR_PARAM; }
int i2c_write_then_read(uint8_t slave, const uint8_t *wr, uint16_t wlen, uint8_t *rd, uint16_t rlen)
    { (void)slave; (void)wr; (void)wlen; (void)rd; (void)rlen; return GD_I2C_ERR_PARAM; }
int i2c_write_reg(uint8_t slave, uint8_t reg, uint8_t val)
    { (void)slave; (void)reg; (void)val; return GD_I2C_ERR_PARAM; }
int i2c_write_regs(uint8_t slave, uint8_t reg, const uint8_t *buf, uint16_t len)
    { (void)slave; (void)reg; (void)buf; (void)len; return GD_I2C_ERR_PARAM; }
int i2c_read_reg(uint8_t slave, uint8_t reg, uint8_t *val)
    { (void)slave; (void)reg; (void)val; return GD_I2C_ERR_PARAM; }
int i2c_read_regs(uint8_t slave, uint8_t reg, uint8_t *buf, uint16_t len)
    { (void)slave; (void)reg; (void)buf; (void)len; return GD_I2C_ERR_PARAM; }

#endif
