# 设备树到驱动

　　不讲抽象流程, 讲七个真实案例。每个案例都从**本 SDK 里真实存在的设备树
节点原文**开始, 到**驱动源码逐行消费这些属性**结束, 四段走读: ①节点在哪
②设备谁造的 ③驱动怎么认出它 ④probe 里属性变成了什么。所有文件行号均可直
接翻源码对照 (6.12.69)。

## 1. 先记住一条主链

　　七个案例共享同一条主干, 只在"设备谁造"和"驱动怎么匹配"两处分岔:

```
.dts/.dtsi 源码 ──dtc──▶ dtb ──U-Boot fixup──▶ 内核 unflatten
                                              (blob → device_node 树)
                                                    │
              ┌─────────────────────────────────────┤
              │ 设备创建 (两条路, §3~§8 分述)        │
              ▼                                     ▼
   populate: 有 compatible 的节点             总线驱动扫描子节点
   → platform_device                          (i2c/spi/serdev/mdio)
              │                                     │
              └──────────── 驱动注册到总线 ─────────┘
                              │ 撮合: compatible 字符串逐个比对
                              ▼
                         probe(dev)  ← 按"属性名"取资源
                              ▼
                     子系统注册 → 用户态可见
```

　　三句认知, 全文反复出现:

- **设备创建分两派**: 有 compatible 的节点由内核统一 populate 建成
  platform_device; 挂在总线控制器下的子设备 (I2C/SPI 等) 由**总线驱动
  probe 成功后**扫描子节点再建——总线驱动没起, 子设备根本不存在。
- **匹配就是字符串比对**: compatible 的值列表**逐个**与驱动
  of_match_table 比对, 哪个值先命中算哪个 (§8 有活例: 板子写 es8388,
  驱动表只有 es8323, 靠第二个值命中)。
- **probe 按名字取资源**: 驱动不读 dts 文本, 而是调内核 API 按属性名
  取——`devm_clk_get(dev, "xvclk")` 找的是 `clock-names = "xvclk"`,
  名字对不上就 -ENOENT 或挂起等 -EPROBE_DEFER。

## 2. 案例一: gpio-leds —— 最短的 platform 链路 (SG 板三颗 LED)

### 2.1 节点在哪

　　AIO-3588SG 板级 dtsi (:11~27, firefly_leds 父节点 + 子节点代表):

```
firefly_leds: leds {
    compatible = "gpio-leds";
    status = "okay";

    power_led: power {
        label = ":power";
        linux,default-trigger = "ir-power-click";
        default-state = "on";
        gpios = <&pca9555 PCA_IO1_7 GPIO_ACTIVE_HIGH>;
    };
    user_led: user {
        label = ":user";
        linux,default-trigger = "ir-user-click";
        default-state = "off";
        gpios = <&pca9555 PCA_IO1_6 GPIO_ACTIVE_HIGH>;
    };
    ...
};
```

　　注意 LED 的 GPIO 挂在 **I2C 扩展芯片 pca9555** 上而非 SoC 引脚
(节点在 :435~441: `compatible = "nxp,pca9555"; reg = <0x21>;
gpio-controller; #gpio-cells = <2>;`)。leds 驱动完全不需要知道这件事——
gpiod 框架把 SoC GPIO 和扩展器 GPIO 统一成一个"控制器+编号"抽象, 这是
设备树分层的第一课。

### 2.2 设备谁造的 / 驱动怎么认出它

　　`gpio-leds` 是有 compatible 的节点, 由内核 populate 统一建成
platform_device (无总线, SoC 内部/纯软件节点都走这条)。驱动在
`drivers/leds/leds-gpio.c`: of_match 表 :209 匹配 `"gpio-leds"`,
probe 函数 gpio_led_probe :262。

### 2.3 probe 里属性变成了什么

　　probe 调 gpio_leds_create (:165 起) 遍历父节点每个子节点——**每个
子节点就是一颗 LED**:

```
device_for_each_child_node(dev, child)              /* :165 遍历 power/user/... */
    led.gpiod = devm_fwnode_gpiod_get(dev, child, NULL,
                    GPIOD_ASIS, ...)                /* :174 吃掉 gpios 属性 */
    ret = create_gpio_led(&led, led_dat, dev, child, ...)  /* :194 */
```

