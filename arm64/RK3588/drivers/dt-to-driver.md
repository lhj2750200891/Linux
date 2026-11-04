# 设备树到驱动

　　一份 dts 属性从文本到被驱动消费的完整旅程: 七个阶段的全链路, 按接口
(platform / I2C / SPI / MDIO / USB / serdev / MFD / of_graph) 分类的机制差异,
匹配失败与 probe 失败的系统化排查。所有例证均取自本 SDK 6.12.69 真实源码
(标了文件与行号), 可直接对照翻源码。

## 1. 全程七个阶段

### 1.1 阶段总览

```
阶段0  .dts/.dtsi 源码   include 展开, label 引用, status 翻译
   │ dtc 编译 (label → phandle 数字展开, 语法/引用错误在这里报)
   ▼
阶段1  dtb               本 SDK: dtb 随 boot 交付, U-Boot 负责读出
   │ U-Boot: /chosen 注入 bootargs/cmdline, 可能做 mac 等运行时 fixup
   ▼
阶段2  内核早期          unflatten_device_tree: blob → device_node 树
   │                       产物: /proc/device-tree + /sys/firmware/fdt (原始 blob)
   ▼
阶段3  设备创建          of_platform_default_populate_init (arch_initcall_sync)
   │                       有 compatible 的节点 → platform_device; simple-bus 递归
   ▼
阶段4  驱动注册          各驱动 module_init/subsys_initcall → bus 上挂 driver
   │ bus core 撮合: driver.of_match_table ↔ device.of_node.compatible
   ▼
阶段5  probe()           devm_* 取资源 (reg/irq/clk/regulator/gpio/pinctrl/属性)
   │ 供应商没就绪 → -EPROBE_DEFER 挂起, 供应商 probe 完成后自动重试
   ▼
阶段6  子系统注册        netdev/drm/mmc/input/... → 用户态节点出现
   ▼
阶段7  uevent/modalias   of:NxxxTxxxCxxx / usb:vXXXXdXXXX → udev 自动 modprobe
```

　　两个时间线的关系是理解钥匙: 阶段 3 建设备 (arch_initcall_sync), 阶段 4 注册
驱动 (各级 initcall), 谁后到谁触发撮合 —— 所以"设备先建、驱动后来"和"驱动先在、
设备后建"都能自动配对, **唯一不能自动恢复的是资源依赖未就绪**, 那会走
-EPROBE_DEFER (见 1.2 阶段 5)。

### 1.2 逐段要点

| 阶段 | 发生了什么 | 你能验证什么 |
|---|---|---|
| 0 源码 | bindings 是合同: 驱动要什么属性写在 Documentation/devicetree/bindings 对应 yaml/txt | 写 dts 前先读 binding, 不靠猜 |
| 1 dtb | label 展开成 phandle 数字; 引用不存在 label 编译即报 | 反编译: `dtc -I dtb -O dts xxx.dtb > x.dts` |
| 2 U-Boot | fixup 后传 fdt 给内核 | 板端看 /sys/firmware/fdt 是否与你的源码一致 (阶段 3 验证) |
| 3 内核早期 | blob → device_node; /proc/device-tree 可 cat | `ls /proc/device-tree/xxx`, `strings /sys/firmware/fdt \| grep compatible` |
| 4 设备创建 | 只给**有 compatible** 的节点建 platform_device; 带 `simple-bus` 的总线节点向下递归; chosen/aliases/memory 这类无 compatible 节点跳过 | `ls /sys/bus/platform/devices/ \| grep fe2c` (按地址) |
| 5 注册撮合 | compatible 逐个比对 of_match_table; 首个匹配生效 | `cat /sys/bus/platform/devices/*/uevent` 看 `OF_FULLNAME`/`MODALIAS` |
| 6 probe | 见 1.3 属性消费表 | `dmesg` 错误码; debugfs devices_deferred |
| 7 子系统/uevent | 注册进子系统后用户态可见; 模块按 modalias 自动加载 | `udevadm info /sys/...` 看 MODALIAS |

