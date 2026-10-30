# MCP2518FD 模块完整适配指南

> 适用平台：SpacemiT K3 / Firefly AIBOX-PRO-K3 / Linux 6.18 SDK  
> 目标器件：Microchip MCP2518FD，40 MHz 外部晶振，SPI 接口，CAN FD  
> 文档日期：2026-08-08  
> SDK 根目录：`/media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18`

## 1. 文档目标和当前结论

本文整理本项目中 MCP2518FD 从硬件连线、IO 电压、设备树、内核配置、K3 SPI 控制器驱动、编译打包、烧录、启动、回环、压力测试到故障诊断的完整适配内容，供后续重新移植时逐项复现。

需要先明确两点：

1. 当前软件已经达到以下阶段：MCP2518FD 能被识别，`can0` 能启动，内部 CAN FD 回环曾连续成功，CAN 中断也能正常增长。
2. 当前仍存在过间歇性发送失败，最新的软件缓解是在设备树增加 `spi-cs-inactive-delay-ns = <2000>;`。该修改需要完成连续压力测试后才能确认最终稳定。

因此，本文可以最大限度避免遗漏，但不能在以下硬件条件仍然存在时承诺“一定一次成功”：

- CAN_INT 仍通过 4.7 kΩ 上拉到 5 V，而 K3 GPIO56 配置为 3.3 V IO。
- K3 的 SPI MOSI/MISO/SCK/CS 配置为 1.8 V，必须确认 MCP2518FD 模块板上存在可靠的双向/单向电平转换；如果是 1.8 V 直接连接 MCP2518FD 数字引脚，则不满足器件输入高电平规范。

## 2. 一次适配成功的必要条件

开始修改软件前，先确认以下全部条件。任意一项不满足，都可能表现为偶发 CRC 错误、读取全 `0xff`、发送不触发 TXREQ、无中断或 `can0 up` 失败。

### 2.1 硬件必要条件

- MCP2518FD 的实际型号、焊接方向、供电和地连接正确。
- MCP2518FD 使用 40 MHz 晶振或有源时钟，设备树频率必须和实测频率一致。
- SPI 信号对应关系正确：SoC MOSI 接模块 SDI，SoC MISO 接模块 SDO，SCK 接 SCK，CS 接 nCS。
- K3 和 MCP2518FD 共地。
- SPI 四根信号电压兼容；K3 当前为 1.8 V IO。
- CAN_INT 输入 K3 GPIO56 前不得超过该 GPIO 的允许电压。
- CANH/CANL 连接到 CAN 收发器而不是直接连接 MCP2518FD 控制器数字引脚。
- 外部总线测试时，总线两端各有 120 Ω 终端电阻；内部回环测试不依赖 CANH/CANL 和终端电阻。
- 供电上升和复位满足 MCP2518FD 数据手册要求，启动期间 nCS 不应被异常拉低。

### 2.2 软件必要条件

- 使用正确的 K3 SPI 控制器节点 `&rspi0`。
- SPI 控制器驱动必须使用本文所述异步 `transfer_one()` 状态机，不能恢复为旧的 `transfer_one_message()` 实现。
- 设备树使用 40 MHz 时钟、GPIO56 下降沿中断、1 MHz SPI 起始频率和 2 µs CS 非活动时间。
- 内核启用 CAN、CAN RAW、MCP251XFD、SPI K1 和 REGMAP SPI。
- Buildroot 启用 `can-utils`。
- 修改设备树后更新 DTB；修改 SPI 驱动或内核配置后同时更新 Image 和 DTB。
- 烧录后确认设备实际启动的是新 `bootfs.img`，不能只看宿主机输出文件时间。

## 3. 最终软件架构

数据和控制路径如下：

```text
SocketCAN / can-utils
        |
Linux mcp251xfd 驱动
        |
Linux SPI core
        |
drivers/spi/spi-spacemit-k1.c
        |
K3 rspi0 控制器
        |
MOSI/MISO/SCK/nCS
        |
MCP2518FD ---- CAN 收发器 ---- CANH/CANL
        |
      CAN_INT
        |
K3 GPIO56 / J2-214
```

当前 Linux 中显示为 `spi4.0` 是 SPI core 分配的运行时总线编号，不代表使用了设备树中的第 4 个控制器。设备树实际节点仍是 `rspi0@c0885000`。

## 4. 硬件引脚对应

### 4.1 J2、SoC Pad 和设备树对应表

| MCP2518FD 模块信号 | J2 物理引脚 | K3 Pad/GPIO | K3 复用功能 | 设备树对象 |
|---|---:|---:|---|---|
| SPI1_MOSI | 106 | Pad 60 | `rssp0 tx` | `rssp0_0_cfg` |
| SPI1_MISO | 110 | Pad 61 | `rssp0 rx` | `rssp0_0_cfg` |
| SPI1_SCK | 108 | Pad 62 | `rssp0 clk` | `rssp0_0_cfg` |
| SPI1_CS_N | 112 | Pad 63 | `rssp0 frm` | `rssp0_0_cfg` |
| CAN_INT | 214 | GPIO56 / Pad 56 | GPIO 中断输入 | `spi_can_int_cfg` |

注意：J2 的物理引脚 214 和 SoC 的 GPIO56 是两套编号，不能把 `214` 写进 `K3_GPIO()`。

### 4.2 SPI 方向检查

| K3 侧名称 | SPI 主机方向 | MCP2518FD 引脚 |
|---|---|---|
| `rssp0 tx` / MOSI | K3 输出 | SDI 输入 |
| `rssp0 rx` / MISO | K3 输入 | SDO 输出 |
| `rssp0 clk` | K3 输出 | SCK 输入 |
| `rssp0 frm` | K3 输出 | nCS 输入 |

