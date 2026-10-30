# xh2a 驱动与 K3 内核 ABI 不匹配排查与解决方案

## 1. 适用问题

适用于 K3 板端加载 `xh2a_drv.ko` 后出现以下现象：

- `insmod` 后内核在 `devm_kmalloc()`、`add_dr()` 或 `xh2a_pcie_probe()` 附近 Oops。
- 只创建了 `/dev/xh2a_ctl0`，没有 IPU、内存、I2C、RPMSG 等完整设备节点。
- `hm_smi -a` 返回 9，提示没有安装驱动。
- 模块的 `vermagic` 显示为相同的 `6.18.3`，但运行结果仍然异常。
- 外部模块编译时使用的 headers、`.config`、`autoconf.h` 与运行内核不一致。

本文记录的核心问题是：模块编译时得到的 `struct pci_dev` 布局与运行内核不一致。

## 2. 结论先行

`CONFIG_KPROBES` 与 `struct pci_dev` 的字段偏移无关。配置中存在：

```text
# CONFIG_KPROBES is not set
```

并不能解释 176 和 192 的差异。

本次 16 字节差异来自 `CONFIG_PCIEPORTBUS`：

```c
#ifdef CONFIG_PCIEPORTBUS
        struct rcec_ea *rcec_ea;
        struct pci_dev *rcec;
#endif
```

两个指针共增加 16 字节，因此：

| 编译条件 | `struct pci_dev.dev` 偏移 |
| --- | ---: |
| `CONFIG_PCIEPORTBUS` 未定义 | 176 |
| `CONFIG_PCIEPORTBUS=y` | 192 |

`CONFIG_PCIEAER` 等其他条件字段也可能影响布局，不能只检查 `KPROBES`。

176 或 192 不能凭经验写死。每一块板都必须以实际运行内核对应的 `vmlinux` DWARF 测量结果为准；本次板端最终以 192 模块成功 probe 并通过 `hm_smi` 验证，说明原先的 176 headers 不是匹配的运行内核 ABI。

## 3. 为什么会导致 Oops

驱动源码中有类似调用：

```c
devm_kzalloc(&pdev->dev, size, GFP_KERNEL);
```

编译器会根据编译时看到的 `struct pci_dev` 定义计算 `&pdev->dev`。如果模块按偏移 176 编译，而运行内核实际把 `dev` 放在 192，模块传给内核的就不是有效的 `struct device *`。

随后内核在 `devm_kmalloc()` / `add_dr()` 中访问错误地址，典型日志为：

```text
Unable to handle kernel paging request
epc : add_dr+...
ra  : devm_kmalloc+...
xh2a_pcie_probe+...
```

这不是 `hm_smi` 本身的问题，也不是 PCIe 供电问题，而是外部模块与内核头文件 ABI 不匹配。

## 4. 本次故障的实际证据

本次保存的模块 DWARF 检查结果：

| 文件 | `struct pci_dev.dev` | 说明 |
| --- | ---: | --- |
| `/tmp/xh2a_drv.board-before.ko` | 176 | 板端原始模块，加载后 probe Oops |
| `/tmp/xh2a-k3-build/linux_driver/linux-driver/linux/xh2a_drv.ko` | 192 | 使用 SDK `linux-custom` 构建的模块 |

对应 SHA256：

```text
510b88f8d01d13be182ca1c927a824071b37cc38e8b55bd8fd749b8eabaf72d5  原始模块
aa3f7bc60060264c3a0913d782a302c84b4221b25bf666151f680bdaa443f122  修复模块
```

SDK 的生成配置包含：

```text
CONFIG_PCIEPORTBUS=y
```

板端旧的：

```text
/usr/lib/modules/6.18.3/build/include/generated/autoconf.h
```

没有 `CONFIG_PCIEPORTBUS`，所以该 headers 会把 `struct pci_dev.dev` 编译成偏移 176。板端这个 build 目录不能作为可靠的外部模块构建目录。

修复模块加载后得到的验证结果：

- `xh2a_drv` 状态为 `Live`，不再是 `Loading`。
- `0000:01:00.0` 和 `0004:01:00.0` 都成功执行 `xh2a_pcie_probe`。
- IPU、内存、I2C、RPMSG 等完整设备节点出现。
- `hm_smi -a` 返回 `0`。
- 复测没有新的 Oops。

## 5. 下一块板的标准排查流程

### 5.1 先记录运行环境

在板端执行：

```sh
uname -a
uname -r
readlink -f /usr/lib/modules/$(uname -r)/build
modinfo /opt/xh2a-for-bianbu-houmo/ko/xh2a_drv.ko
```

