# 声卡

　　ES8388/ES8390 声卡 (multicodecs-card) 与 HDMI/eDP/DP/BT SCO 数字音源。参考板 AIO-3588SG / roc-rk3588s-pc。

## 1. RK3588 音频架构概述

```
应用 (aplay/arecord)
  ====> ASoC machine 卡 (rockchip,multicodecs-card)
          ├── rockchip,cpu   = i2s0_8ch (SOC I2S 控制器)
          └── rockchip,codec = ES8388/ES8390 (I2C 配置 + I2S 数据)
```

- I2S0_8ch: SOC 侧音频数据通路 (fdd00000, 8 通道), 引脚在 GPIO1 组
- codec 芯片: I2C 挂控制 (写寄存器), I2S 走数据, MCLK 由 SOC 提供
- machine 驱动: rockchip_multicodecs (SND_SOC_ROCKCHIP_MULTICODECS=y,
  defconfig 已开), 一张卡聚合 codec
- 驱动映射: **ES8388 用 es8323.c 驱动 (compatible "everest,es8323"),
  ES8390 用 es8389.c 驱动 (compatible "everest,es8389")**

　　内核配置 (defconfig 已开):

```
CONFIG_SND=y
CONFIG_SND_SOC=y
CONFIG_SND_SOC_ROCKCHIP=y
CONFIG_SND_SOC_ROCKCHIP_MULTICODECS=y     # machine 卡
CONFIG_SND_SOC_ES8323=y                    # ES8388 codec 驱动
CONFIG_SND_SOC_ES8389=y                    # ES8390 codec 驱动 (firefly-linux.config)
CONFIG_SND_SOC_BT_SCO=m                    # BT SCO (见第 7 节)
```

## 2. 板间布局速查

| 板 | 芯片 | I2C 总线 | codec 地址 | hp-det | spk/hp-con |
|---|---|---|---|---|---|
| AIO-3588SG | ES8388 | i2c7 (m0) | 0x11 | saradc CH4 | spk GPIO3_B7 |
| itx-3588j | ES8388 | i2c3 | 0x11 | gpio1_C4 低 | spk GPIO3_B2, hp GPIO4_B0 |
| aio-3588q | ES8388 | i2c3 (m0) | 0x11 | saradc | - |
| aio-3588jd4/sjd4 | ES8388 | i2c6 / i2c7 | 0x11 | gpio2_C3 高 (jd4) | hp PCA9555 IO1_3 (jd4) |
| roc-rk3588s-pc | ES8388 或 ES8390 | i2c3 (m0) | 0x11 | gpio1_A6 (es8390) | hp GPIO1_A4 (es8390) |

- MCLK 一律走 mclkout_i2s0 (i2s0_mclk 引脚 GPIO1_C2), 12.288MHz
- I2S 数据引脚一律 i2s0_sdi0/sdo0 (录音 GPIO1_D4 / 放音 GPIO1_C7)

## 3. 方式一: ES8388

　　参考板: AIO-3588SG (完整可复制)。

### 3.1 硬件连接

```
ES8388:
  I2C SCL/SDA ====> I2C7_M0: SCL GPIO1_D0 / SDA GPIO1_D1 (地址 0x11)
  MCLK         ====> i2s0_mclk = GPIO1_C2 (12.288MHz, mclkout_i2s0)
  BCLK/LRCK    ====> i2s0_sclk GPIO1_C3 / i2s0_lrck GPIO1_C5
  录音 SD      ====> i2s0_sdi0 = GPIO1_D4 (codec DACOUT -> SOC)
  放音 SD      ====> i2s0_sdo0 = GPIO1_C7 (SOC -> codec DACIN)
  耳机检测     ====> SARADC CH4 (分压检测插入, 无 GPIO)
  喇叭功放使能 ====> GPIO3_B7 (spk-con, 高有效)
  输出: LOUT2/ROUT2 -> 喇叭功放; LOUT1/ROUT1 -> 耳机 (SG 板注释掉)
  输入: LINPUT1/RINPUT1 麦克风 (SG 板注释掉)
```

### 3.2 设备树配置 (三段, 全部直接可用)

**第一段: 声卡节点 (放 / 根节点下)**

