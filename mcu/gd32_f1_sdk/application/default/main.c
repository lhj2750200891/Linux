/**
 * @file  main.c
 * @brief 默认空应用 —— 板型下没有独立应用时的公共回退
 *
 * 适用场景: 新板型 bring-up (defconfig + dts 就绪, 应用还没写)。
 * 硬件初始化全部由设备树 + 驱动自动完成 (main 之前 DEVICE_INIT 自动 probe),
 * 本应用只保证 main() 存在使链接通过, 然后原地空转。
 */
#include "gd32f10x.h"

int main(void)
{
    SCB->VTOR = FLASH_START;

    while (1) {
        
    }
}
