# DSP 与音频开发

> RK2118 = 智能音频处理器:双核 STAR-MC1 + **3 核 HiFi4 DSP** + 音频 NPU
> 核心目录: `components/hifi4/` | 文档: `Rockchip-docs/develop/rk211x/`(HiFi4 Quick Start、DSP Audio Application Developer Guide、Audio Subsystem)

---

## 1. DSP 硬件资源

| 核 | TCM | Cache | 频率 | 备注 |
|---|---|---|---|---|
| DSP0 | 256K ITCM + 768K DTCM | 64K I/D | 700MHz(M) / 800MHz(G) | **独立电压域,DVFS**(OPP 表 + GPIO0_A5/A6 控制 dcdc) |
| DSP1 | 256K ITCM + 256K DTCM | 64K I/D | 491.52MHz(M) | |
| DSP2 | 同 DSP1 | 64K I/D | 491.52MHz(M) | |

HiFi4: 4 VLIW slots、64-bit SIMD、4 MAC 32x32 / 8 MAC 16x16、双 2-Way SIMD VFPU。
DSP 侧固件也用同一套 HAL 库(`#define HAL_DSP_CORE` + `RK2118_DSP_CORE0/1/2`)。

## 2. DRP 框架 — MCU 侧 DSP 管理(当前主力)

路径 `components/hifi4/rtt/dsp_drp/`(DRP = **DSP Remote Processing**):

- 管理 3 个 DSP 核;固件从 **Built-in / SPI NOR / SPI NAND / eMMC** 加载
- CRC+magic 校验、可选加解密
- 电源/时钟/复位(stall、areset/dreset/breset/jreset)/JTAG 全控
- 硬件操作: `GRF->DSPn_CON0/1/3`(stall/vecsel/addr)、`CRU->SOFTRST_CON`、`PMU`(PD_DSPn power gate)

```c
#include "drp_ctrl.h"
dsp_start(id);                      // 启动 DSP(id=0/1/2)
dsp_stop(id);
int dsp_status(int id, int *status);
```

初始化:`drp_init` 经 INIT_ENV_EXPORT + INIT_COMPONENT_EXPORT 自动执行。
Kconfig:`RT_USING_HIFI4`(总开关)+ `RT_USING_HIFI4_FW_BUILTIN`(固件内置)+ `RT_USING_HIFI4_FW_SECURE_BOOT_CHECK`(向 TF-M 查 OTP 安全启动标志,只接受 RESS 签名固件)。

> 旧框架 `common/drivers/drv_dsp.c`(MBOX work 队列,RT_USING_DSP)是 pisces 遗留,RK2118 不用。

## 3. DSP 固件编译 — mkdsp.sh

```bash
export XTENSA_INSTALL_PATH=/path/to/xtensa/install    # Xtensa 工具链(见安装指南文档)
cd bsp/rockchip/rk2118
./mkdsp.sh adsp_demo_dsp0 build        # 支持 build|clean|rebuild, --target Release|Debug
```

- build target: `HIFI4_64_64_256_512_2ram`,chip_type=rk2118
- 内部调 `components/hifi4/tools/xplorer-builder/build.sh`
- 工程硬编码映射(`components/hifi4/samples/rk2118/` 下,每核一个):
  `evb_partybox_demo_dsp0/1/2`、`vehicle_audio_pipe_dsp0/1/2`、`adsp_demo_dsp0/1/2`、`facc_demo_dsp0/1/2`
- 产物: `components/hifi4/rtt/dsp_fw/` 下 dsp0/1/2.bin(及 `*_ddr.bin`);打包时 mkimage.sh 按板卡替换进 setting.ini

### DSP 工程结构(以 adsp_demo_dsp0 为例)

```
src/main.c          Xtensa 入口 (HAL_DBG 打印, dsp_main() 弱符号)
src/adsp_demo_dsp0.c  直接操作 SAI DMA + librkstudio 音频处理
inc/hal_conf.h      HAL_DSP_CORE 配置(SAI/ASRC/PDM/SPDIFRX/PL330/INTMUX/HWSPINLOCK,
                    HAL_AUDIO_LOW_LATENCY)
mem_layout.h        DSP 内存布局(覆盖 default_mem_layout.h 的 DSP 区)
```

