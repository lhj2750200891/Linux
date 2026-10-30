# AIO-3588SG PD 电源调试笔记(RK3588S / 6.12.69 SDK)

> 记录时间:2026-10-27
> 涉及 SDK:rk3588_6.12.69_sdk(内核 6.12.81,U-Boot 为 6.12 SDK 版)
> 对标杆:rk3588_5.10.198_sdk(5.10 一切正常,以它的行为为"正确答案")
> 编译环境:amd-epyc 服务器(本机只做代码分析,不本地编译)

---

## 1. 现象与目标

| 场景 | 5.10(正确) | 6.12(初始状态) |
|------|------|------|
| PD 供电、不插电池 | 正常启动 | **一直重启循环** |
| PD 供电 + 插电池 | 正常,可充电 | 正常,可充电 |
| 纯电池 | 正常开机 | 正常开机 |

**目标行为**(以 5.10 为准):
1. 插入 PD 电源能够单独使用(无电池)
2. 插入电池也能单独使用
3. 插入 PD 电源可以给电池充电

问题逐层修复后,死点不断后移:U-Boot 重启循环 → 内核启动 → 内核 userspace 塌电。
最终共发现 **4 个叠加缺口**:3 个在 U-Boot/设备树,1 个在内核 tcpm。

---

## 2. 整机电源架构(本板)

```
Type-C PD 口
   │
   ├── fusb302 @ i2c2 0x22   ── PD 协议芯片(tcpm 框架),协商电压/电流契约
   │
   ├── sc8886(兼容 ti,bq25703)@ i2c4 0x6b ── 充电管理芯片
   │       ├── IINDPM(输入限流)寄存器决定能从 PD 口抽多少功率 ← 全部问题的关键
   │       └── 给 Vsys/电池充电
   │
   └── cw2017 @ i2c4 0x63    ── 电量计(FG),TEMP_MIN 寄存器奇偶校验兼做电池在位检测

   RK806 @ spi2              ── 主 PMIC(经 rk3588-rk806-single.dtsi 引入)
```

关键认识:**bq25703 的 IINDPM(输入电流限制)是唯一的功率闸门**。
U-Boot 和内核都需要有人去写它;没人写 = 默认低限流 = 负载一上来欠压重启。

---

## 3. 缺口一:U-Boot fg_cw201x 丢失 cw2017 支持

**文件**:`u-boot/drivers/power/fuel_gauge/fg_cw201x.c`
(6.12 是 cw2015 精简版 415 行;5.10 是 749 行,含完整 cw2017)

**失败链**(全部静默,FG uclass 失败只打 debug 级):

```
cw2017 不匹配(无 "cellwise,cw2017" compatible)
  → fg_charger_get_device() 遍历 UCLASS_FG 找 FG_CAP_FUEL_GAUGE 设备 → -ENODEV
  → charge_animation_probe 提前 return
  → bq25700(UCLASS_FG 的 FG_CAP_CHARGER)不 probe
  → fusb302(UCLASS_PD)不 probe
  → PD 输入电流无人编程 → IINDPM 停留默认低值
```

**修复**(从 5.10 完整移植,保持 6.12 结构,运行时用 `is_cw2017` 区分):

- 新增 cw2017 寄存器宏(VERSION=0x00 / VCELL_H=0x02 / SOC_INT=0x04 /
  MODE_CONFIG=0x08 / BATINFO=0x10 / SOC_ALERT=0x0B / TEMP_MAX=0x0C / TEMP_MIN=0x0D 等)
- `struct cw201x_info` 增加 `alert_level / temp_max / temp_min / max_voltage /
  min_voltage / bool is_cw2017`
- `cw201x_of_to_plat`:`device_is_compatible(dev, "cellwise,cw2017")` 判型,
  解析 `cellwise,alert-level`、`firefly,battery-max-voltage`、
  `firefly,battery-min-voltage`、`firefly,max-temp`、`firefly,min-temp`
- 移植函数:`cw201x_get_version` / `cw2017_enable` /
  `cw2017_update_config_info`(80 字节电池 profile 烧写 + UPDATE_FLG + 等待 SOC)/
  `enum parity_check_type` + `parity_check` / `cw2017_set_battery_exist` /
  `cw2017_check_battery` / `cw2017_init`
