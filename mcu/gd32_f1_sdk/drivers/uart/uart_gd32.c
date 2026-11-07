/**
 * @file  uart_gd32.c
 * @brief GD32F10x UART/USART 驱动实现 —— 实例表由设备树生成 (DT_UARTS_INSTANCES)
 *
 * 匹配条件: CONFIG_DRIVER_UART=y 且设备树存在 uarts 节点 (DT_UARTS_COUNT > 0)。
 *
 * 三种工作模式 (设备树每个实例的 dma-mode / int-mode 属性组合):
 *   1. 纯轮询 (dma=0, int=NONE): 收发都靠应用主动查标志位
 *   2. 中断   (dma=0, int=RX/IDLE/RX_IDLE): RBNE 每字节中断 / IDLE 帧结束中断,
 *      数据进环形缓冲区; 应用层只在 weak 回调里写业务
 *   3. DMA    (dma=1): RX 走 DMA 循环模式写入环形缓冲区, IDLE 中断判定帧边界;
 *      TX 优先走 DMA (忙则退回中断/轮询发送)
 *      UART4 没有 DMA 通道 (UM 表 9-3/9-4), dma-mode 自动忽略退化为中断
 *
 * 引脚来源 (二选一, 设备树描述):
 *   pgroup = <&usart0 1>           引用 SoC dtsi 预定义组 (PA9/PA10=m0, 重映射组=m1...)
 *   tx-gpios/rx-gpios 手动组合      数据手册 2.6 节中任意标了 USARTx_TX/RX 的引脚
 */
#include "uart_gd32.h"

#include <stddef.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "gd32f10x.h"
#include "devicetree_generated.h"
#include "init_fn_macros.h"
#include "gd32f10x_dma.h"
#include "gd32f10x_gpio.h"

/* dt-bindings 编码 (数据位/停止位/校验/中断模式), 设备树与驱动共用同一份定义 */
#include "dt-bindings/serial/gd32f10x-uart.h"

#if DT_UARTS_COUNT > 0

/* GPIO 端口基址/时钟表 (与 gpio_gd32.c 中 port-idx 约定一致) */
static const uint32_t uart_port_base[] = { GPIOA, GPIOB, GPIOC, GPIOD, GPIOE };
static const rcu_periph_enum uart_port_rcu[] = {
    RCU_GPIOA, RCU_GPIOB, RCU_GPIOC, RCU_GPIOD, RCU_GPIOE
};

/* uart-idx -> 外设时钟 (usart_deinit 内部不使能时钟, 驱动需先开) */
static const rcu_periph_enum uart_rcu[] = {
    RCU_USART0, RCU_USART1, RCU_USART2, RCU_UART3, RCU_UART4
};
#define UART_RCU_COUNT  (sizeof(uart_rcu) / sizeof(uart_rcu[0]))

/* uart-idx -> AFIO 重映射码 (gpio_pin_remap_config 的 remap 参数; 0 = 不重映射) */
static const uint32_t uart_remap_code[] = {
    GPIO_USART0_REMAP,                 /* USART0: PA9/PA10 -> PB6/PB7 */
    GPIO_USART1_REMAP,                 /* USART1: PA2/PA3  -> PD5/PD6 (仅 100/144 脚) */
    GPIO_USART2_PARTIAL_REMAP,         /* USART2: PB10/PB11 -> PC10/PC11 (部分) */
    0U,                                /* UART3:  PC10/PC11 固定, 无重映射 */
    0U                                 /* UART4:  PC12/PD2  固定, 无重映射 */
};

/* uart-idx -> IRQ 通道号 (startup_gd32f10x_hd.S 向量表) */
static const IRQn_Type uart_irqn[] = {
    USART0_IRQn, USART1_IRQn, USART2_IRQn, UART3_IRQn, UART4_IRQn
};

/* DMA 请求映射 (UM 表 9-3/9-4): 每个串口的 RX/TX 所在 (DMA 控制器, 通道)
 * 注: DMA_CHx 枚举值 = 通道号 x, DMA0 = 0x40020000, DMA1 = 0x40020400。
 *     UART4 无 DMA 通道, 用 0xFF 标记。 */
