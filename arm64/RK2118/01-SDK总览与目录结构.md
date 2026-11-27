# RK2118 RT-Thread SDK 总览

> 基于 `rk2118/firefly` 分支 (Firefly 维护),内核 RT-Thread **v4.1.1**
> SDK 路径: `/media/lhj/windows/code/arm64/rockchip/rk2118_sdk`
> 笔记时间: 2026-11-26

---

## 1. 芯片定位:RK2118 是什么

RK2118 是 Rockchip 的**音频 DSP SoC**(智能功放/回音壁/Soundbar/Partybox 类产品):

| 项目 | 内容 |
|---|---|
| CPU | **双核 STAR** (ARMv8-M / Cortex-M33 级,16K I/D-Cache、FPU 单精度、MPU、TrustZone) — cpu0 / cpu1 |
| DSP | **3 核 Cadence HiFi4** (DSP0/1/2),DSP0 独立电压域可 DVFS(700/800MHz) |
| NPU | 音频专用 NPU(16/32bit 卷积 MAC;DDR 方案才有,4MB) |
| 加速器 | FIR/IIR 加速器 FACC(4096 阶 FIR / 64 biquad IIR)、ASRC×8 |
| 存储 | 1MB SRAM + 16KB PMU SRAM + BootROM + OTP;外接 SPI NOR/NAND (XIP)、eMMC、SD |
| 音频外设 | 8×SAI (I2S/PCM/TDM)、PDM 8mic、SPDIF TX1/RX2、内置 ACDC DIG codec |
| 编译目标 | `-mcpu=cortex-m33 -mthumb -mfpu=fpv5-sp-d16 -mfloat-abi=hard` |
| 内核移植 | `libcpu/arm/cortex-m33/` |
| 启动 | BootROM → IDB loader → TF-M secure → cpu0_os (RT-Thread) → DSP 固件按 DRP 加载 |
| 变体 | RK2118M(SRAM 方案,无 DDR)/ RK2118M2(带 DDR)/ RK2118G / RK2118B,QFP128L 封装;Datasheet V2.0 2026-09-15 |

menuconfig 第一项就是 `RK2118 cpu core select (STAR-MC1 CORE0)`,选 CORE0/CORE1(CORE1 会 select CORE0)。

## 2. SDK 整体架构

这是 **RT-Thread 官方源码树 + Rockchip BSP/组件** 的组合:

```
上层应用 (applications/, components/hifi4/samples/)
─────────────────────────────────────────────
Rockchip 组件层  hifi4(DSP)/aupipe(音频管道)/rkstudio(调音)/ota/rknpu/rpmsg_cmd
─────────────────────────────────────────────
RT-Thread 组件层 finsh/dfs/drivers(设备框架)/net/libc/utilities/fal
─────────────────────────────────────────────
RT-Thread 内核   src/ (thread/scheduler/ipc/mem/timer...)  v4.1.1
─────────────────────────────────────────────
BSP              bsp/rockchip/rk2118 (板级+芯片配置)
                 bsp/rockchip/common (共享驱动池 + HAL 库)
─────────────────────────────────────────────
硬件             双核 STAR-MC1 + 3x HiFi4 + 外设
```

## 3. 顶层目录结构