- ops 表补 `.bat_is_exist = cw2017_check_battery`
- 匹配表补 `{ .compatible = "cellwise,cw2017" }`

**电池在位检测机制**(cw2017 特有,值得记住):
TEMP_MIN(0x0D)寄存器的**奇偶校验位**就是"电池在位"标志——
`cw2017_set_battery_exist` 按电压窗口(firefly,battery-max/min-voltage)判定,
然后微调 TEMP_MIN使其奇偶校验通过/失败;`cw2017_check_battery` 只查奇偶。

**验证**:U-Boot 日志出现 `cw2017 init success!` → `Exit charge: battery is not exist`(无电池时正确跳过充电动画)。

---

## 4. 缺口二:rk3588_defconfig 缺 CONFIG_CHARGER_BQ25700

**文件**:`u-boot/configs/rk3588_defconfig`

5.10 defconfig 有 `CONFIG_CHARGER_BQ25700=y`,6.12 丢失 → 驱动根本没编译。
同时发现 `u-boot/drivers/power/charge/bq25700_charger.c:202` 有一处
`return 0` 缺分号(**这段代码从未被任何人编译过**),已补。

新增配置:

```
CONFIG_DM_FUEL_GAUGE=y      # 原有
CONFIG_CHARGER_BQ25700=y    # ← 新增
CONFIG_POWER_FG_CW201X=y    # 原有
```

U-Boot PD/typec 相关现有配置(供参考):
`CONFIG_DM_POWER_DELIVERY=y`、`CONFIG_TYPEC_PD_TCPM=y`、`CONFIG_TYPEC_PD_FUSB302=y`、
`CONFIG_DM_CHARGE_DISPLAY=y`、`CONFIG_CHARGE_ANIMATION=y`

**U-Boot 侧 bq25700 工作机制**(drivers/power/charge/bq25700_charger.c):
- `of_to_plat` 用 `fdt_node_offset_by_compatible` 找 `ti,bq25700`/`ti,bq25703`
  (注意:U-Boot 用的是**内核 DTB**——6.12 有 `CONFIG_EARLY_DISTRO_DTB`
  读 extboot 分区 rk-kernel.dtb + `CONFIG_DM_KERNEL_DTB` 在 board_init 内
  `of_live_build`+`dm_extended_scan`,早于 board_late_init 的 `charge_display()`,
  所以内核 dtsi 里的电源节点 U-Boot 直接可用,**无需**在 U-Boot dts 重复添加)
- `probe` → `uclass_get_device(UCLASS_PD, 0)` → fusb302 probe → PD 协商
- `bq25703_charger_current_init`:关充电看门狗 → 按 PD 协商结果写
  INPUTCURREN/INPUTVOLTAGE(仅 charging status 置位才写 CHARGECURREN);
  无 PD 时按 usb type 写 sdp(500mA)/dcp(1500mA) 档

**验证**:U-Boot 日志出现完整链:
`FUSB302 device ID: 0x81` → `CC connected in CC2 as UFP` →
`Requesting PDO x` → `bq25703_charger_current_init pd charge input vol:...uv current:...ua`

---

## 5. 缺口三:connector 节点 sink-pdos 被限到 5V/1A(5W)

**文件**:`kernel-6.12/arch/arm64/boot/dts/rockchip/rk3588-firefly-aio-3588sg.dtsi`
(节点:`&i2c2 → usbc0: fusb302@22 → usb_con: connector`)

前次调试时 sink-pdos 被改成只剩 `PDO_FIXED(5000, 1000)`,
PD 状态机只能协商 PDO 0(5V/1A = 5W);RK3588S + 4CH DRAM + VOP/DSI 负载
远超 5W → 依然欠压重启。

**修复**:恢复 5.10 原值三档:

```dts
op-sink-microwatt = <1000000>;
sink-pdos =
    <PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)
     PDO_FIXED(9000, 3000, PDO_FIXED_USB_COMM)
     PDO_FIXED(12000, 2000, PDO_FIXED_USB_COMM)>;
source-pdos = <PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)>;
```

**原理**:tcpm 的 `tcpm_pd_build_request` 在 sink-pdos 声明范围内取最优 →
sink-pdos 决定本板能向电源要的功率上限。pd.h 由 rk3588-firefly-common.dtsi 引入。

