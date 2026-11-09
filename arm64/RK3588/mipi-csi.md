# MIPI CSI 摄像头

　　摄像头全链路 (sensor→dphy→csi2→ISP): IMX415 单摄、jd4 双摄切换、SG XC7160 单摄+双目。

## 1. RK3588 摄像头数据链路架构

　　RK3588 摄像头通路是链式的, 每一环都要在设备树里用 remote-endpoint 串起来:

```
Sensor (I2C 挂载, 如 IMX415)
  ====> csi2_dphy (MIPI DPHY 接收)
  ====> mipiN_csi2 (CSI2 host 控制器)
  ====> rkcif_mipi_lvdsN (CIF 采集)
  ====> rkcif_mipi_lvdsN_sditf (直通 ISP 的虚拟通道)
  ====> rkispN_virM (ISP 虚拟通道, 去 ISP 处理)
```

| 环节 | 节点 | 说明 |
|---|---|---|
| MIPI PHY | csi2_dphy0/1/2/3, csi2_dcphy0/1 | dphy0/1 共享 hw, dcphy 走 mipidcphy |
| CSI2 host | mipi0~6_csi2 | MIPI 协议解析 |
| CIF 采集 | rkcif, rkcif_mipi_lvds0~6 | 也可不经 ISP 直接出图 |
| ISP | rkisp0/rkisp1 + vir 通道 | 图像处理, rkisp0_vir0~3, rkisp1_vir0~3 |

　　典型映射 (dphy0 -> mipi2_csi2 -> rkcif_mipi_lvds2 -> rkisp0_vir0):
dphyN 输出固定接 mipi(N+2)_csi2, 再接 rkcif_mipi_lvds(N+2)

　　常用内核配置 (defconfig 已开):

```
CONFIG_VIDEO_ROCKCHIP_CIF=y        # rkcif 采集
CONFIG_VIDEO_ROCKCHIP_RKISP1=y     # rkcif ISP
CONFIG_PHY_ROCKCHIP_CSI2_DPHY=y    # CSI2 DPHY
CONFIG_VIDEO_IMX415=y              # 传感器驱动 (按实际 sensor 选)
```

　　注意:
- IMX415 驱动瑞芯微原厂 SDK 自带 (drivers/media/i2c/imx415.c), 非私有
- sensor 驱动在 firefly-linux.config 里也列了 VIDEO_ROCKCHIP_ISPP/FEC 等,
  是 ISP 后处理模块, 一般平台已含

## 2. 方式一: csi2_dphy0 接 IMX415

　　参考板: AIO-3588SG。

### 2.1 硬件连接

```
IMX415 模组 (CMK-OT2022-PX1, 8M):
  MIPI 差分对  ====> csi2_dphy0 (4 lane, data-lanes = <1 2 3 4>)
  I2C SCL/SDA ====> I2C7_M0: GPIO1_D0 / GPIO1_D1 (i2c7m0_xfer)
  MCLK        ====> CLK_MIPI_CAMARAOUT_M1 ====> GPIO3_A6 (mipim1_camera1_clk)
  RST         ====> GPIO1_D5 (低有效)
```

### 2.2 设备树配置

　　参考: rk3588-firefly-aio-3588sg-mipi-csi2-imx415.dtsi