　　create_gpio_led (:80) 内部把 `default-state` 拉成初始电平、把
`linux,default-trigger` 挂到 led_classdev、以子节点的 fwnode 注册
(:123 init_data.fwnode)——于是用户态出现 `/sys/class/leds/:power`,
echo 到 brightness 就翻转 pca9555 的 IO1_7。

　　失败形态: 子节点少写 `gpios` → 该 LED 静默消失 (probe 成功, 只是
少注册一颗); label 漏写 → sysfs 名字变成节点名。**这种失败不报错**,
是"配置对了才有"而非"配错就报"的典型。

## 3. 案例二: cw2017 电量计 —— I2C 子设备与 /bits/ 8 私有属性

### 3.1 节点在哪

　　AIO-3588SG (:446~462, 节选):

```
cw2017: cw2017@63 {
    status = "okay";
    compatible = "cellwise,cw2017";
    reg = <0x63>;
    cellwise,battery-profile = /bits/ 8
        <
        0x3C 0x00 0x00 0x00 0x00 0x00 0x00 0x00
        ... (共 80 字节, Cellwise 厂商提供的电池曲线)
        0x00 0x00 0x00 0x00 0x00 0x00 0x00 0xA2
        >;
};
```

　　`/bits/ 8` 是 dtc 语法: 把尖括号里的数按 8 位打包 (不加的话每个
0x3C 会被当 32 位整数, 驱动读出来的字节流全错)。

### 3.2 设备谁造的 —— 关键差异: 不是 populate

　　cw2017 挂在 i2c 控制器下面。设备树里它**永远不会被 populate 建成
platform_device**——它是等 i2c 适配器驱动 (rk3x-i2c) probe 成功后,
由 i2c core 扫描适配器节点子节点建的 (`drivers/i2c/i2c-core-of.c`:
of_i2c_register_devices :85 → of_i2c_register_device :66 →
of_i2c_get_board_info 把 `reg` 读进 info->addr、节点挂上 info->of_node
:50~51)。所以: 适配器驱动没起来/适配器 status=disabled, cw2017 这个
i2c_client 就根本不存在, 任何报错都不会有。

### 3.3 驱动怎么认出它

　　驱动是 `drivers/power/supply/cw2017_battery.c`: of_match 表 :695
`{ .compatible = "cellwise,cw2017" }`。

　　**同目录还有个 cw2015_battery.c (:767 只认 "cellwise,cw2015")——
那是另一颗芯片另一个驱动**。板级 compatible 写 cw2017 就绑 cw2017
驱动, 写 cw2015 就绑 cw2015 驱动, 差一个字符绑的对象完全不同 (绑错
的一方 probe 时寄存器读回全是错值, 报 -ETIMEDOUT/-ENODEV 之类)。找
驱动时先确认芯片确切型号再搜 compatible, 别两颗混着抄。

### 3.4 probe 里属性变成了什么

```
cw2017_parse_properties(cw_bat);                        /* :602 probe 内调用 */
    length = device_property_count_u8(dev,
                    "cellwise,battery-profile");        /* :499 数出 80 */
    if (length < 0)
        "No battery-profile found, using current flash contents"
    else if (length != CW2017_SIZE_BATINFO)
        dev_err(..., "battery-profile must be %d bytes\n");  /* :504 → -EINVAL */
    device_property_read_u8_array(dev,
                    "cellwise,battery-profile", ...);   /* :514 字节流进驱动 */
    cw_bat->regmap = devm_regmap_init_i2c(client, ...); /* :608 reg=<0x63> 就是 client->addr */
```

　　一条厂商私有属性的完整旅程到此走完: dts 80 字节 → dtb → fdt →
device_node → device_property API → 驱动写进芯片 flash。之后
`/sys/class/power_supply/cw2017-battery/` 出现 (power_supply_desc
.name = "cw2017-battery", :486)。

## 4. 案例三: RK806 —— SPI 设备 + MFD 一拆三

### 4.1 节点在哪

　　`rk3588-rk806-single.dtsi` (:11~48, 节选; 完整 21 轨见 power.md):

