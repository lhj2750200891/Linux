# HDMI

　　K3 平台 HDMI 输出适配笔记: K3 **没有原生 HDMI 发送器**, HDMI 口 =
DP0 通路 (dpu0_crtc0 → dp0) 经 **LT2404 桥接芯片** (Lontium, DP→HDMI)
转出, itx-k3l 的 `FF_HDMI0` (注释原文 "DP0 TO HDMI0") 即此方案。含 DP0
音频链 (RCPU 域 adma2/ri2s2) 与 HDMI0/DSI0 二选一宏。

## 1. 原理

### 1.1 显示链结构 (k3-dp0.dtsi 基座, 78 行)

```
display-subsystem-dp0 ("spacemit,saturn-hee", 0xc0340000)
   └─ ports = <&dpu0_crtc0>
dpu0_crtc0 ("spacemit,dpu-saturn", DPU0, LCD0 电源域, irq90/89)
   │  pipeline-id=1, is_edp=1, dpu-id=0, 6 时钟/5 复位
   └─ dpu0_crtc0_out0 ──> dp0_in
dp0 ("spacemit,inno-dp0", 0xcac84000, irq132, dp-id=0)
   │  #sound-dai-cells = <0>          ← 兼音频 DAI
   └─ DP MAIN LINK + AUX → LT2404 (@i2c4 0x29) → HDMI 座
```

　　节点结构与 dp1 (dp.md) 同构, 差异: DPU 是 **dpu0** (LCD0 域)、编码器
"inno-dp0" @0xcac84000。基座两节点 status 均 disabled, 板级使能。
**必须 include "k3-dp0.dtsi"** — K3 显示节点不在 k3.dtsi。

### 1.2 DP0 与 eDP0 是同一个物理通路

　　k3-dp0.dtsi 与 k3-edp0.dtsi (edp.md) 定义的是**同一套 DPU0 实例**:
subsystem 同 compatible ("spacemit,saturn-hee") 同 reg (0xc0340000)、
dp0 与 edp0 编码器同寄存器块 (0xcac84000), 仅 compatible 差一字
("inno-dp0" vs "inno-edp0")。**两个 dtsi 二选一 include**, 同时 include
= 节点重复定义冲突。板子 DP0 座 (转 HDMI) 与 eDP 屏共用这条通路, 硬件
上也不能同时用。

### 1.3 LT2404 桥 (驱动位置特殊)

　　`drivers/video/LT2404/` (LontiumDrv.c, compatible "lontium,lt2404",
of_match L260) — **厂商树外路径, obj-y 恒编, 不占 CONFIG 项**, 不在
drm/bridge 标准位 (排查别去那里找)。itx 的 HDMI0 版节点极简 (只有
compatible+reg): 电源不挂节点 gpios, 由独立 regulator (hdmi_3v3,
GPIO107) 常供电; 对比 aibox-k3 的 DP1 版 lt2404 节点自带
power/reset-gpios (dp.md 4.2) — 两种接法都合法。

### 1.4 DP0 音频链 (HDMI 出声)

　　与 DP1 对称, 走 RCPU 域 (k3-rdomain.dtsi 基座已定义, status
disabled):

```
adma2 (0xC0883800, 2ch) → ri2s2 (0xc0883900) → sound_card_dp0 → dp0
```

　　基座 sound_card_dp0 已写 format=left_j、mclk-fs=512、cpu=ri2s2, 板级
补 codec 端 (sound-dai = <&dp0>) 并使能, 卡名 "snd-hdmi0"。

## 2. 硬件连接

| 信号 | 来源 | 说明 |
|---|---|---|
| DP 差分对 (MAIN LINK) + AUX | dp0 (0xcac84000 对应模拟 pad) | 专用 pad, 不进 pinctrl |
| DP0 HPD | **pad 97 func5** (dp0_2_cfg) | itx HDMI0 用这组, 3.3V 域 |
| DP0 HPD (备选) | pad 23 func6 (dp0_1_cfg) | 另一组 hpd 脚, 按走线选 |
| LT2404 I2C 控制 | i2c4: pad111 scl / pad112 sda, func4 (i2c4_3_cfg) | 地址 0x29 |
| LT2404 供电 3V3 | GPIO107 (hdmi_3v3, 高有效) | 3.3V 域, vin=vcc5v0_sys |
| HDMI 差分对 | LT2404 输出侧 | 桥芯片到 HDMI 座, 板内布线 |

