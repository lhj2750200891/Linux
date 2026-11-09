/**
 * @file  i2c_gd32.h
 * @brief GD32F10x I2C 主机驱动 (设备树 i2c-buses 节点)
 *
 * 匹配条件: CONFIG_DRIVER_I2C=y 且设备树存在 i2c-buses 节点 (DT_I2C_BUSES_COUNT > 0)。
 * 设备树描述 (仿 Linux i2c 子系统):
 *   i2c-buses {                       总线容器
 *     i2c0 {                          总线实例 (主机): 引脚/速率
 *       从机子节点 { reg = <7位地址>; status; }   挂载的从机设备
 *     };
 *   };
 *
 * 应用不直接关心地址 —— 用设备树生成的宏拿到从机句柄:
 *   oled0@3c 节点 -> DT_OLED0_IDX (从机表下标) / DT_OLED0_ADDR / DT_OLED0_BUS
 * status="disabled" 或未挂载的从机 -> DT_xxx_IDX = DT_IDX_DISABLED(0xFF),
 * API 越界校验后安全空操作, 应用代码无需随设备树增删而修改。
 *
 * 返回值约定 (所有 API): 0 = 成功, 负数 = 错误码
 */
#ifndef DRIVERS_I2C_I2C_GD32_H
#define DRIVERS_I2C_I2C_GD32_H

#include <stdint.h>

#include "devicetree_generated.h"

/* 错误码 */
#define GD_I2C_OK           0    /* 成功 */
#define GD_I2C_ERR_TIMEOUT  (-1) /* 等待硬件标志超时 (总线悬空/设备无响应) */
#define GD_I2C_ERR_NACK     (-2) /* 从机未应答 (地址或数据阶段 ACK 失败) */
#define GD_I2C_ERR_BUSY     (-3) /* 总线被外部拉住 (恢复失败) 或驱动重入 */
#define GD_I2C_ERR_PARAM    (-4) /* 参数非法 (含引用 disabled/未挂载的从机) */

/* 总线实例描述 (设备树 i2cX 节点, DT_I2C_BUSES_INSTANCES 逐字段对应) */
struct gd32_i2c_cfg {
    uint32_t periph;   /**< 外设基址 (I2C0/I2C1, 由 i2c-idx 生成) */
    uint8_t  i2c_idx;  /**< 硬件序号 0~1 */
    uint8_t  scl_port; /**< SCL 端口 A=0..E=4 */
    uint8_t  scl_pin;  /**< SCL 引脚 0~15 */
    uint8_t  sda_port; /**< SDA 端口 */
    uint8_t  sda_pin;  /**< SDA 引脚 */
    uint8_t  remap;    /**< 0=默认引脚组 1=重映射 (仅 I2C0: PB8/PB9) */
    uint8_t  speed;    /**< GD32_I2C_SPEED_STANDARD/FAST (dt-bindings) */
    uint8_t  own_addr; /**< 本机地址 (主机模式不用, 预留从机模式) */
};

/* 从机设备表项 (设备树 i2cX 的从机子节点, DT_I2C_SLAVES 逐字段对应) */
struct gd32_i2c_slave {
    uint8_t bus;       /**< 所在总线实例下标 (DT_I2C0_IDX) */
    uint8_t addr;      /**< 7 位从机地址 (reg 属性, 不含读写位) */
};

/* ---- 总线级 API (bus = DT_I2C0_IDX, addr = 7 位地址) ---- */
int i2c_probe(uint8_t bus, uint8_t addr7);

/* ---- 设备级 API (slave = DT_OLED0_IDX 之类, 从机表下标) ----
 * 典型带寄存器的设备用 write_reg/read_regs 系列;
 * 纯数据流设备 (如 SSD1306) 直接用 i2c_write/i2c_read。 */
int i2c_write(uint8_t slave, const uint8_t *buf, uint16_t len);
int i2c_read(uint8_t slave, uint8_t *buf, uint16_t len);
/* 写-读组合事务: wr 段与 rd 段之间用重复起始位 (Sr), 不释放总线。
 * 绝大多数传感器/存储器的 "写寄存器地址再读数据" 就是这个时序。 */
int i2c_write_then_read(uint8_t slave, const uint8_t *wr, uint16_t wlen,
                        uint8_t *rd, uint16_t rlen);

int i2c_write_reg(uint8_t slave, uint8_t reg, uint8_t val);
int i2c_write_regs(uint8_t slave, uint8_t reg, const uint8_t *buf, uint16_t len);
int i2c_read_reg(uint8_t slave, uint8_t reg, uint8_t *val);
int i2c_read_regs(uint8_t slave, uint8_t reg, uint8_t *buf, uint16_t len);

#endif
