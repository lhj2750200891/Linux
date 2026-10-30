# AIBOX-PRO ES8390 录音适配记录

本文记录 AIBOX-PRO-K3 上 ES8390 的设备树适配、录音测试方法，以及“第一次录音有声音，第二次开始无声音”的驱动修复。下次适配同类板卡时，可按本文逐项检查。

## 1. 适配范围

- SoC/板卡：Spacemit K3，Firefly AIBOX-PRO。
- Codec：Everest ES8390。
- Linux 音频框架：ASoC + `simple-audio-card`。
- 当前内核已有 `sound/soc/codecs/es8389.c`，没有独立的 ES8390 驱动，因此本方案通过 ES8389 兼容驱动访问 ES8390。
- 本次最终修复只修改 `sound/soc/codecs/es8389.c`，没有要求再修改设备树。

> ES8389 与 ES8390 的寄存器/初始化行为并非完全相同。本文的驱动改动是针对本 BSP 硬件连线和 ES8390 现象的兼容性方案；如果产品同时支持真正的 ES8389，建议后续拆分为独立的 ES8390 驱动或按 I2C 匹配信息选择不同待机策略。

## 2. 硬件连接核对

适配前先按原理图确认以下连接，任何一项不一致都不能直接套用本文：

| 信号 | K3 连接 |
| --- | --- |
| Codec I2C 地址 | `i2c0`，地址 `0x11` |
| I2S BCLK | `K3_PADCONF(111, 2)` |
| I2S FS/LRCK | `K3_PADCONF(112, 2)` |
| I2S DOUT | `K3_PADCONF(113, 2)` |
| I2S DIN | `K3_PADCONF(114, 2)` |
| Codec MCLK | `K3_PADCONF(85, 2)`，时钟源 `CLK_MPMU_I2S0_SYSCLK` |
| 耳机检测 | GPIO71，低有效 |
| 外部电话/电源控制 | GPIO44，输出高 |
| 麦克风输入 | ES8390 `INPUT2` |

如果原理图使用的是别的 MCLK 引脚，必须同时修改 pinctrl 和实际时钟连接；仅修改 `clocks` 属性不能替代引脚复用。

## 3. 设备树适配

### 3.1 预处理宏

在 AIBOX-PRO 的 `.dts` 中打开：

```dts
#define FF_ES8390
```

该宏用于打开 ES8390 的声卡、I2C Codec 节点、I2S 节点和 pinctrl 节点。

### 3.2 Codec I2C 节点

设备树节点的关键内容如下：

```dts
&i2c0 {
    status = "okay";

    es8390: audio-codec@11 {
        compatible = "everest,es8389";
        reg = <0x11>;
        #sound-dai-cells = <0>;

        clocks = <&syscon_mpmu CLK_MPMU_I2S0_SYSCLK>;
        clock-names = "mclk";
        everest,mclk-src = /bits/ 8 <0x40>;
        status = "okay";
    };
};
```

说明：

- `compatible` 必须匹配当前内核中的 ES8389 驱动，否则不会绑定到 `es8389.c`。
- `reg = <0x11>` 必须与硬件拨码/地址脚一致。
- `clocks` 和 `clock-names = "mclk"` 是驱动获取 MCLK 的依据。
- `everest,mclk-src = <0x40>` 用于选择 Codec 内部的 MCLK 来源，保留当前板卡已经验证过的值。

### 3.3 simple-audio-card

```dts
es8390_sound: es8390-sound {
    compatible = "simple-audio-card";
    status = "okay";
    simple-audio-card,name = "snd-es8390";
    simple-audio-card,format = "i2s";
    simple-audio-card,mclk-fs = <256>;
    simple-audio-card,bitclock-master = <&es8390_link_cpu>;
    simple-audio-card,frame-master = <&es8390_link_cpu>;

    simple-audio-card,routing =
        "Headphones", "HPOL",
        "Headphones", "HPOR",
        "INPUT2", "Main Mic";

    es8390_link_cpu: simple-audio-card,cpu {
        sound-dai = <&i2s0>;
    };

    simple-audio-card,codec {
        sound-dai = <&es8390>;
    };
};
```

`INPUT2 -> Main Mic` 是本板实际使用的录音通道。若麦克风接在 `INPUT1`，必须按原理图修改 routing，同时确认 Codec 的 PGA/ADC 通道设置。

### 3.4 I2S 和 pinctrl

```dts
&i2s0 {
    pinctrl-names = "default";
    pinctrl-0 = <&es8390_i2s0_cfg>;
    status = "okay";
};
```

`es8390_i2s0_cfg` 必须包含 BCLK、FS、DOUT、DIN 和 MCLK 五根线，且 MCLK 使用 GPIO85 的复用功能 2。GPIO44 的 phone control hog 和 GPIO71 的耳机检测 pinctrl 也要与硬件一致。