**验证**:U-Boot 协商 `Requesting PDO 2: 12000 mV, 2000 mA`,
`pd charge input vol:12000000uv current:2000000ua`,内核可完整启动。

> 教训:动 connector 的 sink-pdos 等于动整板功率预算,排查其他问题时
> 不要顺手"保守化"它,会引入新的欠压问题。

---

## 6. 缺口四(内核):tcpm SNK_TRANSITION_SINK 待机降流 → 500mA 瞬态塌电

**文件**:`kernel-6.12/drivers/usb/typec/tcpm/tcpm.c`(SNK_TRANSITION_SINK case,
编辑前 5220-5227 行)
**对照**:`rk3588_5.10.198_sdk/.../tcpm/tcpm.c:4412-4419` —— 同段代码被
Rockchip **整段注释掉**。

### 6.1 机制

内核接管后 fusb302 重新初始化(拆掉 U-Boot 协商的 12V/2A 契约),从 5V 重新协商。
PD 契约落定进入电压切换时,tcpm 按 USB PD 规范要求 sink 先降到待机功率
(pSnkStdby = 2.5W):

```c
case SNK_TRANSITION_SINK:
        if (port->supply_voltage != port->req_supply_voltage && !port->pps_data.active &&
            port->current_limit * port->supply_voltage / 1000 > PD_P_SNK_STDBY_MW) {
                u32 stdby_ma = PD_P_SNK_STDBY_MW * 1000 / port->supply_voltage;
                // 2500mW*1000/5000mV = 500mA  ← 罪魁
                tcpm_set_current_limit(port, stdby_ma, port->supply_voltage);
        }
        fallthrough;
```

电流值流向 psy:`tcpm_psy_get_current_now()` 返回 `port->current_limit * 1000`
(即 CURRENT_NOW)→ bq25700 的 PD 通知链消费:

### 6.2 bq25700 内核侧消费链(drivers/power/supply/bq25700_charger.c)

- `ti,usb-charger-detection = <&usbc0>` phandle 指向 fusb302,
  `bq25700_register_pd_nb` 用 `power_supply_reg_notifier` 订阅其 psy 事件
  (按 notify_node 的 of_node 过滤)
- `bq2570x_pd_notifier_call`:ONLINE==0 → `discnt_work`;
  否则读 CURRENT_NOW → cur_idx、VOLTAGE_NOW → vol_idx、再读 CURRENT_NOW → chr_idx,
  直接写 INPUT_CURRENT / INPUT_VOLTAGE / CHARGE_CURRENT 三个寄存器,并打印:
  `"INPUT_CURRENT:%d, INPUT_VOLTAGE:%d, CHARGE_CURRENT:%d\n"`
- IRQ handler / discnt_work:AC_STAT==0 时写回 input_current_sdp(默认 500mA)

### 6.3 寄存器档位换算(看日志必备)

| 寄存器 | 编码 | 常见值 |
|---|---|---|
| INPUT_CURRENT | idx × 50mA | 60=3A,40=2A,**10=500mA**,7=350mA |
| INPUT_VOLTAGE | idx0≈5V 档;base 3.2V step 64mV,写时先减 1.28V+3.2V | 0=5V,67≈12V |
| CHARGE_CURRENT | idx × 64mA | 46≈2944mA,31≈1984mA,7≈448mA |

### 6.4 日志证据(插电池场景,三段完整录像)

```
[7.749] INPUT_CURRENT:60, VOL:0, CHR:46   ← 5V/3A 契约(15W,安全)
[8.087] INPUT_CURRENT:10, VOL:0, CHR:7    ← SNK_TRANSITION_SINK 待机降流 500mA(2.5W!)
[8.218] INPUT_CURRENT:40, VOL:67, CHR:31  ← 12V/2A 契约落地(24W)
```

- **插电池**:Vsys 有电池兜底,500mA 的 ~130ms 窗口无感度过 → 最终收敛 12V/2A
- **无电池**:Vsys 全靠 USB 输入,2.5W 顶不住启动负载 →
  在 12V 契约落地前塌电死机(6.918s 收到 500mA 事件写入后即无输出)

### 6.5 修复

对齐 5.10:把 6.12 `SNK_TRANSITION_SINK` 中的整段 if 块注释掉
(含 `stdby_ma` 局部变量声明,避免未使用告警),`fallthrough` 保持不动。
效果:IINDPM 直接从 3A@5V 切到 2A@12V,全程 ≥10W,无电池也扛得住。