接线核对要点:

- HPD 两组 pad 二选一: itx 用 pad97 (func5, 3.3V 域), deepcomputing 的
  eDP 用 pad23 (func6) — 按你板 HPD 走线选组, 用 pinmux-pins debugfs
  核实。
- i2c4 上已有三设备可共存: pca9555_2 @0x20、lt2404 @0x29、(CSI1 方式的)
  IMX415 @0x37 — 地址不冲突; 用 CSI1 时 i2c4 必须使能且 pinctrl 组一致
  (都是 i2c4_3_cfg)。
- LT2404 无独立复位脚接线 (itx 方案): 上电时序靠 hdmi_3v3 的
  regulator-always-on; 若你的板 LT2404 有 reset 脚, 照 aibox-k3 写法
  (dp.md 4.2) 补 gpios。

## 3. 内核配置

```
# k3_defconfig 已有:
CONFIG_DRM_SPACEMIT=y              # saturn DPU + 显示框架
CONFIG_SPACEMIT_INNO_DP=y          # inno-dp0 编码器 (与 dp1/edp0 同驱动)
CONFIG_DRM_SPACEMIT_BACKLIGHT=y
CONFIG_SOUND=y / CONFIG_SND_SOC=y  # HDMI 音频
# LT2404 桥: drivers/video/LT2404/, obj-y 恒编, 无 CONFIG 项
```

## 4. 设备树配置

