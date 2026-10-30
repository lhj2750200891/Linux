# 后摩 XH2A 驱动移植步骤

适用：K3 Linux 6.18，PCIe 主机连接后摩 XH2A 加速卡。

## 1. 拷贝驱动源码

把后摩驱动目录完整拷贝到目标内核：

```text
drivers/misc/houmo/
```

目录不能只拷贝 `xh2a_host_drv.c`，必须保留 `pcie/`、`ipu/`、`memory_allocator/`、`memory_transfer/`、`qspi/`、`i2c/`、`rpmsg_lite/`、`transport/`、`public/`、`include/` 等全部子目录。

如果目标平台使用 Rockchip RKEP PCIe endpoint function，同时拷贝：

```text
drivers/misc/rockchip/
```

## 2. 接入 Kconfig 和 Makefile

在 `drivers/misc/Kconfig` 的 `endmenu` 前加入：

```kconfig
source "drivers/misc/houmo/Kconfig"
```

在 `drivers/misc/Makefile` 加入：

```make
obj-$(CONFIG_HOUMO_XH2A) += houmo/
```

若同时移植 RKEP，则再加入：

```kconfig
source "drivers/misc/rockchip/Kconfig"
```

```make
obj-$(CONFIG_PCIE_FUNC_RKEP) += rockchip/
```

## 3. 配置内核

在目标 defconfig 或配置 fragment 中打开：

```text
CONFIG_PCI=y
CONFIG_PCI_MSI=y
CONFIG_PM=y
CONFIG_PCIE_SPACEMIT_EP=y       # K3 平台已有对应 PCIe 支持时打开
CONFIG_PCIE_FUNC_RKEP=y         # 使用 RKEP 时打开
CONFIG_HOUMO_XH2A=y
```

`HOUMO_XH2A` 的依赖是 `PCI`、`PCI_MSI`、`PM`。如果不确定后摩卡 NOR 型号，选择默认的 `HOUMO_XH2A_NOR_UNKNOWN`；明确使用 Micron 或 GigaDevice 时，在 menuconfig 中选择对应项。

当前 K3 AIBOX-PRO 工程使用的配置 fragment 是：

```text
arch/riscv/configs/k3-firefly-aibox-pro-kernel.config
```

其中至少包含：

```text
CONFIG_PCIE_FUNC_RKEP=y
CONFIG_PCIE_SPACEMIT_EP=y
CONFIG_HOUMO_XH2A=y
```

## 4. 检查 PCIe 设备 ID

后摩驱动按 PCI ID 匹配，不需要新增设备树节点。确认目标设备 ID 与驱动一致：

```text
0x1f6b:0x0c00
0x1ec8:0x0c00
```

如果供应商或设备 ID 不同，修改：

```text
drivers/misc/houmo/pcie/xh2a_pcie.h
```

中的 `XH2A_PCIE_EP_VID/DID` 或 `XH2A_PCIE_EP_ALT_VID/DID`，然后重新编译。

## 5. 编译

### SDK 标准方式

在 SDK 根目录执行：

```bash
# 首次使用 SDK 时配置目标
make envconfig

# 修改内核源码后增量编译
make linux-rebuild
```

`linux-rebuild` 会使用当前 Buildroot 配置重新生成内核及模块。目标配置必须包含 `k3-firefly-aibox-pro-kernel.config`（或你自己的配置 fragment）。

### 只验证内核编译

进入已有内核构建目录执行：

```bash
SDK_ROOT=$PWD
make -C "$SDK_ROOT/output/firefly-k3-aibox-pro/build/linux-custom" \
    ARCH=riscv \
    CROSS_COMPILE="$SDK_ROOT/output/firefly-k3-aibox-pro/host/bin/riscv64-unknown-linux-gnu-" \
    olddefconfig Image modules
```

确认生成：

```text
output/firefly-k3-aibox-pro/build/linux-custom/drivers/misc/houmo/xh2a_drv.ko
```

若配置为 `y`，驱动会链接进内核，不生成 `.ko`；若配置为 `m`，使用 `modules_install` 安装模块。

## 6. 部署到板端

将新内核、设备树和模块放入目标系统。使用 SDK 镜像流程时，推荐：

```bash
./aibox-pro-build.sh rebuild
```

该命令会重新编译 `Image` 和 AIBOX-PRO DTB，并更新 `bootfs.img`。刷入或替换板端镜像后重启。

如果驱动配置为模块，板端执行：

```bash
depmod -a
modprobe xh2a_drv
```

没有模块依赖数据库时可临时执行：

```bash
insmod /lib/modules/$(uname -r)/extra/xh2a_drv.ko
```

## 7. 验证

先确认 PCIe 链路和设备枚举：

```bash
lspci -nn
dmesg | grep -Ei 'pcie|xh2a|houmo'
```

应看到 `1f6b:0c00` 或 `1ec8:0c00`。再确认驱动绑定：

```bash
ls -l /sys/bus/pci/drivers/houmo,xh2a/
cat /sys/bus/pci/drivers/houmo,xh2a/driver_version
ls -l /dev/xh2a*
```

通常应出现 `xh2a_ctl0` 以及 IPU、内存、I2C、QSPI、rpmsg 等对应设备节点。

## 8. 故障定位顺序

1. `lspci` 看不到设备：先查供电、PERST、参考时钟、PCIe 链路和 endpoint 固件；这不是后摩 host 驱动问题。
2. `lspci` 能看到但无 `xh2a` 日志：检查 `CONFIG_HOUMO_XH2A`、`CONFIG_PCI_MSI`、`CONFIG_PM`，以及 `xh2a_pcie.h` 中的 VID/DID。
3. 有 probe 失败日志：重点检查 PCIe BAR、MSI、中断数量、DMA 地址宽度和 endpoint 固件版本。
4. `/dev` 节点不完整：确认 `xh2a_drv` 已加载且 PCIe probe 成功，再查看完整 `dmesg`。