| 目录 | 内容 | 备注 |
|---|---|---|
| `bsp/rockchip/rk2118/` | **RK2118 BSP 主目录(开发主战场)** | Kconfig、rtconfig.h、build.sh、mk*.sh 打包脚本、链接脚本、board/ 板卡变体、Image/ 输出 |
| `bsp/rockchip/common/` | 共享驱动池 `drivers/` + HAL 库 `hal/` + 固件管理 `fwmgr/` | 所有 rockchip MCU 芯片共用 |
| `bsp/rockchip/tools/` | PC 端烧写/打包工具 | DriverAssitant_v5.13.zip、boot_merger、SocToolKit、sign_tool、littlefs-tool 等 |
| `src/` | RT-Thread 内核源码 (19 个 .c) | clock/thread/scheduler/ipc/mem/memheap/slab/mempool/object/irq/idle/timer/device/components/kservice... |
| `include/` | RT-Thread 内核头文件 | 版本宏在 `rtdef.h` (RT_VERSION=4, RT_SUBVERSION=1, RT_REVISION=1) |
| `libcpu/` | CPU 移植,RK2118 用 `arm/cortex-m33/` | context_gcc.S、cpuport.c、trustzone.c |
| `components/` | RT-Thread 组件 + Rockchip 组件 | finsh/dfs/drivers/net/libc/utilities/ota + **hifi4/aupipe/rkstudio/rknpu/rpmsg_cmd** |
| `applications/` | 通用应用 demo(旧芯片遗留) | recording_pen、clock 等 |
| `examples/` | RT-Thread 官方示例 | bluetooth/file/libc/network/pm/ulog/utest |
| `third_party/` | 第三方库 | cmsis、bt、netutils、wfd、rkstack 等 |
| `Rockchip-docs/` | **Rockchip 官方文档(PDF/MD),开发必读** | 见《08-文档与工具资源》 |
| `documentation/` | RT-Thread 官方文档(md) | 内核/组件/设备框架各主题 |
| `tools/` | RT-Thread SCons 构建工具链 | building.py 为核心(没有独立 environment.py) |
| `.repo/manifests/` | repo 多仓库清单 | rk2118_linux_next.xml 等;本仓库是被裁出的主仓库 |

## 4. 固件形态与多核分工

RK2118 固件由多个 bin 组成,最终打包:

| 产物 | 跑在 | 说明 |
|---|---|---|
| `rtt0.bin/elf` | cpu0 (STAR-MC1 core0) | 主系统,RT-Thread |
| `rtt1.bin/elf` | cpu1 (STAR-MC1 core1) | 副核,可有独立 defconfig (`cpu1_defconfig`) |
| `recovery.bin` | cpu0 | 恢复/升级模式系统 |
| DSP 固件 | HiFi4 DSP | SDK 预编译位于 `components/hifi4/rtt/dsp_fw/evb_soundbar_demo/`,源码工程在 `components/hifi4/samples/rk2118/` |
| `root.img` | — | 资源文件只读分区 (mkroot.sh 打包) |

分区/打包两种格式:
- **Firmware.img**:车载 SPI Nor,RK partition 表,配置 `board/xxx/setting.ini`
- **update.img**:消费类 SPI Nor/Nand/eMMC,GPT 分区,配置 `board/xxx/parameter.txt` + `package-file`

## 5. SDK 版本演进(release note 摘要)

`Rockchip-docs/release_notes/RK2118_RT-Thread_Release_Note.txt`,V0.2.0(2024-05)→ V1.5.0(2025-05):

- V1.0.0 (2024-09): 首个正式版 — suspend、OTA A/B 全固件备份、secure boot 签名(Dolby Atmos 库)、GMAC、EV1 V20 板
- V1.1.0 (2024-10): eMMC 支持、Atmos dec/DAP 分离
- V1.2.0 (2024-12): RK2118M2 封装、HDMI repeater 升级、UART 升级 update.img
- V1.3.0 (2025-01): NPU 人声分离/环绕声 demo、rkstudio 0.79、adsp sai 驱动
- V1.4.0 (2025-03): 新 DPS-NPU 驱动框架、**audio pipe 新框架**、车载无缝升级
- V1.5.0 (2025-05): rkstudio 0.83(更多音效/AGC/fade)、rkplayer 1.5.0 suspend/resume

主线方向: **音效生态 (rkstudio) / NPU 音频算法 / audio pipe 新框架 / OTA 升级链路 / Dolby&DTS 认证 / 低功耗**。

## 6. git 分支说明

- 当前分支 `rk2118/firefly`(Firefly 维护的 RK2118 版本),远端 `firefly-linux/rk2118/firefly` 与 `firefly-linux/rk2118/rockchip`
- 近期提交主题: DDR audio pipe DSP 固件区分、evb1_v20_nor soft timer、MISRA 修复、board_base.h 声明清理
- 仓库是 repo 管理的一部分(`.git -> .repo/projects/..git`)
