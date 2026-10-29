# CAN 总线适配笔记

## 1. RK3588 内置 CAN 控制器全景

| 控制器 | 地址 | compatible | 驱动 |
|---|---|---|---|
| can0 | fea50000 | rockchip,can-2.0 | rockchip_canfd.c |
| can1 | fea60000 | rockchip,can-2.0 | rockchip_canfd.c |
| can2 | fea70000 | rockchip,can-2.0 | rockchip_canfd.c |

说明:
- RK3588 内置 3 路 CAN-FD 控制器 (兼容 CAN 2.0), 收发器 (如 TJA1051)
  外接在芯片外, SOC 只出 TX/RX 两根信号
- 每路 CAN 有多个复用引脚组 (m0/m1), 按板子走线选一组
- 引脚互斥: can0m1 与 uart5m0 同引脚 (GPIO4_D4/D5), 选型时注意

常用引脚组 (rk3588s-pinctrl.dtsi, 已核实):

| 复用组 | RX | TX | func | 说明 |
|---|---|---|---|---|
| can0m0 | GPIO0_C0 | GPIO0_B7 | f11 | |
| can0m1 | GPIO4_D5 | GPIO4_D4 | f9 | 与 uart5m0 同引脚, 二选一 |
| can1m0 | GPIO3_B5 | GPIO3_B6 | f9 | |
| can1m1 | GPIO4_B2 | GPIO4_B3 | f12 | 板间最常用 |
| can2m0 | GPIO3_C4 | GPIO3_C5 | f9 | 与 uart5m1 同引脚, 二选一 |
| can2m1 | GPIO0_D4 | GPIO0_D5 | f10 | |

另: 引脚不够或路数不够时, 可用 SPI 外挂 MCP2518FD (见第 4 节)。

内核配置:

```
# defconfig 已开:
CONFIG_CAN=y
CONFIG_CANFD_ROCKCHIP=y          # 内置 CAN-FD 控制器
CONFIG_CAN_DEV=y

# firefly-linux.config (SPI 转 CAN):
CONFIG_CAN_MCP251XFD=m           # MCP2518FD
CONFIG_SPI=y
CONFIG_SPI_ROCKCHIP=y
```

## 2. 方式一: 内置 can1 — aio-3588q / itx-3588j

### 2.1 硬件连接

```
can1 (can1m1):
  RX ====> GPIO4_B2
  TX ====> GPIO4_B3
  外接 CAN 收发器 (板载 TJA1051 等), 收发器再接 CAN_H/CAN_L 差分总线
```

### 2.2 设备树配置

参考: rk3588-firefly-aio-3588q.dtsi (FF_CAN1)

```
&can1 {
	status = "okay";
	assigned-clocks = <&cru CLK_CAN1>;
	assigned-clock-rates = <200000000>;       // 200MHz CAN 内核时钟
	pinctrl-names = "default";
	pinctrl-0 = <&can1m1_pins>;
};
```

要点:
- assigned-clock-rates 200MHz 是推荐配置 (位时序参考它分频)
- can1m1_pins 在 pinctrl dtsi 里已定义, 直接引用即可
- 节点本身 (can@fea60000) 在 rk3588.dtsi 已有, 这里只做使能加引脚

## 3. 方式二: 内置 can2 — AIO-3588SG / aio-3588sjd4

### 3.1 硬件连接

```
can2 (can2m1):
  RX ====> GPIO0_D4
  TX ====> GPIO0_D5
```

### 3.2 设备树配置

参考: rk3588-firefly-aio-3588sjd4.dtsi (FF_CAN2)

```
&can2 {
	status = "okay";
	assigned-clocks = <&cru CLK_CAN2>;
	assigned-clock-rates = <200000000>;
	pinctrl-names = "default";
	pinctrl-0 = <&can2m1_pins>;
};
```

can0 同理 (can@fea50000, 引脚见第 1 节表格, 注意与 uart5 冲突)。

## 4. 方式三: SPI 外挂 MCP2518FD — robotic-evb-v11

### 4.1 硬件连接

