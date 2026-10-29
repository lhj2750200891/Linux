# eDP

　　K3 平台 eDP 屏适配笔记: dpu0_crtc0 (saturn DPU, LCD0 电源域) →
edp0 (inno-edp0) 内嵌屏链路, 含 PWM 背光与厂商 GPIO 属性。参考板:
k3-deepcomputing-fml13v05 (笔记本, eDP 屏实装) — Firefly 三块板均未用
eDP。

## 1. 原理

### 1.1 显示链 (k3-edp0.dtsi 基座)

　　与 DP1 (dp.md) 同构, 换成 LCD0 域的 DPU0 + edp0 编码器:

```c
display-subsystem-edp0 {                  /* compatible = "spacemit,saturn-hee" */
	reg = <0 0xc0340000 0 0x54000>;
	ports = <&dpu0_crtc0>;
};

dpu0_crtc0: dpu0_crtc0 {                  /* DPU0, compatible "spacemit,dpu-saturn" */
	/* 6 时钟 (比 DP1 多 hclk) + 5 复位, LCD0 域 */
	power-domains = <&power K3_PMU_LCD0_PWR_DOMAIN>;
	pipeline-id = <1>;
	is_edp = <1>;
	dpu-id = <0>;
	port -> edp0_in;
};

edp0: edp0@cac84000 {                     /* compatible "spacemit,inno-edp0" */
	interrupts = <132 ...>;
	edp-id = <0>;
	port -> dpu0_crtc0_out0;
};
```

　　驱动: 同在 `drivers/gpu/drm/spacemit/spacemit_inno_dp.c` (一个驱动管
DP/eDP 全家, CONFIG_SPACEMIT_INNO_DP=y 已编) + DRM_SPACEMIT (saturn DPU)。

### 1.2 eDP 屏的识别方式: 无 panel 节点

　　与 RK3588 惯例 (panel 节点 + panel-compatible) **不同**: K3 的 inno-edp
驱动通过 AUX 通道**自行探测 eDP 屏** (读 EDID), 设备树里**不需要** panel
子节点 — deepcomputing 整板无任何 "panel" 节点。换屏 = 换硬件, 软件只管
背光与供电。

### 1.3 厂商私有属性 (驱动已核实解析)

　　`spacemit_inno_dp.c` 在 eDP 场景读两个 **u32 全局 GPIO 号**属性:

| 属性 | 驱动行为 | 参考板值 |
|---|---|---|
| gpios-power | u32 = 全局 GPIO 号, 驱动内部 request/output 控屏供电 | 101 |
| gpios-enable | u32 = 全局 GPIO 号, 驱动内部控制屏 enable | 118 |

　　注意写法特殊: 不是标准 `xxx-gpios = <&gpio N flag>` 引用式, 是裸数字
(驱动 `of_property_read_u32`)。缺省时驱动打 dbg 日志继续 (属性可省,
屏供电由硬件常供的板子就不写)。

## 2. 硬件连接

