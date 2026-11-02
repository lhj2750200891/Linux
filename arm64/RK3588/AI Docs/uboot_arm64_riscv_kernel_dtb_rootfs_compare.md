# ARM64 与 RISC-V SDK 的 U-Boot 启动链对比

本文基于当前目录下的 Rockchip ARM64 SDK、SpacemiT K3 RISC-V SDK 及其生成的 Firefly-K3 镜像，说明 U-Boot 阶段如何取得内核镜像和设备树，以及 `bootargs` 如何参与根文件系统启动。

## 先给结论

需要先纠正一个容易混淆的说法：**U-Boot 通常不负责“挂载”Linux 根文件系统**。U-Boot 做的是：

1. 从存储介质或分区读取内核、设备树和可选 initrd/initramfs；
2. 将它们放到约定的 DDR 地址；
3. 组合或修改传给 Linux 的命令行 `bootargs`；
4. 通过 `bootm`、`booti` 或 `bootz` 把控制权交给 Linux。

真正执行 `mount -t ext4 ...`、挂载 UBI/UBIFS、解析 `root=` 的，是 Linux 内核、initramfs 中的 `/init` 或后续的 `/sbin/init`。

三种启动模型可以概括为：

| 平台 | 内核/DTB 的组织方式 | 典型加载方式 | U-Boot 中的典型入口 | 根文件系统处理 |
|---|---|---|---|---|
| NXP i.MX6ULL 经典方式 | `zImage` 和 `.dtb` 是两个独立文件 | `fatload`/`ext4load` 分别加载到固定地址 | `bootz kernel_addr - fdt_addr` | `bootargs` 传 `root=/dev/...`、`rootfstype=...`，Linux 再挂载 |
| Rockchip ARM64（RK3588） | 常见是 `boot.img`/FIT，内含 kernel、DTB、可选 ramdisk；也支持分量搬运 | 从 `boot`/`recovery` 分区读取整体镜像，再按 FIT/uImage 元数据分配到 `kernel_addr_r`、`fdt_addr_r` 等地址 | FIT/uImage 通常走 `bootm`；裸 `Image` 可走 `booti`，zImage 可走 `bootz` | U-Boot 合并 DTB `/chosen/bootargs`、分区参数和环境变量；Linux 负责真正挂载 |
| SpacemiT K3 RISC-V | `bootfs` 是 ext4 文件系统，里面有独立的 kernel、多个 DTB、`initrd.img` | U-Boot 对 `bootfs` 执行 `load`，分别加载 kernel、DTB、ramdisk | FIT (`Image.itb`) 走 `bootm`，裸/压缩 Image 分支走 `booti` | U-Boot 根据启动介质设置 `root=PARTUUID=...`、`root=ubi0:rootfs` 或 `root=/dev/nfs`；K3 initramfs `/init` 再执行实际挂载 |

地址本身不是 ARM64 或 RISC-V 架构的固定标准，而是板级 DDR 映射和 U-Boot 配置的结果。当前 SDK 中，RK3588 使用低于 0x100000000 的地址，K3 使用 0x100000000 以上的地址。

## 1. ARM64：Rockchip RK3588

以下以 `arm64/rockchip/rk3588_6.1.118_sdk` 为代表。该 SDK 同时保留了 FIT/uImage 处理代码，因此要区分“镜像构建格式”和“U-Boot 运行时分量地址”。

### 1.1 U-Boot 约定的运行时地址

证据：

`arm64/rockchip/rk3588_6.1.118_sdk/u-boot/include/configs/rk3588_common.h:74-88`

文件中的注释给出了内存区域：解压后的内核约为 `4M~84M`，压缩内核约为 `84M~130M`。同一段配置定义了：

```text
scriptaddr    = 0x00500000
pxefile_addr_r = 0x00600000
fdt_addr_r    = 0x08300000
kernel_addr_r = 0x00400000
kernel_addr_c = 0x05480000
ramdisk_addr_r = 0x0a200000
```

因此，RK3588 的典型运行时布局是：

```text
0x00400000  kernel_addr_r  解压后/普通 Image 的目标地址
0x05480000  kernel_addr_c  压缩内核的暂存地址
0x08300000  fdt_addr_r     Linux 设备树地址
0x0a200000  ramdisk_addr_r initrd/ramdisk 地址
```