注意：`vermagic=6.18.3` 只能说明基础内核版本字符串相同，不能证明 `struct pci_dev` 等内核结构体布局相同。

### 5.2 检查实际编译使用的生成配置

```sh
KDIR=/usr/lib/modules/$(uname -r)/build

grep -n 'CONFIG_KPROBES' "$KDIR/include/generated/autoconf.h" 2>/dev/null || true
grep -n 'CONFIG_PCIEAER' "$KDIR/include/generated/autoconf.h" 2>/dev/null || true
grep -n 'CONFIG_PCIEPORTBUS' "$KDIR/include/generated/autoconf.h" 2>/dev/null || true
grep -n 'CONFIG_PCIEASPM' "$KDIR/include/generated/autoconf.h" 2>/dev/null || true

test -e "$KDIR/include/config/PCIEPORTBUS" && echo PCIEPORTBUS=y || echo PCIEPORTBUS=not-set
```

必须检查 `include/generated/autoconf.h` 和 `include/config/*`，不能只看某个 `.config` 文件。`.config` 显示为 `y`、但生成头文件没有对应宏时，说明 headers 是 stale 或来自另一套内核构建。

### 5.3 直接测量运行内核的结构体布局

最可靠的方法是使用**实际运行内核对应的、带 DWARF 的 `vmlinux`**：

```sh
pahole -C pci_dev /path/to/matching/vmlinux | sed -n '1,140p'
```

查看输出中的：

```text
struct device dev; /* 176 或 192 */
```

不要用旧模块的 `dev` 偏移反推运行内核偏移。模块本身可能就是错误的。

同时检查候选模块：

```sh
pahole -C pci_dev xh2a_drv.ko
```

如果系统没有 `pahole`，可以使用 DWARF：

```sh
LC_ALL=C readelf --debug-dump=info xh2a_drv.ko |
awk '
/DW_TAG_structure_type/ { in_pci=0; want_dev=0 }
/DW_AT_name.*pci_dev$/ { in_pci=1 }
in_pci && /DW_AT_name.*: dev$/ { want_dev=1 }
in_pci && want_dev && /DW_AT_data_member_location/ { print; exit }
'
```

### 5.4 必须使用同一套内核源和输出目录编译

推荐使用 SDK 中已经生成并用于打包内核的目录，例如：

```sh
KERNEL_DIR=/path/to/output/firefly-k3-aibox-pro/build/linux-custom
DRIVER_DIR=/tmp/xh2a-linux-driver/linux_driver/linux-driver/linux
CROSS_COMPILE=/usr/local/riscv/spacemit-toolchain-linux-glibc-x86_64-v1.2.4/bin/riscv64-unknown-linux-gnu-

make -C "$DRIVER_DIR" \
    KERNEL_DIR="$KERNEL_DIR" \
    TARGET_ARCH=riscv \
    CROSS_COMPILE="$CROSS_COMPILE"
```

编译前确认：

```sh
grep -n '^CONFIG_PCIEPORTBUS' "$KERNEL_DIR/.config"
grep -n 'CONFIG_PCIEPORTBUS' "$KERNEL_DIR/include/generated/autoconf.h"
test -e "$KERNEL_DIR/include/config/PCIEPORTBUS" && echo generated-config-ok
```

如果内核使用独立输出目录，必须将 `KERNEL_DIR` 指向包含正确 `.config`、`include/generated`、`include/config` 和 `Module.symvers` 的输出目录，而不是只包含少量头文件的 `/usr/lib/modules/.../build` 链接目录。

如果 headers 与 `.config` 不一致，应重新准备匹配的内核输出：

```sh
make -C "$KERNEL_SRC" O="$KERNEL_OUT" ARCH=riscv olddefconfig
make -C "$KERNEL_SRC" O="$KERNEL_OUT" ARCH=riscv prepare modules_prepare
```

不要手工编辑 `autoconf.h` 或 `include/config/PCIEPORTBUS`。这些文件必须由对应内核构建生成。

### 5.5 处理 modpost 主机工具不兼容

如果出现类似错误：

```text
scripts/mod/modpost: version `GLIBC_2.38' not found
```

这只是主机端 `modpost` 二进制与当前主机 glibc 不兼容，不是驱动源代码错误。应在临时目录重新构建与内核源码匹配的 `modpost`，或使用可在当前主机运行的同版本 `scripts/mod/modpost`：

```sh
make -C "$KERNEL_DIR" HOSTCC=gcc scripts/mod/modpost
```

如果不允许改动 SDK，把内核源/输出复制到 `/tmp` 后构建，并通过：

```sh
MODPOST=/tmp/matching-modpost
```

传给外部模块构建。不要通过跳过 `modpost` 来掩盖问题。

### 5.6 上传前静态验收

```sh
modinfo xh2a_drv.ko | grep -E 'vermagic|srcversion|name'
pahole -C pci_dev xh2a_drv.ko
file xh2a_drv.ko
```

模块中的 `dev` 偏移必须与实际运行内核 `vmlinux` 一致。只要偏移不一致，就不能加载。

## 6. 板端替换和验证

### 6.1 先备份旧文件

```sh
adb root
adb connect <BOARD_IP>:5555
adb -s <BOARD_IP>:5555 pull \
    /opt/xh2a-for-bianbu-houmo/ko/xh2a_drv.ko \
    xh2a_drv.before.ko
