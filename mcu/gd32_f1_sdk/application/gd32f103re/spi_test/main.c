/**
 * @file  main.c
 * @brief SPI 主机驱动验证应用 (回环自发自收 + 一主多从演示)
 *
 * 设备树配置 (gd32f103re.dts spi-buses 节点):
 *   spi1: PB13=SCK / PB14=MISO / PB15=MOSI, 9MHz, 8bit CPOL=0 CPHA=1 MSB
 *     cs-gpios = <PB12>, <PB1>          (软片选列表)
 *     spidev0@0: 回环测试从机, CS=PB12 (status = "okay")
 *     spidev1@1: 第二从机演示一主多从, CS=PB1 (已注释, 打开即验证)
 *
 * 验证方法:
 *   1. 用跳线帽把 PB15 (MOSI) 接到 PB14 (MISO)
 *   2. 烧录后看串口: 每秒一次回环传输, 收发数据比对
 *   3. 示波器可看 PB13 时钟 / PB12 片选 (传输期间拉低)
 *
 * 预期串口输出 (115200, USART0 PA9):
 *   === spi_test: spi1 (PB13/14/15 9MHz) loopback ===
 *   [SPI] dev0 loopback PASS (8 bytes, cs=PB12)
 *   [SPI] dev1 loopback PASS (8 bytes, cs=PB1)   <- 挂载 spidev1 时
 *
 * 从机节点从设备树摘除时: DT_SPIDEV0_IDX 变为 DT_IDX_DISABLED,
 * 本应用走 #else 分支, 编译不报错。
 */
#include "main.h"

#include "systick.h"
#include "led.h"
#include "spi_gd32.h"
#include "devicetree_generated.h"

/* 回环测试数据: 交替电平 + 递变, 任何 bit 错位/丢位都会比对失败 */
static const uint8_t tx_pat[8] = { 0x55, 0xAA, 0x01, 0xFE, 0x12, 0x34, 0x7F, 0x80 };

static uint32_t sec = 0;                                     /* 运行秒数 (打印图案随秒变化) */

/* 一轮回环传输: 返回 0 = PASS, -1 = FAIL (打印首个差异字节) */
static int loopback_once(uint8_t slave)
{
    uint8_t rx[8];
    uint8_t tx[8];

    for (uint8_t i = 0; i < 8; i++) {
        tx[i] = (uint8_t)(tx_pat[i] ^ (uint8_t)sec);       /* 每秒换个图案 */
    }
    int rc = spi_transfer(slave, tx, rx, 8);
    if (rc != GD_SPI_OK) {
        printf("[SPI] dev%u transfer ERR rc=%d\r\n", (unsigned)(slave - DT_SPI1_IDX), rc);
        return -1;
    }
    for (uint8_t i = 0; i < 8; i++) {
        if (rx[i] != tx[i]) {
            printf("[SPI] dev%u FAIL byte%u tx=0x%02X rx=0x%02X (MOSI->MISO 跳线?)\r\n",
                   (unsigned)(slave - DT_SPI1_IDX), i, tx[i], rx[i]);
            return -1;
        }
    }
    return 0;
}

int main(void)
{
    SCB->VTOR = FLASH_START;
    sec = 0;

    printf("=== spi_test: spi1 (PB13=SCK PB14=MISO PB15=MOSI, 9MHz) ===\r\n");
    printf("请用跳线连接 PB15 (MOSI) -> PB14 (MISO)\r\n");

    while (1) {
        sys_delay_ms(1000);
        sec++;

#if defined(DT_SPIDEV0_IDX) && DT_SPIDEV0_IDX != DT_IDX_DISABLED
        if (loopback_once(DT_SPIDEV0_IDX) == 0) {
            printf("[SPI] dev0 loopback PASS (8 bytes)\r\n");
        }
#else
        printf("[SPI] 设备树未挂载 spidev0 (DT_SPIDEV0_IDX 不存在/禁用)\r\n");
#endif

#if defined(DT_SPIDEV1_IDX) && DT_SPIDEV1_IDX != DT_IDX_DISABLED
        /* 一主多从: 同一条 SPI1 总线, 不同 CS 的第二个从机 */
        if (loopback_once(DT_SPIDEV1_IDX) == 0) {
            printf("[SPI] dev1 loopback PASS (8 bytes, 共用总线独立片选)\r\n");
        }
#endif

        if (LED_COUNT > 0) {
            led_toggle(DT_LED1_IDX);
        }
    }
}