```
&i2c7 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c7m0_xfer>;

	imx415: imx415@37 {
		compatible = "sony,imx415";
		reg = <0x37>;                          // IMX415 I2C 地址
		clocks = <&cru CLK_MIPI_CAMARAOUT_M1>; // sensor 时钟源
		clock-names = "xvclk";
		pinctrl-names = "default";
		pinctrl-0 = <&mipim1_camera1_clk>;     // MCLK 输出脚 GPIO3_A6
		power-domains = <&power RK3588_PD_VI>;
		reset-gpios = <&gpio1 RK_PD5 GPIO_ACTIVE_LOW>;

		rockchip,camera-module-index = <0>;
		rockchip,camera-module-facing = "back";
		rockchip,camera-module-name = "CMK-OT2022-PX1";
		rockchip,camera-module-lens-name = "IR0147-50IRC-8M-F20";
		port {
			imx415_out: endpoint {
				remote-endpoint = <&mipidphy0_in_ucam1>;
				data-lanes = <1 2 3 4>;   // 4 lane MIPI
			};
		};
	};
};

/* 1. DPHY 接收 sensor */
&csi2_dphy0_hw {
	status = "okay";
};

&csi2_dphy0 {
	status = "okay";

	ports {
		#address-cells = <1>;
		#size-cells = <0>;
		port@0 {
			reg = <0>;
			#address-cells = <1>;
			#size-cells = <0>;

			mipidphy0_in_ucam1: endpoint@1 {
				reg = <1>;
				remote-endpoint = <&imx415_out>;
				data-lanes = <1 2 3 4>;
			};
		};
		port@1 {
			reg = <1>;
			#address-cells = <1>;
			#size-cells = <0>;

			csidphy0_out: endpoint@0 {
				reg = <0>;
				remote-endpoint = <&mipi2_csi2_input>;
			};
		};
	};
};

/* 2. CSI2 host */
&mipi2_csi2 {
	status = "okay";

	ports {
		#address-cells = <1>;
		#size-cells = <0>;
		port@0 {
			reg = <0>;
			#address-cells = <1>;
			#size-cells = <0>;

			mipi2_csi2_input: endpoint@0 {
				reg = <0>;
				remote-endpoint = <&csidphy0_out>;
			};
		};
		port@1 {
			reg = <1>;
			#address-cells = <1>;
			#size-cells = <0>;

			mipi2_csi2_output: endpoint@0 {
				reg = <0>;
				remote-endpoint = <&cif_mipi2_in0>;
			};
		};
	};
};

/* 3. CIF 采集 */
&rkcif {
	status = "okay";
};

&rkcif_mmu {
	status = "okay";
};

&rkcif_mipi_lvds2 {
	status = "okay";

	port {
		cif_mipi2_in0: endpoint {
			remote-endpoint = <&mipi2_csi2_output>;
		};
	};
};

/* 4. 直通 ISP */
&rkcif_mipi_lvds2_sditf {
	status = "okay";

	port {
		mipi_lvds2_sditf: endpoint {
			remote-endpoint = <&isp0_vir0>;
		};
	};
};

/* 5. ISP 处理 */
&rkisp0 {
	status = "okay";
};

&isp0_mmu {
	status = "okay";
};

&rkisp0_vir0 {
	status = "okay";

	port {
		#address-cells = <1>;
		#size-cells = <0>;

		isp0_vir0: endpoint@0 {
			reg = <0>;
			remote-endpoint = <&mipi_lvds2_sditf>;
		};
	};
};
```

```
# imx415 修改默认的30fps为60fps
cd /media/lhj/data/t-chip/7.code/arm64/rockchip/rk3588_6.12.69_sdk/kernel-6.12
vim drivers/media/i2c/imx415.c   
# 找到 .reg_list = imx415_linear_12bit_1932x1096_594M_regs,
.vts_def 的 0x0c5d 改为 0x52e
.denominator 的 300000 改为 600000
.exp_def 的 0x0c5d 改为 0x317

# 找到 imx415_linear_12bit_1932x1096_594M_regs[]
0x3024 的值从0x5D改为0x2E
0x3024 的值从0x0C改为0x06
```



### 2.3 关键属性说明

| 属性 | 说明 |
|---|---|
| clocks/pinctrl (xvclk) | sensor 的 MCLK 由 SOC CAMARAOUT 时钟输出, M0~M3 每路有固定引脚 |
| reset-gpios | sensor 复位, 低有效 |
| power-gpios | sensor 电源使能 (SG 板 sensor 供电常开, 未用) |
| camera-module-name | 模组名, 与 media lib/rkaiq IQ 文件匹配 |
| camera-module-lens-name | 镜头名, IQ 调优文件匹配 |
| data-lanes | MIPI lane 数, IMX415 为 4 lane |