如果 MOSI/MISO 互换，可能看到设备完全无响应、读取全 `0xff` 或 CRC 校验失败。

## 5. 电压域和硬件风险

### 5.1 SPI 电压

当前设备树将 SPI 四根信号配置为 1.8 V：

```dts
rssp0-0-cfg {
	...
	power-source = <1800>;
};
```

MCP2518FD 数据手册 DS20006027B 给出的 VDD 工作范围为 2.7 V～5.5 V，数字输入高电平门限最小值为 `0.7 × VDD`。因此：

- MCP2518FD 供电 2.7 V 时，VIH 最小值为 1.89 V，1.8 V 已低于规范。
- MCP2518FD 供电 3.3 V 时，VIH 最小值为 2.31 V。
- MCP2518FD 供电 5 V 时，VIH 最小值为 3.5 V。

结论：除非模块板上带有电平转换，否则 K3 的 1.8 V MOSI/SCK/CS 不能直接可靠驱动 MCP2518FD。偶尔可识别不代表满足电气规范。

重新适配前必须完成以下测量：

1. 断电测量模块 SPI 信号是否经过电平转换器或串联网络。
2. 上电测量 MCP2518FD 芯片实际 VDD。
3. 示波器测量 MCP2518FD 引脚处的 MOSI、SCK、nCS 高电平幅值，而不是只测 K3 连接器侧。
4. 测量 SDO 返回 K3 MISO 的高电平，确保不超过 K3 1.8 V 输入域允许值。

如果模块没有电平转换，必须增加电平转换电路。仅降低 SPI 频率不能修复直流输入门限不满足的问题。

### 5.2 CAN_INT 电压

当前软件配置：

```dts
power-source = <3300>;
bias-pull-up;
```

当前硬件状态：CAN_INT 通过 4.7 kΩ 上拉到 5 V。

已读取到 MCP2518FD `IOCON=0x03000003`，其中 `INTOD` 位未置位，说明当前 INT 输出为推挽模式，而不是开漏模式。推挽输出通常不需要外部上拉。

建议的最终硬件方案，按优先级选择：

1. 移除 5 V 外部上拉，让 MCP2518FD 推挽 INT 通过合适电平转换后进入 GPIO56。
2. 如果模块 INT 输出本身是 3.3 V 且满足 GPIO56 输入规范，可直接进入 GPIO56，不要再上拉到 5 V。
3. 如果必须使用开漏 INT，则需要在驱动中明确配置 `INTOD`，并把外部上拉接到 GPIO56 可接受的电压，不能默认当前驱动已配置开漏。

在硬件尚未修改前，本文保留当前 GPIO56 软件配置，以避免破坏已经能够工作的中断链路；但这不是推荐的最终电气方案。

## 6. 需要保留和修改的文件

以下路径均相对 SDK 根目录：

| 文件 | 作用 | 修改后是否需要编译内核 Image |
|---|---|---|
| `bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit/k3-firefly-aibox-pro.dts` | 板级入口、功能宏和 include | 否，只编 DTB |
| `bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit/k3-firefly-aibox-pro.dtsi` | MCP 时钟、SPI 从设备、中断和 pinctrl | 否，只编 DTB |
| `bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit/aibox-pro-test.dtsi` | 当前工程中的型号兼容字符串覆盖 | 否，只编 DTB |
| `bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit/k3-rdomain.dtsi` | K3 `rspi0` 控制器基础节点 | 否，只编 DTB |
| `bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit/k3-pinctrl.dtsi` | Pad 60～63 的 SPI 复用 | 否，只编 DTB |
| `bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit/Makefile` | 把目标 DTB 加入 Kbuild | 否，只编 DTB |
| `bsp-src/linux-6.18/arch/riscv/configs/firefly-linux.config` | CAN/SPI 内核配置 | 是 |
| `bsp-src/linux-6.18/drivers/spi/spi-spacemit-k1.c` | K1/K3 SPI 控制器驱动 | 是 |
| `buildroot-ext/configs/spacemit_firefly-k3-aibox-pro_defconfig` | `can-utils` 用户态工具 | 仅重建根文件系统时需要 |
| `aibox-pro-build.sh` | DTB/Image 增量编译和 `bootfs.img` 更新 | 脚本本身不进入目标系统 |
| `arch/riscv/boot/dts/spacemit/can_test.sh` | 板端诊断脚本源文件 | 不需要编译，复制到板端即可 |

## 7. 设备树完整适配

### 7.1 板级入口

文件：`k3-firefly-aibox-pro.dts`

必须打开功能宏并 include 实际板级 DTSI：

```dts
#define FF_SPI_CAN

#include "k3-firefly-aibox-pro.dtsi"
#include "aibox-pro-test.dtsi"

/ {
	model = "spacemit AIBOX-PRO-K3 board";
	compatible = "spacemit,k3-com260";
};
```

当前工程通过 `aibox-pro-test.dtsi` 覆盖具体型号：

```dts
#ifdef FF_SPI_CAN
&mcp251xfd {
	compatible = "microchip,mcp2518fd";
};
#endif
```

后续重新适配时，推荐直接在主 MCP 节点写：

```dts
compatible = "microchip,mcp2518fd";
```

这样不再依赖测试 DTSI 的覆盖顺序。确认其他功能不依赖 `aibox-pro-test.dtsi` 后，才可以删除该 include；不要为了整理 MCP 节点而误删其他板级测试配置。

### 7.2 40 MHz 固定时钟

在根节点中增加：

```dts
#ifdef FF_SPI_CAN
	mcp251xfd_clk: mcp251xfd-clk {
		compatible = "fixed-clock";
		#clock-cells = <0>;
		clock-frequency = <40000000>;
	};
#endif
```

