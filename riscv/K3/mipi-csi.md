# MIPI CSI 摄像头

　　K3 平台 MIPI CSI 摄像头适配笔记: csiphy (DPHY) → ccic (CSI-2 接收器)
→ ccic_dma 的 V4L2 采集链, 以 Firefly itx-k3l 的三路 IMX415 (csi0/1/2) 为
参考。K3 摄像头节点**不在 k3.dtsi**, 整套在 k3-camera.dtsi, 板级按需
include; 摄像头专用 I2C 扩展器 (pca9555) 挂法与四套编号不对齐问题
(csi-id / csiphy / ccic / camN-pinctrl) 是本篇重点。

## 1. 原理

### 1.1 数据链结构 (k3-camera.dtsi 基座, 234 行)

```
sensor (IMX415, I2C 控制 @0x37, 4-lane MIPI)
   ↓ MIPI DPHY                    ↓ I2C (r_i2c1 / i2c3 / i2c4)
csiphy0 (0xd420a000) ──┐
csiphy1 (0xd420a800) ──┤→ ccic0/1/2/3 ("spacemit,ccic", CSI-2 RX)
csiphy2 (0xd4206000) ──┘      ↓
                        ccic_dma (0xd420f000, "spacemit,ccic-dma", 共享 DMA+IOMMU)
                              ↓
                        /dev/videoN (VFL_TYPE_VIDEO, MPLANE capture)
```

　　与 RK3588 的 rkisp/rkcif 多级管线不同, K3 摄像头是**单级 CCIC**:
接收器直接 DMA 出帧, 中间无 ISP 节点 (ISP 能力在 DPU/其他 IP, 采集链
不涉及)。所以设备树很短: sensor 节点 + 对应 csiphy/ccic 使能 + endpoint
互连, 三步。

　　注意 k3-camera.dtsi 里 csiphy0-2 / ccic0-3 / ccic_dma 的 status
**全部已是 "okay"** — include 这个文件 = 整套控制器上电开跑, 板级只需
接 sensor。CSI2 方式例外: csiphy2 同时给 ccic2/ccic3 两个接收器
(bifmode-enable=1), 参考板显式 `&ccic3 { status = "disabled"; }` 让
sensor 独占。

| 控制器 | 基址 | 中断 | 归属 |
|---|---|---|---|
| csiphy0 | 0xd420a000 | - (APMU 时钟 CLK_APMU_CCIC1PHY) | → ccic0 |
| csiphy1 | 0xd420a800 | - (CLK_APMU_CCIC2PHY) | → ccic1 |
| csiphy2 | 0xd4206000 | - (CLK_APMU_CCIC3PHY, bifmode=1) | → ccic2 + ccic3 |
| ccic0-3 | 0xd420a000/800/6000/6800 | saplic 81/82/83/71 | spacemit,ccic |
| ccic_dma | 0xd420f000 | saplic 93 (dma) + 80 (mmu) | spacemit,ccic-dma |

### 1.2 驱动与 CONFIG

- CCIC: `drivers/media/platform/spacemit/cam_ccic/`
  (CONFIG_SPACEMIT_K3_CCIC=y, select MEDIA_CONTROLLER/V4L2_ASYNC/
  VIDEOBUF2_DMA_CONTIG 等; IOMMU 部分单独 CONFIG_SPACEMIT_K3_CCIC_IOMMU=y)
- sensor 驱动两套, 都 match `compatible = "sony,imx415"`:
  - 标准版 `cam_sensor/imx415_sensor.c` (CONFIG_SPACEMIT_K3_CAM_IMX415=y,
    **defconfig 已编**) — 标准 V4L2 subdev, 注册到 media 拓扑;
  - FF 精简版 `cam_sensor/imx415_ff_sensor.c`
    (CONFIG_SPACEMIT_K3_CAM_IMX415_FF, **defconfig 未编**) — misc 设备 +
    ioctl 控制流, 出 `/dev/imx415-<csi-id>`, 按需另开。
- 上游版 `drivers/media/i2c/imx415.c` (VIDEO_IMX415) 未编, 别与上面混淆。

### 1.3 四套编号不对齐 (照抄参考板前必读)

　　csi-id、csiphy 编号、ccic 编号、pinctrl 组名 (camN_x_cfg) 四套编号
**不严格对齐**, 自研板重排引脚时必须逐项核对:

| 参考板路 | csi-id | sensor 时钟 | csiphy/ccic | clk 脚 (pinctrl 组) | sensor I2C |
|---|---|---|---|---|---|
| CSI0 | 0 | VCLK0 | csiphy0/ccic0 | **pad75 func2** (cam0_2_cfg) | r_i2c1 @0x37 |
| CSI1 | 1 | VCLK1 | csiphy1/ccic1 | **pad74 func2** (cam1_2_cfg) | i2c4 @0x37 |
| CSI2 | 2 | **VCLK3** | csiphy2/ccic2 (+ccic3 disabled) | **pad99 func6** (cam3_2_cfg) | i2c3 @0x37 |

　　例如 CSI2 走的是 cam**3** 组 + VCLK**3** 时钟而非 "2" — 组名与 csi 口
号是两套空间, 照抄参考板最稳, 重排要查 k3-pinctrl.dtsi 的组定义。

### 1.4 cam 时钟 pad 三档选择

　　每路 cam 时钟出脚有三档 pad 可选 (k3-pinctrl.dtsi L2864-2974), 按
硬件走线引脚组:

| 组名 | 档 0 | 档 1 | 档 2 |
|---|---|---|---|
| cam0_x_cfg | pad13 func5 | pad46 func3 | **pad75 func2** |
| cam1_x_cfg | pad34 func4 | pad47 func3 | **pad74 func2** |
| cam2_x_cfg | pad35 func4 | pad52 func5 | pad85 func1 |
| cam3_x_cfg | pad43 func3 | pad67 func4 | **pad99 func6** |

　　参考板三路全部用档 2 (粗体); 组内电气统一 bias-disable +
drive-strength 25, csi0 档是 1.8V 域、csi2 档 (pad99) 覆写 3.3V 域。

## 2. 硬件连接

　　参考板: itx-k3l 三路 IMX415 (1920x1080@60, 4-lane, 742.5MHz/lane)。
屏控类参考板大量经 pca9555 I2C 扩展器, 自研板直接用 SoC GPIO。

| 信号 | CSI0 | CSI1 | CSI2 | 说明 |
|---|---|---|---|---|
| MIPI CLK±/D0±..D3± | csiphy0 专用 pad | csiphy1 | csiphy2 | 4-lane, 不进 pinctrl |
| sensor 时钟 CLK_OUT | pad75 func2 | pad74 func2 | pad99 func6 | 24MHz MCLK 源 |
| sensor I2C | r_i2c1 (pad39/40 func4) | i2c4 (pad111/112 func4) | i2c3 (pad82/83 func6) | 地址 0x37 |
| PWDN | pca9555 PCA_IO0_4 | PCA_IO1_0 | PCA_IO0_0 | 高有效 |
| RESET | pca9555 PCA_IO0_5 | PCA_IO1_1 | PCA_IO0_1 | **低有效** |
| INT (sensor 中断) | 未接 | 未接 | 未接 | IMX415 参考板不用中断脚 |

接线核对要点:

- PWDN 高有效 / RESET 低有效是参考板极性, 换 sensor 按手册核对; 极性
  写反 = sensor 永远复位或永不上电。
- 自研板无 pca9555 时 PWDN/RESET 换 `<&gpio K3_GPIO(N) ...>` 直接写。
- i2c3 (CSI2) 上若已有 LT2404 (dp.md 桥接, @0x29) 或 PC9202
  (watch.md, @0x3c) 不冲突 — 地址不同可共存, 但总线必须都使能。
- MCLK 24MHz 由 SoC cam clk pad 输出, 不用板上晶振给 sensor 供时钟
  (IMX415 需要 24MHz±精度, 走 SoC VCLK 即可)。

## 3. 内核配置

```
# k3_defconfig 已有 (摄像头链全套已编, 无需补):
CONFIG_MEDIA_SUPPORT=y
CONFIG_SPACEMIT_K3_CCIC=y          # ccic + csiphy 驱动
CONFIG_SPACEMIT_K3_CCIC_IOMMU=y
CONFIG_SPACEMIT_K3_CAM_IMX415=y    # 标准 V4L2 IMX415 (match "sony,imx415")
CONFIG_SPACEMIT_K3_CAM_IMX219/OV5647/OV2735/...=y   # 其它 sensor 已带

# 按需追加:
CONFIG_SPACEMIT_K3_CAM_IMX415_FF=y # FF 精简版 (misc + ioctl, /dev/imx415-N)
CONFIG_VIDEO_IMX415=y              # 上游版 drivers/media/i2c/imx415.c (别混用)
```

## 4. 设备树配置