#define UART_DMA_NONE   0xFFU
struct uart_dma_map {
    uint32_t dma;              /* DMA0 / DMA1 基址 */
    uint8_t  rx_ch;            /* 接收通道 (dma_channel_enum) */
    uint8_t  tx_ch;            /* 发送通道 (dma_channel_enum) */
};
static const struct uart_dma_map uart_dma[] = {
    { DMA0, 4, 3 },            /* USART0: RX=CH4, TX=CH3 (DMA0) */
    { DMA0, 5, 6 },            /* USART1: RX=CH5, TX=CH6 (DMA0) */
    { DMA0, 2, 1 },            /* USART2: RX=CH2, TX=CH1 (DMA0) */
    { DMA1, 2, 4 },            /* UART3:  RX=CH2, TX=CH4 (DMA1) */
    { 0, UART_DMA_NONE, UART_DMA_NONE },  /* UART4: 无 DMA */
};

/* 设备树生成的实例表 */
static const struct gd32_uart_cfg dt_uarts[DT_UARTS_COUNT] = { DT_UARTS_INSTANCES };

/* 运行时状态 + 环形缓冲区 (缓冲区空间静态分配, 大小来自设备树 rx-buf-size) */
static uint8_t uart_rx_bufs[DT_UARTS_COUNT][DT_UARTS_MAX_BUF_SIZE];
static struct gd32_uart_dev uart_devs[DT_UARTS_COUNT];

/* DMA TX 异步中转区: uart_send 返回后 DMA 仍在继续读源缓冲区。若源是调用方
 * 的栈缓冲 (uart_printf 的格式化 buf / 应用局部数组), 函数返回后即被后续
 * 调用覆盖, 实测表现为回显首字节被吞/夹带幻影字符 —— 曾经的"首字节丢失"
 * 其实一直是这个问题, RX 从来没丢过字节。因此 DMA 只从这块静态区读;
 * 超过中转区长度的发送自动分段, 段间等待发完再复用。 */
#define UART_TX_STAGE_SIZE 256
static uint8_t uart_tx_stage[DT_UARTS_COUNT][UART_TX_STAGE_SIZE];

/* printf console 实例下标 (设备树 console=1 的那个, 没有则为 0xFF) */
static uint8_t uart_console_idx = 0xFF;

/* ---------------------------------------------------------------------- */
/* 环形缓冲区                                                              */
/* ---------------------------------------------------------------------- */

static void uart_rb_push(struct gd32_uart_dev *dev, uint8_t byte)
{
    uint16_t next = (uint16_t)((dev->rx_head + 1U) % dev->cfg->rx_buf_size);
    if (next == dev->rx_tail) {
        /* 缓冲区满: 丢弃最旧数据, 覆盖式前进 (保证最新数据不丢) */
        dev->rx_tail = (uint16_t)((dev->rx_tail + 1U) % dev->cfg->rx_buf_size);
    }
    dev->rx_buf[dev->rx_head] = byte;
    dev->rx_head = next;
}

/* 本帧长度统计 (IDLE 模式用): 写入指针与帧起始位置之差 */
static uint16_t uart_rb_unread(const struct gd32_uart_dev *dev)
{
    uint16_t head = dev->rx_head;
    uint16_t tail = dev->rx_tail;
    if (head >= tail) {
        return (uint16_t)(head - tail);
    }
    return (uint16_t)(dev->cfg->rx_buf_size - tail + head);
}

/* ---------------------------------------------------------------------- */
/* 内部工具                                                                */
/* ---------------------------------------------------------------------- */

static inline struct gd32_uart_dev *uart_get(uint8_t idx)
{
    return (idx < DT_UARTS_COUNT) ? &uart_devs[idx] : NULL;
}

/* 硬件外设号 -> 外设基址 (仅分发器兜底空读寄存器用) */
static uint32_t uart_periph_base[] = { USART0, USART1, USART2, UART3, UART4 };
static inline uint32_t uart_periph_of(uint8_t hw_idx)
{
    return (hw_idx < 5U) ? uart_periph_base[hw_idx] : USART0;
}

