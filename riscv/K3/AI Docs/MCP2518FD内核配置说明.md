# MCP2518FD 内核配置说明

本文档适用于当前 K3 AIBOX-PRO SDK：

```text
SDK 根目录：/media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
当前方案：firefly-k3-aibox-pro
内核源码：bsp-src/linux-6.18
内核输出目录：output/firefly-k3-aibox-pro/build/linux-custom
```

设备树使用的控制器为 Microchip MCP2518FD，对应内核配置项：

```config
CONFIG_CAN_MCP251XFD
```

建议将驱动编译成模块：

```config
CONFIG_CAN_MCP251XFD=m
```

这样生成的驱动模块通常为 `mcp251xfd.ko`，启动后可通过 `modprobe mcp251xfd` 加载。

## 一、修改 CONFIG 配置文件

这种方式会把配置保存在源码配置片段中，执行清理或重新配置后仍然有效，推荐用于正式工程。

### 1. 进入 SDK 根目录

```bash
cd /media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
```

### 2. 修改 Firefly 内核配置片段

打开：

```bash
vim bsp-src/linux-6.18/arch/riscv/configs/firefly-linux.config
```

在文件末尾添加：

```config
CONFIG_CAN_MCP251XFD=m
```

当前工程已经具备以下依赖配置，一般不需要重复添加：

```config
CONFIG_CAN=m
CONFIG_CAN_RAW=m
CONFIG_CAN_DEV=m
CONFIG_SPI=y
CONFIG_SPI_K1=y
CONFIG_REGMAP_SPI=y
```

如果这些选项在后续配置中被关闭，需要同时恢复。模块方式推荐保持如下关系：

```config
CONFIG_CAN=m
CONFIG_CAN_DEV=m
CONFIG_CAN_MCP251XFD=m
```

不要启用额外的运行时检查，除非正在调试驱动内部问题：

```config
# CONFIG_CAN_MCP251XFD_SANITY is not set
```

### 3. 重新生成并编译内核

配置片段发生变化后，推荐执行：

```bash
make -- linux-reconfigure
```

如果输出目录中的内核 `.config` 已经包含 MCP251XFD，也可以只重新编译：

```bash
make -- linux-rebuild
```

也可以执行完整方案编译：

```bash
make -- all
```

注意：命令前面的 `$` 只是终端提示符，不要输入。命令中的 `linux-rebuild` 必须连续输入，中间不能有空格。

### 4. 检查配置是否生效

```bash
grep '^CONFIG_CAN_MCP251XFD=' \
    output/firefly-k3-aibox-pro/build/linux-custom/.config
```

期望输出：

```text
CONFIG_CAN_MCP251XFD=m
```

检查模块是否生成：

```bash
find output/firefly-k3-aibox-pro -name 'mcp251xfd.ko*'
```

## 二、使用 GUI 配置

这种方式通过 Linux Kernel `menuconfig` 图形化终端界面配置，适合交互式选择和临时验证。

### 1. 进入 SDK 根目录

```bash
cd /media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18
```

### 2. 打开 Linux 内核配置界面

当前 SDK 已经通过 `env.mk` 选择了 `firefly-k3-aibox-pro`，直接执行：

```bash
make -- linux-menuconfig
```

如果终端提示缺少菜单界面依赖，需要在主机或构建容器中安装 `ncurses` 开发包；该 SDK 默认通过构建容器运行，通常不需要手动安装。

### 3. 进入 MCP251XFD 配置菜单

菜单路径如下：

```text
Networking support
  -> CAN bus subsystem support
    -> CAN Device Drivers
      -> CAN SPI interfaces
        -> Microchip MCP251xFD SPI CAN controllers
```

在以下选项上按 `M`，将其配置成模块：

```text
<M> Microchip MCP251xFD SPI CAN controllers
```

确认上级依赖至少为：

```text
<M> CAN bus subsystem support
<M> CAN Device Drivers
[*] SPI support
<*> SpacemiT K1/K3 SPI controller support
```

`Additional Sanity Checks` 建议保持关闭：

```text
[ ] Additional Sanity Checks
```

完成后选择 `Save`，保存默认配置文件，然后连续选择 `Exit` 退出。