`clock-frequency` 必须填写 MCP2518FD 实际 OSC1/OSC2 时钟，不是 CAN 仲裁波特率，也不是 SPI 时钟。

### 7.3 K3 SPI 控制器基础节点

文件：`k3-rdomain.dtsi`

```dts
rspi0: rspi0@c0885000 {
	compatible = "spacemit,k3-spi";
	reg = <0x0 0xc0885000 0x0 0x30>;
	interrupt-parent = <&saplic>;
	interrupts = <269 IRQ_TYPE_LEVEL_HIGH>;
	clocks = <&syscon_rcpu_spictrl CLK_RCPU_SPICTRL_RSPI0>,
		 <&syscon_rcpu_spictrl CLK_RCPU_SPICTRL_RSPI0_BUS>;
	clock-names = "func", "bus";
	resets = <&syscon_rcpu_spictrl RESET_RCPU_SPICTRL_RSPI0>;
	spi-max-frequency = <51200000>;
	#address-cells = <1>;
	#size-cells = <0>;
	status = "disabled";
};
```

关键点：

- `compatible` 必须被 SPI 驱动匹配。
- 驱动按名字获取 `func` 和 `bus` 两个时钟，`clock-names` 不能省略或调换为其他名字。
- 基础节点保持 `disabled`，由板级 `&rspi0` 覆盖为 `okay`。
- 控制器上限 51.2 MHz 不代表 MCP2518FD 初始适配也使用该频率。

### 7.4 SPI pinctrl 基础复用

文件：`k3-pinctrl.dtsi`

```dts
rssp0_0_cfg: rssp0-0-cfg {
	rssp0-0-pins {
		pinmux = <K3_PADCONF(60, 3)>, /* rssp0 tx */
			 <K3_PADCONF(61, 3)>, /* rssp0 rx */
			 <K3_PADCONF(62, 3)>; /* rssp0 clk */
		bias-disable;
		drive-strength = <25>;
	};

	rssp0-1-pins {
		pinmux = <K3_PADCONF(63, 3)>; /* rssp0 frm */
		bias-pull-up;
		drive-strength = <25>;
	};
};
```

nCS 空闲应为高，因此 CS pin 保留上拉有利于上电期间不误选中器件。

### 7.5 MCP2518FD 节点

文件：`k3-firefly-aibox-pro.dtsi`

推荐最终合并为以下内容：

```dts
#ifdef FF_SPI_CAN
&rspi0 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&rssp0_0_cfg>;

	mcp251xfd: canfd@0 {
		status = "okay";
		compatible = "microchip,mcp2518fd";
		reg = <0>;
		clocks = <&mcp251xfd_clk>;

		pinctrl-names = "default";
		pinctrl-0 = <&spi_can_int_cfg>;
		interrupt-parent = <&gpio>;
		interrupts = <K3_GPIO(56) IRQ_TYPE_EDGE_FALLING>;

		spi-max-frequency = <1000000>;
		spi-cs-inactive-delay-ns = <2000>;
	};
};
#endif
```

属性说明：

| 属性 | 当前值 | 说明 |
|---|---:|---|
| `compatible` | `microchip,mcp2518fd` | 明确匹配 MCP2518FD 型号和对应 quirks |
| `reg` | 0 | 使用 rspi0 的硬件片选 0 |
| `clocks` | 40 MHz fixed-clock | MCP2518FD 系统时钟 |
| `interrupts` | GPIO56 下降沿 | INT 空闲高、有效低时产生下降沿 |
| `spi-max-frequency` | 1 MHz | 当前保守稳定值，先不要提高 |
| `spi-cs-inactive-delay-ns` | 2000 ns | 强制两次 SPI 命令之间的 nCS 高电平间隔 |

MCP251XFD binding 要求 SPI 频率不超过器件时钟的一半。40 MHz 时理论上限为 20 MHz，但当前平台先固定 1 MHz，只有完成稳定性验证和波形检查后才考虑提高。

### 7.6 GPIO56 和 SPI 电压覆盖

文件：`k3-firefly-aibox-pro.dtsi`

```dts
#ifdef FF_SPI_CAN
spi_can_int_cfg: spi-can-int {
	spi-can-int-pin {
		pinmux = <K3_PADCONF(56, 0)>;
		drive-strength = <25>;
		power-source = <3300>;
		bias-pull-up;
	};
};

rssp0-0-cfg {
	rssp0-0-pins {
		power-source = <1800>;
	};

	rssp0-1-pins {
		power-source = <1800>;
	};
};
#endif
```

这里的 `rssp0-0-cfg` 是对已有 label 节点内容的板级补充，不要重新声明同名 label。GPIO56 当前保持 3.3 V 和内部上拉，是为了不破坏已经工作过的中断配置。

### 7.7 DTB Makefile

文件：`arch/riscv/boot/dts/spacemit/Makefile`

```make
dtb-$(CONFIG_SOC_SPACEMIT_K3) += k3-firefly-aibox-pro.dtb
```

没有此项时，常规 Kbuild 不会生成目标 DTB。

### 7.8 设备树 schema 注意事项

Linux SPI core 已经解析：

```text
spi-cs-setup-delay-ns
spi-cs-hold-delay-ns
spi-cs-inactive-delay-ns
```

本地通用 schema 位于：

```text
Documentation/devicetree/bindings/spi/spi-peripheral-props.yaml
```

本地 MCP binding 位于：

```text
Documentation/devicetree/bindings/net/can/microchip,mcp251xfd.yaml
```

如果执行 `dtbs_check` 时提示 `spi-cs-inactive-delay-ns` 不允许，应让 MCP binding 引用通用 SPI 外设属性 schema，而不是删除运行时需要的 CS 延时。例如在 `allOf` 中加入：

