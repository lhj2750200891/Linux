# HAL 固件库

> Rockchip 自研 MCU HAL 库,规范参考: `bsp/rockchip/common/hal/doc/Rockchip_User_Guide_HAL_CN.md` (V3.5.0, 2026-07)
> 风格类似 STM32 HAL,MISRA-C 规范,基于 CMSIS5

---

## 1. 目录结构

```
bsp/rockchip/common/hal/
├── doc/                     用户指南
├── lib/
│   ├── CMSIS/
│   │   ├── Core/Include/            ARM CMSIS 核心头文件 (core_starmc1.h 等)
│   │   └── Device/RK2118/Include/   ★ 芯片头文件
│   │       ├── soc.h        中断号/模块基地址/寄存器结构体/位宏(HAL 统一引用)
│   │       ├── rk2118.h     rxbb 工具生成的寄存器定义
│   │       └── system_rk2118.h
│   ├── bsp/RK2118/          hal_bsp.c/h — 芯片公共板级配置与抽象资源(如 g_uart0Dev)
│   └── hal/
│       ├── inc/             hal_base.h / hal_uart.h / hal_i2c.h ... (API 声明)
│       └── src/             hal_uart.c / hal_i2c.c ... (驱动实现,含 cru/ pinctrl/ pm/ 子目录)
├── project/rk2118/          裸机工程(GCC/ KEIL/ src/hal_conf.h main.c) + mkimage.sh
└── tools/
```

双核支持: `soc.h` 通过 `HAL_MCU_CORE`(STAR-MC1, core_starmc1.h) 或 `HAL_DSP_CORE`(HiFi4, core_hifi4.h) 区分;CPU 核用 `RK2118_CPU_CORE0/CORE1`,DSP 核用 `RK2118_DSP_CORE0/1/2`。

## 2. HAL API 风格

```c
#include "hal_base.h"

/* 初始化 */
HAL_Init();

/* 以 UART 为例 — 配置结构体 + 设备句柄(来自 hal_bsp) */
struct HAL_UART_CONFIG hal_uart_config = {
    .baudRate = UART_BR_115200,
    .dataBit  = UART_DATA_8B,
    .stopBit  = UART_ONE_STOPBIT,
    .parity   = UART_PARITY_DISABLE,
};
HAL_UART_Init(&g_uart0Dev, &hal_uart_config);
HAL_UART_SerialOutChar(UART0, 'c');
```

命名规则:
- `HAL_PPP_Init/DeInit/...` — 通用 API
- `HAL_PPP_ex_xxx` — 芯片特殊/覆盖 API
- 寄存器访问宏: `WRITE_REG_MASK_WE(GRF->GPIO0B_IOMUX_H, mask, val)`、`READ_REG` 等
- IOMUX 配置直接操作 GRF 寄存器(引脚复用没有独立 pinmux API,手写 SEL 位域)

## 3. hal_conf.h — 模块裁剪开关

每个工程有 `hal_conf.h`(从 `hal_conf.h.template` 裁剪),控制 HAL 模块编译:

```c
#define RKMCU_RK2118
#define HAL_UART_MODULE_ENABLED
#define HAL_I2C_MODULE_ENABLED
#define HAL_CRU_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
...
```

RT-Thread BSP 用的 hal_conf.h 在 `bsp/rockchip/rk2118/hal_conf.h`。

## 4. RT-Thread 与 HAL 的关系

```
应用 (main.c / msh)
  ↓
RT-Thread 设备框架 (rt_device)      ← bsp/rockchip/common/drivers/drv_uart.c 等
  ↓
Rockchip HAL 库 (HAL_UART_Init...)  ← bsp/rockchip/common/hal/lib/hal/
  ↓
寄存器 (soc.h / rk2118.h)
```

`common/drivers/` 的 drv_*.c 是 RT-Thread 设备框架适配层,内部调用 HAL API;直接用 HAL 也可以(裸机或特殊场景)。

## 5. 裸机(HAL only)编译与烧写 — hal/project/rk2118

```shell
export PATH=/path/to/arm-gnu-toolchain-13.2.Rel1-x86_64-arm-none-eabi/bin:$PATH
cd bsp/rockchip/common/hal/project/rk2118/GCC
make clean; make -j16
cd ..
./mkimage.sh
# GCC/TestDemo.elf → 调试用 elf
# Image/bare.img   → 裸机固件(需配合前级 loader)
```

烧写:先按 `Rockchip_Developer_Guide_RK2118_CN.pdf` 正常烧一个 Firmware.img,再把 bare.img 烧到 `cpu0_os_a` 分区。分区位置见 `board/adsp_demo/setting.ini`(PartOffset 单位 512 字节,如 0x300*512=0x60000)。

Keil 工程:加入 `project/rk2118/src`、`CMSIS/Device/RK2118`、`hal/src`(含 cru/pinctrl/pm 子目录)、`bsp/RK2118`,头文件加对应 Include 目录,链接脚本参考 `project/rk2118/GCC/gcc_arm.ld` 改写。