```
MCP2518FD (SPI 转 CAN-FD):
  SPI: CLK/MOSI/MISO/CS# ====> spi0 (M2: GPIO1_PB3/PB1/PB2, CS=GPIO1_PB4)
  INT ====> GPIO4_D0 (低有效, 上拉)
  OSC  ====> 板载 40MHz 晶振 (配成 fixed-clock)
  收发器同内置 CAN (外接 TJA1051 类)
```

### 4.2 设备树配置

参考: rk3588-robotic-evb-v11.dtsi

```
/* 1. 晶振: 40MHz fixed clock */
/ {
	spi0_mcp2518fd_can0_osc: spi0-mcp2518fd-can0-osc {
		compatible = "fixed-clock";
		#clock-cells = <0>;
		clock-frequency = <40000000>;      // 按实际晶振填
	};
};

&spi0 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&spi0m2_cs0 &spi0m2_pins>;
	num_chipselect = <1>;                 // 硬 CS; 用 GPIO CS 时再加 cs-gpios

	mcp2518fd_can0: mcp2518fd@0 {
		compatible = "microchip,mcp2518fd";
		reg = <0>;                         // CS0
		spi-max-frequency = <10000000>;    // 10MHz
		clocks = <&spi0_mcp2518fd_can0_osc>;
		clock-names = "osc";               // 驱动拿它算位时序
		interrupt-parent = <&gpio4>;
		interrupts = <RK_PD0 IRQ_TYPE_LEVEL_LOW>;   // INT 低有效
		pinctrl-names = "default";
		pinctrl-0 = <&can0_int>;
	};
};

&pinctrl {
	can {
		can0_int: can0-int {
			rockchip,pins =
				<4 RK_PD0 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

robotic-evb-v11 第二路: spi4 (M2: GPIO1_PA2/PA0/PA1) 挂同款
mcp2518fd@0, INT = GPIO4_D1 (IRQ_TYPE_LEVEL_LOW), 写法对称。

### 4.3 要点

- compatible 是 "microchip,mcp2518fd" (MCP2518 与 MCP2517 同驱动 mcp251xfd)
- CONFIG_CAN_MCP251XFD=m 记得开 (firefly-linux.config 已有)
- 驱动以模块加载, ip 命令操作界面与内置 CAN 完全一致
- 40MHz 常见, 换 20MHz 晶振要同步改 clock-frequency, 否则位时序全错

## 5. 验证测试

```
# 1. 接口出现 (内置 canX / 外挂 spi 模式统一都是 canX)
ip link show                      # 应看到 can0/can1/can2
dmesg | grep -i -E "can|mcp2518"
# mcp251xfd 应报告: mcp251xfd spi0.0 can0: ... entered ... mode

# 2. 配置位速率并拉起 (500kbps 经典 CAN 最常用)
ip link set can0 type can bitrate 500000
ip link set can0 up

# CAN-FD (内置控制器支持):
ip link set can0 type can bitrate 1000000 dbitrate 5000000 fd on
ip link set can0 up

# 3. 环回自测 (不接总线也能测驱动)
ip link set can0 down
ip link set can0 type can bitrate 500000 loopback on
ip link set can0 up
candump can0 &
cansend can0 123#DEADBEEF         # 应在 candump 收到自己发的帧

# 4. 双机对测
# A 板: candump can0
# B 板: cansend can0 123#DEADBEEF
# A 板应收到; 收不到时:
#   - 量收发器 TX/RX 脚与 CAN_H/CAN_L 波形
#   - 检查两端共地、终端电阻 120R x2
#   - 两端位速率必须一致

# 5. 错误计数
ip -details -s link show can0     # RX/TX errors, bus-off 状态

# 常见问题:
# 1. canX 不出现: pinctrl 复用组选错/引脚被别的节点占用
# 2. bus-off: 波形有问题(终端电阻/速率不匹配), ip link set can0 down && up 恢复
# 3. mcp2518 不枚举: spi-max-frequency 过高, 晶振频率填错
# 4. 内置 can0 与 uart5 同时不通: can0m1 与 uart5m0 同引脚, 二选一
```