```yaml
allOf:
  - $ref: /schemas/spi/spi-peripheral-props.yaml#
  - $ref: can-controller.yaml#
```

该 schema 修改只影响文档校验，不改变运行时行为。

## 8. 内核配置

文件：`arch/riscv/configs/firefly-linux.config`

至少需要：

```text
CONFIG_CAN=y
CONFIG_CAN_RAW=y
CONFIG_CAN_DEV=y
CONFIG_SPI=y
CONFIG_SPI_K1=y
CONFIG_REGMAP_SPI=y
CONFIG_CAN_MCP251XFD=y
```

当前构建目录 `.config` 还包含：

```text
CONFIG_MMP_PDMA=y
```

说明：

- `CONFIG_CAN_MCP251XFD=y` 把驱动内建进内核，启动阶段即可 probe。
- `CONFIG_REGMAP_SPI=y` 支持 MCP251XFD 的 SPI regmap。
- `CONFIG_MMP_PDMA=y` 允许 K1 SPI 驱动申请 DMA；如果没有 DMA channel，当前驱动会回退到 PIO。
- MCP2518FD 的短寄存器访问和当前 1 MHz 测试可以使用 PIO，不能因为 DMA 不可用就让 SPI probe 失败。

配置修改后必须重新编译内核 Image，不能只编 DTB。

## 9. Buildroot 用户态配置

文件：`buildroot-ext/configs/spacemit_firefly-k3-aibox-pro_defconfig`

```text
BR2_PACKAGE_CAN_UTILS=y
```

目标系统至少应提供：

- `ip`
- `candump`
- `cansend`
- `timeout`

如果板端已有这些命令，无需因为 DTS 或内核驱动修改而重建整个根文件系统。

## 10. K1/K3 SPI 控制器驱动要求

文件：`drivers/spi/spi-spacemit-k1.c`

MCP2518FD 对多 transfer SPI message、CS 切换、全双工时钟和异步完成路径要求较高。后续重新适配时，优先完整保留当前经过修正的驱动文件，不建议根据片段重新拼接。

### 10.1 必须使用 SPI core 标准回调

当前驱动注册：

```c
host->setup = k1_spi_setup;
host->cleanup = k1_spi_cleanup;
host->can_dma = k1_spi_can_dma;
host->prepare_message = k1_spi_prepare_message;
host->set_cs = k1_spi_set_cs;
host->transfer_one = k1_spi_transfer_one;
host->handle_err = k1_spi_handle_err;
```

不要恢复为旧的：

```c
host->transfer_one_message = k1_spi_transfer_one_message;
```

原因是 SPI core 的标准 `transfer_one_message()` 实现负责：

- 按顺序处理一个 message 中的多个 transfer。
- 处理 `cs_change`。
- 在 CS 释放后执行设备级 `cs_inactive` 延时。
- 统一处理 message 状态、统计和错误回调。

### 10.2 CS 控制

当前片选回调：

```c
static void k1_spi_set_cs(struct spi_device *spi, bool high)
{
	struct k1_spi_driver_data *drv_data;
	u32 val;

	drv_data = spi_controller_get_devdata(spi->controller);

	val = readl(drv_data->base + SSP_TOP_CTRL);
	if (high)
		val &= ~TOP_HOLD_FRAME_LOW;
	else
		val |= TOP_HOLD_FRAME_LOW;
	writel(val, drv_data->base + SSP_TOP_CTRL);
}
```

本驱动注释中的 `high=true` 表示物理 CS 释放为高。SPI core 调用控制器 `set_cs()` 时已处理 enable 语义，不能随意反转此逻辑。

### 10.3 异步 transfer 完成

PIO `transfer_one()` 启动中断后返回 `1`：

```c
return 1; /* We will call spi_finalize_current_transfer() */
```

中断处理完成 RX 后必须调用：

```c
spi_finalize_current_transfer(drv_data->host);
```

不能在数据还未从 RX FIFO 读完时提前完成，也不能漏掉 finalize，否则 SPI core 会卡在当前 transfer。

### 10.4 强制全双工时钟

```c
host->flags = SPI_CONTROLLER_MUST_RX | SPI_CONTROLLER_MUST_TX;
```

SPI 即使逻辑上只写也会同时接收，即使逻辑上只读也必须发送 dummy 数据以产生时钟。该标志让 SPI core 为缺失方向准备 dummy buffer。

### 10.5 TX FIFO 空闲槽计算

正确实现：

```c
count = K1_SPI_FIFO_SIZE - FIELD_GET(SSP_STATUS_TFL, val);
```

不能把 TX FIFO level 直接当成空闲槽数量，否则可能写少、写多或使 FIFO 状态机异常。

### 10.6 PIO 中断状态机

驱动必须：

- 使能 TX-not-full、RX-not-empty/timeout 和错误中断。
- TX 有空间时继续填充 FIFO。
- RX 有数据时及时读取，直到 `rx_resid` 为 0。
- 检查 TX underrun、RX overrun 和 bit-count error。
- 完成时关闭 SPI port 和中断，再 finalize 当前 transfer。

核心错误掩码：

```c
#define SSP_STATUS_ERROR \
	(SSP_STATUS_TUR | SSP_STATUS_ROR | SSP_STATUS_BCE)
```

### 10.7 DMA 行为

- 同时取得 TX 和 RX DMA channel 后才启用 DMA。
- DMA 不可用时输出提示并使用 PIO。
- DMA setup 失败但不是 `-EPROBE_DEFER` 时，不能阻止 SPI 控制器注册。
- RX DMA 完成意味着当前全双工传输完成，回调中 finalize。
- 错误路径必须终止 TX/RX DMA。

