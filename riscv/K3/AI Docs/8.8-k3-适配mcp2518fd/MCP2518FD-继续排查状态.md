# MCP2518FD 继续排查状态

- 记录日期：2026-08-07
- 当前状态：问题尚未最终解决，暂停排查
- 工作目录：`/media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18/bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit`

## 当前现象

旧内核进行多次 CAN-FD 内部回环测试时表现不稳定：

- 部分测试成功，TX、RX 和 MCP2518FD IRQ 均增加。
- 部分测试超时，TX、RX 和 IRQ 均不增加。
- 连续失败后 `tx_dropped` 累计增加。
- 曾出现控制器无法进入内部回环模式并停留在 Configuration Mode。
- 曾出现明确的 SPI CRC 错误：

```text
CRC read error at address 0x0e0c
(length=4, data=ff ff ff ff, CRC=0xffff)
```

因此当前主要排查方向是 K1 SPI 控制器的间歇性传输异常，而不是单纯的 CAN_INT GPIO 中断问题。

### 2026-08-08 新内核回归

烧录 2026-08-07 20:06 生成的内核后，MCP2518FD 仍能在启动阶段初始化成功，但执行 `ip link set can0 up` 时直接失败：

```text
mcp251xfd spi4.0 can0: CRC read error at address 0x0e0c
(length=4, data=ff ff ff ff, CRC=0xffff).
RTNETLINK answers: Input/output error
```

`0x0e0c` 是 MCP2518FD 的 ECCCON 寄存器。该日志说明在 CAN 控制器启动阶段，普通 SPI CRC 读事务已经返回全 `0xff`，不是 CAN 波特率或回环参数错误。

第一次改为 SPI core 的 `set_cs + transfer_one` 回调、但仍保留旧 PIO/IRQ 等待状态机后，板端继续失败：

```text
mcp251xfd spi4.0: SPI transfer failed: -5
spi_master spi4: failed to transfer one message from queue
spi_master spi4: noqueue transfer failed
mcp251xfd spi4.0 can0: CRC read error at address 0x0e0c
(length=4, data=ff ff ff ff, CRC=0xffff).
```

`-5` 是 `-EIO`。这次日志确认 K1 SPI 控制器状态机先报告传输失败，随后 MCP2518FD 才因读回全 `0xff` 报 CRC 错误。因此不能继续使用“新 CS 回调 + 旧阻塞式 PIO/IRQ 状态机”的混合实现。

### 2026-08-08 完整状态机测试结果

完整异步 SPI 状态机编译烧录后，`can0 up` 已能成功，内部回环也能连续成功，但仍存在间歇性发送失败：

- 成功时 TX 增加 1、RX 增加 2、MCP2518FD IRQ 增加 1。
- 失败时 `cansend` 返回成功，但 TX、RX 和 IRQ 全部不增加。
- 失败发送对应的 `tx_dropped` 会在下一次测试开始前增加。
- 连续多次成功后仍可能连续失败两次，之后又自行恢复成功。

该模式说明 SocketCAN 已接受发送请求，但 MCP2518FD 的 TXREQ 命令有时没有被芯片识别。MCP2518FD 发送路径在同一个 SPI message 中先写 TX RAM，再通过第二条 SPI 指令写入 `UINC | TXREQ`，两条指令之间依赖 `cs_change` 产生 nCS 高电平脉冲。

当前 MCP251XFD 驱动把 `cs_change_delay` 明确设为 `0 ns`。MCP2518FD 要求两条 SPI 指令之间的 nCS 高电平时间至少为一个 SCK 周期；当前 SPI 为 1 MHz，一个周期是 1 us。K1 控制器连续清除和设置片选寄存器时，实际高电平脉冲可能小于该要求，导致第二条 TXREQ 指令有时被当成上一条 TX RAM 写入的连续数据。

## 已确认的脚本问题

以下发送与接收是正确匹配，不是数据损坏：

```text
发送：123##11122334455667788
接收：123##51122334455667788
```

发送标志 `1` 为 BRS，Linux 接收 CAN-FD 帧时增加 FDF 标志 `4`，所以 candump 显示标志 `5`。

`can_test.sh` 已修正该比较逻辑，不再把 `##1` 到 `##5` 误报为数据不一致。

## 当前源码修改

### K1 SPI CS 切换