　　参考板: deepcomputing-fml13v05 (13.5" eDP 屏)。

| 信号 | 来源 | 说明 |
|---|---|---|
| eDP 差分对 + AUX | edp0 (0xcac84000 对应模拟 pad) | 专用 pad, 不进 pinctrl |
| eDP HPD | pad 57 func4 (**edp0_1_cfg** 基座组) | 按你板子走线选组 |
| 屏供电 3.3V | gpios-power = 101 (GPIO101) | 驱动控制 |
| 屏 enable | gpios-enable = 118 (GPIO118) | 驱动控制 |
| 背光 PWM | **pad 106 func6** (pwm18, pwm18_2_cfg) | 20kHz, 经背光驱动板 |
| 背光使能 | 背光板使能脚 (随屏) | 硬件接 pwm 板 |

接线核对要点:

- HPD 组的选择: 基座有 **edp0_1_cfg (pad57 func4, eDP0 专用)** 与
  dp0_1_cfg (pad23 func6, DP0 的 hpd 组) 两组; deepcomputing 实际引用的是
  **dp0_1_cfg** — 说明它板子的 HPD 走在 pad23。自研板按自己走线选组,
  别把 deepcomputing 的选择当通用答案。
- GPIO101 与 aibox-k3 pcf8563 的 INT 脚同号 (func0 vs 驱动控制)、GPIO118
  与 aibox-pro 的 usb_sel 同号、pad106 与 ASM1182e 电源同 pad — 复用冲
  突自查 (README 冲突表)。
- 背光 20kHz (period 20000ns): 人耳不可闻频段, 屏背光板规格要支持。

## 3. 内核配置

```
# k3_defconfig 已有:
CONFIG_DRM_SPACEMIT=y
CONFIG_SPACEMIT_INNO_DP=y         # inno-edp0 同驱动
CONFIG_DRM_SPACEMIT_BACKLIGHT=y
CONFIG_BACKLIGHT_PWM=y            # pwm-backlight (背光)
CONFIG_PWM_SPACEMIT?              # pwm 子系统随 SoC 默认
```

## 4. 设备树配置

　　dts 头部需 `#include "k3-edp0.dtsi"` (dpu0_crtc0/edp0 在其中; 基座
四件套照常)。参考板完整写法:

```dts
/* 背光: pwm-backlight + pwm18 */
&backlight {                          /* 基座? 否 — 本板自定义节点 */
	status = "okay";
};

/* 写法: / 节点下定义 */
/ {
	backlight: backlight {
		compatible = "pwm-backlight";
		pwms = <&pwm18 0 20000 0>;    /* pwm18, 20kHz */
		brightness-levels = <
			  0  20  20  20  21  21  21  21
			 22  22  22  22  23  23  23  24
			 24  24  25  25  25  26  26  27
			 27  28  28  29  29  30  30  31
			 31  32  32  33  33  34  34  35
			 36  36  37  38  38  39  40  41
			 41  42  43  44  45  45  46  47
			 /* ... 按屏规格的伽马表, 参考 deepcomputing 全表 ... */
		>;
		default-brightness-level = <20>;
		enable-gpios = <&gpio K3_GPIO(?) GPIO_ACTIVE_HIGH>;  /* 背光板使能, 按你硬件 */
		power-supply = <&vcc3v3_sys>;
	};
};

&pwm18 {
	pinctrl-names = "default";
	pinctrl-0 = <&pwm18_2_cfg>;   /* 基座组: pad106 func6 */
	status = "okay";
};

/* eDP 链 */
&dpu0_crtc0 {
	memory-region = <&dpu_resv0>;  /* 基座已预留的 DPU0 帧缓冲 */
	status = "okay";
};

&edp0 {
	pinctrl-names = "default";
	pinctrl-0 = <&dp0_1_cfg>;      /* deepcomputing 用 dp0 组 (pad23 func6);
	                                  eDP 专用组是 edp0_1_cfg (pad57 func4),
	                                  按你板 HPD 走线选 */
	backlight = <&backlight>;      /* 背光设备 phandle, 驱动联动亮灭 */
	gpios-power = <101>;           /* 厂商属性: 裸全局 GPIO 号 (u32) */
	gpios-enable = <118>;
	status = "okay";
};
```

### 4.1 属性速查与陷阱

| 属性 | 说明 |
|---|---|
| backlight = <&phandle> | 标准 DRM 背光联动属性 (inno-edp 读) |
| gpios-power / gpios-enable | 厂商属性, **裸数字全局 GPIO 号**, 驱动 of_property_read_u32 |
| memory-region = <&dpu_resv0> | DPU0 用 resv0 (DP1 用 resv1), 别互换 |
| brightness-levels | 伽马表, 按屏规格抄 deepcomputing 全表或自定 |

陷阱清单:

- **无 panel 节点是正常的**: 屏由 AUX/EDID 自检; 屏不亮先查供电/背光, 不
  要找 panel compatible。
- HPD 组选错 (pad57 vs pad23): 插着屏不亮或热插拔无反应; 用
  pinmux-pins debugfs 核实。
- gpios-power 写成引用式 `<&gpio 101 0>` 会解析失败 (驱动只收 u32)。
- 背光 pwm 频率与屏背光板不匹配 → 啸叫/不亮; 20kHz 起步。
- dpu_resv0/resv1 与 restricted-dma-pool (pcie WiFi) 同在 resmem, 调整
  内存布局时整段一起规划。

## 5. 验证测试

```bash
# 1. DRM 连接器 (eDP 屏应恒 connected — 内嵌屏)
ls /sys/class/drm/
cat /sys/class/drm/card0-DRM-?/status

# 2. 背光
ls /sys/class/backlight/                # backlight 设备
cat /sys/class/backlight/backlight/max_brightness
echo 50 > /sys/class/backlight/backlight/brightness   # 调光
#   PWM 波形: 示波器量 pad106 (func6) 应见 20kHz 方波

# 3. 点亮测试 (无桌面时)
modetest -M spacemit -c                 # 找 eDP 连接器
modetest -M spacemit -s <conn_id>:1920x1080

# 4. 排查顺序
#    a) 屏不亮: 量屏 3.3V (GPIO101 电平) -> gpios-power 是否生效
#    b) 有画面无背光: brightness 写入后 pad106 波形 -> pwm18/pinctrl
#    c) 连接器缺失: include k3-edp0.dtsi? DRM 配置?
#    d) dmesg | grep -iE "edp|inno"        -> AUX/EDID 读取日志
```
