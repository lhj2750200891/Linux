# 调试串口

　　K3 平台调试串口适配笔记: SoC 首选调试口 uart0 (ttyS0, 115200) 从
bootloader 到内核的全链路。以 Firefly AIBOX-PRO-K3 为参考板, 覆盖引脚复用
(三种位置)、console 双阶段 (SBI earlycon + 内核 ttyS0) 与基座节点"默认
okay 但没引脚"的陷阱。

## 1. 原理

### 1.1 uart0 控制器与驱动栈

　　K3 的 uart0 在 k3.dtsi 基座 (`uart0: serial@d4017000`), compatible
"spacemit,k1-uart" + "intel,xscale-uart", 走标准 **8250 驱动栈**:

- `drivers/tty/serial/8250/8250_of.c` 按第二个 compatible
  ("intel,xscale-uart") 匹配, 端口类型 PORT_XSCALE; `reg-shift = <2>`、
  `reg-io-width = <4>`、fifo 256。
- 内核配置 k3_defconfig 已全开: `CONFIG_SERIAL_8250=y`、
  `CONFIG_SERIAL_8250_CONSOLE=y`、`CONFIG_SERIAL_OF_PLATFORM=y`、
  `CONFIG_SERIAL_8250_NR_UARTS=17` (uart0-10 + RCPU 的 r_uart0/r_uart1 都
  算在内)。
- **基座节点默认 `status = "okay"` 但没有任何 pinctrl 属性** — pad 复用不配,
  引脚不出串口波形。Firefly 的 FF_DEBUG_115200 宏分支本质上只做一件事: 给
  uart0 补上 pinctrl (名字里的 115200 指的是 bootargs 的波特率, 不是时钟
  改动)。

### 1.2 console 的两阶段来源

　　common.dtsi 的 chosen (板级文件禁用后必须自己写):

```c
chosen {
	bootargs = "earlycon=sbi console=ttyS0,115200 loglevel=8 ...";
	stdout-path = "serial0:115200";
};
```

- `earlycon=sbi`: 最早的输出走 **RISC-V SBI (OpenSBI/ESOS) 的 console 调用**,
  不依赖内核 8250 驱动加载, 覆盖从内核解压起的窗口; 没有它, 内核前段日志
  (setup_arch 之前) 在串口上是空窗。
- `console=ttyS0,115200`: 正式 console, ttyS0 由 aliases 决定 — k3.dtsi 基座
  已写 `serial0 = &uart0`, 所以 ttyS0 = uart0 (r_uart0/r_uart1 是 RCPU 域
  串口, 排 serial11/12)。
- `loglevel=8`: 调试期全量日志; 量产可降到 4。

### 1.3 何时需要动设备树

| 场景 | 要做的事 |
|---|---|
| 只想用 uart0 做调试口 | 只补 `&uart0 { pinctrl-0 = <&uart0_0_cfg>; }` (3.1 节) |
| 调试口换到别的复用位置 | 换 uart0_1_cfg / uart0_2_cfg (3.2 节) |
| 追加普通串口 (如 RS485/RS232) | 同框架, 换 uartN 节点与其 cfg 组, 思路完全一致 |

## 2. 硬件连接

　　参考板: AIBOX-PRO-K3。调试口是 3.3V TTL 电平, 板上引到调试排针/Type-C
调试板, 接 USB-TTL 线三根即可:

| 信号 | pad 全局号 | 复用功能号 | 方向 | 接 USB-TTL |
|---|---|---|---|---|
| uart0 TX | pad 149 | func 2 | SoC 发 | 接线 RXD |
| uart0 RX | pad 150 | func 2 | SoC 收 | 接线 TXD |
| GND | - | - | - | 接线 GND |

接线核对要点:

- **pad 编号与 GPIO 编号是两个空间**: GPIO 只有 0..127 (func 0), pad 总数到
  200+; pad 149/150 超出 GPIO 空间, 是专用 pad, 无"GPIO 复用"干扰。
- 电气参数 (k3-pinctrl.dtsi 原始组): `bias-pull-up; drive-strength = <25>;`,
  无 power-source 属性 (默认 3.3V 域)。
- 波特率 115200 8N1 无流控; 串口乱码优先查晶振/时钟树 (K3 的
  CLK_MPMU_SLOW_UART), 其次查地线。
- TX/RX 接反是最常见错误: 板端 TX 必接 USB-TTL 的 RXD (写 dts 时
  pinmux 列表顺序是 tx 在前、rx 在后, 别凭记忆写反, 从 k3-pinctrl.dtsi
  核实)。

## 3. 内核配置

　　k3_defconfig 已齐, **无需改动**:

```
CONFIG_SERIAL_8250=y            # 8250 驱动本体
CONFIG_SERIAL_8250_CONSOLE=y    # console 支持
CONFIG_SERIAL_OF_PLATFORM=y     # 按设备树节点枚举串口
CONFIG_SERIAL_8250_NR_UARTS=17
CONFIG_SERIAL_8250_RUNTIME_UARTS=17
```

　　earlycon 无需单独配置项 (8250_early 内建于 CONSOLE); `earlycon=sbi` 需要
固件侧 OpenSBI/ESOS 的 console 服务, bootloader 阶段已配好。

## 4. 设备树配置

　　参考板: AIBOX-PRO-K3 (FF_DEBUG_115200 分支)。aliases/chosen 在基座
common 文件里, 禁用公共文件后要自己补; 以下为自研板完整写法:

### 4.1 方式一: 标准调试口 (uart0 @ pad 149/150)

```dts
/ {
	chosen {
		bootargs = "earlycon=sbi console=ttyS0,115200 loglevel=8";
		stdout-path = "serial0:115200";
	};
};

&uart0 {
	pinctrl-names = "default";
	pinctrl-0 = <&uart0_0_cfg>;
	status = "okay";
};
```

　　`uart0_0_cfg` 组已在 k3-pinctrl.dtsi 基座定义 (pad 149/150 func 2), 直接
引用即可, 无需自己写 pinctrl 节点。uart0 本体也在基座, 不用重写。

### 4.2 方式二: 调试口换复用位置

　　k3-pinctrl.dtsi 给 uart0 预置了三组位置, 换 `pinctrl-0` 即可, 引脚如下
(均 bias-pull-up, drive-strength 25):

| cfg 组 | TX pad | RX pad | 复用功能号 | 适用 |
|---|---|---|---|---|
| uart0_0_cfg | 149 | 150 | func 2 | AIBOX-PRO 调试排针位置 |
| uart0_1_cfg | 132 | 133 | func 2 | 自研板走线更近的另一组 pad |
| uart0_2_cfg | 145 | 146 | func 5 | 第三位置 |

```dts
&uart0 {
	pinctrl-names = "default";
	pinctrl-0 = <&uart0_1_cfg>;      /* 换位置只改这一行 */
	status = "okay";
};
```

### 4.3 属性速查与陷阱

| 属性/节点 | 说明 |
|---|---|
| chosen/bootargs | console 与 earlycon 全在这里; 公共文件禁用后必须自己写 |
| stdout-path | 固件/内核选默认输出串口, 与 bootargs 的 console 保持一致 |
| aliases | 基座已把 serial0..10 映射到 uart0..10, ttyS0 即 uart0 |
| pinctrl-0 | **不配则无波形** (基座节点默认 okay 但不带 pinctrl) — 最大陷阱 |
| dmas | uart0 基座未带 DMA, 高吞吐场景自加 (k3-dmac) |

陷阱清单:

- 内核到 `start_kernel` 前的日志缺失: 忘了 `earlycon=sbi` (或 bootloader 阶段
  固件 console 没使能)。
- `console=ttyS0` 无输出但 earlycon 有: pinctrl 没配或配错组 (earlycon 阶段
  bootloader 已把 pad 复用成 uart0, 进内核后 pinctrl 驱动按节点重配, 错组即
  恢复成 GPIO 功能)。
- 波特率不匹配: U-Boot 阶段输出正常、内核阶段乱码 → 检查 bootargs 的
  `,115200` 与 stdout-path 是否一致。
- 若调试口被自研板挪作他用 (如 RS485), 别再给 uart0 配 pinctrl, 同时 bootargs
  去掉 console=ttyS0, 否则半双工总线上持续输出内核日志。

## 5. 验证测试

```bash
# 1. 串口驱动与 console 生效 (应有 ttyS0 且带 console 标记)
cat /proc/tty/driver/serial | head
cat /proc/consoles                    # 看 ttyS0 是否在列及是否 C (console)

# 2. 内核参数核实
cat /proc/cmdline                     # earlycon=sbi console=ttyS0,115200 应在

# 3. 回环测试 (短接板端 TX/RX 后, 收到自己发的字符即 PHY/pinctrl 正确)
stty -F /dev/ttyS0 115200 raw -echo
( cat /dev/ttyS0 & ) ; echo "loopback" > /dev/ttyS0

# 4. 引脚复用状态核实 (pad 149/150 应处于 uart0-0-cfg 组)
cat /sys/kernel/debug/pinctrl/*/pinmux-pins | grep -E "149|150"

# 5. earlycon 阶段验证: 重启观察
#    从"内核解压/SBI 横幅"起就有输出 = earlycon 正常;
#    "Starting kernel ..." 后静默一段才出日志 = earlycon 缺失 (只有 console 生效)

# 6. dmesg 侧确认注册
dmesg | grep -E "ttyS0|8250" | head
```