### 10.8 K3 兼容和时钟

设备匹配表必须包含：

```c
{ .compatible = "spacemit,k1-spi", },
{ .compatible = "spacemit,k3-spi", },
```

probe 必须按名字获取：

```c
drv_data->clk_bus = devm_clk_get_enabled(dev, "bus");
drv_data->clk = devm_clk_get_enabled(dev, "func");
```

### 10.9 电源管理

保留 `spi_controller_suspend()`、`spi_controller_resume()`、时钟关闭/恢复和寄存器恢复逻辑。不要为了临时排查删除 suspend/resume，否则系统休眠后 SPI 可能无法恢复。

## 11. 为什么必须增加 CS 非活动时间

### 11.1 MCP2518FD 发送包含两个 SPI 命令

MCP251XFD 驱动初始化一个 TX 对象时创建两个 transfer：

1. 把 CAN 帧写入 MCP2518FD TX RAM。
2. 写 FIFO 控制寄存器的 `UINC | TXREQ`，请求控制器真正发送。

内核代码结构：

```c
xfer = &tx_obj->xfer[0];
xfer->tx_buf = &tx_obj->buf;
xfer->cs_change = 1;
xfer->cs_change_delay.value = 0;
xfer->cs_change_delay.unit = SPI_DELAY_UNIT_NSECS;

xfer = &tx_obj->xfer[1];
xfer->tx_buf = &ring->rts_buf;
```

第一个 transfer 结束后必须释放 nCS，再开始第二条命令。

### 11.2 间歇失败的吻合现象

已观察到的失败模式：

- `cansend` 返回成功。
- TX packets 不增加。
- RX packets 不增加。
- MCP2518FD IRQ 不增加。
- 后续能看到 `tx_dropped` 增加。
- 再次测试又可能恢复成功。

这说明帧已经进入 Linux 网络发送路径，但 MCP2518FD 没有可靠执行 TXREQ。最吻合的当前推测是两条 SPI 命令之间 nCS 高电平过短，第二条命令被器件当成前一条命令的连续数据。

### 11.3 时序计算

MCP2518FD 数据手册要求两次 SPI 命令之间的 nCS 高电平时间 `TCSD` 至少为一个 SCK 周期。

当前 SPI 频率 1 MHz：

```text
SCK 周期 = 1 / 1,000,000 = 1 µs = 1000 ns
```

设备树设置 2000 ns：

```dts
spi-cs-inactive-delay-ns = <2000>;
```

即提供至少两个 1 MHz SCK 周期的裕量。

### 11.4 Linux SPI core 中的生效路径

SPI core 从设备树读取属性到 `spi->cs_inactive`。每次 `spi_set_cs()` 释放片选后，如果控制器没有硬件 `set_cs_timing` 回调，SPI core 会执行该延时。

当前 K1 驱动有 `set_cs()`，但没有 `set_cs_timing()`，因此该属性由 SPI core 软件延时执行。

### 11.5 必须用示波器确认

软件属性存在不等于物理波形一定满足要求。最终稳定前必须测量：

- TX RAM 写命令结束到 TXREQ 命令开始之间的 nCS 高电平。
- nCS 高电平是否达到至少 2 µs。
- nCS 拉高期间 SCK 是否保持空闲。
- `TOP_HOLD_FRAME_LOW` 在 SPI port 切换状态时是否立即反映到物理引脚。

如果物理 nCS 仍没有正确拉高，应优先修复 K1 SPI 控制器的 `set_cs()` 行为，不要直接修改通用 MCP251XFD 驱动协议逻辑。

## 12. 编译和打包

本文遵守当前约定：不自动执行编译，修改完成后由使用者手动编译。

先进入 SDK 根目录：

```bash
cd /media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
```

### 12.1 只修改设备树

适用修改：

- MCP 节点属性。
- 中断、时钟、pinctrl。
- `spi-max-frequency`。
- `spi-cs-inactive-delay-ns`。
- DTB Makefile。

执行：

```bash
./aibox-pro-build.sh
```

该模式同步设备树、编译 `k3-firefly-aibox-pro.dtb`、更新 `bootfs.img`，不重新编译 Image。

### 12.2 修改 SPI 驱动或内核配置

适用修改：

- `drivers/spi/spi-spacemit-k1.c`。
- `firefly-linux.config`。
- 其他进入内核 Image 的代码。

执行：

```bash
./aibox-pro-build.sh rebuild
```

该模式同步完整内核源码，增量编译：

```text
Image
spacemit/k3-firefly-aibox-pro.dtb
```

然后更新 `bootfs.img` 内的 Image 和 DTB，并比较 SHA256。

### 12.3 输出文件

```text
output/firefly-k3-aibox-pro/images/k3-firefly-aibox-pro.dtb
output/firefly-k3-aibox-pro/images/Image
output/firefly-k3-aibox-pro/images/bootfs.img
```

每次编译后至少检查：

```bash
stat output/firefly-k3-aibox-pro/images/k3-firefly-aibox-pro.dtb
stat output/firefly-k3-aibox-pro/images/Image
stat output/firefly-k3-aibox-pro/images/bootfs.img
sha256sum output/firefly-k3-aibox-pro/images/k3-firefly-aibox-pro.dtb
sha256sum output/firefly-k3-aibox-pro/images/Image
sha256sum output/firefly-k3-aibox-pro/images/bootfs.img
```

当前已观察到的产物时间，仅作为历史参考：

```text
2026-08-08 10:39:11  k3-firefly-aibox-pro.dtb
2026-08-08 10:19:50  Image
2026-08-08 10:39:11  bootfs.img
```

后续重新编译时，时间和 SHA256 应发生符合修改范围的变化。