文件：`../../../../../drivers/spi/spi-spacemit-k1.c`

- 已撤销在旧 `transfer_one_message()` 中手工处理 `transfer->cs_change` 的实现。
- 改为注册 SPI core 的 `host->set_cs` 和 `host->transfer_one` 回调。
- `TOP_HOLD_FRAME_LOW` 明确作为物理片选控制位，由 SPI core 统一负责 message 开始、结束和 transfer 间的 `cs_change`。
- `k1_spi_setup()` 不再提前拉低 CS，避免设备注册后到首个事务前一直保持选中状态。
- transfer 完成后只关闭端口和中断，不再由控制器驱动重复执行 delay、累计 message 长度或 finalize message。
- 已进一步移除旧的阻塞式 completion/message 状态机，避免控制器驱动和 SPI core 同时维护 message 状态。

### K1 SPI TX FIFO 槽位计算

修改前：

```c
count = FIELD_GET(SSP_STATUS_TFL, val);
```

修改后：

```c
count = K1_SPI_FIFO_SIZE - FIELD_GET(SSP_STATUS_TFL, val);
if (!count)
	return false;
```

`TFL` 是已占用槽位数，不能直接当作剩余可写槽位数。

### SPI core message 管理

当前代码已完整切换为单 transfer 异步状态机，并注册标准回调：

```c
host->set_cs = k1_spi_set_cs;
host->transfer_one = k1_spi_transfer_one;
```

SPI core 负责 message 边界、`cs_change`、delay、长度累计和最终 message 完成。控制器驱动的 `transfer_one()` 启动硬件后返回 `1`，由 IRQ 或 DMA 完成回调调用 `spi_finalize_current_transfer()`。

### K1 SPI PIO/IRQ 状态机

- 删除旧 `wait_for_completion_interruptible_timeout()` 阻塞等待流程。
- PIO 传输由 `TNF`/`RNE` 中断驱动，TX 和 RX 剩余字节分别跟踪。
- TX 数据全部写入后立即关闭 TX FIFO 中断，只保留 RX 和错误中断。
- RX 数据全部读完后关闭端口和全部中断，并通知 SPI core 当前 transfer 完成。
- 增加 Bit Count Error 检测，与 TX underrun、RX overrun 一起作为 SPI I/O 错误处理。
- 增加 `SPI_CONTROLLER_MUST_RX | SPI_CONTROLLER_MUST_TX`，保证控制器始终进行对称全双工时钟传输。
- message 开始前统一清理残留 RX FIFO。
- 保留 K3 设备树接口：`spacemit,k3-spi`、`func/bus` 时钟和系统休眠恢复。

### MCP2518FD CS 非活动时间

文件：`k3-firefly-aibox-pro.dtsi`

在 MCP2518FD 节点增加：

```dts
spi-cs-inactive-delay-ns = <2000>;
```

SPI core 在每次 CS 释放后等待 2 us，再允许下一次 CS 拉低。该时间大于 1 MHz SPI 所需的一个 SCK 周期，并给 K1 寄存器片选切换留出裕量。

GPIO56 当前设备树配置为 3.3 V IO，不是此前记录的 1.8 V。考虑到用户要求先处理软件且保持当前已实现功能，GPIO56 暂时继续保留原有 `bias-pull-up` 配置，本轮不改变中断引脚的软件行为。板端 4.7 kΩ 到 5 V 的外部上拉属于待处理硬件风险，后续修改硬件时再同步调整 pinctrl 配置。

### CAN 测试脚本

文件：`can_test.sh`

- 默认测试 CAN-FD+BRS 帧：`123##11122334455667788`。
- 自动将期望 candump 标志从 `1` 规范化为 `5`。
- 更新失败诊断提示，区分 SPI 写入、TXREQ、CAN_INT 和 GPIO IRQ。

## 当前编译状态

2026-08-07 的 TX FIFO 和手工 CS 修改已编译并烧录，但板端出现 `can0 up` 直接失败。2026-08-08 的第一次 SPI core 混合回移仍出现 `SPI transfer failed: -5`。完整异步状态机已经由用户编译烧录，`can0 up` 和回环可以成功，但发送仍因 CS 指令间隔不足而间歇失败。

当前最新功能性修改仅增加设备树 CS 非活动延时；GPIO56 保持原有 pinctrl 和中断配置，尚未重新生成 DTB 和 `bootfs.img`。