这与 i.MX6ULL 示例中常见的 `0x80800000`、`0x83000000` 不是冲突，而是两个平台的 DDR 映射不同。

### 1.2 从 boot/recovery 分区取得镜像

证据：

`arm64/rockchip/rk3588_6.1.118_sdk/u-boot/arch/arm/mach-rockchip/uimage.c:74-123`

`uimage_load_bootables()` 从 U-Boot 环境读取 `kernel_addr_r`、`fdt_addr_r`、`ramdisk_addr_r`，根据启动模式选择 `PART_BOOT` 或 `PART_RECOVERY`，找到对应分区后把整个 bootable image 读入内存。

随后，`uimage_sysmem_reserve_each()` 把多镜像中的各个组件安排到环境地址：

`uimage.c:126-166`

- component 0（kernel）使用 `kernel_addr_r` 或压缩内核地址；
- component 1（ramdisk）使用 `ramdisk_addr_r`；
- component 2（FDT）使用 `fdt_addr_r`；
- 同时设置 `fdt_high`、`initrd_high` 和 `bootm-reloc-at`。

也就是说，Rockchip 的常规启动不一定表现为用户在命令行里看到的三条独立 `fatload`。它可以先读取整个 `boot.img`/uImage，再由 U-Boot 解析内部组件。

### 1.3 FIT 镜像如何描述 kernel 和 DTB

证据：

`arm64/rockchip/rk3588_6.1.118_sdk/device/rockchip/.chips/rk3588/boot.its:11-64`

该 FIT 描述包含：

- `fdt` 节点：`data=/incbin/("@KERNEL_DTB@")`，类型 `flat_dt`，架构 `arm64`；
- `kernel` 节点：`data=/incbin/("@KERNEL_IMG@")`，类型 `kernel`，架构 `arm64`，Linux 入口；
- 可选 `resource` 节点；
- `configurations` 把 kernel、fdt、resource 绑定起来。

`zboot.its:24-36` 的差别是 kernel compression 写成 `lz4`。构建脚本
`device/rockchip/common/scripts/mk-fitimage.sh:26-31`
会把实际 DTB、kernel、resource 路径替换到 ITS，然后调用 Rockchip `mkimage` 生成 FIT。

ITS 中的 `load = <0xffffff00>`、`entry = <0xffffff01>` 是 Rockchip FIT 生成阶段的占位/特殊语义，不能直接当作最终 DDR 地址。运行时地址由 U-Boot 环境和 FIT 预处理逻辑决定。

### 1.4 FIT 运行时分配和 `bootm`/`booti`/`bootz`

证据：

`arm64/rockchip/rk3588_6.1.118_sdk/u-boot/arch/arm/mach-rockchip/fit.c:260-323`

`fit_image_pre_process()` 的关键行为是：

- FDT 根据 `fdt_addr_r` 分配；
- 64 位 Image 默认根据 `kernel_addr_r` 分配；
- 32 位 ARM 可使用 `kernel_addr_aarch32_r`；
- 如果 `bootz_setup()` 识别出 zImage，则使用 `kernel_addr_c`，否则使用 `kernel_addr_r`；
- ramdisk 使用 `ramdisk_addr_r`。

因此，ARM64 SDK 的实际逻辑不是“所有内核都固定用一个地址”，而是由镜像格式决定：

```text
FIT/uImage       -> U-Boot 解析组件，通常以 bootm 进入
普通 arm64 Image -> 目标地址 kernel_addr_r，通常以 booti 进入
zImage           -> 压缩地址 kernel_addr_c，通常以 bootz 进入
```

Rockchip 的 `boot_rkimg.c` 还编译启用了 `bootm`、`booti`、`bootz` 三类命令支持；实际使用哪一条取决于生成的镜像格式和启动脚本。

### 1.5 ARM64 的分区和 rootfs 线索

证据：

`arm64/rockchip/rk3588_6.1.118_sdk/device/rockchip/.chips/rk3588/parameter-buildroot-fit.txt:10-14`

其中定义了 GPT 分区、`boot` 分区、`rootfs` 分区以及 rootfs UUID，例如：

```text
CMDLINE: ... (boot:bootable) ... (rootfs)
uuid:rootfs=614e0000-0000-4b53-8000-1d2800000000
uuid:boot=7A3F0000-0000-4B53-8000-1D2800000000
```

