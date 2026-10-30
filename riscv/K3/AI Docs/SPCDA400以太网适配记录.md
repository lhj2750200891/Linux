# SPCDA400 双以太网适配记录

## 1. 问题现象

板卡为 SpacemiT K3 Firefly SPCDA400，系统为 Bianbu 4.0、Linux 6.18.3。

初始启动后只能枚举一张 RTL8125：

```text
0002:01:00.0 Ethernet controller: Realtek RTL8125 2.5GbE Controller
eth0
```

第二张网卡没有出现。此前 `r8169` 编译为模块时，udev 自动加载和手动 `modprobe r8169` 还会触发内核 Oops。

## 2. 硬件连接

### Ethernet0

```text
PCIE20_0 TX/RX/REFCLK -> PCIE4/USB3-D
ISOLATEB_M0           -> GPIO8
WAKEN_M0              -> GPIO81
CLKREQN_M0            -> GPIO80
PERSTN_M0             -> GPIO101
POW_EXT_M0            -> GPIO21
```

### Ethernet1

```text
PCIE20_1 TX/RX/REFCLK -> PCIE2/USB3-B
ISOLATEB_M1           -> GPIO36
WAKEN_M1              -> GPIO59
CLKREQN_M1            -> GPIO60
PERSTN_M1             -> GPIO58
POW_EXT_M1            -> GPIO86
```

## 3. 根因

### 3.1 PCIe 编号映射错误

原理图中的 `PCIE4/USB3-D` 是板级高速线路名称，不等于 Linux 设备树中的 `pcie4_rc` 节点。

SPCDA400 的实际映射为：

```text
PCIE4/USB3-D -> Linux pcie3_rc -> phy4
PCIE2/USB3-B -> Linux pcie2_rc -> phy2
```

此前错误使用 `pcie4_rc + phy5`，造成 PCIe4 链路为 down，第二网卡无法枚举。

### 3.2 GPIO 侧带冲突

GPIO101 是 Ethernet0 的外部 `PERST#`，由 PCIe 控制器通过 `reset-gpios` 请求。GPIO 控制器不能再同时申请 GPIO80/81/101 这一整组 pinctrl，否则会造成 pinmux/GPIO 所有权冲突。

GPIO8 和 GPIO36 仅用于两路网卡的 `ISOLATEB`，继续由 GPIO hog 保持高电平。

### 3.3 r8169 模块加载崩溃

原始驱动使用 `devm_alloc_etherdev()`，在当前平台探测 RTL8125 时触发 `devres_add()` Oops。改用普通 `alloc_etherdev()`，并在错误路径和 remove 路径显式 `free_netdev()`。

## 4. 设备树修改

修改文件：

```text
bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit/k3-firefly-spcda400.dtsi
```

Ethernet0 改为使用 `pcie3_rc/phy4`：

```dts
&phy4 {
    status = "okay";
};

&pcie3_rc {
    pinctrl-names = "default";
    pinctrl-0 = <&rtl8125_eth0_sideband_cfg>;
    phys = <&phy4>;
    phy-names = "phy4";
    reset-gpios = <&gpio K3_GPIO(101) GPIO_ACTIVE_LOW>;
    num-lanes = <1>;
    max-link-speed = <2>;
    vpcie3v3-supply = <&rtl8125_eth0_pwr>;
    status = "okay";
};
```

错误的 `pcie4_rc/phy5` 关闭：

```dts
&pcie4_rc {
    status = "disabled";
};
```

Ethernet0 电源为 GPIO21 低有效，Ethernet1 电源为 GPIO86 低有效。Ethernet1 的 `pcie2_rc` 配置保持不变。

GPIO 控制器只保留隔离引脚：

```dts
&gpio {
    pinctrl-names = "default";
    pinctrl-0 = <&rtl8125_isolate_cfg>;
};
```

## 5. r8169 内建配置

新增配置片段：

```text
bsp-src/linux-6.18/arch/riscv/configs/k3-firefly-spcda400-kernel.config
```

内容包含：

```text
CONFIG_NET_VENDOR_REALTEK=y
CONFIG_R8169=y
```

`kernel-fast-build.sh` 在 `olddefconfig` 前使用 `merge_config.sh` 合并该板级片段，避免旧输出目录的 `.config` 将驱动覆盖回 `m`。

验证：

```bash
grep '^CONFIG_R8169=' output/firefly-k3-spcda400/build/linux-custom/.config
grep -Fx 'kernel/drivers/net/ethernet/realtek/r8169.ko' \
    output/firefly-k3-spcda400/build/linux-custom/modules.builtin
```

正确结果：

```text
CONFIG_R8169=y
kernel/drivers/net/ethernet/realtek/r8169.ko
```

`modules.builtin` 中记录 `.ko` 是内建模块的正常 Kbuild 记录，不表示它实际以可加载模块存在。

## 6. 编译和刷写

```bash
bash kernel-fast-build.sh firefly-k3-spcda400 k3-firefly-spcda400.dtb
fastboot flash bootfs output/firefly-k3-spcda400/images/bootfs.img
fastboot reboot
```

生成文件：

```text
output/firefly-k3-spcda400/images/k3-firefly-spcda400.dtb
output/firefly-k3-spcda400/images/bootfs.img
```

最终 DTB 状态：

```text
pcie2_rc: okay       # 原有网卡，未修改
pcie3_rc: okay       # 新增网卡
pcie4_rc: disabled   # 错误映射关闭
```

## 7. 启动后验收

```bash
lspci -nn
lspci -k
ip link
ifconfig -a
dmesg | grep -Ei 'pcie|rtl8125|r8169|link'
```

预期看到两个 RTL8125 控制器。原有接口继续工作，新接口名称可能是 `eth1`，也可能由 systemd/udev 按 MAC 地址命名。

## 8. 仍异常时的排查顺序

```bash
dmesg | grep -Ei 'pcie|phy|link is|reset|regulator'
lspci -vv -s 0003:01:00.0
```

依次确认：

1. `pcie3_rc` 是否报告 `link is up`；
2. GPIO21 电源是否已使能；
3. GPIO101 是否在延时后释放；
4. 当前启动的 DTB 是否为最新版本；
5. 当前 `Image` 是否包含内建的 `r8169`。