其它 demo: evb_partybox_demo(默认预编译)、facc_demo(FIR/IIR 加速器)、helloworld_demo、npu_demo、vocal_separate_demo(人声分离)、vehicle_audio_pipe(车载)。

## 4. 核间通信(MCU ↔ DSP)

| 通道 | 机制 | 用途 |
|---|---|---|
| DRP | Mailbox(MBOX0@0x40240000,16 元素)+ GRF + 共享内存 | 控制/加载/状态 |
| **dsplink** | `components/hifi4/dsp/drivers/dsplink/` | **DSP↔DSP 音频流互联**:DSP0 同步/转发音频流给 DSP1/2(`DSP0_sync_dsp1_init(rx_mem, rx_ch, tx_mem, tx_ch, frames, period_cnt)`) |
| rkstudio_comm | `components/hifi4/rtt/rkstudio_comm/`(spi2apb 协议) | 调音工具 ↔ DSP(librkstudio_listen/get_status) |
| rpmsg-lite / rpmsg_remote | virtio RPMsg | 核间通用通信(log2ap、rpmsg_i2c/spi/tty) |
| NPU IPC | `components/hifi4/dsp/drivers/npu/rknn_ipc_msg_dsp.c` | NPU 跑在 DSP 时的通信 |

注意:`hal_icc/drv_icc` 是**总线 QoS**(master 优先级/带宽限速,如 ICC_DSP0),不是核间通信。

## 5. MCU 侧音频软件栈

```
应用 (rkplayer / uac_app / system_app  — components/hifi4/rtt/app/)
  ↓
aupipe 音频管道 (components/aupipe/, 类 gstreamer: audiosrc/sink/pad/queue/link)
  ↓
audio pipe 新框架 (V1.4.0 引入) / RT-Thread audio 设备框架 (components/drivers/audio)
  ↓
rk_audio ASoC 中间层 (audio_card + dai_ops + codec_ops)
  ↓
drv_sai/pdm/spdif + codec 驱动 (tas5805m/tas6424/ak5736vn/rk751...)
  ↓
HAL (hal_sai/hal_asrc/hal_facc FIR-IIR加速器) → 8×SAI / PDM / SPDIF / ASRC×8
```

- rkplayer(`components/hifi4/rtt/app/rkplayer`): 播放器框架,V1.5.0 起 1.5.0 版支持 suspend/resume
- uac_app: USB Audio Class 应用
- rkstudio: 音效调音(V1.5.0 = 0.83,更多音效/AGC/fade),`RT_USING_RKSTUDIO_COMM/TUNING`
- DSP 音频算法库跑在 HiFi4 上(librkstudio、杜比 Atmos/DTS、NPU 人声分离)

## 6. 音频开发典型流程

1. **板级声卡**: 在 `board/<板>/board.c` 或 `audio_base.c` 配 `rk_board_audio_cards[]`(SAI + codec + mclkfs)
2. **选择 HIFI4_PROJECT**(menuconfig): helloworld → partybox → adsp → vehicle_audio_pipe
3. **DSP 固件**: 用 SDK 预编译(`components/hifi4/rtt/dsp_fw/evb_soundbar_demo/`)起步;自编用 `./mkdsp.sh <proj>_dspN build`(需 Xtensa 工具链)
4. **MCU 固件**: `./build.sh board/<板>/package-file` 会把 dsp0/1/2.bin 打进镜像
5. **调音**: rkstudio_comm 经 SPI2APB 与外部调音工具通信
6. 参考文档: `RK2118_DSP_Audio_Application_Developer_Guide_CN.pdf`、`RK2118_Audio_Subsystem_CN.pdf`、`RK211X_HiFi4_Quick_Start_CN.pdf`

## 7. NPU(音频专用)

- "One NPU specially designed for audio",16/32bit 卷积 MAC,支持 TFLite/Pytorch/Onnx 等
- DDR 方案才有(RAM 占用 4MB,DRAM_NPU 区);CPU0 管理(`RT_USING_RKNPU` + `RT_USING_RKNPU_RTT_DRIVER`)或 DSP 管理(`RT_USING_RKNPU_DSP_DRIVER`)
- demo: `components/hifi4/samples/rk2118/npu_demo`、`vocal_separate_demo`(人声分离,V1.3.0 引入)
