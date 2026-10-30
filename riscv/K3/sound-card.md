# 音频 (sound card)

　　K3 平台板载音频适配笔记: i2s (sspa) 控制器 + es8389 codec +
simple-audio-card 组链, itx-k3l 的 FF_ES8390 为实装参考。DP/HDMI 出声
的音频链 (adma+ri2s+sound_card_dpX) 已分别在 dp.md / hdmi.md, 本篇是
**I2S codec 类**板载音频。

## 1. 原理

### 1.1 控制器与声卡骨架

- I2S 控制器 6 组: i2s0-i2s5 ("spacemit,k1-i2s", k3.dtsi 基座) +
  RCPU 域 rsspa (k3-rdomain.dtsi, ri2s 已在 dp/hdmi 音频用过)。
- 声卡骨架: sound_card0 / sound_card1 (k3.dtsi, 仅
  `compatible = "simple-audio-card"` 的**空壳**, status disabled) —
  与 sound_card_dp0/dp1 (rdomain, 带预填 dai-link) 不同, 板级要自己
  填整个 dai-link。
- codec: es8389 驱动 `sound/soc/codecs/es8389.c`
  (CONFIG_SND_SOC_ES8389, defconfig 里以 imply 声明, 验证不完整则
  显式补 =y)。

### 1.2 compatible 名字陷阱

　　itx 节点名 es8390, 但 `compatible = "everest,es8389"` — **芯片
es8390 用 es8389 的驱动 compatible** (Everest 两代寄存器兼容), 照抄
没错但别"顺手改齐"成 es8390, 改了反而无驱动匹配。

### 1.3 时钟链

```
CLK_MPMU_I2S1_SYSCLK (MPMU 域) ──> es8390 mclk (板级 clocks 属性)
i2s1 (sspa1) <──> es8390 (I2S 4 线: bclk/lrck/sdin)
```

　　sound_card1 的 mclk-fs = <256> (256 × fs 采样率 = mclk), format
i2s, frame/bitclock-master 都在 cpu 端 (SoC 供时钟)。

## 2. 硬件连接

　　参考板: itx-k3l FF_ES8390 (功放 es8390, 扬声器输出)。

| 信号 | 来源 | 说明 |
|---|---|---|
| sspa1 clk (BCLK) | **pad15 func2** (sspa1_0_cfg) | 1.8V 域 (板级覆写) |
| sspa1 frm (LRCK) | **pad16 func2** | |
| sspa1 tx (SDOUT→codec) | **pad17 func2** | |
| sspa1 rx (SDIN←codec) | **pad18 func2** | 录音才用 |
| sspa1 sysclk (MCLK) | **pad19 func2** | codec 主钟 |
| codec I2C | i2c4 @0x11 | 控制通道 |
| 扬声器/功放控 | spk-ctl-gpio (参考板注释掉) | 按板补 |

接线核对要点:

- sspa1 组板级覆写 power-source=1800 (pad15-19 在 1.8V bank) — itx
  有此覆写, 别省。
- es8390 的 mclk 必须与 mclk-fs、采样率匹配 (48k×256 = 12.288MHz);
  codec 有 PLL 时可宽一些, 参考板直接吃 SYSCLK。
- i2c4 上已有 lt2404/pc9202/pca9555_2 等邻居 (hdmi.md), 地址 0x11
  不冲突, 总线照常使能。

## 3. 内核配置

```
# k3_defconfig:
CONFIG_SND=y / CONFIG_SND_SOC=y      # 已有
CONFIG_SND_SOC_ES8389=?              # defconfig 仅 imply; 确认未编则补:
# CONFIG_SND_SOC_ES8389=y
```

## 4. 设备树配置

### 4.1 itx FF_ES8390 完整展开

