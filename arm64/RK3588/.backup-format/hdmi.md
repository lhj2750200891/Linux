# HDMI 适配笔记

## 1. RK3588 HDMI 架构

| 控制器 | 地址 | PHY | 互斥 | VOP 数据源 |
|---|---|---|---|---|
| hdmi0 | fde80000 | hdptxphy0 | 与 eDP0 共享 PHY, 二选一 | vp0/vp1/vp2 |
| hdmi1 | fdea0000 | hdptxphy1 | 与 eDP1 共享 PHY, 二选一 | vp0/vp1/vp2 |
| hdmirx_ctrler | fdee0000 | 内置 | 仅 RK3588 (非 RK3588S) | (显示输入) |

说明:
- RK3588 有 2 个 HDMI TX (DW HDMI) + 1 个 HDMI RX (仅 RK3588 全功能版),
  RK3588S 无 HDMI RX
- 用了 eDP0 就不能同时用 HDMI0 (hdptxphy0 被占), eDP1/HDMI1 同理,
  规划显示接口先定 PHY 分配
  (如 AIO-3588SG 用了 eDP0, 因此没有 HDMI)
- HDMI TX 引脚 (CEC/SCL/SDA/HPD) 由节点默认 pinctrl 指定,
  一般不需要改; 板级只需配 enable-gpios (HDMI 电源使能脚)

内核配置 (defconfig 已开):

```
CONFIG_ROCKCHIP_DW_HDMI=y          # HDMI TX 控制器
CONFIG_ROCKCHIP_DW_HDMI_QP=y       # RK3588 DW HDMI QP 版本
CONFIG_ROCKCHIP_HDMITX_HDMI_PHY=y  # hdptxphy (RK3588 HDMI PHY)
CONFIG_ROCKCHIP_HDMIRX=y           # HDMI RX (需要 HDMI 输入时)
```

## 2. 方式一: 单 HDMI (hdmi0) — aio-3588q / jd4 / sjd4 等

### 2.1 硬件连接

```
HDMI TX0 (差分对直接走连接器, 由 hdptxphy0 输出, 无需设备树引脚配置):
  CEC  ====> GPIO4_C1 (hdmim0_tx0_cec, 节点默认)
  HPD  ====> GPIO1_A5 (hdmim0_tx0_hpd, 节点默认)
  DDC SCL ====> GPIO4_B7 (hdmim0_tx0_scl, 节点默认)
  DDC SDA ====> GPIO4_C0 (hdmim0_tx0_sda, 节点默认)
  HDMI 5V 电源使能 ====> GPIO4_A0 (enable-gpios, 高有效)
```

### 2.2 设备树配置

参考: rk3588-firefly-common.dtsi (FF_HDMI0)

```
&hdmi0 {
	enable-gpios = <&gpio4 RK_PA0 GPIO_ACTIVE_HIGH>;   // HDMI 电源使能, 无此脚可去掉
	status = "okay";
};

&hdmi0_in_vp0 {
	status = "okay";               // VOP VP0 -> HDMI0
};

&hdptxphy0 {
	status = "okay";               // HDMI0 PHY (与 eDP0 互斥!)
};

&route_hdmi0 {
	status = "okay";
	connect = <&vp0_out_hdmi0>;    // 显示路由
};

/* 音频部分见声卡模块 (hdmi0_sound + i2s5_8ch), 不需要 HDMI 音频可省略 */
&i2s5_8ch {
	status = "okay";
};
```

注意:
- enable-gpios 各板不同: 常见默认 GPIO4_A0;
  roc-rk3588-rt 板为 GPIO4_B0 (hdmi0) / GPIO4_B1 (hdmi1), 照原理图改
- VOP 数据源可选 vp0/vp1/vp2, 与板上其他显示接口统一规划
  (VP0 带宽最高, 4K@60 建议 VP0; Firefly 板 HDMI0 默认 vp0)

## 3. 方式二: 双 HDMI (hdmi0 + hdmi1) — itx-3588j

itx-3588j 同时定义 FF_HDMI0 + FF_HDMI1。

### 3.1 硬件连接