　　自包含版 dts 组成: 基座四件套照常 + `#include "k3-camera.dtsi"`
(csiphy/ccic/ccic_dma 全在其中) + 以下板级段。

### 4.1 方式一: CSI0 + IMX415 (r_i2c1, 参考板展开修正版)

```dts
/* dts 头部需含: #include "k3-camera.dtsi" (基座四件套照常) */

&r_i2c1 {                                  /* RCPU 域 I2C, 基座 k3-rdomain.dtsi */
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&ri2c1_1_cfg>;            /* pad39 scl / pad40 sda, func4 */

	imx415_0: imx415-0@37 {
		compatible = "sony,imx415";        /* 参考板写 "sony,imx415-ff" —
		                                      全内核无驱动匹配, 见 4.3 陷阱 */
		reg = <0x37>;
		csi-id = <0>;
		clock-names = "xclk";
		clocks = <&syscon_apmu CLK_APMU_ISIM_VCLK0>;
		/* 参考板经 I2C 扩展器; 自研板直挂 SoC GPIO: */
		pwdn-gpios  = <&gpio K3_GPIO(30) GPIO_ACTIVE_HIGH>;  /* 按你板选脚 */
		reset-gpios = <&gpio K3_GPIO(31) GPIO_ACTIVE_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&cam0_2_cfg>;         /* cam0 clk = pad75 func2 */
		status = "okay";

		port {
			imx415_0_out: endpoint {
				data-lanes = <1 2 3 4>;
				link-frequencies = /bits/ 64 <742500000>;
				remote-endpoint = <&ccic0_in>;
			};
		};
	};
};

&csiphy0 { status = "okay"; };             /* k3-camera.dtsi 已 okay, 显式无害 */

&ccic0 { status = "okay"; };

&ccic0_in {
	remote-endpoint = <&imx415_0_out>;     /* 反向回填, 必写 */
};

&pinctrl {
	cam0-2-cfg {                           /* 覆写基座组 (可省, 默认已同值) */
		cam1-0-pins {
			pinmux = <K3_PADCONF(75, 2)>;  /* cam0 clk */
			bias-disable;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};
};
```

### 4.2 方式二: CSI1 / CSI2 (普通 I2C)

　　CSI1 (i2c4, csiphy1/ccic1) — 与 CSI0 只差四处: I2C 总线、csi-id、
时钟/引脚组、endpoint 对:

```dts
&i2c4 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c4_3_cfg>;             /* pad111 scl / pad112 sda, func4 */

	imx415_1: imx415-1@37 {
		compatible = "sony,imx415";
		reg = <0x37>;
		csi-id = <1>;
		clocks = <&syscon_apmu CLK_APMU_ISIM_VCLK1>;
		pwdn-gpios  = <&gpio K3_GPIO(30) GPIO_ACTIVE_HIGH>;   /* 按你板选脚 */
		reset-gpios = <&gpio K3_GPIO(31) GPIO_ACTIVE_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&cam1_2_cfg>;         /* cam1 clk = pad74 func2 */
		status = "okay";

		port {
			imx415_1_out: endpoint {
				data-lanes = <1 2 3 4>;
				link-frequencies = /bits/ 64 <742500000>;
				remote-endpoint = <&ccic1_in>;
			};
		};
	};
};

&csiphy1 { status = "okay"; };
&ccic1   { status = "okay"; };
&ccic1_in { remote-endpoint = <&imx415_1_out>; };
```

　　CSI2 (i2c3, csiphy2/ccic2, **clk 用 cam3 组 + VCLK3**): 与 CSI1 同构,
差异项照抄下表 — 额外必须 disable ccic3 (与 ccic2 共享 csiphy2):

```dts
&i2c3 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c3_2_cfg>;             /* pad82 scl / pad83 sda, func6 */

	imx415_2: imx415-2@37 {
		compatible = "sony,imx415";
		reg = <0x37>;
		csi-id = <2>;
		clocks = <&syscon_apmu CLK_APMU_ISIM_VCLK3>;   /* 注意是 VCLK3 */
		pwdn-gpios  = <&gpio K3_GPIO(30) GPIO_ACTIVE_HIGH>;  /* 按你板选脚 */
		reset-gpios = <&gpio K3_GPIO(31) GPIO_ACTIVE_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&cam3_2_cfg>;         /* clk = pad99 func6 (不是 cam2 组!) */
		status = "okay";

		port {
			imx415_2_out: endpoint {
				data-lanes = <1 2 3 4>;
				link-frequencies = /bits/ 64 <742500000>;
				remote-endpoint = <&ccic2_in>;
			};
		};
	};
};

&csiphy2 { status = "okay"; };
&ccic2    { status = "okay"; };
&ccic3    { status = "disabled"; };        /* csiphy2 双接收器, 让位 */
&ccic2_in { remote-endpoint = <&imx415_2_out>; };

&pinctrl {
	cam3-2-cfg {
		cam3-0-pins {
			pinmux = <K3_PADCONF(99, 6)>;  /* cam3 clk */
			bias-disable;
			drive-strength = <25>;
			power-source = <3300>;         /* pad99 在 3.3V 域 */
		};
	};
};
```