`output/update/Image/package-file:1-10` 又明确把 `boot.img`、`rootfs.img` 分别打包为 boot 和 rootfs 分区内容。

这里的参数文件主要描述分区和 UUID；最终传给 Linux 的 `root=` 可能来自 DTB `/chosen/bootargs`、环境变量或 Android AB 逻辑，并不等价于参数文件本身就是一次 `mount` 操作。

### 1.6 ARM64 的 bootargs 合成

证据：

`arm64/rockchip/rk3588_6.1.118_sdk/u-boot/arch/arm/mach-rockchip/board.c:1515-1638`

`board_fdt_chosen_bootargs()` 及其辅助函数会：

1. 读取 DTB `/chosen/bootargs` 和 `/chosen/bootargs_ext`；
2. 合并 U-Boot 环境中的 `bootargs`；
3. 添加 `mtdparts` 或 `blkdevparts`；
4. 添加 `sys_bootargs`、固件版本、Android 启动参数；
5. 在 Android A/B 场景下清理旧的 `root=`，让 bootctl/分区选择逻辑重新决定 root UUID；
6. 删除旧式 `initrd=` 等不再适用的参数。

这证明 U-Boot 的职责是**准备 Linux 命令行和设备树 chosen 节点**。它不会在此处调用 Linux 的 `mount`，也不会替代内核的块设备、ext4 或 squashfs 驱动。

## 2. RISC-V：SpacemiT K3

以下使用 `riscv/spacemit/k3_6.18.3_sdk`，并用 `riscv/download_file/Firefly-K3_Buildroot_debug_260910` 中的实际镜像交叉验证。

### 2.1 K3 的地址布局

源码证据：

`riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/include/configs/k3.h:18-24`

```text
RAMDISK_LOAD_ADDR = 0x130000000
KERNEL_DTB_ADDR   = 0x138000000
```

`k3.h:206-223` 又定义：

```text
kernel_comp_addr_r = CONFIG_SYS_LOAD_ADDR
kernel_addr_r      = CONFIG_FASTBOOT_BUF_ADDR
ramdisk_addr_r     = 0x130000000
fdt_addr_r         = 0x138000000
```

配置文件证据：

`riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/configs/k3_defconfig:1-24`

```text
CONFIG_SYS_TEXT_BASE=0x102000000
CONFIG_SYS_LOAD_ADDR=0x102000000
CONFIG_SPL_OPENSBI_LOAD_ADDR=0x100000000
CONFIG_SPL_LOAD_FIT_ADDRESS=0x140000000
```

实际生成的 `env.bin` 中也能看到：

```text
fdt_addr_r=0x138000000
kernel_addr_r=0x140000000
kernel_comp_addr_r=0x102000000
ramdisk_addr_r=0x130000000
```

所以 K3 的 Linux 启动地址明显位于 4 GiB 以上，原因是 K3 的板级 DDR/地址映射和 U-Boot 配置如此，并不是 RISC-V 指令集规定所有系统都必须使用这些地址。

### 2.2 K3 bootfs 是“文件系统中的多个文件”

K3 和典型的 i.MX6ULL 文件启动方式更接近。证据：

`riscv/spacemit/k3_6.18.3_sdk/buildroot-ext/board/spacemit/k3/gen_bootfs.sh:36-60,89-123,142-145`

该脚本会检查并复制：

- kernel image；
- 一个或多个 DTB；
- `initrd.img`（如果生成）；
- `env_k3.txt` 和启动 logo；

然后创建 ext4 的 bootfs 镜像。

对实际下载镜像执行 ext4 目录检查得到：

```text
riscv/download_file/Firefly-K3_Buildroot_debug_260910/bootfs.img
  Image
  initrd.img
  k3-firefly-aibox-pro.dtb
  k3-firefly-spcda400-k3.dtb
  ...（多个板型 DTB）
```

也就是说，K3 的 bootfs 并不是一个只包含单一 FIT 的黑盒；它是一个 ext4 文件系统，U-Boot 可以按文件名分别取 kernel、DTB 和 initrd。

实际镜像的分区描述也支持这一点：

`riscv/spacemit/k3_6.18.3_sdk/buildroot-ext/board/spacemit/k3/partition_universal.json:51-63`

把 `bootfs` 单独放在 12 MiB 起始、256 MiB 大小的分区，`rootfs` 放在后续分区。生成的 `genimage.cfg` 具有相同的 bootfs/rootfs 分离关系。