## 3. 方式二: 双摄 CAM0/CAM1 切换

　　参考板: aio-3588jd4 (csi0/csi1 共用接口)。

　　aio-3588jd4 只有一个摄像头连接器, 但 CAM0/CAM1 两个通道经
一个模拟开关选择, dtsi 用 CAM0_OR_CAM1 宏二选一编译。

### 3.1 硬件连接

```
CAM0 通道:
  I2C    ====> I2C6 (i2c6m0: GPIO1_B5/B6)
  MCLK   ====> CLK_MIPI_CAMARAOUT_M1 ====> GPIO3_A6
  电源    ====> GPIO3_D5 (power-gpios)
  复位    ====> PCA9555 IO0_5 (有 PCA9555 时) 或不用
  差分对  ====> csi2_dphy0

CAM1 通道:
  I2C    ====> I2C6
  MCLK   ====> CLK_MIPI_CAMARAOUT_M0 ====> GPIO4_B1
  电源    ====> GPIO1_D5
  复位    ====> PCA9555 IO0_6
  差分对  ====> csi2_dphy3 (经 dphy3 -> mipi4_csi2 -> rkcif_mipi_lvds4)

通道选择: GPIO3_C1 (cam0_cam1_switch, 高=CAM0 低=CAM1)
```

### 3.2 设备树差异 (相比方式一)

- 通路换为: csi2_dphy3 -> mipi4_csi2 -> rkcif_mipi_lvds4 -> rkisp0_vir2
- sensor 节点用 clocks = CLK_MIPI_CAMARAOUT_M0 /
  pinctrl-0 = mipim0_camera0_clk (GPIO4_B1)
- 增加通道选择节点:

```
/ {
	cam0_cam1_switch: cam0-cam1-switch {
		compatible = "regulator-fixed";
		regulator-name = "cam0_cam1_switch";
		regulator-min-microvolt = <1800000>;
		regulator-max-microvolt = <1800000>;
		regulator-boot-on;
		regulator-always-on;
		status = "okay";
		enable-active-high;                       // 1: CAM0, 0: CAM1
		gpio = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;
		pinctrl-names = "default";
		pinctrl-0 = <&cam0_or_cam1_switch_pin>;
	};
};

&pinctrl {
	cam {
		cam0_or_cam1_switch_pin: cam0-or-cam1-switch-pin {
			rockchip,pins = <3 RK_PC1 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};
```

- 摄像头占用的引脚与 SPI 复用, 需关闭: &spi0/&spi1 { status = "disabled"; }

## 4. 方式三: CSI0 XC7160 单摄 + CSI1 双目

　　参考板: AIO-3588SG (6.12 移植)。

　　从 5.10/6.1 SDK 移植的两个 Firefly 私有模组 (XC7160 = ISP+SC8238 一体,
compatible "firefly,xc7160", 驱动 drivers/media/i2c/xc7160.c 已在 6.12
树中完成 v4l2 API 适配, CONFIG_VIDEO_XC7160=y)。

### 4.1 CSI0 单摄 (cam-8ms1m)

　　参考: rk3588-firefly-aio-3588sg-cam-8ms1m.dtsi (以 6.1 版为底稿,
data-lanes <1 2 3 4>)

```
XC7160:
  I2C    ==> I2C7_M0 (i2c7m0_xfer), 地址 0x1b
  MCLK   ==> CLK_MIPI_CAMARAOUT_M1 ==> GPIO3_A6 (mipim1_camera1_clk)
  power  ==> GPIO1_C4 (低有效)
  reset  ==> GPIO1_D5 (高有效)
  pwdn   ==> GPIO3_C0 (高有效)
  差分对 ==> csi2_dphy0 -> mipi2_csi2 -> rkcif_mipi_lvds2
```