```
&spi2 {
    status = "okay";
    assigned-clocks = <&cru CLK_SPI2>;
    assigned-clock-rates = <200000000>;
    pinctrl-0 = <&spi2m2_cs0 &spi2m2_pins>;
    num-cs = <1>;

    rk806single: rk806single@0 {
        compatible = "rockchip,rk806";
        spi-max-frequency = <1000000>;      /* RK806 只能 1MHz, 写高直接通信异常 */
        reg = <0x0>;                        /* SPI 片选 0 */
        interrupt-parent = <&gpio0>;
        interrupts = <7 IRQ_TYPE_LEVEL_LOW>;  /* GPIO0_A7, 低电平中断 */
        low_voltage_threshold = <3000>;     /* 私有阈值属性, 驱动消费 */
        shutdown_temperture_threshold = <160>;
        pmic-reset-func = <1>;
        vcc1-supply = <&vcc5v0_sys>;        /* 每路 DCDC 的输入轨声明 */
        ...
        regulators { vcc1... };             /* 21 路输出全在这一个子树里 */
    };
};
```

### 4.2 驱动怎么认出它

　　匹配入口是 `drivers/mfd/rk8xx-spi.c` (:101 of_match
`"rockchip,rk806"`)——RK806 有 SPI 版和 I2C 版 (rk8xx-i2c.c :228),
同一颗芯片按挂在哪条总线上被不同入口接住, 公共实现在 rk806-core.c。
SPI 子设备的创建与 I2C 同构: spi2 控制器 probe 成功后, spi core 扫
子节点, `reg` 解释为片选号。

### 4.3 MFD: 一个节点拆出三个设备

　　rk806-core.c probe 成功后按 cells 表 (:340~349) 拆子设备:

```
static const struct mfd_cell rk806_cells[] = {
    { .name = "rk806-pinctrl", },
    { .name = "rk805-pwrkey", .num_resources = ..., .resources = ... },
    { .name = "rk806-regulator", },
};
...
devm_mfd_add_devices(rk806->dev, ..., rk806_cells,    /* :943 */
                     ARRAY_SIZE(rk806_cells), ...);
```

　　这一步**凭空造出三个 platform_device** (名字来自 .name, 不走
compatible), 各自被对应驱动接住: pinctrl 驱动、按键驱动、regulator
驱动。regulator 驱动再把 `regulators {}` 子树的 21 路逐个注册成
regulator——这就是"regulator 子节点为什么没有 compatible 也能工作"的
答案: 它们的设备不是 populate 建的, 是 MFD 父驱动造的。父节点上的
私有阈值属性 (low_voltage_threshold 等) 由 rk806-core probe 读走
(:670~749), 属于父驱动自己消费。

　　失败形态: 父 probe 失败 (SPI 不通/中断引脚不对) → 三个子设备全部
不出现, 21 路电源全消失, 系统直接跑不到 rootfs——所以排 PMIC 问题
永远先看父设备。

## 5. 案例四: bluetooth-platdata —— 自定义属性平台驱动

### 5.1 节点在哪

　　AIO-3588SG (:94~105, 节选):

```
wireless_bluetooth: wireless-bluetooth {
    compatible = "bluetooth-platdata";
    clocks = <&hym8563>;
    clock-names = "ext_clock";
    uart_rts-gpios = <&gpio3 RK_PD2 GPIO_ACTIVE_LOW>;
    pinctrl-names = "default", "rts_gpio";
    pinctrl-0 = <&uart9m2_rtsn>, <&bt_reset_gpio>, <&bt_wake_gpio>, <&bt_irq_gpio>;
    pinctrl-1 = <&uart9_gpio>;
    BT,reset-gpios      = <&gpio0 RK_PD0 GPIO_ACTIVE_HIGH>;  /* BT_REG_ON */
    BT,wake-gpios       = <&gpio0 RK_PC6 GPIO_ACTIVE_HIGH>;
    BT,wake_host-gpios  = <&gpio0 RK_PC5 GPIO_ACTIVE_HIGH>;
    status = "okay";
};
```

### 5.2 驱动在哪 —— 一个找驱动的坑

　　这个驱动的位置违反直觉: 在 `net/rfkill/rfkill-bt.c` (of_match
:863 匹配 "bluetooth-platdata", probe rfkill_rk_probe :708)——**在
net/ 下, 不在 drivers/ 下**。全局搜驱动时别只 grep drivers/, 按模块
归属猜目录会漏 (wifi/bt 厂商驱动经常散落在 net/rfkill、
net/wireless、drivers/net/wireless 三处, rkwifibt 方案还在
external/rkwifibt)。

### 5.3 probe 里属性变成了什么