旧产物：

```text
Image 时间：2026-08-07 19:26:13
Image SHA256：82b76d0d882119e850c1351513ee6a050f3601c7256f47cfa328c3c44fd434ee

bootfs.img 时间：2026-08-07 19:26:13
bootfs.img SHA256：4df91c9d4ec880e9339a4454c0a4e20ffddff15b8a85265c1b5f8e177619e6e2
```

新产物：

```text
SPI 驱动对象时间：2026-08-07 19:56:37

Image 时间：2026-08-07 20:06:14
Image SHA256：2e5f6776f2315f8712bba060f010c76cac54f1e16a3a144aad1f2b7cb531a6b7

bootfs.img 时间：2026-08-07 20:06:18
bootfs.img SHA256：d22b4a787309a16320beed160470e41353b7a238f35aed9436674910994cd902
```

上述 2026-08-07 20:06 产物包含有问题的手工 CS 修改，不包含 2026-08-08 的 SPI core 回调修正，不能继续作为待验证的新镜像。

当前最新设备树修改按用户要求未执行编译，仅完成 DTS 属性、SPI core 属性解析和脚本语法的静态检查。

## 下次继续步骤

### 1. 用户重新编译设备树

```sh
cd /media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
./aibox-pro-build.sh
```

这次只修改了设备树和脚本，不需要重新编译内核 Image。确认新 DTB 和 `bootfs.img` 的时间已更新。

### 2. 烧录和更新脚本

- 烧录完整的 `output/firefly-k3-aibox-pro/images/bootfs.img`。
- 不能只更新 DTB，因为修改位于内核 SPI 驱动。
- 将当前目录最新的 `can_test.sh` 更新到板端 `/home/firefly/can_test.sh`。

先验证 CAN 接口可以稳定启动：

```sh
ip link set can0 down
ip link set can0 type can bitrate 500000 fd on dbitrate 2000000
ip link set can0 up
ip -details link show can0
```

确认没有 `SPI transfer failed: -5`、`CRC read error` 和 `RTNETLINK answers: Input/output error` 后再运行回环测试。

### 3. 连续测试

```sh
for i in $(seq 1 50); do
	echo "===== TEST $i ====="
	bash /home/firefly/can_test.sh loopback || break
done
```

目标结果：连续 50 次均 `PASS=9 FAIL=0`，TX/RX/IRQ 增加，`tx_dropped` 不再累计，且无 SPI CRC 错误。

### 4. 增加延时后仍失败时收集

```sh
dmesg | grep -E 'mcp251xfd|spi4|CRC|Internal Loopback' | tail -100

REGMAP=/sys/kernel/debug/regmap/spi4.0-crc/registers
grep -E '^(000|01c|030|040|044|048|05c|060|064|e00|e04|e08|e0c):' "$REGMAP"

grep -E 'c0885000|spi4\.0|pdma' /proc/interrupts
ip -details -statistics link show can0
```

如果仍然间歇失败，下一步重点检查：

- 用示波器或逻辑分析仪确认 TX RAM 写与 TXREQ 写之间的 CS 高电平至少为 2 us。
- `TOP_HOLD_FRAME_LOW` 在 `TOP_SSE` 关闭时能否立即改变物理 CS。
- SPI TX/RX FIFO 是否在失败后卡死。
- SPI core 的 `set_cs()` 回调是否在示波器或逻辑分析仪上产生正确的高低跳变。

## 当前判断

- CAN-FD 测试脚本误判已修正。
- MCP2518FD、内部回环和 CAN_INT 中断链路曾成功工作。
- 当前核心问题是 SPI 通信存在间歇性异常，包括读取全 `0xff` 和 CRC 错误。
- 完整异步 SPI 状态机已使 `can0 up` 和回环基本可用，剩余失败集中在发送阶段的 TXREQ 指令间歇丢失。
- 最符合现有证据的根因是两条 MCP2518FD SPI 指令之间 CS 高电平小于一个 SCK 周期。
- 已通过 `spi-cs-inactive-delay-ns = <2000>` 强制提供 2 us 的 CS 高电平间隔。
- GPIO56 和中断配置本轮保持不变，外部 5 V 上拉风险留待后续硬件修改时处理。
- 在新 DTB 完成连续 50 次压力测试前，不标记为最终解决。
