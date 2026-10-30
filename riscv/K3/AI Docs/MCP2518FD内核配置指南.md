# MCP2518FD 内核配置指南

本文适用于当前 K3 Linux SDK 的 `firefly-k3-aibox-pro` 工程，介绍以下两种 MCP2518FD 驱动配置方法：

1. 修改内核 CONFIG 配置片段，配置可长期保存。
2. 使用 `menuconfig` 图形界面配置，适合交互式选择和临时调试。

当前 SDK 根目录为：

```text
/media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
```

当前工程使用的内核配置由以下两部分合并生成：

```text
bsp-src/linux-6.18/arch/riscv/configs/k3_bianbu_defconfig
bsp-src/linux-6.18/arch/riscv/configs/firefly-linux.config
```

其中 `firefly-linux.config` 是 Firefly 板级配置片段，建议将 MCP2518FD 配置写入该文件。

## 一、配置项说明

MCP2518FD 对应的内核配置项是：

```config
CONFIG_CAN_MCP251XFD
```

虽然芯片型号是 MCP2518FD，但 Linux 内核驱动名称和模块名称使用的是 `mcp251xfd`，该驱动同时支持 MCP2517FD、MCP2518FD 等系列芯片。

推荐配置成模块：

```config
CONFIG_CAN_MCP251XFD=m
```

这样生成的驱动模块通常名为：

```text
mcp251xfd.ko
```

当前工程已经具备以下依赖配置：

```config
CONFIG_CAN=m
CONFIG_CAN_DEV=m
CONFIG_CAN_RX_OFFLOAD=y
CONFIG_SPI=y
CONFIG_SPI_K1=y
CONFIG_REGMAP=y
CONFIG_REGMAP_SPI=y
CONFIG_WANT_DEV_COREDUMP=y
```

因此正常情况下只需要新增 `CONFIG_CAN_MCP251XFD=m`。

不建议启用下面的调试选项：

```config
# CONFIG_CAN_MCP251XFD_SANITY is not set
```

该选项会增加运行时检查开销，除非正在排查 MCP2518FD 驱动内部异常，否则保持关闭即可。

## 二、方法一：修改 CONFIG 配置文件

### 1. 打开板级配置片段

配置文件路径：

```text
bsp-src/linux-6.18/arch/riscv/configs/firefly-linux.config
```

从 SDK 根目录执行：

```bash
cd /media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
vim bsp-src/linux-6.18/arch/riscv/configs/firefly-linux.config
```

### 2. 增加 MCP2518FD 配置

在文件末尾添加：

```config
CONFIG_CAN_MCP251XFD=m
```

如果希望将驱动直接编译进内核，可以使用：

```config
CONFIG_CAN=y
CONFIG_CAN_DEV=y
CONFIG_CAN_MCP251XFD=y
```

注意：当前工程的 `CONFIG_CAN` 和 `CONFIG_CAN_DEV` 是模块模式。此时 `CONFIG_CAN_MCP251XFD` 也应配置为 `m`，不能将上层 CAN 配置为 `m`、MCP251XFD 驱动单独配置为 `y`。

### 3. 重新合并内核配置

修改配置片段后执行：

```bash
cd /media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
make linux-reconfigure
```

该命令会重新使用基础 defconfig 和 `firefly-linux.config` 生成内核 `.config`。

### 4. 检查生成结果

```bash
grep '^CONFIG_CAN_MCP251XFD=' \
    output/firefly-k3-aibox-pro/build/linux-custom/.config
```

模块模式应输出：

```text
CONFIG_CAN_MCP251XFD=m
```

同时可以检查相关依赖：

```bash
grep -E '^CONFIG_(CAN|CAN_DEV|CAN_MCP251XFD|CAN_RX_OFFLOAD|SPI|SPI_K1|REGMAP_SPI)=' \
    output/firefly-k3-aibox-pro/build/linux-custom/.config
```

### 5. 重新编译内核

```bash
make linux-rebuild
```

编译完成后，可以检查驱动模块是否生成：

```bash
find output/firefly-k3-aibox-pro -name 'mcp251xfd.ko' -print
```

如果使用 `CONFIG_CAN_MCP251XFD=y`，驱动会直接编译进内核，不会生成 `mcp251xfd.ko`。

## 三、方法二：GUI 图形界面配置

### 1. 进入内核 menuconfig

在 SDK 根目录执行：

```bash
cd /media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
make linux-menuconfig
```

当前 SDK 会通过已配置的构建环境打开 Linux 内核的 ncurses 配置界面。

### 2. 启用 CAN 协议栈

先按以下菜单路径启用 CAN 协议栈：

```text
Networking support
  └─ CAN bus subsystem support
```

