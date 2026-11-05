/**
 * @file  uart_gd32.h
 * @brief GD32F10x UART/USART 驱动 (设备树 uarts 节点) —— 结构定义
 *
 * 一个 uarts 容器节点可挂多个 uart 实例, 每个实例:
 *   - 引脚: pgroup = <&usart0 0>(预定义组 m0/m1...) 或 tx/rx 手动组合
 *   - 数据格式: baud-rate / line-ctl = <数据位 停止位 校验>(dt-bindings)
 *   - 工作模式: dma-mode (0/1), int-mode (GD32_UART_INT_xxx)
 *       dma=0 int=NONE   : 纯轮询, 应用轮询 uart_poll_read()/发送TBE
 *       dma=0 int=RX     : RBNE 中断, 每字节存入环形缓冲区
 *       dma=0 int=IDLE   : IDLE 中断 (仅帧结束通知, 一般配合 dma 用)
 *       dma=0 int=RX_IDLE: RBNE+IDLE, 不定长帧的纯中断接收
 *       dma=1            : DMA 收到环形缓冲区, IDLE 中断通知帧结束
 *                          (int-mode 建议 IDLE; UART4 无 DMA 通道, 自动退化为中断)
 *   - printf 重定向: console 属性 (该实例做为 printf 输出口)
 *
 * 应用层接收:
 *   1. 轮询方式: uart_read() / uart_available() 查环形缓冲区
 *   2. 回调方式: 用户实现 weak 回调(在 UART 中断上下文执行, 应尽量短):
 *        uart_rx_callback(uart)          每收到 1 字节 (RBNE)
 *        uart_idle_callback(uart, len)   一帧接收完成 (IDLE, len=本帧字节数)
 *      回调里正常读 uart_read() 即可, 不需要清标志位 (驱动已处理)。
 */
#ifndef DRIVERS_UART_UART_GD32_H
#define DRIVERS_UART_UART_GD32_H

#include <stdint.h>

#include "gd32f10x_usart.h"

/* 设备树 uart 实例配置 (字段与 gen_devicetree.py 生成的 DT_UARTx_INSTANCES 对应) */
struct gd32_uart_cfg {
    uint32_t periph;                  /* USART0/1/2, UART3/4 基址宏 */
    uint8_t  uart_idx;                /* 0~4, 中断号/DMA通道映射索引用 */
    uint8_t  tx_port;                 /* TX 引脚: 端口序号 A=0~E=4 */
    uint8_t  tx_pin;                  /* TX 引脚号 0~15 */
    uint8_t  rx_port;                 /* RX 引脚端口序号 */
    uint8_t  rx_pin;                  /* RX 引脚号 */
    uint8_t  remap;                   /* AFIO 重映射码 (0=不重映射, 见 uart_gd32.c) */
    uint8_t  rx_pull;                 /* RX 输入模式: 0=浮空 1=上拉 (dt-bindings level 位) */
    uint8_t  data_bits;               /* GD32_UART_DATA_8/9 */
    uint8_t  stop_bits;               /* GD32_UART_STOP_1/0_5/2 */
    uint8_t  parity;                  /* GD32_UART_PM_NONE/EVEN/ODD */
    uint8_t  dma_mode;                /* 1=启用 DMA 收发 */
    uint8_t  int_mode;                /* GD32_UART_INT_xxx 标志组合 */
    uint8_t  console;                 /* 1=printf 重定向到本实例 */
    uint32_t baud_rate;               /* 波特率 */
    uint16_t rx_buf_size;             /* RX 环形缓冲区大小 */
};

/* UART 实例运行时状态 (含环形缓冲区指针, 静态分配) */
struct gd32_uart_dev {
    const struct gd32_uart_cfg *cfg;  /* 指向设备树生成的配置 */
    volatile uint16_t rx_head;        /* 写入位置 (中断/DMA 推进) */
    volatile uint16_t rx_tail;        /* 应用读取位置 */
    uint8_t *rx_buf;                  /* 环形缓冲区 (大小 = cfg->rx_buf_size) */
    volatile uint8_t  tx_busy;        /* DMA 发送进行中标志 */
    volatile uint16_t idle_len;       /* 最近一帧长度 (IDLE 中断时计算) */
    volatile uint16_t idle_flag;      /* IDLE 帧完成标志 */
};

/* ==== 应用层 API (初始化由 DEVICE_INIT 在 main 之前自动完成) ==== */

/* 发送: data-mode 与 int-mode 轮询写 TBE (阻塞); dma-mode 优先走 DMA */
void uart_send(uint8_t idx, const uint8_t *data, uint16_t len);

/* printf 重定向底层实现 (console 实例), 内部调用 uart_send */
void uart_putc(uint8_t ch);

/* 接收: 从环形缓冲区读 1 字节, 无数据返回 -1 */
int16_t uart_read(uint8_t idx);

/* 接收: 环形缓冲区内可读字节数 */
uint16_t uart_available(uint8_t idx);

/* 接收: 阻塞式读一行(到 \n 或 buf 满), 返回长度 (仅建议轮询模式应用使用) */
uint16_t uart_readline(uint8_t idx, uint8_t *buf, uint16_t size);

/* 查询最近一帧是否完成 (IDLE 模式), 完成则清除标志并返回帧长, 否则返回 0 */
uint16_t uart_idle_frame(uint8_t idx);

/* DMA 发送是否完成 */
uint8_t uart_tx_done(uint8_t idx);

/* ===== 应用层回调 (weak, 用户在应用中实现即可, 在中断上下文调用) ===== */

/* RBNE / DMA 接收回调: 每收到 1 字节触发一次 (数据已入环形缓冲区) */
void uart_rx_callback(uint8_t idx);

/* IDLE 回调: 一帧结束触发, len = 本帧字节数 (不定长协议帧处理入口) */
void uart_idle_callback(uint8_t idx, uint16_t len);

/* 支持的实例个数 (设备树描述) */
#define UART_COUNT  DT_UARTS_COUNT

/* 按设备树子节点名访问: uart1 节点 -> DT_UART1_IDX */
/* 例: uart_send(DT_UART1_IDX, buf, 10); */

#endif