```

### 6.2 处理启动自动加载

先查找加载入口：

```sh
adb -s <BOARD_IP>:5555 shell \
    'grep -R -n -i "xh2a_drv\|insmod" /etc /opt 2>/dev/null'
```

本次板端入口是：

```text
/etc/rc.local
insmod /opt/xh2a-for-bianbu-houmo/ko/xh2a_drv.ko
```

因此必须替换这个路径对应的文件，否则下一次启动仍会加载旧模块：

```sh
adb -s <BOARD_IP>:5555 push xh2a_drv.ko \
    /opt/xh2a-for-bianbu-houmo/ko/xh2a_drv.ko
adb -s <BOARD_IP>:5555 shell \
    'sha256sum /opt/xh2a-for-bianbu-houmo/ko/xh2a_drv.ko'
```

### 6.3 如果旧模块处于 `Loading`

如果 `/proc/modules` 显示：

```text
xh2a_drv ... Loading ...
```

并且 `rmmod` 报：

```text
Module xh2a_drv is in use
```

不要反复强制 `rmmod`。先同步文件系统：

```sh
sync
```

然后使用硬件复位或已确认安全的直接复位。普通 `reboot` 可能在旧模块的 PCI shutdown 状态下卡在：

```text
systemd-shutdown: Rebooting.
```

这表示用户空间关机已经完成，卡点位于后续内核/SoC 复位阶段。硬件复位后，启动入口会加载已经替换的新模块。

### 6.4 运行时验证

```sh
grep '^xh2a_drv ' /proc/modules
ls -l /dev/xh2a*
lspci -nnk | grep -A3 -B1 -E '1ec8:0c00|1f6b:0c00'
dmesg -T | grep -i -E 'xh2a|Oops|Unable to handle|Call Trace'
hm_smi -a
echo $?
```

成功标准：

1. `/proc/modules` 中模块状态为 `Live`，不是 `Loading`。
2. 两个目标 PCI 端点都显示 `Kernel driver in use: houmo,xh2a`。
3. 存在 `xh2a_ipu0`、`xh2a_ipu1` 及其他完整设备节点。
4. `hm_smi -a` 返回 `0`。
5. `dmesg` 没有新的 Oops、paging request 或 Call Trace。

## 7. 回退方案

如果新模块验证失败：

```sh
adb -s <BOARD_IP>:5555 push xh2a_drv.before.ko \
    /opt/xh2a-for-bianbu-houmo/ko/xh2a_drv.ko
sync
```

然后硬件复位。文件替换只影响下一次加载，已经运行的旧模块不会因为覆盖文件而自动变成新模块。

## 8. 常见误判

### 误判一：`KPROBES` 关闭就能固定结构体布局

错误。`CONFIG_KPROBES` 不控制 `struct pci_dev` 的条件字段。应检查实际运行 `vmlinux`、`CONFIG_PCIEPORTBUS`、`CONFIG_PCIEAER` 以及生成 headers。

### 误判二：`vermagic` 相同就可以加载

错误。`vermagic` 通常只包含内核版本、SMP、抢占、架构等信息，不编码所有结构体布局条件。

### 误判三：只看 `.config` 不看 `autoconf.h`

错误。外部模块编译使用的是生成后的配置头。`.config` 与 `include/generated/autoconf.h` 不一致时，模块会按错误布局编译。

### 误判四：手动在模块源码中把 176 改成 192

错误。结构体偏移不能在驱动中硬编码修复。必须使模块和运行内核使用同一套内核源、配置、生成头和编译流程。

## 9. 最终经验

1. 先测量运行内核的真实 DWARF 布局，再决定模块应为 176 还是 192。
2. 对外部模块而言，`KERNEL_DIR` 的生成目录比 `uname -r` 更重要。
3. 看到 `devm_kmalloc()` 入口 Oops、模块只创建控制节点、`hm_smi` 返回 9 时，优先检查内核结构体 ABI。
4. 任何用于下一块板的模块都应在加载前完成 `pahole`/DWARF 偏移对比，并保留原模块回退副本。