## 13. 烧录要求

- 只修改 DTS：烧录包含新 DTB 的 `bootfs.img`。
- 修改 SPI 驱动：必须烧录同时包含新 Image 和新 DTB 的 `bootfs.img`。
- 不要把旧 Image 和新 DTB 混合，除非明确知道本次没有驱动修改。
- 烧录完成后彻底重启，避免旧内核仍在内存中运行。
- 如果启动介质存在多个 boot 分区，确认 bootloader 实际加载的是刚更新的分区。

可在目标板确认当前设备树：

```bash
tr -d '\0' </proc/device-tree/model; echo
tr -d '\0' </proc/device-tree/compatible; echo
find /proc/device-tree -name 'canfd@0' -print
```

如果系统安装了 `dtc`，可检查实际启动设备树：

```bash
dtc -I fs -O dts /proc/device-tree | grep -A20 -B5 'canfd@0'
```

应能看到 `spi-max-frequency = <1000000>` 和 `spi-cs-inactive-delay-ns = <2000>` 对应的十六进制值。

## 14. 首次启动验证

### 14.1 驱动初始化

```bash
dmesg | grep -E 'mcp251xfd|spi4|k1-spi|DMA'
```

期望看到类似：

```text
mcp251xfd spi4.0 can0: MCP2518FD ... successfully initialized.
```

当前成功日志中的典型信息：

```text
MCP2518FD rev0.0
o:40.00MHz
c:40.00MHz
m:1.00MHz
+CRC_REG +CRC_RX +CRC_TX +ECC
```

含义：

- `o:40.00MHz`：外部振荡器声明为 40 MHz。
- `c:40.00MHz`：CAN 控制器时钟为 40 MHz。
- `m:1.00MHz`：当前 SPI 频率为 1 MHz。
- CRC_REG/RX/TX：MCP2518FD 驱动启用了 SPI CRC 相关 quirk。
- `-RX_INT`：未使用可选 INT1 RX 专用中断，不代表主 CAN_INT 失效。
- `-PLL`：没有启用 MCP 内部 PLL；40 MHz 外部时钟直接作为控制器时钟。

### 14.2 设备绑定

```bash
ip link show can0
readlink -f /sys/class/net/can0/device
cat /sys/class/net/can0/device/modalias
```

期望：

- 存在 `can0`。
- 父设备为 `spi4.0`。
- 驱动绑定到 MCP251XFD。

### 14.3 中断和 debugfs

```bash
mountpoint -q /sys/kernel/debug || mount -t debugfs none /sys/kernel/debug
grep 'spi4\.0' /proc/interrupts
ls /sys/kernel/debug/regmap/spi4.0-crc
```

接口未发送前中断计数为 0 可以接受，发送成功后应增长。

## 15. CAN 接口启动

```bash
ip link set can0 down
ip link set can0 type can bitrate 500000 fd on dbitrate 2000000
ip link set can0 up
ip -details -statistics link show can0
```

成功标准：

- 命令无 `RTNETLINK answers: Input/output error`。
- 接口包含 `UP,LOWER_UP,ECHO`。
- CAN 状态为 `ERROR-ACTIVE`。
- `clock 40000000`。
- 仲裁波特率 500000，数据波特率 2000000。
- `dmesg` 没有新增 SPI CRC error 或 `SPI transfer failed: -5`。

如果这里失败，不要继续回环，先处理 SPI 通信或时钟问题。

## 16. 基础检查和内部回环

把当前测试脚本复制到板端：

```bash
cp can_test.sh /home/firefly/can_test.sh
chmod +x /home/firefly/can_test.sh
```

### 16.1 基础检查

```bash
bash /home/firefly/can_test.sh base
```

期望：

```text
PASS=5 FAIL=0 WARN=0
```

### 16.2 内部 CAN FD 回环

```bash
bash /home/firefly/can_test.sh loopback
```

默认帧：

```text
123##11122334455667788
```

可能看到：

```text
can0 123##51122334455667788
```

这是正确结果，不是数据被修改：

- 发送字符串中的 flag `1` 表示 BRS。
- `candump` 接收显示增加 CAN FD 的 FDF flag `4`。
- `1 | 4 = 5`，因此接收 flag 为 `5`。

单次成功标准：

- `PASS=9 FAIL=0 WARN=0`。
- TX packets 增加 1。
- RX packets 增加 2；内部回环中本地 echo 和控制器接收路径可能各计一次。
- `spi4.0` IRQ 增加 1。
- TX/RX errors 不增加。
- TX/RX dropped 不增加。

## 17. 压力测试和最终验收

### 17.1 连续回环 50 次

```bash
for i in $(seq 1 50); do
	echo "===== TEST $i ====="
	bash /home/firefly/can_test.sh loopback || break
done
```

### 17.2 反复启动接口

```bash
for i in $(seq 1 50); do
	echo "===== UP TEST $i ====="
	ip link set can0 down
	ip link set can0 type can bitrate 500000 fd on dbitrate 2000000
	ip link set can0 up || break
done
```

### 17.3 监控内核错误

另开终端：

```bash
dmesg -w | grep -E 'mcp251xfd|spi4|CRC|transfer failed|ERROR'
```

### 17.4 软件稳定验收标准

以下条件全部满足，才能认为软件适配稳定：

- 冷启动至少 10 次都能 probe 成功。
- `can0 up` 连续 50 次成功。
- 内部回环连续 50 次全部 `PASS=9 FAIL=0`。
- 无 `CRC read error`。
- 无 `SPI transfer failed: -5`。
- 无 `RTNETLINK answers: Input/output error`。
- 每帧 TX、RX 和 IRQ 都按预期增长。
- `tx_dropped`、`rx_dropped`、TX/RX errors 不增长。
- 示波器确认两条 SPI 命令间 nCS 高电平至少 2 µs。