### 2.3 K3 U-Boot 的逐文件加载命令

证据：

`riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/board/spacemit/k3/k3.env:153-190`

核心环境变量如下：

```text
loadknl=load ${boot_devname} ${boot_devnum}:${bootfs_part} ${kernel_addr_r} ${knl_name}
loaddtb=load ${boot_devname} ${boot_devnum}:${bootfs_part} ${fdt_addr_r} ${dtb_dir}/${dtb_name}
loadramdisk=load ${boot_devname} ${boot_devnum}:${bootfs_part} ${ramdisk_addr_r} ${ramdisk_name}
```

然后：

```text
start_kernel=
    fdt addr ${kernel_addr_r};
    if fdt list /; then
        bootm ${kernel_addr_r} ${ramdisk_combo} ${fdt_addr_r};
    else
        booti ${kernel_addr_r} ${ramdisk_combo} ${fdt_addr_r};
    fi
```

最终的 `boot_kernel` 顺序是：

```text
run set_root_arg
run detect_dtb
run loadknl
run loaddtb
run loadramdisk
run start_kernel
```

这与用户给出的 i.MX6ULL 模式非常相似：先把 kernel 和 DTB 放到地址，再启动；区别在于 K3 的命令使用 `load` 访问 bootfs 文件系统，地址是 `0x140000000`/`0x138000000`/`0x130000000`，并且启动入口会根据文件是否为 FIT 在 `bootm` 和 `booti` 之间选择。

### 2.4 K3 的 kernel 名称和实际镜像一致性

`k3.env:77-87` 的源码逻辑是：

```text
有 FIT 签名 -> knl_name=Image.itb
否则       -> knl_name=Image.gz
```

而当前下载的 `env.bin` 中确实出现了 `knl_name=Image.gz`，同时实际 `bootfs.img` 目录检查看到的 kernel 文件名是 `Image`。这说明不同构建产物或环境变体之间可能存在命名差异；刷写前必须确认部署的 `env_k3.txt/env.bin` 与 bootfs 内核文件名一致，否则 `loadknl` 会因找不到文件而失败。K3 U-Boot 的 NAND/UBI 分支也明确同时处理 `Image.itb` 和 `Image`：

`k3.env:217-238`

### 2.5 K3 各种存储介质的 root 参数

证据：

`riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/board/spacemit/k3/k3.env:58-61,201-213,240-274,276-317,326-349`

K3 根据启动介质选择不同的 root 描述：

```text
MMC/UFS:
  root=PARTUUID=${rootfs_guid}
  bootfs=PARTUUID=${bootfs_guid}
  rootwait rootfstype=ext4

NAND/UBI:
  root=ubi0:rootfs
  rootfstype=ubifs
  ubi.mtd=6

NOR:
  root=/dev/mtdblock6
  rootfstype=squashfs 或 ext4

NFS:
  root=/dev/nfs
  nfsroot=<server>:<path>,<options>
```

`set_root_arg` 会把计算出的 rootfs/bootfs GUID 追加到 `bootargs`：

```text
root=PARTUUID=${rootfs_guid} bootfs=PARTUUID=${bootfs_guid}
```

因此，K3 的 bootargs 不是一个固定字符串，而是由启动介质、分区 GUID、文件系统类型和网络启动选项共同生成。

### 2.6 K3 的 SPL 与 U-Boot 分工

证据：

`riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/board/spacemit/k3/spl_extra_fit.c:67-95,148-233,800-938`

K3 的 SPL 会从 MMC/分区加载 `esos.itb`、`u-boot.itb` 等早期启动组件，并把相应 FIT 的 DTB 和入口地址交给后续阶段。这个 DTB 主要是 OpenSBI/U-Boot/板级早期启动使用的 DTB；Linux 的 kernel DTB 则是在后续 `k3.env` 的 `loaddtb` 中从 bootfs 读取。

因此要区分两类设备树：

```text
SPL/U-Boot FIT 中的 DTB -> 供 U-Boot 自身及早期启动阶段使用
bootfs/${dtb_dir}/${dtb_name} -> 作为 Linux 启动参数传给内核
```

K3 的 `uboot_fdt.its`（`board/spacemit/k3/configs/uboot_fdt.its:1-39` 及后续 fdt 节点）证明了前一种 FIT 内嵌 DTB；bootfs 目录内容证明了后一种 Linux DTB 是独立文件。

