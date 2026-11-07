# UART 串口 (uart)

功能最多的驱动。三种工作模式由设备树组合决定,**应用层 API 统一**,
换模式不用改代码。

**头文件**: `#include "uart_gd32.h"`(开关: `CONFIG_DRIVER_UART`)

## API 一览

| 函数 | 说明 |
|---|---|
| `void uart_send(uint8_t idx, const uint8_t *data, uint16_t len)` | 发送(阻塞到完成)。DMA 模式自动走 DMA,轮询模式自动退化为查询发送 |
| `void uart_printf(uint8_t idx, const char *fmt, ...)` | **指定串口的 printf 语法输出**(等价 STM32 HAL 的 `USART_printf`):向 `idx` 实例格式化发送,与 console 无关。单次最长 256 字节(超出截断) |
| `void uart_putc(uint8_t ch)` | 单字节发送,发到设备树 `console=1` 的实例(常用) |
| `int16_t uart_read(uint8_t idx)` | 从环形缓冲区读 1 字节,空返回 -1 |
| `int uart_poll_read(uint8_t idx)` | **纯轮询模式专用**(dma=0 且 int=NONE):直接查 RBNE 标志读 1 字节,无返回 -1。其他模式请用 `uart_read()` |
| `uint16_t uart_available(uint8_t idx)` | 环形缓冲区内可读字节数 |
| `uint16_t uart_readline(uint8_t idx, uint8_t *buf, uint16_t size)` | 读到 `\n` 为止(含 `\n`),返回实际长度,无完整行返回 0 |
| `uint16_t uart_idle_frame(uint8_t idx)` | 返回最近一帧长度(数据仍在缓冲区)。**>0 表示新帧到达,读完自动清零** |
| `uint8_t uart_tx_done(uint8_t idx)` | DMA 发送是否完成(一般不用调,`uart_send` 内部已等待) |

`idx` 为设备树 `uarts` 下子节点顺序(第 1 个实例 = 0),
按名字用 `DT_UART1_IDX`(uart1 节点)、`DT_UART2_IDX`(uart2 节点)……

## 指定串口打日志: uart_printf

`printf(...)` 只能走设备树 `console=1` 的那一个口。多串口应用中,
向**其他**串口输出文本/协议数据用 `uart_printf`:

```c
uart_printf(DT_UART2_IDX, "[USART1] tick=%lu\r\n", (unsigned long)tick);
uart_send(DT_UART2_IDX, buf, n);                 /* 二进制数据仍走 uart_send */
```

完整多串口示例见 `application/gd32f103re/uart3p/`
(三串口全部 DMA+IDLE,接哪个口测哪个口)。

## 两种接收姿势

### 姿势 1: 主循环查询(推荐,好调试)

```c
#define UART_IDX  DT_UART1_IDX        /* 设备树 uart1 节点 */

/* 可选: 在中断上下文执行,做轻活,重活留给主循环 */
void uart_idle_callback(uint8_t idx, uint16_t len)
{
    (void)idx; (void)len;             /* 本例用查询,回调留空 */
}

int main(void)
{
    SCB->VTOR = FLASH_START;
    while (1) {
        if (uart_idle_frame(UART_IDX) > 0) {       /* 一帧结束(不定长) */
            uint8_t buf[64]; uint16_t n = 0;
            while (uart_available(UART_IDX) && n < sizeof(buf))
                buf[n++] = (uint8_t)uart_read(UART_IDX);
            uart_send(UART_IDX, buf, n);           /* 回显 */
        }
    }
}
```

### 姿势 2: 覆盖 weak 回调(实时性高)

```c
volatile uint8_t frame_ready;
volatile uint16_t frame_len;

void uart_idle_callback(uint8_t idx, uint16_t len)   /* 帧结束, 中断上下文 */
{
    if (idx == DT_UART1_IDX) { frame_ready = 1; frame_len = len; }
}

/* 主循环: */
if (frame_ready) {
    frame_ready = 0;
    ...  /* 从 uart_read() 取 frame_len 字节处理 */
}
```

回调运行在中断上下文,只置标志/短拷贝,不做延时与 printf
(见 [common/README.md](../common/README.md) 准则)。
每字节回调为 `uart_rx_callback(idx)`(数据已入环形缓冲区)。

## printf 重定向

设备树实例写 `console = <1>;` + Kconfig 开 `CONFIG_DRIVER_UART_PRINTF`,
直接:

```c
printf("value = %d\r\n", v);      /* 自动走该串口, 无需 fputc */
```

## 三种模式(设备树决定,API 不变)

| 设备树配置 | 行为 |
|---|---|
| `dma-mode=<1>; int-mode=<GD32_UART_INT_IDLE>` | **DMA 模式**: 循环 DMA 收 + IDLE 判帧,TX 走 DMA(不占 CPU) |
| `dma-mode=<0>; int-mode=<GD32_UART_INT_RX_IDLE>` | **中断模式**: RBNE 每字节入环形缓冲区 + IDLE 判帧 |
| `dma-mode=<0>; int-mode=<GD32_UART_INT_NONE>` | **纯轮询**: 无中断无 DMA(调试起步最简) |

限制: UART4 无 DMA(驱动自动退化为中断);UART3 DMA 仅 RX=DMA1_CH2/TX=CH4。
模式常量(`GD32_UART_INT_*` 等)定义在
`arm/include/dt-bindings/serial/gd32f10x-uart.h`。

## 完整示例

见 `application/gd32f103re/uart_echo/`(IDLE 帧查询 + 回显),
它还演示了应用自带 `defconfig` 覆盖板级配置的用法。