### 17.5 整机最终验收标准

软件压力测试通过后，还必须完成：

- 修复 CAN_INT 5 V 上拉风险。
- 确认 SPI 1.8 V 电平转换满足 MCP2518FD 规范。
- 使用外部 CAN FD 节点收发测试。
- 在目标线束长度、终端电阻、温度和供电范围下测试。
- 如果提高 SPI 频率，每个频率重新执行完整压力测试和波形检查。

## 18. 外部 CAN FD 总线测试

内部回环通过只证明控制器、SPI 和主中断基本工作，不证明 CAN 收发器、CANH/CANL 和终端匹配正确。

准备另一台 CAN FD 节点，两端配置一致：

```bash
ip link set can0 down
ip link set can0 type can bitrate 500000 fd on dbitrate 2000000 restart-ms 100
ip link set can0 up
```

接收端：

```bash
candump -L can0
```

发送端：

```bash
cansend can0 123##11122334455667788
```

检查：

- 两端波特率、sample point 和 FD/BRS 设置一致。
- 总线两端终端电阻正确，断电测量 CANH-CANL 约为 60 Ω。
- CANH/CANL 没有接反。
- 收发器有供电且 STBY/EN 引脚处于工作状态。
- 无 ACK 时发送端可能不断重发并进入 error-passive/bus-off，这和 SPI 故障不是同一问题。

## 19. 常见故障和诊断

| 现象 | 高概率原因 | 优先检查 |
|---|---|---|
| 没有 `can0` | DTS 未加载、驱动未启用、SPI 控制器未 probe | 实际 DTB、内核配置、`dmesg`、驱动绑定 |
| `MCP2518FD successfully initialized` 后 `can0 up` 报 I/O error | SPI 运行时读写失败、CS 时序或电平问题 | CRC 日志、nCS/SCK/MOSI/MISO 波形、SPI 电压 |
| `CRC read error ... data=ff ff ff ff` | MISO 浮高、CS 未选中、器件掉电、命令未识别、电平不兼容 | 供电、MISO、nCS、线序、电平转换 |
| `SPI transfer failed: -5` | K1 SPI 状态机报告 I/O 错误、FIFO underrun/overrun/bit-count error | SPI 控制器 IRQ、状态寄存器、驱动错误路径 |
| `cansend` 成功但 TX/RX/IRQ 都不增长 | TX RAM 写或 TXREQ 命令没有真正执行 | 两条命令间 CS 高时间、TX FIFO、TXREQ 写 |
| 前几次成功，随后偶发失败，再次又恢复 | 临界 CS 脉宽、临界电平、信号完整性或状态机竞态 | 示波器触发失败波形、2 µs CS delay、1.8 V 门限 |
| TX 增长但 IRQ 不增长 | CAN_INT/GPIO IRQ 链路异常 | INT 引脚电平、GPIO56 pinmux、IRQ 类型、5 V 上拉 |
| IRQ 一直为 0，但接口刚启动 | 尚未发生 CAN 事件 | 发送一帧后再判断 |
| IRQ 有增长但 candump 无数据 | RX/TEF 处理、过滤、用户态监听或总线配置问题 | regmap、CAN 状态、candump 启动顺序 |
| 外部总线 bus-off，内部回环成功 | 收发器、终端、ACK、波特率或线束问题 | CANH/CANL、60 Ω、对端配置、收发器 EN/STBY |
| 接收显示 `##5` 而发送为 `##1` | CAN FD flag 的正常显示差异 | 不需要修复 |
| 修改 DTS 后行为完全不变 | 烧录的仍是旧 DTB/旧 boot 分区 | `/proc/device-tree`、产物哈希、bootloader 分区 |

## 20. 失败现场采集命令

发生一次失败后，不要立即重启，先保存以下信息：

```bash
date
uname -a
ip -details -statistics link show can0
dmesg | grep -E 'mcp251xfd|spi4|CRC|transfer failed|Internal Loopback' | tail -200
grep -E 'c0885000|spi4\.0|pdma' /proc/interrupts
```

读取关键 regmap：

```bash
REGMAP=/sys/kernel/debug/regmap/spi4.0-crc/registers
grep -E '^(000|01c|030|040|044|048|05c|060|064|e00|e04|e08|e0c):' "$REGMAP"
```

已知关键寄存器：

- `CiINT`：地址 `0x01c`，用于判断 MCP 内部中断事件。
- `IOCON`：地址 `0xe04`，用于判断 INT 输出模式等 IO 配置。

同时记录失败前后：

- TX packets。
- RX packets。
- TX/RX errors。
- TX/RX dropped。
- `spi4.0` IRQ 总数。
- nCS、SCK、MOSI、MISO、CAN_INT 波形。

## 21. 不要这样做

- 不要把 J2-214 写成 GPIO214；CAN_INT 是 SoC GPIO56。
- 不要把 MCP 时钟 40 MHz 写成 SPI 频率或 CAN 波特率。
- 不要一开始就把 SPI 提高到 10 MHz/20 MHz。
- 不要删除 `spi-cs-inactive-delay-ns` 后用“多试几次”判断稳定。
- 不要恢复旧的 `transfer_one_message()` SPI 驱动。
- 不要在 K1 SPI 驱动中手工遍历 MCP message 并重复实现 SPI core 的 CS 语义。
- 不要把 TX FIFO level 当成 free slots。
- 不要漏掉 `SPI_CONTROLLER_MUST_RX | SPI_CONTROLLER_MUST_TX`。
- 不要在 PIO 数据尚未读完时调用 finalize。
- 不要因为 DMA 不存在就让 SPI 控制器 probe 失败。
- 不要只烧 DTB，却期待 SPI 驱动修改生效。
- 不要把 CAN_INT 继续上拉到 5 V 作为最终方案。
- 不要假设 1.8 V SPI 可以直接可靠驱动 3.3 V/5 V MCP2518FD。
- 不要用内部回环通过替代外部 CAN 收发器和总线测试。
- 不要修改通用 MCP251XFD 驱动来掩盖 K1 SPI 控制器 CS 波形问题。