/* 实例是否真的用 DMA (UART4 没有通道, 声明了也退化为中断) */
static inline uint8_t uart_use_dma(const struct gd32_uart_cfg *cfg)
{
    return (uint8_t)(cfg->dma_mode &&
                     uart_dma[cfg->uart_idx].rx_ch != UART_DMA_NONE);
}

/* TX 引脚模式: 复用推挽; RX 引脚模式: 浮空或上拉(设备树 rx-pull 决定) */
static void uart_pins_init(const struct gd32_uart_cfg *cfg)
{
    uint32_t tx_gpio = uart_port_base[cfg->tx_port];
    uint32_t rx_gpio = uart_port_base[cfg->rx_port];
    uint32_t tx_mask = (uint32_t)1U << cfg->tx_pin;
    uint32_t rx_mask = (uint32_t)1U << cfg->rx_pin;

    rcu_periph_clock_enable(uart_port_rcu[cfg->tx_port]);
    rcu_periph_clock_enable(uart_port_rcu[cfg->rx_port]);

    /* 重映射组 (m1/手动组合走重映射脚): 需要 AFIO 时钟 + PCF 配置 */
    if (cfg->remap) {
        rcu_periph_clock_enable(RCU_AF);
        gpio_pin_remap_config(uart_remap_code[cfg->uart_idx], ENABLE);
    }

    gpio_init(tx_gpio, GPIO_MODE_AF_PP, GPIO_OSPEED_50MHZ, tx_mask);
    gpio_init(rx_gpio, cfg->rx_pull ? GPIO_MODE_IPU : GPIO_MODE_IN_FLOATING,
              GPIO_OSPEED_50MHZ, rx_mask);
}

/* DMA RX: 循环模式写到环形缓冲区整段 (head/tail 由 IDLE/应用层推进语义换算) */
static void uart_dma_rx_init(struct gd32_uart_dev *dev)
{
    const struct gd32_uart_cfg *cfg = dev->cfg;
    uint32_t dma = uart_dma[cfg->uart_idx].dma;
    dma_channel_enum ch = (dma_channel_enum)uart_dma[cfg->uart_idx].rx_ch;
    dma_parameter_struct init;

    rcu_periph_clock_enable(dma == DMA0 ? RCU_DMA0 : RCU_DMA1);

    dma_deinit(dma, ch);
    dma_struct_para_init(&init);
    init.direction = DMA_PERIPHERAL_TO_MEMORY;
    init.periph_addr = (uint32_t)&USART_DATA(cfg->periph);
    init.periph_width = DMA_PERIPHERAL_WIDTH_8BIT;
    init.periph_inc = DMA_PERIPH_INCREASE_DISABLE;
    init.memory_addr = (uint32_t)dev->rx_buf;
    init.memory_width = DMA_MEMORY_WIDTH_8BIT;
    init.memory_inc = DMA_MEMORY_INCREASE_ENABLE;
    init.number = cfg->rx_buf_size;
    init.priority = DMA_PRIORITY_ULTRA_HIGH;
    dma_init(dma, ch, &init);

    dma_circulation_enable(dma, ch);          /* 循环模式: 缓冲区写满自动回卷 */
    dma_memory_to_memory_disable(dma, ch);
    dma_channel_enable(dma, ch);

    usart_dma_receive_config(cfg->periph, USART_RECEIVE_DMA_ENABLE);
}