　　与 FF_MIPI_CSI2_IMX415 互斥 (同一条 i2c7 + csi2_dphy0 链),
.dts 里用 FF_CAM_8MS1M 宏控制。

### 4.2 CSI1 双目 (dcphy-cam-8ms1m, BP 扩展板)

　　参考: rk3588-firefly-aio-3588sg-dcphy-cam-8ms1m.dtsi (6.1 中由
bp.dtsi 无条件包含, 即双目摄像头物理上装在 BP 扩展板上)

```
xc7160_1 (前置, module-index 1):
  I2C    ==> I2C1_M4 (i2c1m4_xfer: GPIO1_D2/D3), 地址 0x1b
  MCLK   ==> CLK_MIPI_CAMARAOUT_M4 ==> GPIO1_D7 (mipim0_camera4_clk)
  power  ==> PCA9554 IO0_6 (BP 板上的 IO 扩展)
  reset  ==> PCA9554 IO0_5
  pwdn   ==> GPIO3_C5
  差分对 ==> csi2_dcphy0 (mipidcphy0) -> mipi0_csi2 -> rkcif_mipi_lvds

xc7160_2 (后置, module-index 2):
  I2C    ==> I2C0_M2 (i2c0m2_xfer), 地址 0x1b
  MCLK   ==> CLK_MIPI_CAMARAOUT_M3 ==> GPIO1_D6 (mipim0_camera3_clk)
  power  ==> GPIO1_B4
  reset  ==> PCA9554 IO0_4
  pwdn   ==> GPIO3_C4
  差分对 ==> csi2_dcphy1 (mipidcphy1) -> mipi1_csi2 -> rkcif_mipi_lvds1
```

　　依赖 FF_BP (pca9554 在 bp.dtsi 定义), 宏 FF_DCPHY_CAM_8MS1M。

### 4.3 互斥关系 (硬件级, 不可同开)

| 组合 | 冲突点 |
|---|---|
| dcphy 双目 vs DSI0 (LVDS101/215) | 共享 mipidcphy0 |
| dcphy 双目 vs DSI1 (MIPI 屏) | 共享 mipidcphy1 |
| XC7160_1 MCLK (GPIO1_D7) vs WIFI 电源 | vcc3v3_pcie20_1l2 同脚 |
| CSI0 XC7160 vs IMX415 | 同 i2c7 + csi2_dphy0 |

　　注意: GPIO1_D7 冲突在 6.1 出厂配置里同样存在 (FF_PCIE2_1L2 与
bp.dtsi 无条件包含 dcphy-cam), Firefly 原厂未解决, 属遗留互斥。
双目摄像头场景: 显示走 DP+eDP, WIFI 需实测确认 (可能需换时钟脚
或关 WIFI)。

## 5. MCLK 引脚速查 (CLK_MIPI_CAMARAOUT_M0~M4)

| 时钟 | pinctrl | 引脚 |
|---|---|---|
| M0 | mipim0_camera0_clk | GPIO4_B1 (func1) |
| M1 | mipim1_camera1_clk | GPIO3_A6 (func4) |
| M3 | mipim0_camera3_clk | GPIO1_D6 (func2) |
| M4 | mipim0_camera4_clk | GPIO1_D7 (func2, 与 WIFI 电源冲突!) |

## 6. 验证测试

```
# IMX415
grep -H '' /sys/class/video4linux/video*/name   # 查找节点,选MAINPATH的

sudo -u firefly env \
  XDG_RUNTIME_DIR=/run/user/1000 \
  WAYLAND_DISPLAY=wayland-0 \
  gst-launch-1.0 \
  v4l2src device=/dev/video31 io-mode=2 \
  ! video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 \
  ! videoconvert \
  ! waylandsink sync=false
```