```dts
/* codec: i2c4 @0x11 (注意 compatible 是 es8389 不是 es8390) */
&i2c4 {
	/* i2c4 使能与 pinctrl 见 hdmi.md; 此处补 codec 节点 */
	es8390: es8390@11 {
		compatible = "everest,es8389";
		reg = <0x11>;
		#sound-dai-cells = <0>;
		/* spk-ctl-gpio = <&gpio K3_GPIO(100) GPIO_ACTIVE_HIGH>;
		 * 参考板注释掉 (功放常开); 自研板按功放使能脚补 */
		clocks = <&syscon_mpmu CLK_MPMU_I2S1_SYSCLK>;
		clock-names = "mclk";
		status = "okay";
	};
};

/* I2S 控制器 */
&i2s1 {
	pinctrl-names = "default";
	pinctrl-0 = <&sspa1_0_cfg>;        /* 基座组: pad15-19 func2 */
	status = "okay";
};

/* 声卡: 基座 sound_card1 是空壳, dai-link 全由板级填 */
&sound_card1 {
	status = "okay";
	simple-audio-card,name = "snd-es8390";
	simple-audio-card,mclk-fs = <256>;
	simple-audio-card,dai-link@0 {
		format = "i2s";
		frame-master = <&link1_cpu>;
		bitclock-master = <&link1_cpu>;

		link1_cpu: cpu {
			sound-dai = <&i2s1>;
		};

		link1_codec: codec {
			sound-dai = <&es8390>;
		};
	};
};

&pinctrl {
	sspa1-0-cfg {                      /* 覆写基座组电压域 */
		sspa1-0-pins {
			power-source = <1800>;
		};
	};
};
```

### 4.2 换路 I2S (i2s0/2-5)

　　写法同构: pinctrl 换对应 sspX 组 (k3-pinctrl.dtsi 有 sspa/rssp
多组), sound_card0 或自定义 card 节点填 dai-link — 注意 K3 还有
RCPU 域的 rsspa/ri2s (k3-rdomain.dtsi), 用它们 = 免 pinctrl (RCPU
侧专用) 但依赖 rdomain 基座。

### 4.3 属性速查与陷阱

| 属性 | 说明 |
|---|---|
| compatible = "everest,es8389" | es8390 芯片的驱动 compatible (1.2 陷阱) |
| clocks/mclk | codec 主钟; 与 mclk-fs 配套 |
| mclk-fs = <256> | 采样率倍数, codec 规格定 (256/512 常见) |
| format = "i2s" | 标准菲利普 I2S; 对齐 codec 寄存器格式 |
| frame/bitclock-master = cpu | SoC 供时钟; codec 为主才反转 |
| spk-ctl-gpio | 功放使能 (参考板注释掉); 驱动存在该属性 |

陷阱清单:

- **compatible 写成 es8390**: 无驱动匹配 (驱动只认 everest,es8389),
  codec 不 probe, 声卡卡在 "codec dai 未注册"。
- **sound_card1 忘填 dai-link**: 基座空壳只有 compatible, 不填
  simple-audio-card probe 失败或注册出空卡。
- mclk-fs 与 codec 实配不符: 有声但失真/无声, 量 BCLK 换算确认。
- 功放使能脚没控: 硬件功放默认关时"链路全通就是没声", 量功放
  EN 脚。
- ES8389 未编 (imply 未生效): aplay -l 有卡但 playback 报
  -EPIPE/无声, dmesg 无 codec probe 行 — 补 CONFIG 显式 =y。

## 5. 验证测试

```bash
# 1. 声卡与链路
aplay -l                            # card snd-es8390
dmesg | grep -iE "es8389|es8390|sspa|i2s1" | head

# 2. 播放
speaker-test -D plughw:0 -c 2 -t sine       # 扬声器出正弦音
aplay /usr/share/sounds/alsa/Front_Center.wav

# 3. 录音 (接了 SDIN 才有效)
arecord -D plughw:0 -f S16_LE -r 48000 -d 3 /tmp/rec.wav
aplay /tmp/rec.wav

# 4. 混音器
amixer -c 0 contents                # codec 控件 (音量/通路)
tinymix                             # 无 alsa-lib 时用 tiny 工具

# 5. 排查顺序
#    a) 无声卡设备        -> sound_card1 dai-link 填了? ES8389 编了?
#    b) 卡在但无声        -> mclk/BCLK 波形, 功放 EN 脚
#    c) 失真              -> mclk-fs/format 与 codec 实配对齐
#    d) codec 无 probe    -> compatible 必须 everest,es8389 (1.2 节)
```