/* DMA TX 通道配置 (每次发送调用, 单次模式) */
static void uart_dma_tx_start(struct gd32_uart_dev *dev,
                              const uint8_t *data, uint16_t len)
{
    const struct gd32_uart_cfg *cfg = dev->cfg;
    uint32_t dma = uart_dma[cfg->uart_idx].dma;
    dma_channel_enum ch = (dma_channel_enum)uart_dma[cfg->uart_idx].tx_ch;
    dma_parameter_struct init;

    dma_deinit(dma, ch);
    dma_struct_para_init(&init);
    init.direction = DMA_MEMORY_TO_PERIPHERAL;
    init.periph_addr = (uint32_t)&USART_DATA(cfg->periph);
    init.periph_width = DMA_PERIPHERAL_WIDTH_8BIT;
    init.periph_inc = DMA_PERIPH_INCREASE_DISABLE;
    init.memory_addr = (uint32_t)data;
    init.memory_width = DMA_MEMORY_WIDTH_8BIT;
    init.memory_inc = DMA_MEMORY_INCREASE_ENABLE;
    init.number = len;
    init.priority = DMA_PRIORITY_ULTRA_HIGH;
    dma_init(dma, ch, &init);

    dma_circulation_disable(dma, ch);
    dma_memory_to_memory_disable(dma, ch);

    usart_dma_transmit_config(cfg->periph, USART_TRANSMIT_DMA_ENABLE);
    dma_channel_enable(dma, ch);
}

/* DMA 模式下根据 DMA 剩余计数刷新 head (写指针就是硬件写到的位置) */
static void uart_dma_head_update(struct gd32_uart_dev *dev)
{
    const struct gd32_uart_cfg *cfg = dev->cfg;
    uint32_t remain = dma_transfer_number_get(uart_dma[cfg->uart_idx].dma,
                                              (dma_channel_enum)uart_dma[cfg->uart_idx].rx_ch);
    dev->rx_head = (uint16_t)(cfg->rx_buf_size - remain);
}

/* ---------------------------------------------------------------------- */
/* 初始化                                                                  */
/* ---------------------------------------------------------------------- */

static void uart_init_one(struct gd32_uart_dev *dev, uint8_t idx)
{
    const struct gd32_uart_cfg *cfg = &dt_uarts[idx];

    dev->cfg = cfg;
    dev->rx_buf = uart_rx_bufs[idx];
    dev->rx_head = 0;
    dev->rx_tail = 0;
    dev->tx_busy = 0;

    uart_pins_init(cfg);

    /* 串口外设时钟 (usart_deinit 只复位外设, 不开时钟) */
    if (cfg->uart_idx < UART_RCU_COUNT) {
        rcu_periph_clock_enable(uart_rcu[cfg->uart_idx]);
    }

    /* 数据格式: 波特率 + 数据位/停止位/校验 (设备树 line-ctl) */
    usart_deinit(cfg->periph);
    usart_baudrate_set(cfg->periph, cfg->baud_rate);
    usart_word_length_set(cfg->periph,
                          cfg->data_bits ? USART_WL_9BIT : USART_WL_8BIT);
    usart_parity_config(cfg->periph, cfg->parity == GD32_UART_PM_EVEN ? USART_PM_EVEN :
                                   cfg->parity == GD32_UART_PM_ODD  ? USART_PM_ODD  :
                                                                      USART_PM_NONE);
    usart_stop_bit_set(cfg->periph,
                       cfg->stop_bits == GD32_UART_STOP_2   ? USART_STB_2BIT   :
                       cfg->stop_bits == GD32_UART_STOP_0_5 ? USART_STB_0_5BIT :
                                                              USART_STB_1BIT);

    usart_receive_config(cfg->periph, USART_RECEIVE_ENABLE);
    usart_transmit_config(cfg->periph, USART_TRANSMIT_ENABLE);

    if (cfg->console) {
        uart_console_idx = idx;
    }

    /* 接收通道初始化: DMA 优先, 其次中断, 否则纯轮询 */
    if (uart_use_dma(cfg)) {
        uart_dma_rx_init(dev);
        if (cfg->int_mode & GD32_UART_INT_IDLE) {
            usart_interrupt_enable(cfg->periph, USART_INT_IDLE);
            nvic_irq_enable(uart_irqn[cfg->uart_idx], 1, 0);
        }
    } else if (cfg->int_mode & GD32_UART_INT_RX) {
        usart_interrupt_enable(cfg->periph, USART_INT_RBNE);
        if (cfg->int_mode & GD32_UART_INT_IDLE) {
            usart_interrupt_enable(cfg->periph, USART_INT_IDLE);
        }
        nvic_irq_enable(uart_irqn[cfg->uart_idx], 1, 0);
    } else if (cfg->int_mode & GD32_UART_INT_IDLE) {
        /* 仅 IDLE 无 RBNE (dma=0): 帧中断只做通知, 数据仍需应用读 DATA */
        usart_interrupt_enable(cfg->periph, USART_INT_IDLE);
        nvic_irq_enable(uart_irqn[cfg->uart_idx], 1, 0);
    }
    /* int_mode == 0: 纯轮询, 不开任何中断, 应用用 uart_poll_read() */

    usart_enable(cfg->periph);
}