### 4.3 属性速查与陷阱

| 属性 | 解析者 | 说明 |
|---|---|---|
| compatible = "sony,imx415" | 两个 sensor 驱动 of_match (精确匹配) | **必须**是这个值 |
| csi-id (u32) | imx415_sensor.c:1253 / ff_sensor.c:1303 | 路号, ff 版兼作 misc 设备名 |
| pwdn-gpios | devm_gpiod_get_optional "pwdn" | 高有效 (参考板极性) |
| reset-gpios | 同上 "reset" | 低有效 (参考板极性) |
| data-lanes = <1 2 3 4> | V4L2 fwnode (ccic 端解析) | 4-lane 全开 |
| link-frequencies (u64) | V4L2 fwnode | 742.5MHz/lane (1485Mbps) |
| remote-endpoint (双向) | V4L2 async | sensor→ccic 与 ccic→sensor 都要写 |

陷阱清单:

- **compatible = "sony,imx415-ff" 匹配不到任何驱动** (参考板 dts 原文,
  全内核 grep 无此字符串): 三个候选驱动 (cam_sensor 两版 + 上游版) 的
  of_match 全是 `"sony,imx415"`, 精确匹配无后缀模糊 — 照抄参考板 =
  sensor 节点无驱动 probe。本篇已改回 `"sony,imx415"`; 若你确要 FF
  精简版 (ioctl 控制流), 开 CONFIG_SPACEMIT_K3_CAM_IMX415_FF 后
  compatible 同样写 `"sony,imx415"`。
- **忘记反向回填** `&ccicN_in { remote-endpoint = ...; }`: endpoint 是
  双向图, 只写 sensor 端 V4L2 async 注册失败, media 拓扑断链。
- **CSI2 用 cam3_2_cfg + VCLK3** (1.3 节编号不对齐): 抄成 cam2 组 /
  VCLK2 则时钟不出、sensor 不亮。
- ccic2/ccic3 共享 csiphy2: 用 CSI2 时 disable ccic3, 否则两接收器抢
  同一 PHY。
- FF 版与标准版同时开 CONFIG: 两个驱动 match 同一 compatible, i2c 设备
  只绑先注册者 — 二选一。
- r_i2c1 是 RCPU 域 I2C (基座 k3-rdomain.dtsi 已带节点): 用它作 sensor
  总线的前提是 rdomain include 存在; 自研板换普通 i2cN 更简单。
- 3.3V/1.8V 电压域: pad75 (cam0) 1.8V、pad99 (cam3) 3.3V — 按档位覆写
  power-source, 与传感器时钟输入电平规格对上。

## 5. 验证测试

```bash
# 1. 链路 probe
dmesg | grep -iE "ccic|csiphy|imx415" | head -15
ls /dev/video*                             # ccic 注册的 MPLANE capture 节点
ls /dev/v4l-subdev*                        # sensor subdev

# 2. media 拓扑 (sensor → ccic 链应完整)
media-ctl -p -d /dev/media0

# 3. FF 精简版 (若开 IMX415_FF)
ls /dev/imx415-*                           # misc 设备, 按 csi-id 命名

# 4. 采图
v4l2-ctl -d /dev/video0 --list-formats-ext  # 应见 1920x1080@60 系列
v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=1 \
         --stream-to=/tmp/frame.raw        # 抓一帧
v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=30  # 连续采, 掉帧率

# 5. 排查顺序
#    a) 无 /dev/videoN     -> include k3-camera.dtsi? SPACEMIT_K3_CCIC?
#    b) video 在但采图超时 -> sensor 没出图: i2cdetect 0x37 / MCLK pad 波形
#    c) sensor i2c 通但无 probe -> compatible 是否 "sony,imx415" (4.3 首坑)
#    d) 反向回填缺失       -> dmesg 见 v4l2 async 注册失败串
#    e) 花屏/绿屏          -> data-lanes / link-frequencies 与 sensor 实配
```