```
HDMI TX0: CEC GPIO4_C1 / HPD GPIO1_A5 / SCL GPIO4_B7 / SDA GPIO4_C0
          电源使能 ====> GPIO4_A0
HDMI TX1: CEC GPIO3_C4 (hdmim2_tx1_cec) / HPD GPIO1_A6 (hdmim0_tx1_hpd)
          SCL GPIO3_C6 (hdmim1_tx1_scl) / SDA GPIO3_C5 (hdmim1_tx1_sda)
          电源使能 ====> GPIO3_D0
```

(hdmi1 的 pinctrl 由节点默认指定: hdmim2_tx1_cec + hdmim0_tx1_hpd
 + hdmim1_tx1_scl + hdmim1_tx1_sda)

### 3.2 设备树配置

在方式一基础上增加 hdmi1:

```
&hdmi1 {
	enable-gpios = <&gpio3 RK_PD0 GPIO_ACTIVE_HIGH>;
	status = "okay";
};

&hdmi1_in_vp1 {
	status = "okay";               // VOP VP1 -> HDMI1
};

&hdptxphy1 {
	status = "okay";               // HDMI1 PHY (与 eDP1 互斥!)
};

&route_hdmi1 {
	status = "okay";
	connect = <&vp1_out_hdmi1>;
};

&i2s6_8ch {                       // 音频, 见声卡模块
	status = "okay";
};
```

## 4. HDMI 输入 (HDMI RX) — itx-3588j / aio-3588q (FF_HDMIRX)

### 4.1 硬件连接

```
HDMI RX (差分对直连 hdmirx 控制器):
  CEC    ====> GPIO3_D1 (hdmim1_rx_cec)
  DDC SCL ====> GPIO3_D2 (hdmim1_rx_scl)
  DDC SDA ====> GPIO3_D3 (hdmim1_rx_sda)
  HPDIN  ====> GPIO3_D4 (hdmim1_rx_hpdin)
  输入检测 DET ====> GPIO1_D5 (低有效, hdmirx-det-gpios)
```

### 4.2 设备树配置

```
&hdmirx_ctrler {
	status = "okay";
	#sound-dai-cells = <1>;
	pinctrl-names = "default";
	pinctrl-0 = <&hdmim1_rx &hdmirx_det>;
	/* Effective level used to trigger HPD: 0-low, 1-high */
	hpd-trigger-level = <1>;
	hdmirx-det-gpios = <&gpio1 RK_PD5 GPIO_ACTIVE_LOW>;   // HDMIIRX_DET_L
};

&pinctrl {
	hdmirx {
		hdmirx_det: hdmirx-det {
			rockchip,pins = <1 RK_PD5 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};

&i2s7_8ch {                       // HDMI RX 音频, 见声卡模块
	status = "okay";
};
```

## 5. 验证测试

```
# HDMI TX
ls /sys/class/drm/
# 应看到 card?-HDMI-A-1 (hdmi0) / card?-HDMI-A-2 (hdmi1)

cat /sys/class/drm/card*-HDMI-A-1/status    # 接显示器后为 connected
cat /sys/class/drm/card*-HDMI-A-1/edid | edid-decode

# 点亮指定模式
modetest -M rockchip -s <conn_id>:<mode_id>

# dmesg
dmesg | grep -i -E "hdmi|dw-hdmi"
# 正常应看到: dw-hdmi ... hdmi0 探测, hdptxphy 初始化

# HDMI RX (itx/q 板)
dmesg | grep -i hdmirx
# 插入输入源后应看到信号锁定, 分辨率打印
v4l2-ctl --list-devices          # hdmirx 枚举为 video 设备
v4l2-ctl -d /dev/videoX --all    # 查看当前输入格式

# 常见问题:
# 1. status 一直 disconnected: enable-gpios 电源脚极性错, 或 HPD 引脚被复用
# 2. 8K/4K120 点不亮: 检查内核 dmc/带宽策略与 VOP 通道分配 (需 VP0)
# 3. 无图像: route_hdmi0/hdmi0_in_vp0 忘记使能
# 4. HDMI RX 无信号: hdmirx-det-gpios 极性错/未插紧
```