　　这是"厂商自定义属性怎么进驱动"的完整样本: probe 里逐个
`of_get_named_gpio_flags(node, "BT,reset-gpios", ...)` 取 GPIO——
**逗号前缀是属性名的一部分**, 查代码时照抄整串。pinctrl-names 定义
了 default / rts_gpio 两个状态: BT 正常收发时 RTS 脚复用给 uart9
(default), 需要把 RTS 强拉当普通 GPIO 用时驱动切到 rts_gpio 态
(pinctrl_select_state)——一个脚在两个状态间切换, 这正是 ITX-3588J
BT 修复案例里 RTS 卡死导致扫描不到设备的根因背景 (见 board 笔记)。

## 6. 案例五: EC25 4G 模组 —— 设备根本不在设备树里

### 6.1 反转: DT 里找不到这个设备

　　4G 模组插上 USB 后才存在, 设备树不可能预先描述它。DT 只负责三
件事: USB 控制器 (usbhost3_0)、PHY (combphy2_psu)、VBUS 供电门控
(见 phy-controller.md §8 实例 2 与 power.md 门控轨)。

### 6.2 驱动怎么认出它 —— VID/PID 硬表

　　`drivers/usb/serial/option.c`: 厂商 ID 宏 :252
(`QUECTEL_VENDOR_ID 0x2c7c`), 产品 ID :254~257 (RG650V=0x0122,
EC25=0x0125), ID 表 :1187 `USB_DEVICE_AND_INTERFACE_INFO(0x2c7c,
0x0125, ...)`。USB core 枚举时读设备描述符拿到 VID/PID, 逐表比对
命中后调 option 的 probe——全程与设备树无关。

　　匹配成功的设备 modalias 形如 `usb:v2C7Cd0125d...`, udev 据此自动
modprobe。换模组型号后"插上没反应"先 `lsusb` 看 VID/PID 在不在
option.c 表里; 而"枚举列表里根本没设备"则是 DT 侧问题 (vbus 没供/
u2phy 没开/dr_mode 错)——两种症状排查方向完全相反, 第一步先分清。

## 7. 案例六: imx415 摄像头 —— of_graph 端点图

### 7.1 节点在哪

　　AIO-3588SG (:1350~1393, 两端互指是关键):

```
imx415: imx415@37 {
    compatible = "sony,imx415";
    reg = <0x37>;
    clocks = <&cru CLK_MIPI_CAMARAOUT_M1>;
    clock-names = "xvclk";
    power-domains = <&power RK3588_PD_VI>;
    reset-gpios = <&gpio1 RK_PD5 GPIO_ACTIVE_LOW>;
    rockchip,camera-module-index = <0>;          /* rockmodule 私有属性族 */
    rockchip,camera-module-name = "CMK-OT2022-PX1";
    rockchip,camera-module-lens-name = "IR0147-50IRC-8M-F20";
    port {
        imx415_out: endpoint {
            remote-endpoint = <&mipidphy0_in_ucam1>;   /* 出边: 指向接收端 */
            data-lanes = <1 2 3 4>;
        };
    };
};

&csi2_dphy0 {
    status = "okay";
    ports {
        port@0 {
            mipidphy0_in_ucam1: endpoint@1 {
                reg = <1>;
                remote-endpoint = <&imx415_out>;     /* 回边: 互指成对 */
                data-lanes = <1 2 3 4>;
            };
        };
        port@1 { ... };   /* 下一跳: csi2_dphy0 → mipi_csi2 → rkisp 一路指下去 */
    };
};
```

### 7.2 驱动怎么认出它 / probe 取什么

　　驱动 `drivers/media/i2c/imx415.c`: of_match :3367
`"sony,imx415"`; 设备由 i2c core 扫子节点创建 (同案例二); probe
(:3164) 里 `devm_clk_get(dev, "xvclk")` (:3238) 按 **clock-names 的
名字**取时钟, rockchip,camera-module-* 私有属性用 of_property_read
(:3184 起) 读出塞进 submodule 信息。链路对接发生在 probe 尾部
v4l2_async_register_subdev_sensor (:3319)——它以 fwnode 图为媒, 把
自己注册成异步 subdev, 等下游 (rkisp) 的 async notifier 沿
remote-endpoint 找上来完成配对。

### 7.3 为什么"probe 全绿还是没图像"