## 3. 根文件系统到底在哪里挂载

### 3.1 U-Boot 阶段：只准备参数和地址

U-Boot 做的事情可以表示为：

```text
读取 kernel/DTB/initrd
        |
        v
放到 kernel_addr_r/fdt_addr_r/ramdisk_addr_r
        |
        v
合成 bootargs，例如 root=PARTUUID=... 或 root=ubi0:rootfs
        |
        v
bootm / booti / bootz
```

### 3.2 Linux/initramfs 阶段：执行真正的挂载

K3 SDK 提供了非常直接的证明：

`riscv/spacemit/k3_6.18.3_sdk/buildroot-ext/board/spacemit/k3/target_overlay/init:207-291`

这个 `/init` 会：

1. 从 `/proc/cmdline` 解析 `root=`、`rootfstype=`、`bootfs=`、`ubi.mtd=`、`nfsroot=`；
2. 如果 `root=ubi...`，执行 UBI attach 并挂载 `ubiX:VOL`；
3. 否则等待 root 块设备出现；
4. 执行 `mount -t "$ROOTFSTYPE" ... "$ROOT" /rootfs`；
5. 把 `/proc`、`/sys`、`/dev`、`/run` 等移动到新根，再 `run-init`。

这就是“bootargs 指定根文件系统”和“真正挂载根文件系统”的边界：U-Boot 只负责把字符串传下去，早期用户空间脚本负责把字符串转换成实际的 mount 操作。

## 4. 与 i.MX6ULL `fatload + bootz` 模式的对比

用户给出的 i.MX6ULL 例子可以抽象为：

```text
fatload mmc <dev>:<part> 0x80800000 zImage
fatload mmc <dev>:<part> 0x83000000 board.dtb
setenv bootargs 'console=... root=/dev/mmcblk0p2 rootwait rw'
bootz 0x80800000 - 0x83000000
```

当前目录内的 Boundary Devices U-Boot 脚本也提供了同一模型的直接证据：

`riscv/spacemit/k3_6.18.3_sdk/buildroot/board/boundarydevices/common/boot.cmd:1-6,27-30,50-51,167-168`

- 默认 `kernelimage=zImage`、`bootcommand=bootz`；
- 以 `a_base=0x10000000` 为基础计算 `a_zImage=a_base+0x00800000`、`a_fdt=a_base+0x03000000`；
- 当 CPU 字符串为 `6UL` 时选择 `imx6ull-${board}.dtb`；
- 用 `load ... ${a_zImage} ...` 读取 kernel，然后执行 `${bootcommand} ${a_zImage} - ${a_fdt}`。

这份脚本的地址与某些 i.MX6ULL 板卡常见的 `0x80800000`/`0x83000000` 略有不同，但启动结构完全相同：独立文件、固定地址、`bootz kernel - dtb`。地址差异来自具体板卡的 U-Boot 内存布局，不改变启动机制。

其特点是：

- kernel 和 DTB 是两个独立文件；
- 地址由启动脚本直接写死或由环境变量展开；
- `bootz` 明确表示输入是 ARM zImage；
- `root=` 通过 bootargs 传给 Linux；
- rootfs 仍由 Linux/initramfs 挂载，而不是 `bootz` 或 U-Boot 挂载。

与之相比：

1. **RK3588** 更偏向 Android/FIT：先读 `boot`/`recovery` 镜像，再由 U-Boot 按 FIT/uImage 组件解析，通常走 `bootm`；地址集中由 `rk3588_common.h` 维护。
2. **K3** 更偏向文件系统启动：bootfs 是 ext4，kernel、DTB、initrd 都是可见文件，环境脚本逐个 `load`，然后在 `bootm`/`booti` 间选择。
3. **i.MX6ULL** 的经典裸文件方式和 K3 的“逐文件加载”相似，但命令、地址和 kernel 格式不同；i.MX6ULL 常见是 `zImage + dtb + bootz`，K3 常见是 `Image`/`Image.gz`/`Image.itb + dtb + booti/bootm`。

## 5. 三个平台的可复现检查清单

出现启动失败时，建议按以下顺序检查：

