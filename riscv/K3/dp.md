# DP

　　K3 平台 DP 输出适配笔记: dpu1_crtc0 (saturn DPU) → dp1 (inno-dp1) 的
直出与 LT2404 桥接两种方式, 含 DP 音频链 (RCPU 域)。参考板: aibox-k3
(FF_DP1, 带桥接) 为唯一实际启用 DP1 的板子; AIBOX-PRO 的 FF_DP1 只有注释
掉的供电段 (未实装)。

## 1. 原理

### 1.1 显示链路结构 (k3-dp1.dtsi 基座, 77 行全量)

　　K3 的显示控制器**不在 k3.dtsi**, 而在按接口拆分的 dtsi 里 (dp0 →
k3-dp0.dtsi, dp1 → k3-dp1.dtsi, edp0 → k3-edp0.dtsi), 板级按需 include。
k3-dp1.dtsi 三个节点:

```c
display-subsystem-dp1 {                    /* 显示子系统入口 */
	compatible = "spacemit,saturn-edp";
	reg = <0 0xc0440000 0 0x54000>;
	hw_ver = <2>;
	ports = <&dpu1_crtc0>;
};

dpu1_crtc0: dpu1_crtc0 {                   /* DPU (CRTC) */
	compatible = "spacemit,dpu-saturn";
	interrupts = <139 ...>, <138 ...>;     /* ONLINE/OFFLINE_IRQ */
	/* 5 时钟: pxclk/mclk/aclk/escclk/dscclk, 5 复位, 全在 APMU DSI4LN2 组 */
	power-domains = <&power K3_PMU_LCD1_PWR_DOMAIN>;
	pipeline-id = <1>;
	is_edp = <1>;                          /* 走 edp 协议层标志 */
	dpu-id = <1>;
	spacemit-dpu-min-mclk = <40960000>;
	port -> dp1_in;                        /* CRTC → 编码器 */
};

dp1: dp1@cac88000 {                        /* DP 编码器 */
	compatible = "spacemit,inno-dp1";
	interrupts = <140 ...>;
	dp-id = <1>;
	#sound-dai-cells = <0>;                /* 同时是 DP 音频 DAI! */
	port -> dpu1_crtc0_out0;
};
```

　　驱动栈: `drivers/gpu/drm/spacemit/` (CONFIG_DRM_SPACEMIT=y, saturn
DPU) + inno-dp (CONFIG_SPACEMIT_INNO_DP=y) — k3_defconfig 已齐。

### 1.2 DP 音频链 (走 RCPU 域)

　　DP 带内音频 (DP sound) 不走普通 I2S, 走 **RCPU 域**的音频通路
(k3-rdomain.dtsi 基座 — 这就是基座 include 四件套里它存在的原因):

```
adma3 (RCPU DMA, 0xC0883C00) → ri2s3 (RCPU I2S, 0xc0883D00)
     → sound_card_dp1 (simple-audio-card) → dp1 (DP DAI)
```

　　基座 sound_card_dp1 已写好 format=left_j、mclk-fs=512、cpu=ri2s3, 板级
只需补 codec 端 (sound-dai = <&dp1>) 并使能。

### 1.3 帧缓冲预留内存

　　DPU 需要连续帧缓冲, k3.dtsi 基座已预留 `dpu_resv1: dpu_reserved1@
101d80000` (resmem 段), 板级通过 `&dpu1_crtc0 { memory-region = <&dpu_resv1>; }`
引用 — 不用自己划内存。

## 2. 硬件连接

| 信号 | 来源 | 说明 |
|---|---|---|
| DP 差分对 (MAIN_LINK 2/4 lane) | dp1 (0xcac88000 对应模拟 pad) | 专用 pad, 不进 pinctrl |
| AUX+ / AUX- | dp1 | 专用 pad |
| HPD (热插拔检测) | 6 组 pad 可选 (下表), 必配否则不识别插拔 | 按走线引脚选组 |
| DP 供电 | 板级 (GPIO85, aibox-k3 用于 lt2404 power) | 高有效 |

　　dp1 hpd 有 6 组基座组 (k3-pinctrl.dtsi), 按你板 HPD 走线选其一:

| 组名 | pad/func | 采用板 |
|---|---|---|
| dp1_0_cfg | pad10 func6 | - |
| dp1_1_cfg | pad24 func6 | deepcomputing / k3-pico |
| dp1_2_cfg | pad69 func4 | - |
| dp1_3_cfg | pad72 func4 | aibox-k3 / AIBOX-PRO |
| **dp1_4_cfg** | **pad98 func5, 3.3V 域** | itx-k3l |
| dp1_5_cfg | pad125 func4 | - |

　　aibox-k3 的 DP 经 **LT2404 桥接芯片** (Lontium, I2C3 地址 0x29):

| 信号 | GPIO | 说明 |
|---|---|---|
| lt2404 power-gpios | GPIO85 | 高有效, 1.8V 域 (与 aibox-pro 注释掉的 vcc_dp_pwr_en 同脚) |
| lt2404 reset-gpios | GPIO74 | 高有效 (复位释放) |

接线核对要点:

- HPD 脚 pad72 func4 不配 → 插拔显示器无反应 (dp1_3_cfg 基座组, 一行引用
  即可)。
- 直出方式 (不经桥): DP 座差分对/aux 直连 SoC 模拟 pad; 桥接方式: 经
  LT2404 转 LVDS/其他接口, I2C 控制通道要通 (i2c3 使能)。
- DP 口热插拔时 K3_PMU_LCD1_PWR_DOMAIN 电源域自动上下电, 无需用户态参与。

## 3. 内核配置

```
# k3_defconfig 已有:
CONFIG_DRM=y
CONFIG_DRM_SPACEMIT=y              # saturn DPU + 显示框架
CONFIG_SPACEMIT_INNO_DP=y          # inno-dp1 DP 编码器驱动
CONFIG_DRM_SPACEMIT_BACKLIGHT=y
CONFIG_SOUND=y / CONFIG_SND_SOC=y  # DP 音频
# LT2404 桥: drivers/video/LT2404/, drivers/video/Makefile 里 obj-y 恒编,
# 不占 CONFIG 项 (厂商树外路径, 不在 drm/bridge 标准位)
```

## 4. 设备树配置

　　基座 include 四件套 (k3.dtsi 等) 之外, **DP1 需要 include
"k3-dp1.dtsi"** (dpu/dp 节点在其中), DP 音频需要 include "k3-rdomain.dtsi"
(基座四件套已含)。

### 4.1 方式一: DP 直出 (最小使能)

```dts
/* dts 头部需含: #include "k3-dp1.dtsi" (基座四件套照常) */

&dp1 {
	pinctrl-names = "default";
	pinctrl-0 = <&dp1_3_cfg>;      /* aibox-k3 选择: pad72 func4; 6 组对照见 2 节 */
	status = "okay";
};

&dpu1_crtc0 {
	memory-region = <&dpu_resv1>;  /* 帧缓冲 (基座已预留) */
	status = "okay";
};

/* DP 音频 (可选): 基座 sound_card_dp1 已写 cpu=ri2s3/format/mclk-fs */
&adma3 { status = "okay"; };
&ri2s3 { status = "okay"; };

&sound_card_dp1 {
	status = "okay";
	simple-audio-card,name = "snd-dp1";
	simple-audio-card,dai-link@0 {
		format = "left_j";
		frame-master = <&dp1_link_cpu>;
		bitclock-master = <&dp1_link_cpu>;
		dp1_link_codec: codec {
			playback-only;
			sound-dai = <&dp1>;    /* 板级补的只有 codec 端 */
		};
	};
};
```

### 4.2 方式二: 经 LT2404 桥接 (aibox-k3)

　　参考板: aibox-k3 (FF_DP1 分支)。DP1 输出先接 LT2404 (转你需要的接口),
I2C3 作控制通道:

```dts
&i2c3 {
	pinctrl-names = "default";
	pinctrl-0 = <&i2c3_2_cfg>;     /* 基座组: pad82/83 func6 */
	i2c-scl-rising-time-ns = <475>;
	i2c-scl-falling-time-ns = <26>;
	status = "okay";

	lt2404: lt2404@29 {
		compatible = "lontium,lt2404";
		reg = <0x29>;
		power-gpios = <&gpio K3_GPIO(85) GPIO_ACTIVE_HIGH>;
		reset-gpios = <&gpio K3_GPIO(74) GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
};

&dp1 {
	pinctrl-names = "default";
	pinctrl-0 = <&dp1_4_cfg>;      /* itx 选择: pad98 func5, 3.3V 域; 对照见 2 节 */
	status = "okay";
};

&dpu1_crtc0 {
	memory-region = <&dpu_resv1>;
	status = "okay";
};

&adma3 { status = "okay"; };
&ri2s3 { status = "okay"; };

&sound_card_dp1 {
	status = "okay";
	simple-audio-card,name = "snd-dp1";
	simple-audio-card,mclk-fs = <512>;
	simple-audio-card,dai-link@0 {
		format = "left_j";
		frame-master = <&dp1_link_cpu>;
		bitclock-master = <&dp1_link_cpu>;
		dp1_link_codec: codec {
			playback-only;
			sound-dai = <&dp1>;
		};
	};
};

&pinctrl {
	i2c3-2-cfg {
		i2c3-0-pins {
			i2c-scl-rising-time-ns = <475>;   /* 桥芯片时序要求,
			                                     直接改基座组的子节点 */
			i2c-scl-falling-time-ns = <26>;
		};
	};
};
```

### 4.3 属性速查与陷阱

| 属性/节点 | 说明 |
|---|---|
| is_edp = <1> | dpu1_crtc0 基座自带; DP1 硬件管线与 eDP 共用协议层 |
| dp-id / pipeline-id | 1; dp0 侧对应 0 (k3-dp0.dtsi), 别混用 |
| memory-region | dpu_resv1 基座已预留, 引用即可 |
| i2c-scl-rising/falling-time | LT2404 的 I2C 时序要求, 改在 cfg 子节点上 |
| #sound-dai-cells = <0> | dp1 兼音频 DAI; 不用 DP 音频可不使能音频链 |

陷阱清单:

- **忘记 include "k3-dp1.dtsi"**: dpu1_crtc0/dp1 节点不存在, &dp1 引用
  编译报错 — K3 显示节点不在 k3.dtsi, 这与 RK3588 (vop 在 soc dtsi) 不同。
- HPD 不配 (dp1_3_cfg): 显示器插上无任何反应, 看似"DP 不工作"。
- LT2404 驱动路径特殊 (drivers/video/LT2404, obj-y 恒编): 排查别去
  drm/bridge 找; 桥不通先看 I2C (i2cdetect 0x29) 与上电时序。
- sound_card_dp1 的 codec 端 sound-dai 忘写 → 声卡注册失败 (卡名出现但
  无 pcm 设备)。
- AIBOX-PRO 的 FF_DP1 是**注释掉**的: 别把它当参考, aibox-k3 才是实装板。

## 5. 验证测试

```bash
# 1. DRM 设备与连接器
ls /sys/class/drm/                      # card0-DRM-1 (DP1) 等连接器
cat /sys/class/drm/card0-DRM-1/status   # connected/disconnected 随插拔变化

# 2. 模式与点亮
modetest -M spacemit -c                 # 连接器列表
modetest -M spacemit -c <conn_id> -v    # 支持的模式列表
#  桌面环境直接看显示器点亮; 无桌面用 modetest 打测试图:
modetest -M spacemit -s <conn_id>:1920x1080@60

# 3. DP 音频
aplay -l                                # 应有 snd-dp1 卡
speaker-test -D plughw:1 -c 2 -t sine   # 显示器出正弦音 (卡号按实际)

# 4. 热插拔
#   插拔 DP 线, dmesg -w 应见 hpd/连接状态变化日志

# 5. 排查顺序
#    a) 连接器不存在           -> include k3-dp1.dtsi? DRM_SPACEMIT/INNO_DP?
#    b) status 恒 unknown      -> HPD 组 (6 选 1, 2 节表) func 是否生效
#    c) 点亮但花屏             -> dpu_resv1 引用/分辨率带宽
#    d) 桥接无输出             -> i2cdetect -y 3 (0x29) / GPIO85/74 时序
```