　　of_graph 表达的是**设备与设备之间的数据流**, 与驱动匹配是两回事。
匹配只看 compatible 字符串; 数据流走不走, 取决于这条边链每一跳的
remote-endpoint 是否成对互指。链上任何一跳的边缺失/单向指, pipeline
就静默断流——所有节点 probe 正常, dmesg 干净, 就是没有帧。真实案例:
AIO-3588L DP 无画面 (typec.md 实录), connector 图缺 dp0 一条边,
dw-dp 的 mux 永远不被回调。**显示/摄像头问题第一动作: 打印两端
endpoint, 核对 phandle 互指, 再谈驱动** (`cat /proc/device-tree/...
/endpoint/remote-endpoint` 比对)。

## 8. 案例七: es8388 声卡 —— 纯属性消费者 + phandle 串卡

### 8.1 节点在哪

　　声卡是"设备树配置密度最高、驱动代码最薄"的类型。SG 板两个节点:

```
es8388: es8388@11 {                          /* :526 编解码器 (I2C 设备) */
    compatible = "everest,es8388", "everest,es8323";
    reg = <0x11>;
    clocks = <&mclkout_i2s0>;
    clock-names = "mclk";
    assigned-clock-rates = <12288000>;       /* MCLK 12.288MHz */
    pinctrl-0 = <&i2s0_mclk>;                /* MCLK 从 I2S0_MCLK 脚输出 */
};

es8388_sound: es8388-sound {                 /* :141 声卡 (纯属性消费者) */
    compatible = "rockchip,multicodecs-card";
    rockchip,card-name = "rockchip-es8388";
    spk-con-gpio = <&gpio1 RK_PC0 GPIO_ACTIVE_HIGH>;
    rockchip,format = "i2s";
    rockchip,mclk-fs = <256>;
    rockchip,cpu = <&i2s0_8ch>;              /* DAI 的 CPU 侧: phandle */
    rockchip,codec = <&es8388>;              /* DAI 的 codec 侧: phandle */
    rockchip,audio-routing = "Speaker", "LOUT2", ...;  /* 路由表字符串对 */
    ...
};
```

　　先看 codec 节点的 compatible: `everest,es8388", "everest,es8323"`
——**compatible 是列表, 内核逐个比对**。es8323.c 的 of_match 表里只
有 `"everest,es8323"` (:939), 第一个值匹配不上, 第二个值命中——板子
和芯片手册都叫 ES8388, 驱动按 ES8323 兼容, 两个值都写才两边都满足。
这就是"匹配是字符串比对"最直观的活例。

### 8.2 声卡节点 probe 里属性变成了什么

　　驱动 `sound/soc/rockchip/rockchip_multicodecs.c`, probe
rk_multicodecs_probe :872:

| dts 属性 | 驱动消费点 |
|---|---|
| rockchip,card-name | snd_soc_of_parse_card_name (:902) → /proc/asound 卡名 |
| rockchip,cpu | of_parse_phandle (:968) → dai_link 的 CPU of_node |
| rockchip,codec | of_count_phandle_with_args + of_parse_phandle (:922/928) |
| rockchip,codec-hp-det | of_property_read_bool (:1015) |
| rockchip,audio-routing | snd_soc_of_parse_audio_routing (:1080) |
| spk-con-gpio | probe 里 of_get_named_gpio_flags 取出, 运行时拉高/拉低开关功放 |

　　注意这个节点**没有 reg、没有中断、没有自己的时钟**——它是一份
"配置声明", probe 的工作就是把属性翻译成 ALSA 的 card/dai_link/
routing 结构体。phandle 消费 (`rockchip,cpu = <&i2s0_8ch>`) 拿到的
是**另一个节点的引用**: 声卡驱动由此把 i2s0 控制器驱动和 es8323 编
解码器驱动"焊接"成一条 I2S 链路, 三方 (cpu/codec/card) probe 全部
就位后才注册出声卡。

### 8.3 probe 全绿 ≠ 有声音

　　真实案例 (sound-card.md 实录): 声卡注册成功、aplay 不报错, 但喇
叭无声——根因有两层: ①板级 spk-con-gpio 抄错引脚 (GPIO3_B7 抄自旧
板, 实际接 GPIO1_C0), 功放使能脚永远没拉高; ②wireplumber (用户态
音频服务) 冷启动把 Speaker Switch 置 0。第一层是"probe 时取了属性但
值错", 第二层是"内核一切正常, 运行态被用户态改"——排查声音问题要
按 内核 probe → ALSA 路由 → 用户态 mixer 三层各查一次。