### 1.3 probe 期: 属性名 ↔ 驱动 API 对照表

　　驱动不是"读 dts 文本", 而是经内核 API 按**名字**取已解析好的资源。
dts 属性名写错, 对应 API 取不到, 这张表是排查对照的锚:

| dts 属性 | 驱动侧 API | 取不到时 |
|---|---|---|
| `reg` (地址/CS) | platform_get_resource / i2c 地址在 client->addr | -ENXIO |
| `interrupts` | platform_get_irq / i2c client->irq | -ENXIO 或轮询退化 |
| `clocks` + `clock-names` | devm_clk_get(dev, "name") | -ENOENT→常转 EPROBE_DEFER |
| `xxx-supply` | devm_regulator_get(dev, "xxx") | -EPROBE_DEFER (等 PMIC) |
| `pinctrl-0` + `pinctrl-names` | pinctrl 框架 default state 自动应用 | 引脚保持复用错误状态 |
| `xxx-gpios` | devm_gpiod_get(dev, "xxx", flags) | -ENOENT/-EINVAL |
| 自定义属性 (`rockchip,xxx` 等) | of_property_read_u32/string/... device_property_read_* | 驱动用默认值或 -EINVAL |
| `compatible` 本身 | of_match_device / i2c_client->of_node | 已在匹配期用掉 |

　　CW2017 例子 (真实源码 drivers/power/supply/cw2015_battery.c:591):
`device_property_count_u8(dev, "cellwise,battery-profile")` —— 板级 dts 里的
厂商前缀属性就这样进驱动。

## 2. 按接口分类 (每类五要素: DT 写法/谁建设备/驱动匹配/probe 取资源/典型失败)

### 2.1 platform: SoC 内部控制器与纯 DT 驱动

　　绝大多数控制器 (uart/i2c/spi/gmac/pcie/dsi/vop/mmc...) 都是这一类。
设备树里写在 SoC dtsi (rk3588s.dtsi) 的节点, 板级只做三件事: 翻 status、
补 pinctrl、接 supply。

- **DT 写法**: 控制器节点在 rk3588s.dtsi 已有 (地址/中断/compatible 全带),
  板级覆盖 `&sdmmc { status = "okay"; vmmc-supply = <&vcc3v3_sd_s0>; ... }`;
- **谁建设备**: 阶段 4 populate 统一建;
- **驱动匹配**: `drivers/mmc/host/dw_mmc-rockchip.c` of_match 表含
  `"rockchip,rk3588-dw-mshc"` (与 README 方法论第 3 条同款查法);
- **probe 取资源**: reg/irq 来自 SoC dtsi 的 reg/interrupts, clk 按 clock-names,
  vmmc/vqmmc 按 supply 名;
- **典型失败**: 只翻了子节点 status 没翻**父控制器** status (最常见);
  pinctrl 组名写错 → 引脚复用不对但 probe 照样成功 (2.1 特性: 失败是静默的)。

　　gpio-keys / gpio-leds / pwm-backlight / regulator-fixed 也归此类:
驱动不挂总线, probe 里直接 of_property 读属性。

### 2.2 I2C 外设

- **DT 写法**: 作为 i2c 控制器的子节点, `compatible` + `reg` (7bit 地址) +
  私有属性; 例 (sound-card.md 的 ES8388): compatible = "everest,es8323";
  充放电 (charging.md): compatible = "cellwise,cw2015", reg = <0x63>;
- **谁建设备**: **不是 populate** —— i2c 控制器驱动 probe 成功后, i2c core
  扫描其 of_node 子节点, 逐个造 i2c_client (so: 适配器驱动没跑起来, 子设备
  全都不存在);
- **驱动匹配**: 内核 i2c 驱动 of_match 表对 compatible, 例
  `sound/soc/codecs/es8323.c:939` → `"everest,es8323"`,
  `drivers/power/supply/cw2015_battery.c:767` → `"cellwise,cw2015"`;