```
# 枚举 media 设备
ls /dev/media*
media-ctl -p -d /dev/media0     # 打印整条链路, 应看到
                                # imx415 -> dphy0 -> mipi2 -> cif -> isp 链

# 枚举 video 节点
ls /dev/video*
# 一般 video0 是 ISP 主通道, 带 ISP 输出

# 抓一帧 (需要 ISP 正常工作, 依赖 rkaiq)
v4l2-ctl -d /dev/video0 --set-fmt-video=width=3840,height=2160,pixelformat=NV12 \
         --stream-mmap --stream-count=1 --stream-to=/tmp/frame.raw
ls -l /tmp/frame.raw            # 3840*2160*1.5 ≈ 12MB

# 或用 gstreamer 预览 (接显示器)
gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink

# dmesg
dmesg | grep -i -E "imx415|rkcif|rkisp|csi2|dphy"
# 正常: imx415 probe 成功, rkisp0 注册, 无 mipi 错误

# 常见问题:
# 1. sensor probe 失败: I2C 地址/reg 错, MCLK 没输出 (示波器量 sensor xvclk),
#    reset-gpios 极性不对
# 2. 链路断裂 (media-ctl 缺某一环): 少使能了中间节点, 对照本笔记 2.2 全链配置
# 3. 抓图全绿/全灰: ISP 未生效 (缺 rkaiq) 或 lane 极性反, 检查 data-lanes
# 4. mipi err cnt 报错: MIPI 信号完整性问题, 检查 lane 数配置与硬件走线
# 5. 画面偏色: IQ 文件不匹配, 检查 camera-module-name/lens-name 是否与
#    /etc/iqfiles 一致
```

## 7. 实战: AIO-3588L CSI0/CSI1 双 IMX415 (6.12, 板级验证)

　　定制板两路 MIPI CSI 座, 均接 IMX415 (8M, 3840x2160)。顶层宏相互
独立, 可同时开:

```
#define FF_MIPI_CSI0_IMX415
#define FF_MIPI_CSI1_IMX415
```

### 7.1 两路硬件连接

| 资源 | CSI0 (IMX415-0) | CSI1 (IMX415-1) |
|---|---|---|
| I2C | i2c3 (i2c3m0_xfer), 0x37 | i2c8 (i2c8m4_xfer), 0x37 |
| MCLK | CLK_MIPI_CAMARAOUT_M1 (mipim0_camera1_clk = **GPIO1_B6**) | CLK_MIPI_CAMARAOUT_M3 (mipim0_camera3_clk = GPIO1_D6) |
| reset | GPIO2_B5 (低有效) | GPIO2_C5 (低有效) |
| DPHY | csi2_dphy0 (dphy0) | csi2_dphy1_hw + csi2_dphy3 (dphy3) |
| CSI2 / CIF | mipi2_csi2 → rkcif_mipi_lvds2 | mipi4_csi2 → rkcif_mipi_lvds4 |
| ISP | rkisp0_vir0 (rkisp0) | rkisp1_vir0 (rkisp1) |

　　注意 M1 时钟有两组复用: 本板 (与 6.1 官方 AIO-3588L 一致) 用
**mipim0_camera1_clk (GPIO1_B6)**, 不是第 5 节表里的 mipim1_camera1_clk
(GPIO3_A6)。MCLK 引脚配错 → sensor 无时钟, probe 读 ID 得 000000。

### 7.2 数据链路 (dts 全链)

```
CSI0 (rk3588-firefly-aio-3588l-mipi-csi0-imx415.dtsi):
  imx415-0 (i2c3 0x37)
    ====> mipidphy0_in_ucam1 (csi2_dphy0, data-lanes <1 2 3 4>)
    ----> csidphy0_out ----> mipi2_csi2 ----> cif_mipi2_in0 (rkcif_mipi_lvds2)
    ----> rkcif_mipi_lvds2_sditf ----> isp0_vir0 (rkisp0 + isp0_mmu)

CSI1 (rk3588-firefly-aio-3588l-mipi-csi1-imx415.dtsi):
  imx415-1 (i2c8 0x37)
    ====> mipidphy3_in_ucam1 (csi2_dphy1_hw + csi2_dphy3, data-lanes <1 2 3 4>)
    ----> csidphy3_out ----> mipi4_csi2 ----> cif_mipi4_in0 (rkcif_mipi_lvds4)
    ----> rkcif_mipi_lvds4_sditf ----> isp1_vir0 (rkisp1 + isp1_mmu)
```