## 9. 失败排查

### 9.1 三种失败, 对号入座

| 症状 | 判别 | 对应案例 |
|---|---|---|
| 设备目录不存在 (`/sys/bus/*/devices/` 找不到) | 设备没创建 | populate 漏了 (没 compatible/status 没翻) 或**总线驱动没起** (I2C/SPI 子设备, §3/§4) |
| 设备在, 但目录里没有 driver 符号链接 | 匹配失败 (静默!) | compatible 逐字符比对 of_match_table; §3 的 cw2015/cw2017 与 §8 的 es8388/es8323 都是活例 |
| 有 driver, probe 失败或反复 defer | probe 出错 | dmesg 错误码 (9.3) + devices_deferred |

### 9.2 排查决策树

```
第一步: 板端 dtb 是不是这份? (烧错/忘重编是第一大坑)
  strings /sys/firmware/fdt | grep <节点关键字>
  dtc -I dtb -O dts /sys/firmware/fdt > /tmp/board-fdt.dts   # 与源码 diff

第二步: 设备存在吗? (platform 按地址 ls /sys/bus/platform/devices;
  i2c 用 i2cdetect; usb 用 lsusb)
  ├── 不存在 → 节点有 compatible 吗? status okay 吗?
  │           父总线控制器 (i2c/spi/uart) probe 成功了吗?
  └── 存在 → ls 设备目录, 有 driver 链接吗?
        ├── 无 → compatible 与 of_match_table 逐字符比对
        │       驱动编进内核了吗? (modules.builtin / lsmod)
        └── 有 → probe 失败: dmesg 错误码 + devices_deferred
```

### 9.3 probe 错误码速查

| dmesg 返回 | 含义 | 高发原因 |
|---|---|---|
| -517 | -EPROBE_DEFER | 等 supply/clk/pinctrl/iommu; 供应商永远不来就永远 defer |
| -2 | -ENOENT | clk/gpio 名字对不上 (clock-names/xxx-gpios 拼错, §7 的 xvclk 例) |
| -6 | -ENXIO | reg/irq 不存在 (地址错, interrupts-parent 没接对) |
| -22 | -EINVAL | 必填属性缺失/值域错 (§3 的 profile 长度 != 80) |
| -19 | -ENODEV | 驱动内部检查不过 (硬件 ID 不符/feature 不支持) |
| -16 | -EBUSY | 地址/中断被占 (两个节点同 reg) |
| -110 | -ETIMEDOUT | 芯片没应答 (没上电/没 clock/地址错/I2C 没接上拉) |

```
cat /sys/kernel/debug/devices_deferred     # 全部挂起设备与等谁
```

### 9.4 工具箱

```
# 资源三表 (probe 失败三查)
cat /sys/kernel/debug/pinctrl/pinctrl-rockchip-pinctrl/pinmux-pins  # 引脚实际复用
cat /sys/kernel/debug/clk/clk_summary             # clock 树与使能计数
cat /sys/kernel/debug/regulator/regulator_summary # 电源树与消费者

# 设备↔驱动撮合状态
ls -l /sys/bus/platform/devices/fe2c0000.*        # driver 符号链接在不在
cat /sys/bus/platform/devices/*/uevent | grep -E "OF_FULLNAME|MODALIAS"

# 手动撮合实验 (隔离时序问题: unbind 再 bind, 成功则是时序不是配置)
echo <driver> > /sys/bus/platform/devices/xxx/driver_override
echo xxx > /sys/bus/platform/drivers/<driver>/bind
```

### 9.5 实战案例索引 (各文档已修过的真坑)

| 案例 | 失败类型 | 出处 |
|---|---|---|
| AIO-3588L DP 无画面 | of_graph 边缺失, probe 全绿 | typec.md (§7.3 机制) |
| ES8388 喇叭无声 | 板级属性值错 + 用户态 mixer | sound-card.md (§8.3 机制) |
| ITX-3588J BT 不起 | RTS/pinctrl 状态 + 用户态 rfkill 链 | board 笔记 (§5.3 机制) |
| cw2017 绑错 cw2015 驱动风险 | compatible 一字之差 | §3.3 机制 |
| RK806 上电 21 轨全失 | 父 MFD probe 失败连坐子设备 | power.md (§4.3 机制) |