- **probe 取资源**: client->addr 即 reg; 属性走 device_property_*;
- **典型失败**: compatible 与驱动表一字之差 (es8323 vs es8388: 驱动只用 es8323
  兼容, compatible 必须写 es8323); i2c 地址错 → i2c core 在 client 创建时就
  -ENXIO (设备探测不到 ACK); 适配器本身没起来 (查 dmesg 适配器 probe)。

### 2.3 SPI 外设

- **DT 写法**: spi 控制器子节点, `reg` = 片选号, `spi-max-frequency`;
  例: CAN 外挂 MCP2518FD (can.md), PMIC RK806 (power.md, spi2 cs0, 1MHz);
- **谁建设备**: spi 控制器 probe 后由 spi core 造 spi_device, 机制与 I2C 同构;
- **驱动匹配**: `drivers/net/can/spi/mcp251xfd/` 对 `"microchip,mcp2518fd"`;
  `drivers/mfd/rk806-core.c` 对 `"rockchip,rk806"` (SPI+MFD 组合, 见 2.7);
- **probe 取资源**: reg=片选, 双向走 spi_transfer, DT 属性照旧;
- **典型失败**: 片选引脚被别的模块占 (引脚冲突表思路); max frequency 超芯片
  上限 (rk806 只能 1MHz, 写高直接通信异常); CS 极性/spi-cpha 等时序位错。

### 2.4 MDIO/PHY (以太网 PHY)

- **DT 写法**: gmac 节点内的 `mdio { ethernet-phy@N { reg = <N>; } }`,
  外加 gmac 上的 `phy-mode` / delay 属性 (gmac.md 的 tx_delay);
- **谁建设备**: gmac 驱动 probe 时 of_mdiobus_register 扫子节点造 phy_device;
- **驱动匹配**: **不靠 compatible** —— PHY 驱动按硬件 ID 表硬匹配
  (`drivers/net/phy/realtek.c` 用 PHY_ID_MATCH_EXACT 列 ID, 读寄存器 2/3 得到);
  compatible 可写可不写, 仅用于额外信息;
- **probe 取资源**: PHY 框架自管; dts 的 reg 决定 MDIO 地址;
- **典型失败**: MDIO 地址错 (千兆网口"链路起不来"); PHY 供电/reg_on 没给
  (mdio 扫描不到任何设备); delay 属性不对 (能 link 但丢包)。

### 2.5 USB 设备

　　认知反转: **USB 设备本身不在设备树里** —— 热插拔的设备 dts 管不着。
DT 只负责三件事: 控制器 (dwc3/ehci) + PHY (u2phy/combphy) + 供电 (vbus 门控轨,
见 power.md 2.5)。

- **驱动匹配**: VID/PID 硬编码表, 例 4G 模组 `drivers/usb/serial/option.c`:
  `USB_DEVICE_AND_INTERFACE_INFO(0x2c7c, 0x0125, ...)` (Quectel EC25/EC20 族);
- **设备创建**: USB core 枚举时按描述符造 usb_device/interface;
- **modalias**: `usb:v2C7Cd0125d...`, udev 据此 modprobe;
- **probe 取资源**: 描述符 (interface class/endpoint), DT 无关;
- **典型失败**: 驱动表没有该 VID/PID (换模组型号后不开机不了网) → 用
  `lsusb` 拿 ID 对照; 但"枚举不到设备"则是 DT 侧问题 (vbus 没供上 / u2phy
  没配 / dr_mode 错) —— 先分清"设备没枚举"还是"枚举了没驱动", 排查方向
  完全不同。

### 2.6 serdev: UART 上的蓝牙

- **DT 写法**: uart 控制器子节点带 compatible + `current-speed`, 例
  Realtek BT: `"realtek,rtl8822cs-bt"` (真实源码 drivers/bluetooth/hci_h5.c:1104
  的 rtl_bluetooth_of_match);
