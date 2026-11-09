/**
 * @file  spi_gd32.h
 * @brief GD32F10x SPI 主机驱动 (设备树 spi-buses 节点)
 *
 * 匹配条件: CONFIG_DRIVER_SPI=y 且设备树存在 spi-buses 节点 (DT_SPI_BUSES_COUNT > 0)。
 * 设备树描述 (仿 Linux spi 子系统):
 *   spi-buses {                       总线容器
 *     spi0 {                          总线实例 (主机): 引脚/波特率/模式
 *       cs-gpios = <&gpiox n MODE>, ...;          软片选 GPIO 列表
 *       从机子节点 { reg = <片选下标>; status; }  挂载的从机设备
 *     };
 *   };
 * 不用硬件 NSS (多数外设要求帧间抬片选): 片选由驱动在传输前后拉低/抬高。
 *
 * 应用用设备树生成的宏拿到从机句柄:
 *   spidev0@0 节点 -> DT_SPIDEV0_IDX (从机表下标) / DT_SPIDEV0_BUS / DT_SPIDEV0_CS
 * status="disabled" 或未挂载的从机 -> DT_xxx_IDX = DT_IDX_DISABLED(0xFF),
 * API 越界校验后安全空操作。
 *
 * 返回值约定 (所有 API): 0 = 成功, 负数 = 错误码
 */
#ifndef DRIVERS_SPI_SPI_GD32_H
#define DRIVERS_SPI_SPI_GD32_H

#include <stdint.h>

#include "devicetree_generated.h"

/* 错误码 */
#define GD_SPI_OK           0    /* 成功 */
#define GD_SPI_ERR_TIMEOUT  (-1) /* 等待硬件标志超时 */
#define GD_SPI_ERR_BUSY     (-2) /* 同一总线传输进行中 (中断重入保护) */
#define GD_SPI_ERR_PARAM    (-3) /* 参数非法 (含引用 disabled/未挂载的从机) */

/* 总线实例描述 (设备树 spiX 节点, DT_SPI_BUSES_INSTANCES 逐字段对应) */
struct gd32_spi_cfg {
    uint32_t periph;   /**< 外设基址 (SPI0/SPI1/SPI2, 由 spi-idx 生成) */
    uint8_t  spi_idx;  /**< 硬件序号 0~2 */
    uint8_t  sck_port; /**< SCK 端口 A=0..E=4 */
    uint8_t  sck_pin;  /**< SCK 引脚 0~15 */
    uint8_t  miso_port;/**< MISO 端口 */
    uint8_t  miso_pin; /**< MISO 引脚 */
    uint8_t  mosi_port;/**< MOSI 端口 */
    uint8_t  mosi_pin; /**< MOSI 引脚 */
    uint8_t  remap;    /**< 0=默认引脚组 1=重映射 (仅 SPI0) */
    uint8_t  frame16;  /**< 0=8 位帧 1=16 位帧 (GD32_SPI_FRAME_x) */
    uint8_t  cpol;     /**< GD32_SPI_CPOL_x (dt-bindings) */
    uint8_t  cpha;     /**< GD32_SPI_CPHA_x (dt-bindings) */
    uint8_t  lsb_first;/**< GD32_SPI_FIRST_x (dt-bindings) */
    uint32_t baud_hz;  /**< 目标 SCLK 频率 (驱动按 PCLK 自动就近降档, 不超过该值) */
};

/* 从机设备表项 (设备树 spiX 的从机子节点, DT_SPI_SLAVES 逐字段对应) */
struct gd32_spi_slave {
    uint8_t bus;       /**< 所在总线实例下标 (DT_SPI0_IDX) */
    uint8_t cs;        /**< cs-gpios 列表下标; 0xFF = 无软片选 (外部自控) */
    uint8_t cs_port;   /**< 片选 GPIO 端口 (cs=0xFF 时无效) */
    uint8_t cs_pin;    /**< 片选 GPIO 引脚 */
    uint8_t cs_mode;   /**< 片选 GPIO 模式编码 (GD32_MODE_OUT_PP) */
};

/* ---- 全双工传输 (slave = DT_SPIDEV0_IDX 之类, 从机表下标) ----
 * len 单位: 帧 (8 位帧 = 字节, 16 位帧 = 半字)。全双工同时收发:
 *   tx = NULL 发 0xFF 填充;  rx = NULL 丢弃接收 */
int spi_transfer(uint8_t slave, const uint8_t *tx, uint8_t *rx, uint16_t len);
/* 单向写 (只发不收) / 单向读 (发 0xFF 收) */
int spi_write(uint8_t slave, const uint8_t *buf, uint16_t len);
int spi_read(uint8_t slave, uint8_t *buf, uint16_t len);
/* 写-读组合: 一帧传输内 CS 全程有效 —— 常见传感器时序
 * (先发命令/地址, 紧接着读数据, 期间不释放片选) */
int spi_write_then_read(uint8_t slave, const uint8_t *wr, uint16_t wlen,
                        uint8_t *rd, uint16_t rlen);
/* 手动片选控制 (特殊时序 / DC 类控制脚配合用; 正常传输自动控制) */
void spi_cs_set(uint8_t slave, uint8_t level);   /* level: 1=释放(高) 0=选中(低) */

#endif