1. **确认镜像格式**：是 zImage、arm64 Image、FIT `Image.itb`、Android boot.img 还是 uImage。
2. **确认加载地址**：kernel、压缩 kernel、DTB、initrd 是否落在不重叠的 DDR 区域。
3. **确认文件/分区来源**：`fatload`/`ext4load`/`load` 的设备、分区号和路径是否正确；RK 是否实际在读 `boot` 或 `recovery` 分区。
4. **确认 DTB**：传给 Linux 的 DTB 是否与板型、内核版本和内存布局匹配；不要把 SPL/U-Boot FIT 中的 DTB 与 Linux DTB 混淆。
5. **确认 bootargs**：在 U-Boot 中打印最终 `bootargs`，重点看 `root=`、`rootfstype=`、`rootwait`、`ubi.mtd=`、`bootfs=` 和 `nfsroot=`。
6. **确认 rootfs 实际存在**：PARTUUID/GUID、分区 label、UBI volume 名称必须与分区表和镜像一致。
7. **确认文件名一致**：特别是 K3，源码可能选择 `Image.itb`/`Image.gz`，而实际 bootfs 可能是 `Image`；环境和 bootfs 必须成对验证。

## 6. 证据索引

### ARM64/RK3588

- `arm64/rockchip/rk3588_6.1.118_sdk/u-boot/include/configs/rk3588_common.h:74-98`：kernel、DTB、ramdisk 地址。
- `arm64/rockchip/rk3588_6.1.118_sdk/u-boot/arch/arm/mach-rockchip/uimage.c:74-166`：boot/recovery 分区读取和多镜像组件分配。
- `arm64/rockchip/rk3588_6.1.118_sdk/u-boot/arch/arm/mach-rockchip/fit.c:260-323`：FIT 对 kernel、zImage、DTB、ramdisk 的运行时地址处理。
- `arm64/rockchip/rk3588_6.1.118_sdk/device/rockchip/.chips/rk3588/boot.its:11-64`：FIT 中 kernel、DTB、resource 和 configuration。
- `arm64/rockchip/rk3588_6.1.118_sdk/device/rockchip/.chips/rk3588/parameter-buildroot-fit.txt:10-14`：boot/rootfs 分区和 UUID。
- `arm64/rockchip/rk3588_6.1.118_sdk/u-boot/arch/arm/mach-rockchip/board.c:1515-1638`：DTB bootargs、环境变量、分区参数的合并。

### RISC-V/K3

- `riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/include/configs/k3.h:18-24,206-223`：K3 DDR 地址和 U-Boot 环境地址。
- `riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/configs/k3_defconfig:1-24`：RISC-V、OpenSBI、FIT 加载地址。
- `riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/board/spacemit/k3/k3.env:58-190`：root 参数、kernel/DTB/ramdisk 加载和启动入口。
- `riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/board/spacemit/k3/k3.env:201-349`：NOR、NAND、MMC、UFS、NFS 各路径的 rootfs 参数。
- `riscv/spacemit/k3_6.18.3_sdk/buildroot-ext/board/spacemit/k3/gen_bootfs.sh:36-60,89-145`：bootfs 生成和 kernel/DTB/initrd 文件复制。
- `riscv/spacemit/k3_6.18.3_sdk/buildroot-ext/board/spacemit/k3/partition_universal.json:51-63`：bootfs/rootfs 分区布局。
- `riscv/spacemit/k3_6.18.3_sdk/buildroot-ext/board/spacemit/k3/target_overlay/init:207-291`：解析 bootargs 并真正 mount rootfs。
- `riscv/spacemit/k3_6.18.3_sdk/bsp-src/uboot-2022.10/board/spacemit/k3/spl_extra_fit.c:67-95,148-233,800-938`：SPL 加载 ESOS/U-Boot FIT 的早期启动链。
- `riscv/download_file/Firefly-K3_Buildroot_debug_260910/bootfs.img`：实际 ext4 bootfs，包含 `Image`、`initrd.img` 和多个 DTB。

### i.MX6ULL 经典启动

- `riscv/spacemit/k3_6.18.3_sdk/buildroot/board/boundarydevices/common/boot.cmd:1-6`：`zImage` + `bootz` 默认模型。
- `.../boot.cmd:27-30`：kernel、DTB、initrd 的地址计算。
- `.../boot.cmd:50-51`：6UL CPU 选择 `imx6ull-${board}.dtb`。
- `.../boot.cmd:167-168`：加载 zImage 后执行 `bootz ${a_zImage} - ${a_fdt}`。
