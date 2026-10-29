# MIPI DSI 屏

　　K3 平台 MIPI DSI 屏适配笔记: dpu_crtc0 → dsi0 (Synopsys host) → dphy0
→ panel 全链路, 含 K3 特色的"屏表"机制 (lcds 节点 + force-attached)、
GT9xxx 触摸与背光。参考板: Firefly itx-k3l-DSI0 (lcd_mipi101_BSD1218_A101KL68
10.1" 屏)。K3 显示节点**不在 k3.dtsi**, DSI 链在 lcd_dsi_panel.dtsi。

## 1. 原理

### 1.1 显示链结构

```
dpu_crtc0 (saturn DPU, pipeline 1, is_edp=0, dsipll 时钟方案)
   ├─ port0 out0 ──> dsi0_in (DSI host)
   └─ port0 out1 ──> wb0_in0 (writeback, 录屏/镜像用, 基座 status ok)
dsi0 ("spacemit,dsi-host", 0xd421a800, irq79, ip=synopsys-dhost, dev-id=2)
   └─ dsi0_out ──> dphy0_in
dphy0 ("spacemit,dsi-phy", 与 dsi0 同寄存器块 0xd421a800)
   └─> MIPI 4-lane → 屏
```

　　这套链路 (display-subsystem-dsi + dpu_crtc0/1 + dsi0 + dphy0 + wb0)
整体定义在 `lcd_dsi_panel.dtsi` — **板级 include 它** (不是 k3.dtsi!)。
旁边还有 dp0 (k3-dp0.dtsi)、dp1 (k3-dp1.dtsi)、edp0 (k3-edp0.dtsi) 各自
独立的 DPU 实例, 同一时间宏决定 HDMI0 还是 DSI0 占用 pad (itx 板
`HDMI0_OR_DSI0` 二选一宏)。

### 1.2 "屏表"机制 (K3 与 RK3588 差异最大处)

　　K3 的 DSI 屏不走标准 `panel-compatible` 驱动, 而是厂商通用面板驱动
`spacemit_mipi_panel.c` (CONFIG_SPACEMIT_MIPI_PANEL=y) + **名字匹配的
屏参数表**:

- 每个 lcd/lcd_xxx.dtsi 在 `/lcds` 节点下定义一张表, 节点名 = 屏型号名,
  内容: 时序 (width/hfp/hbp/hsync/vfp/vbp/vsync/fps)、DSI 参数
  (lane/color-format/phy-freq/burst-mode)、初始化指令流 `initial-command`
  (格式: `type mode timeout len cmd...` 的字节数组)。
- 板级 panel 节点用 `force-attached = "lcd_mipi101_BSD1218_A101KL68"`
  按名字把面板绑到表上。
- 换屏 = 换一张 lcd/ 表 (或自己写) + 改 force-attached 字符串。

### 1.3 时钟与位宽

　　参考屏 800x1280@60, 4-lane RGB888: `phy-bit-clock = <550000000>`
(550MHz/lane, 驱动注释注明在计算范围内), dpu 侧
`spacemit-dpu-bitclk = <550000000>`。换分辨率/帧率先算 lane 带宽
(pixel_clk × bpp / lanes), 再填表内三个频率字段。

## 2. 硬件连接

　　参考板: itx-k3l-DSI0 (10.1" 800x1280 MIPI 屏 + GT9 触摸)。itx 用
pca9555 I2C 扩展器挂屏控脚, 自研板直接用 SoC GPIO (写法见 4.1 注释)。

| 信号 | 参考板接法 | 自研板建议 | 说明 |
|---|---|---|---|
| DSI CLK± / D0±..D3± | dphy0 专用模拟 pad | 同 | 4-lane, 不进 pinctrl |
| 屏复位 RST | pca9555_2 PCA_IO0_2, 低有效 | `<&gpio K3_GPIO(N) GPIO_ACTIVE_LOW>` | panel reset-gpios |
| 背光使能 BL_EN | pca9555_2 PCA_IO0_1, 高有效 | `<&gpio ... GPIO_ACTIVE_HIGH>` | panel bl-gpios |
| 屏电源 3.3V | pca9555_2 PCA_IO0_0 (lcd_pwr_en regulator) | 直接 `<&gpio ...>` | always-on |
| 背光 PWM | pwm1, **pad 95 func6** (pwm1_2_cfg), 3.3V 域 | 同 | 50kHz, pwm-backlight |
| 触摸 INT | **GPIO94**, 下降沿 | 同 | GT9xxx 中断 |
| 触摸 RST | pca9555_2 PCA_IO0_3 | `<&gpio ...>` | 触摸复位 |
| 触摸 I2C | r_i2c1 (RCPU I2C, ri2c1_1_cfg) | 普通 i2cN 也行 | 地址 0x14 |

接线核对要点:

- itx 的屏控脚都在 I2C 扩展器上 — 自研板**没有扩展器时全部换成 SoC
  GPIO**, 换引脚同时注意 pad 冲突表。
- 触摸在 RCPU 域的 r_i2c1 上 (基座 k3-rdomain.dtsi), 自研板换普通 i2cN
  更简单 (i2c0_0_cfg 等), 不必抄。
- 背光 pwm1 50kHz (period 50000ns); itx 把 pwm1_2_cfg 的 power-source
  覆写为 3300 — pad95 所在 bank 是 3.3V 域。

## 3. 内核配置

```
# k3_defconfig 已有:
CONFIG_DRM_SPACEMIT=y              # saturn DPU
CONFIG_SPACEMIT_MIPI_PANEL=y       # 通用 MIPI 面板驱动 (force-attached 机制)
CONFIG_DRM_SPACEMIT_BACKLIGHT=y
CONFIG_BACKLIGHT_PWM=y
CONFIG_TOUCHSCREEN_GOODIX=y        # GT9xxx 触摸 (若缺按 defconfig 实际值补)
```

## 4. 设备树配置

　　自包含版 dts 组成: `#include "lcd_dsi_panel.dtsi"` (DSI 链) +
`#include "lcd/lcd_mipi101_BSD1218_A101KL68.dtsi"` (屏表, 换屏换它) + 以下
板级段。基座四件套照常。

### 4.1 背光 + 屏电源 + panel 节点

```dts
/ {
	backlight: backlight {
		status = "okay";
		compatible = "pwm-backlight";
		pwms = <&pwm1 0 50000 0>;          /* pwm1, 50kHz */
		brightness-levels = <
			255 254 253 ... /* 0-255 递减表, 全表见参考板 162 行文件 */
			7   6   5   4   3   2   1   0>;
		default-brightness-level = <50>;
	};

	lcd_pwr_en: lcd-pwr-en {
		compatible = "regulator-fixed";
		regulator-name = "lcd_pwr_en";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;
		regulator-always-on;
		regulator-boot-on;
		enable-active-high;
		/* 参考板经 I2C 扩展器: gpios = <&pca9555_2 PCA_IO0_0 GPIO_ACTIVE_HIGH>;
		 * 自研板直挂 SoC GPIO: */
		gpios = <&gpio K3_GPIO(20) GPIO_ACTIVE_HIGH>;   /* 按你的板选脚 */
		status = "okay";
	};
};

&pwm1 {
	pinctrl-names = "default";
	pinctrl-0 = <&pwm1_2_cfg>;             /* 基座组: pad95 func6 */
	status = "okay";
};

&dsi0 {
	status = "okay";

	panel0: panel0@0 {
		compatible = "spacemit,mipi-panel";
		reg = <0>;                          /* DSI 虚拟通道 0 */
		backlight = <&backlight>;
		reset-gpios = <&gpio K3_GPIO(21) GPIO_ACTIVE_LOW>; /* 参考板经 pca9555_2 */
		bl-gpios   = <&gpio K3_GPIO(22) GPIO_ACTIVE_HIGH>; /* 参考板经 pca9555_2 */
		id = <2>;
		force-attached = "lcd_mipi101_BSD1218_A101KL68";   /* 绑屏表名 */
		status = "okay";
	};
};

&dpu_crtc0 {
	memory-region = <&dpu_resv0>;
	spacemit-dpu-bitclk = <550000000>;
	status = "okay";
};

&dpu_crtc1 {
	memory-region = <&dpu_resv1>;
	spacemit-dpu-bitclk = <550000000>;
	status = "okay";
};

&dphy0 { status = "okay"; };
&lcds   { status = "okay"; };              /* 屏表节点使能, 忘了面板找不到表 */

&pinctrl {
	pwm1-2-cfg {                           /* 覆写基座组的电压域 */
		pwm1-0-pins {
			power-source = <3300>;
		};
	};
};
```

### 4.2 触摸 (GT9xxx)

```dts
&i2c0 {                                    /* 参考板用 r_i2c1, 自研板用普通 i2c 更简 */
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c0_0_cfg>;

	goodix_tx: goodix-ts@14 {
		status = "okay";
		compatible = "goodix,gt9xxx";
		reg = <0x14>;
		interrupt-parent = <&gpio>;
		interrupts = <K3_GPIO(94) IRQ_TYPE_EDGE_FALLING>;
		reset-gpios = <&gpio K3_GPIO(23) GPIO_ACTIVE_HIGH>;
		irq-gpios = <&gpio K3_GPIO(94) IRQ_TYPE_EDGE_FALLING>;
		irq-flags = <2>;                    /* 1 rising, 2 falling */
		touchscreen-size-x = <800>;
		touchscreen-size-y = <1280>;
		goodix,driver-send-cfg = <1>;
		goodix,int-sync = <1>;
		goodix,esd-protect = <1>;
		/* goodix,cfg-group2 = [ ...寄存器配置表... ];
		 * 参考板 186 字节完整表见 wrapper 文件; driver-send-cfg=1 时必配 */
	};
};
```

### 4.3 属性速查与陷阱

| 属性 | 说明 |
|---|---|
| force-attached | 屏表名, 必须与 /lcds 下节点名**逐字一致** |
| id = <2> | 厂商面板驱动的面板编号, 参考屏为 2 |
| reset-gpios / bl-gpios | 屏复位/背光使能; 极性按屏规格书 |
| initial-command | 屏表内的初始化指令流 (type mode timeout len cmd 字节组) |
| spacemit-dpu-bitclk | DPU 位时钟, 与屏表 phy-bit-clock 配套 |
| irq-flags | 触摸中断极性; 与 interrupts 触发类型保持一致 |

陷阱清单:

- **&lcds 忘了使能**: 面板驱动按名查表失败, 屏不亮且日志常只打 dbg 级。
- force-attached 拼写差一个字符 = 查无此表, 现象同上; 两处名字从同一个
  lcd/ 文件复制。
- include 关系: 不 include "lcd_dsi_panel.dtsi" 则 dsi0/dphy0/dpu_crtc0
  都不存在 — K3 显示节点全在接口分立的 dtsi 里。
- itx 板同一组 pad 是 HDMI0/DSI0 二选一 (HDMI0_OR_DSI0 宏): 自研板若两
  者都要, 硬件上就不成立, 别在软件上想办法。
- 触摸 cfg-group2 是 186 字节寄存器 blob, 屏/触摸 IC 版本不配会导致触摸
  乱跳或无触; driver-send-cfg=0 时可不发 (用 IC 自带配置)。

## 5. 验证测试

```bash
# 1. DSI 链 probe
dmesg | grep -iE "dsi|dphy|dpu" | head -15
ls /sys/class/drm/                          # DSI 连接器出现

# 2. 屏表匹配核实
dmesg | grep -i "force-attached\|lcd_mipi101"   # 找到表=匹配成功
cat /proc/device-tree/lcds/*/.. 2>/dev/null | head   # 或 dtb 反汇编核对

# 3. 点亮
modetest -M spacemit -c                     # 连接器列表
modetest -M spacemit -s <dsi_conn>:800x1280@60  # 打测试图

# 4. 背光
cat /sys/class/backlight/backlight/max_brightness
echo 100 > /sys/class/backlight/backlight/brightness

# 5. 触摸
evtest                                      # 选 goodix 设备, 滑动看坐标
hexdump /dev/input/event2 &                 # 或原始事件流

# 6. 排查顺序
#    a) 屏不亮: &lcds 使能? force-attached 名字? dpu_crtc0/dphy0 status?
#    b) 有背光无画面: initial-command 后屏进 video 模式? lane/时钟表值?
#    c) 花屏: phy-bit-clock 与 spacemit-dpu-bitclk 配套重算
#    d) 触摸无: i2cdetect 0x14 / INT GPIO94 电平
```