static void uart_init_all(void)
{
    for (uint8_t i = 0; i < DT_UARTS_COUNT; i++) {
        uart_init_one(&uart_devs[i], i);
    }
}
DEVICE_INIT(uart, uart_init_all, GD_INIT_DEVICE);

/* ---------------------------------------------------------------------- */
/* 发送                                                                    */
/* ---------------------------------------------------------------------- */

void uart_send(uint8_t idx, const uint8_t *data, uint16_t len)
{
    struct gd32_uart_dev *dev = uart_get(idx);
    if (dev == NULL || data == NULL || len == 0) {
        return;
    }
    const struct gd32_uart_cfg *cfg = dev->cfg;

    /* DMA 发送: 数据拷贝到本实例静态中转区, DMA 只读静态内存。
     * 超过中转区长度自动分段 (段间等待上一段发完)。 */
    if (uart_use_dma(cfg)) {
        while (len > 0) {
            uint16_t n = (len > UART_TX_STAGE_SIZE) ? UART_TX_STAGE_SIZE : len;
            while (!uart_tx_done(idx)) { }      /* 等上一段发完 */
            memcpy(uart_tx_stage[idx], data, n);
            dev->tx_busy = 1;
            uart_dma_tx_start(dev, uart_tx_stage[idx], n);
            data += n;
            len = (uint16_t)(len - n);
        }
        return;
    }

    /* 轮询发送 (与是否开 RX 中断无关): 逐字节等 TBE */
    for (uint16_t i = 0; i < len; i++) {
        while (RESET == usart_flag_get(cfg->periph, USART_FLAG_TBE)) { }
        usart_data_transmit(cfg->periph, data[i]);
    }
}

/* 指定串口的 printf 语法输出 (等价 STM32 HAL 的 USART_printf):
 * idx = 设备树实例下标 (uart1 节点 -> DT_UART1_IDX), 格式化后走 uart_send。
 * 默认 printf 口由设备树 console=<1> 的实例承担 (通常 uart0/USART0);
 * 其他串口要打日志/协议文本时用本函数。
 * 注意: DMA 模式下 uart_send 内部会等上一帧发完, 别在中断上下文调用。 */