## 22. 推荐的重新适配顺序

严格按以下顺序执行，可以减少多个问题叠加：

1. 核对原理图、J2、Pad 和 GPIO 编号。
2. 测量 MCP2518FD VDD、40 MHz 时钟和 SPI/INT 电压。
3. 先解决 1.8 V SPI 与 MCP 逻辑域的电平兼容。
4. 解决 CAN_INT 5 V 上拉问题。
5. 恢复当前已验证过的 K1/K3 SPI 驱动文件。
6. 检查 `rspi0` compatible、时钟名、reset 和 IRQ。
7. 加入 SPI pinctrl 和 1.8 V power-source 配置。
8. 加入 MCP 40 MHz fixed-clock。
9. 加入 MCP2518FD 节点、GPIO56 下降沿中断、1 MHz SPI。
10. 加入 2 µs CS inactive delay。
11. 启用内核 CAN/SPI/MCP251XFD 配置。
12. 确认 Buildroot 包含 `can-utils`。
13. 修改过驱动时执行 `./aibox-pro-build.sh rebuild`。
14. 烧录完整 `bootfs.img` 并冷启动。
15. 先检查 probe，再执行 `can0 up`。
16. 执行 base、单次 loopback、50 次 loopback。
17. 示波器确认 CS 命令间隔。
18. 最后执行外部 CAN FD 总线测试。

## 23. 黄金文件和 SHA256

以下哈希对应 2026-08-08 当前工作区内容。以后如果希望复现当前软件基线，可先比较文件哈希；如果文件有预期修改，哈希变化属于正常现象。

| 文件 | SHA256 |
|---|---|
| `k3-firefly-aibox-pro.dts` | `d027d2b99b2829e4cbb42afa610303effee0e4e8d95ae02f4d69d5b9e5081a55` |
| `k3-firefly-aibox-pro.dtsi` | `d2fa27d5733f87b84049b019f72c7632d35637dd27bd228391d993dc07206b10` |
| `aibox-pro-test.dtsi` | `0abb0939e57915207f3c1fa9467f4a63178026fd0acc71515ad7673f55872259` |
| DTS Makefile | `aadc0adbe85d351b24d495f2ac29cb005043c46c9355fdba21f9c89ca9823a48` |
| `can_test.sh` | `ee4bff1bd4b5d1775fca02eb39bfbb6793db90f9f969e407c02932159035410f` |
| `drivers/spi/spi-spacemit-k1.c` | `2af733576b12da176db1461745f955aabf627d71d38e4db784b8fe691828d66d` |
| `arch/riscv/configs/firefly-linux.config` | `44a9900472b14b288d6e9118b962da06b67ac0eedd2cc2806498c68ca41317f0` |
| `aibox-pro-build.sh` | `c96e73b22ecb3a7f79fe29c1199f456447d6fe2d1ca5bf72c142c3538cd4c208` |

建议在确认最终稳定后，把这些相关文件、最终 Image/DTB/bootfs 哈希、原理图版本和压力测试日志一起归档。

## 24. 最小备份清单

为了以后不从零排查，至少备份：

```text
k3-firefly-aibox-pro.dts
k3-firefly-aibox-pro.dtsi
aibox-pro-test.dtsi
k3-rdomain.dtsi
k3-pinctrl.dtsi
arch/riscv/boot/dts/spacemit/Makefile
arch/riscv/configs/firefly-linux.config
drivers/spi/spi-spacemit-k1.c
Documentation/devicetree/bindings/net/can/microchip,mcp251xfd.yaml
Documentation/devicetree/bindings/spi/spi-peripheral-props.yaml
buildroot-ext/configs/spacemit_firefly-k3-aibox-pro_defconfig
aibox-pro-build.sh
can_test.sh
最终 Image
最终 k3-firefly-aibox-pro.dtb
最终 bootfs.img
```

## 25. 参考资料

- Microchip《MCP2518FD External CAN FD Controller with SPI Interface Data Sheet》，文档号 DS20006027B。
- Linux 本地 binding：`Documentation/devicetree/bindings/net/can/microchip,mcp251xfd.yaml`。
- Linux 通用 SPI 外设属性：`Documentation/devicetree/bindings/spi/spi-peripheral-props.yaml`。
- Linux SPI core：`drivers/spi/spi.c`。
- Linux MCP251XFD 驱动：`drivers/net/can/spi/mcp251xfd/`。
- 当前 K1/K3 SPI 驱动：`drivers/spi/spi-spacemit-k1.c`。
- 当前板级引脚记录：`arch/riscv/boot/dts/spacemit/subject_模块引脚对应表.md`。

## 26. 当前待验证项

截至 2026-08-08，软件已加入：

```dts
spi-cs-inactive-delay-ns = <2000>;
```

但在用户明确确认以下结果前，不能把问题标记为最终解决：

- 新 DTB 已编译并烧录。
- 实际启动设备树包含 2 µs CS inactive delay。
- 连续 50 次内部回环全部成功。
- 连续 50 次接口 up 全部成功。
- 无 SPI CRC、`-EIO` 和丢包累计。
- 示波器确认 CS 高电平间隔满足要求。
- SPI 和 CAN_INT 电压风险已通过硬件修改消除。

