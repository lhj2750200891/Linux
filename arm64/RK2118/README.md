/*
 * RK2118 RT-Thread SDK 开发笔记
 * 芯片: RK2118 (双核 STAR-MC1 + 3 核 HiFi4 DSP + 音频 NPU, 智能音频处理器)
 * SDK:  /media/lhj/windows/code/arm64/rockchip/rk2118_sdk
 * 分支: rk2118/firefly (RT-Thread v4.1.1)
 * 时间: 2026-11-26
 */

# RK2118 SDK 笔记索引

| 笔记 | 内容 | 何时读 |
|---|---|---|
| [01-SDK总览与目录结构](01-SDK总览与目录结构.md) | 芯片架构、SDK 组成、固件形态、版本演进 | **第一次接触必读** |
| [02-编译构建与打包](02-编译构建与打包.md) | build.sh、menuconfig、mk*.sh 打包脚本、RESC 头、签名、启动链 | 第一次编译前 |
| [03-内存布局与链接脚本](03-内存布局与链接脚本.md) | XIP/SRAM/DDR 三套地址图、链接脚本、分区表格式 | 改内存/分区/移植时 |
| [04-板级配置与板卡变体](04-板级配置与板卡变体.md) | 13 个板卡目录、board_base.c 启动流程、时钟/OPP、新建板级步骤 | 选板/建板时 |
| [05-HAL库](05-HAL库.md) | Rockchip HAL 结构、API 风格、hal_conf.h 裁剪、裸机编译 | 直接操作寄存器/裸机时 |
| [06-DSP与音频开发](06-DSP与音频开发.md) | HiFi4×3、DRP 框架、mkdsp.sh、核间通信、音频软件栈 | 音频/DSP 开发必读 |
| [07-组件与RT-Thread内核](07-组件与RT-Thread内核.md) | v4.1.1 内核配置、组件清单、自动初始化、常用 API | 应用开发 |
| [08-文档与工具资源](08-文档与工具资源.md) | Rockchip-docs 文档地图、PC 烧写工具、SDK 同步 | 找文档/工具时 |
| [09-驱动层](09-驱动层.md) | 外设 Kconfig、驱动实现要点、寄存器基址、音频驱动架构、fwmgr | 写驱动时 |
| [10-EVB板快速上手实操](10-EVB板快速上手实操.md) | **拿板实测路径**: V10/V20 区分、上电看日志、编译、烧写、msh 体验、快速迭代 | **上手第一篇** |
| [11-接口功能验证](11-接口功能验证.md) | msh 内置命令 + common tests 组件开法、按接口验证矩阵(音频/存储/网口/低功耗...) | 外设调试时 |
| [12-新建板级实操指南](12-新建板级实操指南.md) | **从 evb1_v20 模板新建 firefly-rk2118g-evb 板**:目录/Kconfig/SConscript 三挂钩、defconfig 切换、编译烧写验收、7 个真实踩坑 | 建自己板子时跟着做 |

## 五分钟上手

```bash
# 1. 工具链(强制 13.2.Rel1 版本)
export RTT_EXEC_PATH=/path/to/arm-gnu-toolchain-13.2.Rel1-x86_64-arm-none-eabi/bin

# 2. 编译(在 BSP 目录下,没有顶层 build.sh)
cd bsp/rockchip/rk2118
./build.sh board/evb/package-file        # EVB → Image/update.img
./build.sh board/adsp_demo/setting.ini   # 车载 → Image/Firmware.img
./build.sh board/evb/package-file rtt0   # 只编 cpu0

# 3. 配置(板卡 defconfig 为准;rtconfig.h 是生成物)
cp board/evb/defconfig .config
scons --menuconfig                       # 调完 cp .config board/evb/defconfig 存回
scons --useconfig=.config                # 重新生成 rtconfig.h

# 4. 烧写: DriverAssitant_v5.13.zip (bsp/rockchip/tools/) 进 maskrom/loader 模式烧 update.img
# 5. 串口: uart0, 1500000 波特 (g_uart0_board)
```

## 关键认知(避免踩坑)

1. **rtconfig.h 是生成物** — 改配置要改 `board/<板>/defconfig`,不要直接改 rtconfig.h
2. **XIP 与非 XIP** — rtconfig.py 默认 XIP;编 nand/eMMC 固件时 build.sh 自动处理(RTT_BUILD_XIP),手动编时需把 "XIP" 改 "W"
3. **三种运行形态** — XIP(0x11060800)/SRAM(recovery)/DDR(0xA0100000),由 Kconfig `CPU_RUN_IN_*` 选择
4. **双核分工** — 只有 CORE0 支持完整 HIFI4 栈;CPU1 通常只做日志重定向
5. **DSP 固件两套来路** — SDK 预编译(`components/hifi4/rtt/dsp_fw/`)或 `mkdsp.sh` 自编(需 Xtensa 工具链)
6. **userdata 必须是最后一个分区**;nor 64KB / nand 256KB 对齐;OTA 要 A/B 双份
7. **文档都在 SDK 里** — `Rockchip-docs/manuals/rk2118/`(芯片)+ `develop/rk211x/`(开发)+ HAL 中文指南