```
/ {
	es8388_sound: es8388-sound {
		status = "okay";
		compatible = "rockchip,multicodecs-card";
		rockchip,card-name = "rockchip-es8388";
		//hp-det-gpio = <&gpio3 RK_PC1 GPIO_ACTIVE_LOW>;   // GPIO 检测时用
		io-channels = <&saradc 4>;                // SARADC 通道 4 检测耳机
		io-channel-names = "adc-detect";
		keyup-threshold-microvolt = <1800000>;    // 高于 1.8V 视为拔出
		poll-interval = <100>;                    // 100ms 轮询
		spk-con-gpio = <&gpio3 RK_PB7 GPIO_ACTIVE_HIGH>;  // 喇叭功放使能
		//hp-con-gpio = <&gpio3 RK_PB2 GPIO_ACTIVE_HIGH>; // 耳机功放使能(有则加)
		rockchip,format = "i2s";
		rockchip,mclk-fs = <256>;                 // MCLK = 256 * fs
		rockchip,cpu = <&i2s0_8ch>;
		rockchip,codec = <&es8388>;
		rockchip,audio-routing =
			"Speaker", "LOUT2",              // 喇叭接 LOUT2/ROUT2
			"Speaker", "ROUT2",
			"Speaker", "Speaker Power",
			"Speaker", "Speaker Power";
			// 耳机启用时加:
			//"Headphone", "LOUT1",
			//"Headphone", "ROUT1",
			//"Headphone", "Headphone Power",
			//"Headphone", "Headphone Power",
			// 麦克风启用时加:
			//"LINPUT1", "Main Mic",
			//"RINPUT1", "Headset Mic",
		//pinctrl-names = "default";
		//pinctrl-0 = <&hp_det>;                 // GPIO 检测时配 pinctrl
		play-pause-key {                          // 耳机按键 (ADC 分压识别)
			label = "playpause";
			linux,code = <KEY_PLAYPAUSE>;
			press-threshold-microvolt = <2000>;
		};
	};
};
```

　　需要 #include <dt-bindings/input/input.h> (KEY_PLAYPAUSE, 一般板级 dts 已含)。

**第二段: codec 节点 (挂在 I2C 下)**

```
&i2c7 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c7m0_xfer>;

	es8388: es8388@11 {
		status = "okay";
		#sound-dai-cells = <0>;
		compatible = "everest,es8388", "everest,es8323";   // es8323 驱动
		reg = <0x11>;
		clocks = <&mclkout_i2s0>;
		clock-names = "mclk";
		assigned-clocks = <&mclkout_i2s0>;
		assigned-clock-rates = <12288000>;          // 12.288MHz
		pinctrl-names = "default";
		pinctrl-0 = <&i2s0_mclk>;                   // MCLK 引脚复用
	};
};
```

**第三段: I2S 控制器使能**

```
&i2s0_8ch {
	status = "okay";
	pinctrl-0 = <&i2s0_sdi0 &i2s0_sdo0>;   // 数据脚; BCLK/LRCK 走默认
};
```

　　itx/jd4 版本在这段额外加 i2s0_lrck/i2s0_sclk 到 pinctrl-0 (引脚相同,
写上更保险)。hp-det 用 GPIO 时再加 pinctrl 段:

```
&pinctrl {
	headphone {
		hp_det: hp-det {
			rockchip,pins = <2 RK_PC3 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};
```

### 3.3 属性速查 (照板改)

| 属性 | 说明 |
|---|---|
| hp-det-gpio | 耳机插拔 GPIO 检测 (itx: gpio1_C4 低有效) |
| io-channels + adc-detect | 耳机检测走 SARADC (SG CH4 / itx CH3) |
| spk-con-gpio | 喇叭功放使能 |
| hp-con-gpio | 耳机功放使能 (es8390: gpio1_A4) |
| rockchip,pre/power-on-delay | 上下电延时 30/40ms (es8390/itx 用) |
| audio-routing | 输出通路: LOUT1/2=耳机/喇叭 (SG 反接; es8390 统一 HPOL/HPOR) |
| ff-separate-headphone-jack | Firefly 私有 (独立耳机口, itx 用, 6.12 驱动是否收敛? 如无效可去掉) |

## 4. 方式二: ES8390

　　参考板: roc-rk3588s-pc (完整可复制)。

### 4.1 硬件连接

```
ES8390:
  I2C SCL/SDA ====> I2C3_M0: SCL GPIO1_C1 / SDA GPIO1_C0 (地址 0x11)
  MCLK/BCLK/LRCK/SD ====> 同 ES8388 (i2s0 一组)
  耳机检测     ====> GPIO1_A6 (hp-det, 高有效)
  耳机功放使能 ====> GPIO1_A4 (hp-con, 高有效)
  输出: HPOL/HPOR 同时接耳机和喇叭功放
  输入: INPUT1 主麦克风, INPUT2 耳机麦克风
```