### 3.5 避免重复定义

本次源码中 `k3-firefly-aibox-pro.dts` 同时包含了 `k3-firefly-aibox-pro.dtsi` 和 `aibox-pro-test.dtsi`。这两个文件都可能包含 `es8390`、`es8390_sound`、`es8390_i2s0_cfg` 等同名节点。

适配时必须选择一个文件作为 ES8390 配置的唯一来源：

1. 将完整配置放在 `k3-firefly-aibox-pro.dtsi`；或
2. 将完整配置放在 `aibox-pro-test.dtsi`。

不要把相同 label 和节点复制到两个同时被 include 的文件中。编译前检查预处理后的 DTS，确认每个 ES8390 label 只有一个定义。本文不要求修改设备树，以上只是下次适配时的检查项。

## 4. 录音参数限制

K1 I2S 驱动在 `SND_SOC_DAIFMT_I2S` 模式下固定约束：

- 声道数必须为 2；
- 格式必须为 `S16_LE`。

因此下面的命令会失败：

```text
arecord -D hw:0,0 -r 48000 -f S16_LE
arecord: set_params:1404: Channels count non available
```

正确的测试命令必须显式指定 `-c 2`：

```sh
export XDG_RUNTIME_DIR=/run/user/0
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 test.wav
```

`XDG_RUNTIME_DIR` 只影响部分用户态音频程序的运行环境，不会修复 Codec 的硬件状态问题。

## 5. 故障现象和定位过程

复现步骤：

```sh
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 t1.wav
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 t2.wav
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 t3.wav
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 t4.wav
```

第一次录音有声音，后面连续录音无声音；增益调到最大也无效。并且不需要在两次录音之间播放 WAV，也能稳定复现。

这说明：

- I2C 地址、MCLK、I2S 时序和第一次初始化基本正确；
- 不是录音文件格式或 `-c 2` 参数问题；
- 不是播放操作改变了状态；
- 故障发生在第一次 PCM close/stop 之后，属于 Codec 电源状态或寄存器恢复问题。

## 6. 根因分析

原始 `sound/soc/codecs/es8389.c` 在 `es8389_set_bias_level()` 的 `SND_SOC_BIAS_STANDBY` 分支执行完整的深度待机流程：

```c
regmap_write(es8389->regmap, ES8389_CSM_JUMP, 0xD4);
regmap_write(es8389->regmap, ES8389_ADC_EN, 0x00);
regmap_write(es8389->regmap, ES8389_CLK_OFF1, 0x00);
regmap_write(es8389->regmap, ES8389_RESET, 0x3E);
clk_disable_unprepare(es8389->mclk);
```

这套流程适用于 ES8389，但 ES8390 在第一次 PCM 结束后进入该状态时，下一次打开 PCM 虽然 ALSA 能成功配置参数并开始 DMA，ADC 数据链路却没有恢复，因此录音文件只有静音。

驱动中 `es8389_mute()` 的录音静音操作只修改 `ES8389_ADC_FORMAT_MUTE` 的低两位，适合在流切换期间暂时静音；不应通过关闭 ADC、关闭 MCLK 和复位 Codec 来代替普通 PCM 流的静音。

## 7. 最终驱动修改

修改文件：`sound/soc/codecs/es8389.c`。

### 7.1 增加状态字段

```c
struct es8389_private {
    ...
    bool mclk_enabled;
    bool es8390_compat;
};
```

`mclk_enabled` 防止 bias 状态重复切换时对同一个时钟重复 enable/disable。`es8390_compat` 表示当前 BSP 按 ES8390 的浅待机策略运行。

### 7.2 BIAS_ON 避免重复打开 MCLK

```c
case SND_SOC_BIAS_ON:
    if (!es8389->mclk_enabled) {
        ret = clk_prepare_enable(es8389->mclk);
        if (ret)
            return ret;
        es8389->mclk_enabled = true;
    }
    ...
```

Probe 成功打开 MCLK 后立即设置：

```c
es8389->mclk_enabled = true;
```

### 7.3 ES8390 使用浅待机

在 `SND_SOC_BIAS_STANDBY` 分支最前面加入：

```c
if (es8389->es8390_compat) {
    regmap_update_bits(es8389->regmap,
                       ES8389_ADC_FORMAT_MUTE, 0x03, 0x03);
    break;
}
```

这样 PCM 关闭时只静音 ADC，不执行 `CSM_JUMP/ADC_EN/CLK_OFF1/RESET` 深度关机序列，也不关闭 MCLK。下一次 PCM 打开时，Codec 的 ADC、时钟和模拟通路仍处于可恢复状态。

