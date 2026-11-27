# RT-Thread 内核与组件体系

> 内核版本 **v4.1.1** (rtdef.h: RT_VERSION=4, RT_SUBVERSION=1, RT_REVISION=1; rtconfig.h: RT_VER_NUM 0x40101)

---

## 1. 内核 (src/)

19 个源文件,标准 RT-Thread 结构:

| 文件 | 职责 |
|---|---|
| scheduler.c / thread.c / clock.c | 调度器、线程、时钟 tick |
| ipc.c | 信号量/互斥量/事件集/邮箱/消息队列 |
| timer.c | 定时器(hard/soft timer) |
| object.c | 内核对象容器(rt_object) |
| irq.c / idle.c | 中断管理、空闲线程+hook |
| mem.c / slab.c / memheap.c / mempool.c | 三种内存算法都带,**RK2118 选 SMALL_MEM** |
| device.c | 设备框架(rt_device) |
| components.c | 自动初始化机制(INIT_BOARD_EXPORT 等 6 级) |
| kservice.c | rt_kprintf 等内核服务 |

### RK2118 当前内核配置 (bsp/rockchip/rk2118/rtconfig.h)

```
RT_NAME_MAX 8              RT_ALIGN_SIZE 4
RT_THREAD_PRIORITY_32      (32 级优先级)
RT_TICK_PER_SECOND 1000
RT_USING_SMALL_MEM + RT_USING_SMALL_MEM_AS_HEAP   ← 内存算法
RT_USING_MEMHEAP (FAST_MODE) + RT_USING_HEAP + RT_USING_MEMPOOL
RT_USING_OVERFLOW_CHECK    栈溢出检查
RT_USING_HOOK
main 线程: 优先级 10, 栈 2048
ARCH_ARM / ARCH_ARM_CORTEX_M
```

## 2. 设备框架 (components/drivers/)

RT-Thread 标准设备框架,`rt_device_find()` 按名称找:

| 子目录 | 设备名前缀 | rk2118 默认启用 |
|---|---|---|
| serial | uartN | ✅ SERIAL_V1 + DMA |
| i2c | i2cN | ✅ (bitops 模式) |
| spi | spiN | 可选 |
| pin | pin | ✅ |
| audio | audioN | 按板卡(音频 demo 板开) |
| mtd | mtd | ✅ MTD_NOR |
| sdio/watchdog/hwtimer/pwm/rtc/can/usb/sensors... | — | 按需 |

## 3. 组件清单与 RK2118 启用状态

| 组件 | 用途 | rk2118 (adsp_demo 默认 rtconfig.h) |
|---|---|---|
| `finsh/` | **msh 命令行 shell** | ✅ RT_USING_FINSH + RT_USING_MSH |
| `dfs/` | 文件系统框架(devfs/elmfat FAT/littlefs/ramfs/romfs) | 默认未开,板卡 defconfig 可开(Quick Start: root 只读挂 /,userdata 挂 /data 用 elm-fat(nand/emmc) 或 littlefs(nor)) |
| `drivers/` | 设备框架 | ✅ SERIAL/I2C/PIN/MTD_NOR |
| `net/` | lwip/sal/netdev/at | ❌ |
| `libc/` | C 库 | libc_nano |
| `utilities/` | ulog/utest/cmbacktrace/ymodem | ✅ **cmbacktrace**(M33 平台,崩溃栈回溯) |
| `fal/` | Flash 抽象层 | ❌(Rockchip 用自研 SNOR 栈) |
| `ota/` | OTA 升级(ota_file/gpt/http/new/lzma/md5/crc) | 部分板卡 defconfig 启用 |
| **`hifi4/`** | **HiFi4 DSP 支持(核心组件)** | ✅ RT_USING_HIFI4 |
| `aupipe/` | 音频管道框架(类 gstreamer 简化版) | 部分板卡启用 |
| `rkstudio/` | RkStudio 音效调音(dsp+rtt 双端) | ✅ RKSTUDIO_COMM/TUNING |
| `rknpu/` | NPU 驱动与示例 | ❌(可选 RT_USING_RKNPU_DSP_DRIVER) |
| `rpmsg_cmd/` | 多核 rpmsg 命令通道 | 可选 |
| `benchmark/` | coremark 等 | ✅ RT_USING_COREMARK |
| system/ (lvgl) / vbus/ / vmm/ / lwp/ / cec/ | 图形/虚拟化/进程 | ❌ |

## 4. hifi4 组件结构(音频 DSP 核心)

```
components/hifi4/
├── dsp/       DSP 端系统 (dsp/components/core/drivers/rockit)
├── rtt/       MCU 端支持
│   ├── app/codecs/      音频编解码
│   ├── dsp_fw/          预编译 DSP 固件 (evb_soundbar_demo/)
│   ├── dsp_drp/         DSP 资源管理
│   ├── rkstudio_comm/ rkstudio_bin/   调音通信
│   ├── rockit/ rknn_dsp_comm/
├── samples/rk2118/   ★ DSP 固件源码工程 (menuconfig HIFI4_PROJECT 选择)
│   ├── adsp_demo           默认 demo
│   ├── evb_partybox_demo   预编译固件对应的工程 (readme.txt)
│   ├── facc_demo / helloworld_demo
│   ├── npu_demo            NPU demo (依赖 RT_USING_RKNPU_DSP_DRIVER)
│   ├── vocal_separate_demo 人声分离
│   └── vehicle_audio_pipe  车载 audio pipe
├── shared/    mcu/dsp 共享代码
└── tools/     DSP 固件构建: mkfw.py / mkld.py / mkprojects.py / xplorer-builder (Xtensa 工具链)
```

## 5. 自动初始化机制(应用开发必知)

`components.c` 提供 6 级自动初始化宏,按序执行:

```
INIT_BOARD_EXPORT(fn)      → 板级硬件初始化(调度器启动前)
INIT_PREV_EXPORT(fn)       → 软件初始化前段
INIT_DEVICE_EXPORT(fn)     → 设备驱动初始化
INIT_COMPONENT_EXPORT(fn)  → 组件初始化
INIT_ENV_EXPORT(fn)        → 环境初始化(文件系统挂载等)
INIT_APP_EXPORT(fn)        → 应用初始化(main 之前)
```

板级驱动(drv_uart 等)多用 `INIT_BOARD_EXPORT` / `INIT_DEVICE_EXPORT` 注册设备;应用代码用 `INIT_APP_EXPORT` 或在 main() 里初始化。

## 6. 常用内核 API 速查

```c
/* 线程 */
rt_thread_create(name, entry, param, stack_size, prio, tick);
rt_thread_startup(tid);
/* 同步 */
rt_sem_create/take/release;  rt_mutex_create/take/release;
rt_event_create/send/recv;   rt_mb_create/send/recv;  rt_mq_create/send/recv;
/* 内存 */
rt_malloc / rt_free / rt_realloc          (SMALL_MEM 堆)
rt_mp_create (内存池)
/* 设备 */
rt_device_find(name);  rt_device_open/read/write/control/close;
/* 时间 */
rt_thread_mdelay(ms);  rt_tick_get();  rt_timer_create;
/* 控制台 */
rt_kprintf();  msh 命令: FINSH_FUNCTION_EXPORT / MSH_CMD_EXPORT
```