### 4.2 设备树配置

**第一段: 声卡节点**

```
/ {
	es8390_sound: es8390-sound {
		status = "okay";
		compatible = "rockchip,multicodecs-card";
		rockchip,card-name = "rockchip-es8390";
		hp-det-gpio = <&gpio1 RK_PA6 GPIO_ACTIVE_HIGH>;    // GPIO 检测
		hp-con-gpio = <&gpio1 RK_PA4 GPIO_ACTIVE_HIGH>;    // 耳机功放
		pinctrl-names = "default";
		pinctrl-0 = <&hp_det>;
		keyup-threshold-microvolt = <1800000>;
		poll-interval = <100>;
		rockchip,pre-power-on-delay-ms = <30>;
		rockchip,post-power-down-delay-ms = <40>;
		rockchip,format = "i2s";
		rockchip,mclk-fs = <256>;
		rockchip,cpu = <&i2s0_8ch>;
		rockchip,codec = <&es8390>;
		rockchip,audio-routing =
			"Headphone", "HPOL",
			"Headphone", "HPOR",
			"Speaker", "HPOL",
			"Speaker", "HPOR",
			"Headphone", "Headphone Power",
			"Headphone", "Headphone Power",
			"Speaker", "Speaker Power",
			"Speaker", "Speaker Power",
			"INPUT1", "Main Mic",
			"INPUT1", "Main Mic",
			"INPUT2", "Headset Mic",
			"INPUT2", "Headset Mic";
		play-pause-key {
			label = "playpause";
			linux,code = <KEY_PLAYPAUSE>;
			press-threshold-microvolt = <2000>;
		};
	};
};
```

**第二段: codec 节点 (含 PGA 配置, ES8390 特有)**

```
&i2c3 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c3m0_xfer>;

	es8390: es8390@11 {
		status = "okay";
		#sound-dai-cells = <0>;
		compatible = "everest,es8389";            // 注意: es8389 驱动!
		reg = <0x11>;
		clocks = <&mclkout_i2s0>;
		clock-names = "mclk";
		assigned-clocks = <&mclkout_i2s0>;
		assigned-clock-rates = <12288000>;
		pinctrl-names = "default";
		pinctrl-0 = <&i2s0_mclk>;

		/* 左通道 PGA (麦克风前级) */
		left,input-mode = "diff";            // se=单端, diff=差分
		left,input-source = "input1";        // input1/input2/both
		left,gain = <0x00>;                  // 0x00-0x0E 增益档

		/* 右通道 PGA */
		right,input-mode = "diff";
		right,input-source = "input1";
		right,gain = <0x00>;
	};
};
```

**第三段: I2S + pinctrl**

```
&i2s0_8ch {
	status = "okay";
	pinctrl-0 = <&i2s0_sdi0 &i2s0_sdo0>;
};

&pinctrl {
	headphone {
		hp_det: hp-det {
			rockchip,pins = <1 RK_PA6 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};
```

### 4.3 ES8388 与 ES8390 的差异对照

| 项 | ES8388 | ES8390 |
|---|---|---|
| compatible | "everest,es8388", "everest,es8323" | "everest,es8389" (单个) |
| 内核驱动 | es8323.c (SND_SOC_ES8323) | es8389.c (SND_SOC_ES8389) |
| 输出引脚命名 | LOUT1/ROUT1, LOUT2/ROUT2 | HPOL/HPOR (耳机喇叭共用) |
| PGA 配置 | 无 dts 属性 (寄存器默认) | left/right input-mode/input-source/gain |
| 典型 hp-det | SARADC 或 GPIO | GPIO (gpio1_A6) |
| 卡名 | rockchip-es8388 | rockchip-es8390 |

## 5. 数字音频: HDMI / eDP / DP / BT SCO 声卡

　　Firefly common dtsi 里数字声卡是几行式 (无外部 codec, 显示控制器就是 codec):