### 4. 检查 GUI 保存结果

```bash
grep '^CONFIG_CAN_MCP251XFD=' \
    output/firefly-k3-aibox-pro/build/linux-custom/.config
```

期望输出：

```text
CONFIG_CAN_MCP251XFD=m
```

### 5. 编译内核

```bash
make -- linux-rebuild
```

### 6. GUI 配置的持久化说明

GUI 默认修改的是当前输出目录中的：

```text
output/firefly-k3-aibox-pro/build/linux-custom/.config
```

当前工程同时使用以下源码配置片段：

```text
bsp-src/linux-6.18/arch/riscv/configs/firefly-linux.config
```

如果执行了 `distclean`、删除输出目录或重新应用方案配置，GUI 中的修改可能丢失。确认 GUI 配置验证成功后，建议将下面这一行同步写入 `firefly-linux.config`：

```config
CONFIG_CAN_MCP251XFD=m
```

由于当前工程启用了 Kconfig fragment，Buildroot 的 `linux-update-config` 或 `linux-update-defconfig` 可能提示不能在存在 fragment 时自动回写，因此手动同步这一行最可靠。

## 三、处理 `Passing target 'l'` 错误

如果出现：

```text
Passing target 'l' to output/firefly-k3-aibox-pro
No rule to make target 'l'
```

说明 Make 实际收到的目标是单个字母 `l`，不是 `linux-rebuild`。这通常是复制命令时混入了提示符、不可见字符，或者在 `l` 后出现了空格。

不要输入下面命令最前面的提示符字符：

```text
$ make linux-rebuild
```

请在 SDK 根目录重新手动输入：

```bash
make -- linux-rebuild
```

如果仍然异常，绕过可能存在的 shell alias，执行：

```bash
\make -- linux-rebuild
```

检查实际执行的 `make`：

```bash
type -a make
alias make 2>/dev/null
```

正常启动时应显示：

```text
Passing target 'linux-rebuild' to output/firefly-k3-aibox-pro
```

而不应该显示：

```text
Passing target 'l' to output/firefly-k3-aibox-pro
```

## 四、上板检查

### 1. 检查模块

```bash
modinfo mcp251xfd
modprobe mcp251xfd
lsmod | grep mcp251xfd
```

### 2. 检查驱动日志

```bash
dmesg | grep -i -E 'mcp251|can|spi'
```

### 3. 检查 CAN 网络设备

```bash
ip -details link show type can
```

如果设备注册成功，通常可以看到 `can0`。

### 4. 启动 CAN-FD 示例

以下参数仅为示例，实际仲裁速率和数据段速率必须与总线上其他设备一致：

```bash
ip link set can0 down
ip link set can0 type can bitrate 500000 dbitrate 2000000 fd on
ip link set can0 up
ip -details link show can0
```

发送和接收测试需要目标系统安装 `can-utils`：

```bash
candump can0
cansend can0 123##01122334455667788
```

## 五、常见故障判断

### 没有生成 `mcp251xfd.ko`

检查：

```bash
grep -E '^CONFIG_(CAN|CAN_DEV|CAN_MCP251XFD|SPI|SPI_K1)=' \
    output/firefly-k3-aibox-pro/build/linux-custom/.config
```

确认 `CONFIG_CAN_MCP251XFD=m`，并重新执行 `make -- linux-reconfigure`。

### `modprobe` 提示找不到模块

确认新内核模块已经安装到目标根文件系统，并且目标板运行的内核版本与模块目录一致：

```bash
uname -r
find /lib/modules/$(uname -r) -name 'mcp251xfd.ko*'
depmod -a
modprobe mcp251xfd
```

### 驱动加载但没有 `can0`

优先检查：

1. 设备树中 MCP2518FD 节点状态是否为 `okay`。
2. SPI 控制器和 `rssp0_0_cfg` pinctrl 是否生效。
3. MCP2518FD 晶振是否确实为 40MHz。
4. SPI 时钟是否不高于晶振频率的一半；当前设备树配置为 20MHz。
5. GPIO56 是否连接到 MCP2518FD 的低电平有效中断输出。
6. 供电、复位和 SPI CS 信号是否正常。