　　dts 头部需 `#include "k3-dp0.dtsi"` (dpu0_crtc0/dp0 在其中; 基座
四件套照常)。以下为 FF_HDMI0 分支的完整展开 (itx 板级宏 + k3-firefly-
itx-k3l.dtsi 五处 #ifdef 块合并)。

### 4.1 完整板级段 (itx FF_HDMI0 展开)

```dts
/* dts 头部需含: #include "k3-dp0.dtsi" (基座四件套照常) */

/ {
	/* LT2404/桥供电 3V3 (itx: GPIO107) */
	hdmi_3v3: hdmi-3v3 {
		compatible = "regulator-fixed";
		regulator-name = "hdmi_3v3";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		regulator-always-on;
		regulator-boot-on;
		enable-active-high;
		gpios = <&gpio K3_GPIO(107) GPIO_ACTIVE_HIGH>;
		pinctrl-0 = <&lt2404_pwr_cfg>;
		pinctrl-names = "default";
		vin-supply = <&vcc5v0_sys>;    /* 板级 5V 系统, 按你的电源树 */
		status = "okay";
	};
};

/* LT2404: i2c4 @0x29, itx 版极简节点 (电源由 hdmi_3v3 管) */
&i2c4 {
	pinctrl-names = "default";
	pinctrl-0 = <&i2c4_3_cfg>;         /* pad111 scl / pad112 sda, func4 */
	status = "okay";

	lt2404: lt2404@29 {
		compatible = "lontium,lt2404";
		reg = <0x29>;
		status = "okay";
	};
};

/* DP0 链 */
&dp0 {
	pinctrl-names = "default";
	pinctrl-0 = <&dp0_2_cfg>;          /* 基座组: pad97 func5, hpd, 3.3V 域 */
	status = "okay";
};

&dpu0_crtc0 {
	memory-region = <&dpu_resv0>;      /* DPU0 帧缓冲 (基座已预留) */
	status = "okay";
};

/* DP0 音频 (HDMI 出声) */
&adma2  { status = "okay"; };
&ri2s2  { status = "okay"; };

&sound_card_dp0 {
	status = "okay";
	simple-audio-card,name = "snd-hdmi0";
	simple-audio-card,mclk-fs = <512>;
	simple-audio-card,dai-link@0 {
		format = "left_j";
		frame-master = <&dp0_link_cpu>;
		bitclock-master = <&dp0_link_cpu>;
		dp0_link_codec: codec {
			playback-only;
			sound-dai = <&dp0>;    /* 板级补的只有 codec 端 */
		};
	};
};

&pinctrl {
	lt2404_pwr_cfg: lt2404-pwr-cfg {
		lt2404-pwr-pin {
			pinmux = <K3_PADCONF(107, 0)>;   /* hdmi 3v3 使能 */
			bias-disable;
			drive-strength = <25>;
			power-source = <3300>;
		};
	};
};
```

### 4.2 LT2404 带复位脚的变体 (参照 aibox-k3 DP1 写法)

　　你的板 LT2404 若有 power/reset 脚, 节点补两行 (GPIO 号按硬件):

```dts
	lt2404: lt2404@29 {
		compatible = "lontium,lt2404";
		reg = <0x29>;
		power-gpios = <&gpio K3_GPIO(85) GPIO_ACTIVE_HIGH>;  /* 按你板 */
		reset-gpios = <&gpio K3_GPIO(74) GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
```

### 4.3 属性速查与陷阱

| 属性/节点 | 说明 |
|---|---|
| dp-id = 0 | dp0 基座自带; dp1 侧是 1, 别混 |
| memory-region = <&dpu_resv0> | DPU0 用 resv0 (DP1 用 resv1), 别互换 |
| dp0_2_cfg / dp0_1_cfg | hpd 两组 pad (97 func5 / 23 func6), 二选一 |
| #sound-dai-cells = <0> | dp0 兼音频 DAI, sound_card_dp0 codec 端引用 |
| simple-audio-card,name = "snd-hdmi0" | 用户态看卡名; DP1 的叫 snd-dp1 |

陷阱清单:

- **include 冲突**: k3-dp0.dtsi 与 k3-edp0.dtsi 是同一 DPU0 的两份定义
  (1.2 节), 只能 include 其一; itx 用 `#ifdef FF_HDMI0 / FF_DSI0`
  宏切换 (HDMI0_OR_DSI0: 1=HDMI0, 0=DSI0), 自研板直接二选一即可。
- LT2404 驱动在 `drivers/video/LT2404/` (obj-y 恒编): 桥不通先
  `i2cdetect -y 4` 看 0x29 应答, 别怀疑 CONFIG。
- HPD 组选错 (pad97 vs pad23): 插拔无反应; debugfs pinmux-pins 核实
  func5/6 已生效。
- sound_card_dp0 的 codec 端 sound-dai 忘写 → 卡出现但无 pcm 设备。
- GPIO107 与 AIBOX-PRO 的 pcie3 WiFi clkreq (pad107) 同 pad — 引脚冲突
  见 README 冲突速查表; 用 WiFi+ASM1182e 方案的板别把 107 给 HDMI。
- pad111/112 (i2c4) 若你板作了别的复用 (查 README 冲突表), lt2404 的
  I2C 控制通道换别的 i2cN 也可以, compatible 不变。

## 5. 验证测试

```bash
# 1. DRM 连接器
ls /sys/class/drm/                       # card0-DRM-? (DP0/HDMI0)
cat /sys/class/drm/card0-DRM-?/status    # 插 HDMI 线应 connected

# 2. 桥芯片应答
i2cdetect -y 4                           # 0x29 应有应答 (LT2404)

# 3. 点亮
modetest -M spacemit -c                  # 连接器列表
modetest -M spacemit -s <conn_id>:1920x1080@60   # 打测试图

# 4. HDMI 音频
aplay -l                                 # 应有 snd-hdmi0 卡
speaker-test -D plughw:1 -c 2 -t sine    # 电视出正弦音 (卡号按实际)

# 5. 热插拔
#   插拔 HDMI 线, dmesg -w 应见 hpd/连接状态变化

# 6. 排查顺序
#    a) 连接器不存在           -> include k3-dp0.dtsi? 与 edp0 二选一?
#    b) status 恒 unknown      -> HPD pad97 func5 (dp0_2_cfg) 生效?
#    c) 桥无输出               -> i2cdetect 0x29 / hdmi_3v3 电平 (GPIO107)
#    d) 点亮但无声             -> adma2/ri2s2 使能? codec 端 sound-dai?
#    e) dmesg | grep -iE "inno|lt2404|saturn"   -> 各级 probe 日志
```