- **谁建设备**: uart probe 后 serdev core 造 serdev_device;
- **驱动匹配**: hci_uart 各 serdev 驱动 of_match 表;
- **典型失败**: 与用户态方案混淆 —— 本 SDK 的 WiFi/BT 组合卡走
  external/rkwifibt 用户态 (hciattach/loader) 方案 (wifi-bt.md), DT 里**没有**
  BT serdev 节点属正常; 只有内核态 serdev 方案才需要这节。判断依据:
  `dmesg | grep hci` 看 BT 是谁拉起来的。

### 2.7 MFD + cells: 一颗芯片拆成多个设备

　　RK806 是标准教材: DT 里只有一个 PMIC 节点, 但内核里跑着五六个驱动。

- **DT 写法**: 只有父节点 (power.md 2.2 完整版); regulators/pwrkey 等功能
  **没有独立 DT 节点**, 作为父节点的子结构存在;
- **谁建设备**: 父驱动 (mfd) probe 成功后 `devm_mfd_add_devices` 按
  mfd_cell 表造子 platform_device (rk806-core.c:340 rk806_cells[], :943
  devm_mfd_add_devices, PLATFORM_DEVID_AUTO);
- **驱动匹配**: 两级 —— 父驱动匹配 `"rockchip,rk806"`; 子驱动按 cell 的
  `.name` (如 "rk806-pinctrl"/"rk805-pwrkey" 族) 平台匹配, **不走 compatible**;
- **probe 取资源**: 子驱动通过 parent->of_node 读属性 (父 DT 节点里的私有
  属性子驱动照样能取), regmap 由 MFD 框架共享;
- **典型失败**: 父 probe 失败则全军覆没 (先看父); 子设备缺一个先查 cells
  注册条件 (rk806_cells 里部分 cell 按硬件特性开关)。

### 2.8 of_graph: 端口图 (显示/摄像头的数据流)

　　与前面所有类别本质不同: 匹配的不是"驱动↔设备", 而是**设备↔设备**。
ports/endpoints/remote-endpoint 构成一张有向图, 表达像素/数据的流动路径:

- **DT 写法**: 每个参与节点带 ports 子树, endpoint 用 remote-endpoint phandle
  互指成边。例: VOP → HDMI 控制器 → PHY; 摄像头链 imx415 → csi2_dphy →
  mipi_csi2 (mipi-csi.md 的 CAM0/CAM1 切换就是改图的边);
- **谁消费**: 显示用 `drm_of_find_panel_or_bridge`/drm core 沿图找对端,
  v4l2 用 async subdev 注册器;
- **驱动匹配**: 照旧 compatible, 但 probe 成功 ≠ 能出画面 —— 图不完整时
  probe 正常、数据流断;
- **典型失败 (高发!)**: 边缺失或单向指 —— 整条 pipeline 因某一跳 remote
  为空而静默不工作。AIO-3588L DP 无画面实录 (typec.md) 就是这个: connector
  图缺 dp0 边 → dw-dp mux 永不回调, probe 一切正常。**显示/摄像头问题先
  打图, 再查驱动**;
- **验证**: `/proc/device-tree` 里 cat 各 endpoint 的 remote-endpoint phandle,
  两端 phandle 必须互指。

## 3. 失败排查

### 3.1 先分清两种失败

| 现象 | 判别 | 对应排查 |
|---|---|---|
| `/sys/bus/xxx/devices/` 里没这个设备 | 设备压根没创建 | DT 没进 dtb / status 没翻 / 父控制器没起 / (I2C·SPI·MDIO·serdev) 总线驱动没起 |
| 设备在, 但没有 driver 文件 | 匹配失败 | compatible 与 of_match_table 不一致 / 驱动没编入 / modalias 不在驱动表 (USB 常见) |
| 有 driver 文件但 probe 失败/反复 defer | probe 出错 | 错误码表 (3.3) + devices_deferred |

### 3.2 排查决策树 (从"它没工作"开始)