> 注:这是有意违反 USB PD 规范的 pSnkStdby 要求(Rockchip 5.10 亦如此),
> 后果是电压切换瞬间可能多抽一点电流,规范风险自负;对本板这是唯一让
> 无电池 PD 存活的做法。

**验证判据**(无电池 + PD):
- ✅ 生效:`INPUT_CURRENT:60 → 40, VOL:67` 两段,**中间无 `INPUT_CURRENT:10`**,
  系统进到登录提示符
- ❌ 未生效:仍见 `INPUT_CURRENT:10` 或塌电重启

---

## 7. 全部改动文件清单

| # | 文件 | 改动 | 状态 |
|---|---|---|---|
| 1 | `u-boot/drivers/power/fuel_gauge/fg_cw201x.c` | 从 5.10 移植完整 cw2017 支持(415→701 行) | ✅ 已验证 |
| 2 | `u-boot/configs/rk3588_defconfig` | 加 `CONFIG_CHARGER_BQ25700=y` | ✅ 已验证 |
| 3 | `u-boot/drivers/power/charge/bq25700_charger.c` | :202 `return 0` 补分号(死代码笔误) | ✅ 已验证(编译通过) |
| 4 | `kernel-6.12/arch/arm64/boot/dts/rockchip/rk3588-firefly-aio-3588sg.dtsi` | sink-pdos 恢复 5.10 三档(5V/3A, 9V/3A, 12V/2A) | ✅ 已验证(U-Boot 协商 12V/2A) |
| 5 | `kernel-6.12/drivers/usb/typec/tcpm/tcpm.c` | SNK_TRANSITION_SINK 待机降流整段注释(对齐 5.10) | ⏳ 待编译烧录验证 |

> 注:`rk3588-firefly-aio-3588sg.dtsi` 为新建未跟踪文件,服务器同步时注意别漏。
> 内核 bq25700_charger.c 里另有一处用户早前打的补丁
> ("no battery, skip input_current_sdp programming"):probe 时无电池则
> 跳过 input_current_sdp 初编,避免空板插 PD 即进异常电源路径,保留。

---

## 8. 遗留 / 待验证

1. **缺口四验证**(改动 #5):无电池 + PD 应完整进系统;
   回归:插电池+PD 充电正常(cw2017-battery status=Charging)、纯电池开机正常
2. Linux 侧 probe 时序:`bq25700 notify_psy is error` —— BQ probe 时 fusb302
   psy 尚未注册(`power_supply_get_by_phandle` 失败),非致命,后续 psy 事件
   到来即恢复;5.10 亦有此打印,暂不处理
3. `Invalid or missing extcon dev1`(bq25700 无 extcon):
   dtsi 里 `extcon = <&u2phy0>` 存在,该打印为 usb2-phy 侧 probe 顺序问题,
   不影响 PD 路径,暂不处理
4. U-Boot 交接日志 `PD chip enter low power mode`:fusb302 在内核接管前进
   低功耗,内核驱动重新初始化会拆掉 U-Boot 契约重新协商 —— 属正常序列,
   5.10 相同;这就是为什么内核侧也必须能正确写 IINDPM(不能只依赖 U-Boot)

---

## 9. 排查方法论备忘(下次少走弯路)

1. **先找"谁在写 IINDPM"**——PD 供电问题本质是功率预算问题,
   寄存器档位(idx×50mA)换算成瓦特,和板子负载对比,立判
2. **U-Boot charge 链是串行的**:PMIC → FG(cw2017)→ charger(bq25700)→
   PD(fusb302)→ RTC → power key,任何一环 -ENODEV 后面全部静默不跑;
   日志里"缺少哪一段打印"就等于"断在哪一环"
3. **FG uclass 失败只打 debug 级**,普通日志看不到,别被骗
4. **对比 5.10 是最高效的路径**:一切"5.10 可以、6.12 不行"的差异
   (驱动删减/配置丢失/dts 改动/上游代码重新启用)都值得 diff 一遍
5. **三方日志解码**:同一个 psy 事件,插电池是"无感瞬态",
   无电池是"致死窗口"——插电池日志可以用来完整还原失败时序
6. 改 connector sink-pdos = 改功率预算,别在排查其他问题时顺手保守化