```
/* HDMI0/1: i2s5/i2s6_8ch 直连 hdmi 控制器 */
hdmi0_sound: hdmi0-sound {
	status = "okay";
	compatible = "rockchip,hdmi";
	rockchip,mclk-fs = <128>;
	rockchip,card-name = "rockchip-hdmi0";
	rockchip,cpu = <&i2s5_8ch>;
	rockchip,codec = <&hdmi0>;
	rockchip,jack-det;
};

/* eDP0: 同款结构, codec 指向 edp0 (默认 disabled) */
edp0_sound: edp0-sound {
	status = "disabled";
	compatible = "rockchip,hdmi";
	rockchip,mclk-fs = <128>;
	rockchip,card-name = "rockchip-edp0";
	rockchip,cpu = <&i2s5_8ch>;
	rockchip,codec = <&edp0 0>;
};

/* DP0 (含 Type-C DP altmode): spdif_tx2 直连 dp0 */
dp0_sound: dp0-sound {
	status = "okay";
	compatible = "rockchip,hdmi";
	rockchip,card-name = "rockchip-dp0";
	rockchip,mclk-fs = <512>;
	rockchip,cpu = <&spdif_tx2>;
	rockchip,codec = <&dp0 1>;
	rockchip,jack-det;
};
&spdif_tx2 { status = "okay"; };        // SPDIF 节点在 rk3588s.dtsi 已定义
```

　　BT SCO 语音 (SG 板, 搭配 AP6275P):

```
bt_sco: bt-sco {
	status = "okay";
	compatible = "delta,dfbmcs320";
	#sound-dai-cells = <1>;
};

bt_sound: bt-sound {
	status = "okay";
	compatible = "simple-audio-card";
	simple-audio-card,format = "dsp_a";
	simple-audio-card,bitclock-inversion = <0>;
	simple-audio-card,mclk-fs = <256>;
	simple-audio-card,name = "rockchip,bt";
	simple-audio-card,cpu {
		sound-dai = <&i2s1_8ch>;
	};
	simple-audio-card,codec {
		sound-dai = <&bt_sco 1>;
	};
};

&i2s1_8ch {
	status = "okay";
	pinctrl-0 = <&i2s1m0_lrck
		     &i2s1m0_sclk
		     &i2s1m0_sdi2
		     &i2s1m0_sdo3>;
	rockchip,bclk-fs = <32>;
};
```

　　以上 BT SCO 声卡配置已完整 (i2s1 引脚 sdi2/sdo3 为 SG 板接法)。
BT 模组本身的 UART/电源控制节点 (wireless_bluetooth + uart9) 属
wifi-bt 模块, 两者都配上 SCO 语音通路才通。

## 6. 验证测试

```
# 1. 声卡注册
cat /proc/asound/cards
# 应看到 ES8388: rockchip-es8388 ... / ES8390: rockchip-es8390 ...
dmesg | grep -i -E "es8388|es8390|asoc|sound"

# 2. codec I2C 通信 (probe 成功的间接证据)
dmesg | grep -i es8
# 报 i2c transfer error => 检查总线/地址; 无输出但卡在 => MCLK 没起

# 3. 播放 (喇叭)
speaker-test -D hw:rockchipes8388 -c 2 -F 32000 -f 48000  # 或按 aplay -l 的卡名
aplay -f cd /usr/share/sounds/test.wav
# 听到声音 => I2S+codec+功放全通

# 4. 录音 (麦克风)
arecord -D hw:rockchipes8388 -f cd -d 5 /tmp/test.wav
aplay /tmp/test.wav

# 5. 耳机检测
插拔耳机时 dmesg 应打印 jack 状态变化 (adc-detect 轮询型无内核日志,
用 amixer 看控件变化)

# 6. 音量
alsamixer
# 找到 Headphone/Speaker 等控件调音量 (无输出先查这里是否为 0/Mute)

# 7. MCLK 检查 (无声时)
示波器量 GPIO1_C2 应有 12.288MHz; 没有 => i2s0_mclk pinctrl 或
assigned-clock-rates 未生效

# 常见问题:
# 1. 卡没注册: multicodecs-card 三要素缺一 (cpu/codec/format),
#    或 codec probe 失败 (看 dmesg i2c)
# 2. codec probe 失败: I2C 地址错 / 总线没使能 / MCLK 没供 ---
#    ES 芯片必须 MCLK 在才有 I2C 响应
# 3. 有卡无声明: ES8390 的 compatible 必须是 "everest,es8389",
#    写成 es8390 没有驱动匹配
# 4. 有声音但杂音: mclk-fs 与 codec 支持率不符 (256/384),
#    或 audio-routing 接错 (LOUT1/2 与实际接线)
# 5. 耳机检测不工作: saradc 的 io-channels 通道号与硬件分压电路对不上
# 6. DP 无声: spdif_tx2 未使能 (DP audio 走 spdif, 不是 i2s)
```