```
第一步: 板端跑的 dtb 是不是这份?
  strings /sys/firmware/fdt | grep -A1 <节点关键字>
  (编译产物没烧对是第一大坑, 尤其改了 dtsi 忘重编/忘烧)

第二步: 设备存在吗? (按接口找: platform 按地址, i2c 用 i2cdetect,
  usb 用 lsusb, mdio 看 eth0 的 phydev)
  ├── 不存在 → 查 populate 链: 节点有 compatible 吗? status okay 吗?
  │           父控制器 (i2c/spi/uart/gmac 本身) probe 成功了吗?
  │           (I2C/SPI/MDIO/serdev 的子设备寿命完全挂在总线驱动上)
  └── 存在 → ls 该设备目录, 有 driver 符号链接吗?
        ├── 无 → compatible 与驱动 of_match_table 逐字符比对
        │       驱动编进内核了吗? (modules.builtin / lsmod)
        │       USB: MODALIAS (udevadm info) 在驱动 ID 表里吗?
        └── 有 → probe 失败: dmesg 错误码 + devices_deferred (3.3)
```

### 3.3 probe 错误码速查

| dmesg 返回 | 含义 | 高发原因 |
|---|---|---|
| -517 | -EPROBE_DEFER | 等 supply/clk/pinctrl/iommu 供应商; 看下方 deferred 表, 供应商永远不来就永远 defer |
| -2 | -ENOENT | clk/gpio 名字对不上 (clock-names/xxx-gpios 拼错或缺) |
| -6 | -ENXIO | reg/irq 资源不存在 (地址错, interrupts-parent 没接对) |
| -22 | -EINVAL | 必填 DT 属性缺失或值域错 (binding 合同没满足) |
| -19 | -ENODEV | 驱动内部检查不过 (硬件 ID 不符/feature 判定不支持) |
| -16 | -EBUSY | 地址/中断被占 (两个节点写同一 reg) |
| -11 | -EAGAIN | 总线通信暂失败 (I2C NACK 抖动, 供电时序) |
| -110 | -ETIMEDOUT | 芯片没应答 (没上电/没 clock/地址错) |

```
cat /sys/kernel/debug/devices_deferred    # 全部挂起的设备及等谁
```

### 3.4 工具箱

```
# 反编译板端真实 dtb (与源码 diff, 烧错/没生效一翻两瞪眼)
dtc -I dtb -O dts /sys/firmware/fdt > /tmp/board-fdt.dts

# 设备↔驱动撮合状态 (platform 示例, 其他 bus 同构)
ls -l /sys/bus/platform/devices/fe2c0000.*        # driver 符号链接在不在
cat /sys/bus/platform/devices/*/uevent | grep -E "OF_FULLNAME|MODALIAS"

# 资源三表 (probe 失败三查)
cat /sys/kernel/debug/devices_deferred            # 等谁
cat /sys/kernel/debug/pinctrl/pinctrl-rockchip-pinctrl/pinmux-pins   # 引脚实际复用
cat /sys/kernel/debug/clk/clk_summary             # clock 树与使能计数
cat /sys/kernel/debug/regulator/regulator_summary # 电源树与消费者

# 手动撮合实验 (临时 override, 重启失效)
echo <driver> > /sys/bus/platform/devices/xxx/driver_override
echo xxx > /sys/bus/platform/drivers/<driver>/bind     # 反向 unbind 释放
```

　　driver_override/bind/unbind 是"隔离变量"神器: 怀疑顺序/依赖问题时,
unbind 后重新 bind 一次, 若这次成功 → 是时序问题不是配置问题。

### 3.5 实战案例索引 (本目录已修过的真坑)

| 案例 | 失败类型 | 教训 |
|---|---|---|
| AIO-3588L DP 无画面 (typec.md) | of_graph 边缺失, probe 全绿 | 显示问题先查端口图互指, 再查驱动 |
| ES8388 喇叭 (sound-card.md) | probe 正常, 运行态被用户态改 | 内核态正常 ≠ 功能正常, 分层排查 |
| ITX-3588J BT (board/ITX-3588J) | 用户态 rfkill/加载链 | 先确定 BT 走 serdev 还是 rkwifibt 用户态 (2.6) |
| RGA no-core-match (根目录) | 6.12 API 变化致驱动匹配失败 | SDK 升级时 compatible/驱动结构对不上的典型 |