void uart_printf(uint8_t idx, const char *fmt, ...)
{
    char buf[256];
    va_list args;

    va_start(args, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    if (n > 0) {
        if ((uint32_t)n >= sizeof(buf)) {
            n = (int)sizeof(buf) - 1;    /* 截断保护 */
        }
        uart_send(idx, (const uint8_t *)buf, (uint16_t)n);
    }
}

void uart_putc(uint8_t ch)
{
    if (uart_console_idx != 0xFF) {
        uart_send(uart_console_idx, &ch, 1);
    }
}

uint8_t uart_tx_done(uint8_t idx)
{
    struct gd32_uart_dev *dev = uart_get(idx);
    if (dev == NULL) {
        return 1;
    }
    if (!dev->tx_busy) {
        return 1;
    }
    /* DMA 传输完成 (FTF) 则认为发送结束 */
    const struct gd32_uart_cfg *cfg = dev->cfg;
    uint32_t dma = uart_dma[cfg->uart_idx].dma;
    dma_channel_enum ch = (dma_channel_enum)uart_dma[cfg->uart_idx].tx_ch;
    if (SET == dma_flag_get(dma, ch, DMA_FLAG_FTF)) {
        dma_flag_clear(dma, ch, DMA_FLAG_FTF);
        usart_dma_transmit_config(cfg->periph, USART_TRANSMIT_DMA_DISABLE);
        dev->tx_busy = 0;
        return 1;
    }
    return 0;
}

/* ---------------------------------------------------------------------- */
/* 接收 (应用层主动读)                                                     */
/* ---------------------------------------------------------------------- */

int16_t uart_read(uint8_t idx)
{
    struct gd32_uart_dev *dev = uart_get(idx);
    if (dev == NULL) {
        return -1;
    }
    if (dev->cfg->dma_mode) {
        uart_dma_head_update(dev);          /* DMA 模式: 先同步硬件写指针 */
    }
    if (dev->rx_tail == dev->rx_head) {
        return -1;
    }
    uint8_t byte = dev->rx_buf[dev->rx_tail];
    dev->rx_tail = (uint16_t)((dev->rx_tail + 1U) % dev->cfg->rx_buf_size);
    if (dev->cfg->dma_mode) {
        uart_dma_head_update(dev);
    }
    return byte;
}

uint16_t uart_available(uint8_t idx)
{
    struct gd32_uart_dev *dev = uart_get(idx);
    if (dev == NULL) {
        return 0;
    }
    if (dev->cfg->dma_mode) {
        uart_dma_head_update(dev);
    }
    return uart_rb_unread(dev);
}

uint16_t uart_readline(uint8_t idx, uint8_t *buf, uint16_t size)
{
    uint16_t n = 0;
    if (buf == NULL || size == 0) {
        return 0;
    }
    while (n < (uint16_t)(size - 1U)) {
        int16_t c = uart_read(idx);
        if (c < 0) {
            break;
        }
        buf[n++] = (uint8_t)c;
        if ((uint8_t)c == '\n') {
            break;
        }
    }
    buf[n] = 0;
    return n;
}

uint16_t uart_idle_frame(uint8_t idx)
{
    struct gd32_uart_dev *dev = uart_get(idx);
    if (dev == NULL || !dev->idle_flag) {
        return 0;
    }
    dev->idle_flag = 0;
    return dev->idle_len;
}

/* ---------------------------------------------------------------------- */
/* 中断服务 (普通 RBNE + IDLE 空闲, 按实例分发)                            */
/* ---------------------------------------------------------------------- */

void gd32_uart_irq_handler(uint8_t idx)
{
    struct gd32_uart_dev *dev = &uart_devs[idx];
    const struct gd32_uart_cfg *cfg = dev->cfg;

    /* RBNE: 收到 1 字节 (纯中断模式; DMA 模式下 RBNE 不使能)
     * 读 DATA 寄存器同时完成取数与清标志 (一次读, 不能读两次) */
    if (SET == usart_interrupt_flag_get(cfg->periph, USART_INT_FLAG_RBNE)) {
        uint8_t byte = (uint8_t)usart_data_receive(cfg->periph);
        uart_rb_push(dev, byte);
        uart_rx_callback(idx);                              /* weak 回调 */
        return;
    }

    /* IDLE: 一帧结束 —— DMA 模式下同步 head 计算帧长;
     *       纯中断模式下只通知帧边界 (RBNE 已把数据入环形缓冲区) */
    if (SET == usart_interrupt_flag_get(cfg->periph, USART_INT_FLAG_IDLE)) {
        /* IDLE 清除序列: flag_get 已读 STAT0, 这里读 DATA 完成清除。
         * DMA 模式下数据已被 DMA 搬进环形缓冲区 (DMAR 使能后 RBNE 不会置位,
         * CPU 空读 DATA 与 DMA 无竞争); 纯中断模式数据已由 RBNE 中断入队。
         * 帧长 = head 同步后的未读字节数。*/
        (void)usart_data_receive(cfg->periph);
        uint16_t len;
        if (uart_use_dma(cfg)) {
            uart_dma_head_update(dev);                      /* 同步 DMA 写指针 */
        }
        len = uart_rb_unread(dev);
        dev->idle_len = len;
        dev->idle_flag = 1;
        uart_idle_callback(idx, len);                       /* weak 回调 */
    }
}

/* 纯轮询读 (dma=0, int-mode=<GD32_UART_INT_NONE>): 查 RBNE 标志直接读
 * DATA 寄存器。不开任何中断; 其他模式下请用 uart_read() (环形缓冲区)。 */
int uart_poll_read(uint8_t idx)
{
    struct gd32_uart_dev *dev = uart_get(idx);
    if (dev == NULL) {
        return -1;
    }
    if (SET == usart_flag_get(dev->cfg->periph, USART_FLAG_RBNE)) {
        return (int)usart_data_receive(dev->cfg->periph);    /* 读 DATA 同时清标志 */
    }
    return -1;
}

/* 弱回调默认实现: 应用层覆盖即可 (在 UART ISR 上下文执行, 应尽量短) */
__attribute__((weak)) void uart_rx_callback(uint8_t idx) { (void)idx; }
__attribute__((weak)) void uart_idle_callback(uint8_t idx, uint16_t len)
{
    (void)idx; (void)len;
}

/* 向量表入口 (startup_gd32f10x_hd.S 中的 weak 符号) —— 转发到公共分发器。
 * gd32_uart_irq_handler 参数是设备树实例下标, 而这里拿到的是硬件外设号:
 * 按实例表里记录的 uart_idx 反查, 节点顺序与外设号不一致的板级 dts 也能正确分发。
 * (设备树没配的外设不会开中断, 走不到这里; 查不到时读 USART 清标志防止挂死。) */
static void gd32_uart_irq_dispatch(uint8_t hw_idx)
{
    for (uint8_t i = 0; i < DT_UARTS_COUNT; i++) {
        if (dt_uarts[i].uart_idx == hw_idx) {
            gd32_uart_irq_handler(i);
            return;
        }
    }
    (void)usart_data_receive(uart_periph_of(hw_idx));   /* 未配置: 空读清标志 */
}
void USART0_IRQHandler(void) { gd32_uart_irq_dispatch(0); }
void USART1_IRQHandler(void) { gd32_uart_irq_dispatch(1); }
void USART2_IRQHandler(void) { gd32_uart_irq_dispatch(2); }
void UART3_IRQHandler(void)  { gd32_uart_irq_dispatch(3); }
void UART4_IRQHandler(void)  { gd32_uart_irq_dispatch(4); }

/* ---------------------------------------------------------------------- */
/* printf 重定向 (newlib nano / GCC): 输出到设备树 console=1 的实例          */
/* ---------------------------------------------------------------------- */

#if defined(CONFIG_DRIVER_UART_PRINTF)
int _write(int fd, const char *buf, int len)
#else
static int uart_stdio_write(int fd, const char *buf, int len)
#endif
{
    (void)fd;
    struct gd32_uart_dev *dev = uart_get(uart_console_idx);
    if (dev == NULL) {
        return 0;
    }
    /* console 走轮询发送, 保证 printf 语义直观 (不与后台 DMA TX 抢占) */
    for (int i = 0; i < len; i++) {
        while (RESET == usart_flag_get(dev->cfg->periph, USART_FLAG_TBE)) { }
        usart_data_transmit(dev->cfg->periph, (uint8_t)buf[i]);
    }
    return len;
}

#else /* 设备树中没有 uart 节点: 提供空实现, 保证编译通过 */

void uart_send(uint8_t idx, const uint8_t *data, uint16_t len) { (void)idx; (void)data; (void)len; }
void uart_putc(uint8_t ch) { (void)ch; }
void uart_printf(uint8_t idx, const char *fmt, ...) { (void)idx; (void)fmt; }
int16_t uart_read(uint8_t idx) { (void)idx; return -1; }
int uart_poll_read(uint8_t idx) { (void)idx; return -1; }
uint16_t uart_available(uint8_t idx) { (void)idx; return 0; }
uint16_t uart_readline(uint8_t idx, uint8_t *buf, uint16_t size) { (void)idx; (void)buf; (void)size; return 0; }
uint16_t uart_idle_frame(uint8_t idx) { (void)idx; return 0; }
uint8_t uart_tx_done(uint8_t idx) { (void)idx; return 1; }
__attribute__((weak)) void uart_rx_callback(uint8_t idx) { (void)idx; }
__attribute__((weak)) void uart_idle_callback(uint8_t idx, uint16_t len) { (void)idx; (void)len; }

#endif
