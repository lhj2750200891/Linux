# CAN

　　K3 平台 CAN 适配笔记: 5 路经典 flexcan 控制器 (flexcan0-4,
"spacemit,k1-flexcan", 默认 CAN-FD 模式) + RCPU 域 rcan 组的引脚备份。
驱动是**上游 flexcan** (6.18 已拆分为 flexcan-core.c), defconfig 已编,
板级只需 pinctrl + bitrate。

## 1. 原理

### 1.1 控制器总表 (k3.dtsi 基座, 全部 disabled)

| 控制器 | 基址 | 中断 | 时钟域 |
|---|---|---|---|
| flexcan0 | 0xd4028000 | saplic 161 | CLK_APBC_CAN0 |
| flexcan1 | 0xd402c000 | saplic 163 | CLK_APBC_CAN1 |
| flexcan2 | 0xd4034000 | - | CLK_APBC_CAN2 |
| flexcan3 | 0xd4038000 | - | CLK_APBC_CAN3 |
| flexcan4 | 0xd403c000 | - | CLK_APBC_CAN4 |

- 节点名标签 flexcan0-4, 单元名 `fdcan@d4028000` — 标签与单元名
  不一致, 引用一律用 `&flexcanN`。
- compatible = "spacemit,k1-flexcan", 驱动
  `drivers/net/can/flexcan/flexcan-core.c` (CONFIG_CAN_FLEXCAN=y,
  defconfig 已编): 该 compatible 走 **CAN-FD** devtype
  (spacemit_k1_devtype_data_fd); 另有 "spacemit,k1-flexcan-can2.0"
  兼容串走经典 CAN 2.0 — 只要经典 CAN 时改 compatible 而不是靠参数。
- 基座自带 `fsl,clk-source = <0>` (peripheral 时钟源)。

### 1.2 与 RK3588 的差异

　　RK3588 无原生 CAN (靠 SPI-CAN/MCP251x 外挂), K3 是**原生 5 路
flexcan + FD**, 无需外挂控制器 — 板级工作量只有引脚组与位率。

## 2. 硬件连接

　　每组 CAN = TX + RX 两脚, 组内 bias-pull-up + drive-strength 25。
引脚组 (k3-pinctrl.dtsi, 每路多档 pad 可选):

| 路 | 档 0 | 档 1 | 档 2 |
|---|---|---|---|
| can0_x_cfg | pad11 tx / pad12 rx (func3) | pad44/45 (func3) | pad76/77 (func4) |
| can1_x_cfg | pad48 rx / pad49 tx (func3) | pad88/89 (func6) | pad109/110 (func4) |
| can2_x_cfg | pad50 tx / pad51 rx (func3) | pad86/87 (func4) | - |
| can3_x_cfg | pad80 rx / pad81 tx (func4) | pad103/104 (func4) | - |
| can4_x_cfg | pad40 tx / pad41 rx (func6) | (rcan 组见下) | 另有第 3 档 |

　　另有 RCPU 域备份组 rcan1-4_x_cfg (k3-pinctrl.dtsi L1816+, RCPU
引脚域), 用普通 APBC 域 CAN 即可, 不必碰。

接线核对要点:

- **TX/RX 组内顺序不统一**: can1_0_cfg 是 rx 在前 (pad48/49),
  can0_0_cfg 是 tx 在前 (pad11/12) — 照抄组不展开, 或展开时逐行核对
  注释。
- pad76/77 (can0 档 2) 与 pcie4 perst/clkreq (pad76/78 func5) 邻域、
  pad80/81 与 pcie4 wake/clkreq (pad80/78 func5) 同脚 — 冲突自查
  README 冲突表。
- 收发器 (TJA1050 类) 供电与 STB 脚: 软件只管 TX/RX, 收发器待机脚若
  接了 GPIO 需板级 regulator/GPIO-hog 初始化。

## 3. 内核配置

```
# k3_defconfig 已有:
CONFIG_CAN=y
CONFIG_CAN_FLEXCAN=y               # 上游 flexcan (flexcan-core.c)
CONFIG_CAN_DEV=y                   # 用户态 socketcan 基础 (随 CAN)
```

## 4. 设备树配置

### 4.1 单路使能 (flexcan0 为例, 其余同构)

```dts
&flexcan0 {
	pinctrl-names = "default";
	pinctrl-0 = <&can0_0_cfg>;         /* 基座组: pad11 tx / pad12 rx func3 */
	status = "okay";
};
```

　　位率不再写 dts (上游 flexcan 新内核用 ip 命令设), 要固定的话用
`assigned-clock-rates` 调 CAN 时钟基频, 或运行时:

```bash
ip link set can0 type can bitrate 500000 dbitrate 2000000 fd on
```

### 4.2 经典 CAN 2.0 (不用 FD)

```dts
&flexcan0 {
	compatible = "spacemit,k1-flexcan-can2.0";   /* 覆盖基座 compatible */
	pinctrl-names = "default";
	pinctrl-0 = <&can0_0_cfg>;
	status = "okay";
};
```

### 4.3 属性速查与陷阱

| 属性/节点 | 说明 |
|---|---|
| &flexcanN (标签) | 节点单元名是 fdcan@, 引用必须用标签 |
| compatible k1-flexcan | 默认 CAN-FD devtype |
| compatible k1-flexcan-can2.0 | 经典 CAN 2.0 |
| fsl,clk-source = <0> | 基座自带, 时钟源选择, 不动 |
| canN_X_cfg 组名 | 每路多档, 组内 TX/RX 顺序不一 (2 节) |

陷阱清单:

- **FD/经典模式选错**: compatible 默认 = FD; 对端是经典 CAN 时帧
  发不出去 (报错帧), 反向同理 — 两端先对模式。
- 引脚组档位与收发器接脚不符: TX/RX 量波形反了就是选错档或组内
  顺序看反。
- pad 冲突 (2 节): can0 档 2 与 pcie4、can1 档 2 (pad109/110) 与
  i2c4_3_cfg (pad111/112) 邻脚 — 全板引脚表排一次。
- 位率不配: socketcan 默认起不来 (ip link set 报 No such device 或
  state ERROR-ACTIVE 前无通信) — 记得 fd on 时补 dbitrate。

## 5. 验证测试

```bash
# 1. 接口出现
ip link show | grep can             # can0 等
dmesg | grep -i flexcan | head

# 2. 配置并拉起
ip link set can0 down
ip link set can0 type can bitrate 500000        # 经典 500k
#   FD: ip link set can0 type can bitrate 500000 dbitrate 2000000 fd on
ip link set can0 up
ip -details -s link show can0       # 位率/FD 能力/错误计数

# 3. 收发 (两路对接或 CAN 卡)
candump can0 &                      # A 板收
cansend can0 123#DEADBEEF           # B 板发 (或回环测试)

# 4. 回环自测 (无对端时)
ip link set can0 type can loopback on
ip link set can0 up
cansend can0 123#AA && candump can0 # 收到自己 = 控制器链路通

# 5. 排查顺序
#    a) 接口不在       -> CONFIG_CAN_FLEXCAN / pinctrl 组 status
#    b) ERROR-ACTIVE   -> 波形量 TX; 档位/组内顺序
#    c) 能发不能收     -> 收发器 RX 回来的方向; bitrate 对端
#    d) bus-off        -> 波特率两端不一致 / 终端电阻 120Ω x2
```