原 ES8389 的深度待机流程保留给 `es8390_compat == false` 的路径，并在真正关闭 MCLK 后设置：

```c
es8389->mclk_enabled = false;
```

### 7.4 当前 BSP 的兼容模式选择

当前内核没有独立的 `everest,es8390` compatible 匹配项，因此在 `es8389_probe()` 中设置：

```c
es8389->es8390_compat = true;
```

这适用于本 BSP 的 ES8390 板卡。若未来同一内核需要同时支持 ES8389 和 ES8390，应增加独立驱动或基于正式 compatible/匹配数据选择该标志，不要无条件影响真正的 ES8389。

### 7.5 为什么没有修改 K1 I2S 驱动

`sound/soc/spacemit/k1_i2s.c` 在 I2S 模式下负责双声道、`S16_LE` 约束以及 `SSCR_SSE` 启停。连续录音测试中 I2S DMA 可以正常启动，问题只在第一次 PCM 结束后的 Codec 状态恢复，因此不需要通过修改 FIFO 或 I2S trigger 来规避。只有在日志明确显示 I2S FIFO/中断没有恢复时，才应单独分析 K1 I2S 驱动。

## 8. 编译和部署

使用 SDK 原有的 AIBOX-PRO 内核配置和打包流程，确认至少启用了：

```text
CONFIG_SND_SOC_ES8389=y        # 或 m
CONFIG_SND_SOC_GENERIC_SIMPLE_CARD=y
CONFIG_SND_SOC_SPACEMIT=y
```

重新编译内核/模块并将新的 Image、模块和对应启动镜像部署到板卡。设备树沿用已经验证的 AIBOX-PRO 配置，不需要为了本次“第二次录音无声”问题新增设备树属性。

在源码树不完整、没有生成 `include/generated/autoconf.h` 和 `include/config/auto.conf` 时，直接编译单个模块会失败；应先使用 SDK 的完整 kernel build 流程生成配置和头文件，再编译目标内核。

## 9. 验收测试

### 9.1 连续录音

```sh
cd /userdata/es8390
rm -f t1.wav t2.wav t3.wav t4.wav
alsamixer -c 0
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 t1.wav
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 t2.wav
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 t3.wav
arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 5 t4.wav
```

四个文件都应能录到相同量级的声音。测试中间不要播放 WAV，这样可以直接验证 PCM stop/start 的恢复能力。

### 9.2 播放检查

```sh
aplay -D hw:0,0 -f S16_LE -r 48000 -c 2 t1.wav
aplay -D hw:0,0 -f S16_LE -r 48000 -c 2 t2.wav
```

### 9.3 状态和日志

```sh
cat /proc/asound/cards
cat /proc/asound/pcm
amixer -c 0 contents
dmesg | grep -Ei 'es8389|es8390|i2s|snd'
```

若需要观察每次 bias 状态切换，可临时打开 `es8389.c` 和 `k1_i2s.c` 的 dynamic debug，然后对比第一次和第二次录音期间的日志。重点确认第二次启动时没有 I2C 错误，且 Codec 没有被重新置于深度复位状态。

## 10. 下次适配检查清单

- [ ] 确认 ES8390 I2C 地址为 `0x11`，且节点 compatible 为当前驱动支持的 `everest,es8389`。
- [ ] 确认 MCLK 实际接 GPIO85，并同时配置 clock provider、`clock-names` 和 pinmux。
- [ ] 确认 I2S 五根信号线和电气属性与原理图一致。
- [ ] 确认 `simple-audio-card` 的 CPU/Codec phandle、I2S 格式、`mclk-fs = <256>` 和 `INPUT2` routing。
- [ ] 确认 ES8390 配置只存在于一个被 include 的 dtsi 中，避免重复 label。
- [ ] 使用 `S16_LE`、48 kHz、双声道命令测试，不能省略 `-c 2`。
- [ ] 连续执行至少四次 `arecord`，中间不播放，确认每次都有声音。
- [ ] 确认 `es8389.c` 的 ES8390 浅待机兼容代码已编入最终内核/模块。
- [ ] 若仍无声，先查 MCLK、I2C 通信和录音 routing，再检查增益；不要先修改设备树或盲目增大增益。

## 11. 最终结论

本问题不是增益不足，也不是 `arecord` 第一次之后参数改变，而是 ES8389 兼容驱动在每次 PCM 结束时执行了 ES8390 无法可靠恢复的深度待机流程。修复方法是：ES8390 运行在兼容模式下，PCM 结束只静音 ADC，保持 ADC 供电和 MCLK；再次打开 PCM 时复用现有状态。设备树保持已经验证的配置，驱动修改集中在 `sound/soc/codecs/es8389.c`。