　　要点:
- CSI1 的 dphy 是 dcphy1 的 dphy3 组, sensor 端点经 mipidphy3_in_ucam1
  挂 csi2_dphy3, 与 CSI0 的 csi2_dphy0 结构不同, 抄链时别混
- compatible = "sony,imx415" → drivers/media/i2c/imx415.c,
  CONFIG_VIDEO_IMX415=y
- **i2c8 为共享总线**: CSI1 sensor@0x37 与 LCD0 座触摸 goodix@0x14 共存
  (地址不同不冲突); i2cdetect 看到 0x37 显示 UU 属正常 (内核已占用)

### 7.3 板上实测结论

　　CSI1 (i2c8): probe 成功, 全链可用:

```
imx415 8-0037: Detected imx415 id 0000e0
rockchip-csi2-dphy csi2-dphy3: dphy3 matches m01_b_imx415 8-0037
# 取流时: s_stream: 1.  3864x2192, hdr: 0, bpp: 10
# AE 曝光/增益自动收敛, 正常关流 (s_stream: 0) —— 出图链路完整
```

　　CSI0 (i2c3): probe 失败:

```
imx415 3-0037: Unexpected sensor id(000000), ret(-5)
```

　　id 读到全 0 + ret(-5) (EIO) = I2C 完全无应答, 典型原因是**座上没插
模组**或模组供电/接线问题, 不是时序/驱动问题 (驱动问题通常是 probe
defer 或读到部分字节)。CSI0 待硬件确认后重测。

　　板上 media/video 节点分布 (双摄配置、CSI0 sensor 缺席时):

| 设备 | 归属 |
|---|---|
| /dev/media1 | rkcif-mipi-lvds4 (CSI1 cif) |
| /dev/media3 | rkisp (isp vir0, CSI1 链) |
| /dev/media0 | 缺失 (CSI0 链 sensor 未 probe, media 未注册) |
| video11~14 | stream_cif_mipi_id0~3 |
| video15~18 | rkcif_scale_ch0~3 |
| 共 21 个 video 节点 | cif + isp + scale 混编, 用 name 确认 |

### 7.4 验证测试

```
# sensor probe 与 dphy 匹配
dmesg | grep -iE "imx415|dphy.*match"
# 正常: Detected imx415 id 0000e0 + dphyN matches

# 拓扑
ls /dev/media*
media-ctl -p -d /dev/media1               # CSI1 cif 链
media-ctl -p -d /dev/media3               # isp 链

# 找 ISP MAINPATH 节点抓 NV12 (节点号以板上 name 为准)
grep -H '' /sys/class/video4linux/video*/name
v4l2-ctl -d /dev/videoXX --set-fmt-video=width=3840,height=2160,pixelformat=NV12 \
         --stream-mmap --stream-count=1 --stream-to=/tmp/f.raw

# 常见问题:
# 1. sensor id 000000 ret(-5): I2C 无应答 —— 没插模组/供电/接线, 先查硬件
# 2. 模组在位但读不到 ID: 量 MCLK (GPIO1_B6 / GPIO1_D6) 有无时钟,
#    核对 reset 极性 (本板均低有效)
# 3. media 设备缺失: 链上 sensor 没 probe 成功, rkcif/isp 不注册 media
# 4. CSI1 无图 CSI0 有图: 两链 dphy 组不同 (7.2), 别把 dphy0 的链抄给 dphy3
# 5. i2c8 上 0x14/0x37 有一方失联: 确认 DSI 屏座触摸 (0x14) 与 CSI1
#    sensor (0x37) 的供电独立, 一方坏不会拉死总线
```