将该选项设置为模块 `<M>`，然后进入 CAN 驱动菜单：

```text
Device Drivers
  └─ Network device support
      └─ CAN Device Drivers
          └─ CAN SPI interfaces
              └─ Microchip MCP251xFD SPI CAN controllers
```

模块方案应将以下选项设置为 `<M>`：

```text
<M> CAN bus subsystem support
<M> CAN Device Drivers
<M> Microchip MCP251xFD SPI CAN controllers
```

如果需要直接编译进内核，则将三个选项都设置为 `<*>`。

不能将上层 `CAN bus subsystem support` 设置成 `<M>`，同时将 MCP251xFD 驱动设置成 `<*>`。

### 3. 检查 SPI 控制器配置

继续检查以下菜单：

```text
Device Drivers
  └─ SPI support
      └─ Spacemit K1 SPI Controller
```

该选项应为：

```text
<*> Spacemit K1 SPI Controller
```

对应配置项为：

```config
CONFIG_SPI_K1=y
```

当前工程已经启用了该选项，一般不需要修改。

### 4. 保存并退出

依次选择：

```text
Save
Exit
```

保存后，配置会写入当前构建输出目录中的：

```text
output/firefly-k3-aibox-pro/build/linux-custom/.config
```

### 5. 检查 GUI 配置结果

```bash
grep '^CONFIG_CAN_MCP251XFD=' \
    output/firefly-k3-aibox-pro/build/linux-custom/.config
```

预期输出：

```text
CONFIG_CAN_MCP251XFD=m
```

### 6. 编译内核

```bash
make linux-rebuild
```

### 7. GUI 配置的持久化注意事项

`make linux-menuconfig` 修改的是当前输出目录中的内核 `.config`。如果后续执行以下操作，GUI 配置可能被基础 defconfig 和板级配置片段覆盖：

```bash
make linux-reconfigure
make distclean
重新创建 output/firefly-k3-aibox-pro
```

如果 GUI 验证成功，并且希望配置长期保留，应把以下内容同步写入：

```text
bsp-src/linux-6.18/arch/riscv/configs/firefly-linux.config
```

需要同步的配置为：

```config
CONFIG_CAN_MCP251XFD=m
```

由于当前工程使用了 Kconfig fragment，Buildroot 的 `linux-update-config` 或 `linux-update-defconfig` 不能直接用于回写该配置片段，因此建议手动同步这一行。

## 四、板端加载与验证

### 1. 加载驱动模块

如果配置为模块：

```bash
modprobe mcp251xfd
```

检查模块：

```bash
lsmod | grep mcp251xfd
```

如果配置为内建驱动，则不需要执行 `modprobe`。

### 2. 检查内核日志

```bash
dmesg | grep -i -E 'mcp251|canfd|spi'
```

如果设备树、SPI 通信、晶振和中断均正常，应能看到 MCP2518FD probe 成功相关信息。

常见错误含义：

| 日志或现象 | 常见原因 |
| --- | --- |
| 没有 MCP2518FD 日志 | 驱动未启用、模块未安装或设备树节点未加载 |
| `Failed to detect` 或 SPI 读写失败 | SPI 引脚、片选、SPI 时钟或供电异常 |
| 时钟频率相关错误 | 设备树晶振频率与硬件晶振不一致 |
| 中断持续触发或没有收包 | GPIO56 中断引脚、上拉或触发边沿异常 |
| 出现 CAN 设备但无法通信 | CAN 波特率、终端电阻、CANH/CANL 或收发器供电异常 |

### 3. 检查 CAN 网络设备

```bash
ip -details link show type can
```

一般情况下会出现 `can0`。如果系统还有其他 CAN 控制器，设备编号可能不是 `can0`。

### 4. 配置 CAN FD 接口示例

以下仅为示例，实际仲裁段和数据段波特率需要与总线上的其他节点保持一致：

```bash
ip link set can0 down
ip link set can0 type can bitrate 500000 dbitrate 2000000 fd on
ip link set can0 up
ip -details link show can0
```

发送测试需要安装 `can-utils`：

```bash
cansend can0 123##01122334455667788
```

接收测试：

```bash
candump can0
```

## 五、推荐选择

开发调试阶段推荐使用：

```config
CONFIG_CAN_MCP251XFD=m
```

优点是可以通过 `modprobe`、`rmmod` 快速重新加载驱动，方便查看 probe 日志和排查 SPI、中断问题。

验证稳定后，可以继续保留模块方式；如果产品要求驱动在根文件系统挂载前就可用，也可以将 CAN 核心、CAN 设备驱动和 MCP251XFD 全部改为内建方式。
