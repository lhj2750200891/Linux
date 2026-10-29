# RTC

　　K3 平台实时时钟适配笔记: 三个候选路径 — SoC 内置 mmp-rtc、RCPU 固件侧
rpmi_rtc (默认)、外部 I2C RTC (pcf8563 / hym8563)。以 Firefly AIBOX-PRO-K3 /
aibox-k3 / itx-k3l 为参考板, 覆盖选型逻辑、断电保持、定时开机与内核配置陷阱。

## 1. 原理

### 1.1 K3 的三个 RTC 来源与选型逻辑

| 路径 | 设备树节点 | 驱动 | 断电保持 | 现状 |
|---|---|---|---|---|
| SoC 内置 RTC | `rtc@d4010000` (k3.dtsi, 默认 okay) | rtc-sa1100.c (mrvl,mmp-rtc) | 无电池域, 同样不保持 | **CONFIG_RTC_DRV_SA1100 未编入** (k3_defconfig 无), 默认不可用 |
| RPMI RTC | `rpmi_rtc` (k3.dtsi, 默认 okay) | rtc-rpmi.c (riscv,rpmi-rtc) | 时间由 RCPU 固件维持, **断电丢失** | CONFIG_RTC_DRV_RPMI=y, 开箱即用 |
| 外部 I2C RTC | pcf8563/hym8563 @0x51 | 对应 I2C 驱动 | **纽扣电池保持** | CONFIG 缺省未开, 需要自己补 |

　　选型原则: 只要产品需要"断电后时间不丢" (绝大多数场景), 必须**外部 I2C
RTC + 纽扣电池**; rpmi_rtc 只适合不需要断电保持、只要系统时钟暂存的场景。

### 1.2 rtc0 顺序问题 (Firefly 为什么关掉 rpmi_rtc)

　　多个 RTC 同时存在时, **先 probe 的成为 /dev/rtc0**, 而 hwclock / systemd
默认只操作 rtc0。rpmi_rtc 是 built-in 平台设备, 永远比后挂 I2C 总线的外部
RTC 先注册 → 外部 RTC 会被排到 rtc1, 断电保持等于白配。所以 Firefly 两块
带外部 RTC 的板都在设备树里把 rpmi_rtc `status = "disabled"`:

```c
/* aibox-k3 (FF_RTC), 注释原文: only use pcf8563 rtc */
&rpmi_rtc {
	status = "disalbed";    /* 拼写错误, 详见 4.4 陷阱 */
};
/* itx-k3l (FF_RTC), 注释原文: only use hym8563 rtc */
&rpmi_rtc {
	status = "disabled";
};
```

### 1.3 hym8563 的 spacemit,p1 与定时开机

　　itx-k3l 的 hym8563 节点带厂商私有布尔属性 `spacemit,p1`, 驱动
`drivers/rtc/rtc-hym8563.c` 解析为 `spacemit_p1` 标志: 闹钟中断触发时, INT
线保持拉低 1 秒才清 alarm 标志 (驱动注释: "The P1 power-on path requires
the line to remain low for one second")。用途 = **RTC 定时开机**: 闹钟把
INT 拉低足够久, 板上电源电路据此完成上电。自研板若不需要定时开机, 该属性
可省。

## 2. 硬件连接

　　外部 I2C RTC 的典型接法 (两参考板一致, 仅总线/中断脚不同):

- RTC 芯片 VDD ≈ 3.3V (主电), 备用纽扣电池 (CR2032, 3V) 接 VBAT 脚;
- SCL/SDA 接 I2C 总线, 总线上拉由 pinctrl/板上电阻提供;
- INT 脚接 GPIO, 闹钟到点拉低 (open-drain, 板上/内部上拉);
- 地址固定 0x51。

| 参考板 | 芯片 | I2C 总线 | SCL/SDA pad (复用号) | INT GPIO | IO 域 | 触发方式 |
|---|---|---|---|---|---|---|
| aibox-k3 | pcf8563 | i2c1 | pad 54 / 55 (func 5) | GPIO101 | 1.8V | 低电平 |
| itx-k3l | hym8563 | i2c6 | pad 151 / 152 (func 2) | GPIO41 | 1.8V | 下降沿 |

接线核对要点:

- i2c 总线节点本身要 `status = "okay"` 且配好 pinctrl 组 (i2c1_1_cfg /
  i2c6_0_cfg 均在 k3-pinctrl.dtsi 基座预置, bias-pull-up, drive-strength
  25)。
- 纽扣电池电压不足 (CR2032 低于 ~2.5V) 时时间照走但断电即丢, 验证断电保持
  前先量电池电压。
- INT 脚不接也可用 (时间读写不依赖中断), 只有闹钟/定时开机需要。

## 3. 内核配置

　　k3_defconfig 现状: `CONFIG_RTC_CLASS=y`、`CONFIG_RTC_DRV_RPMI=y` (rpmi_rtc
开箱即用)。外部 RTC 驱动**两者都未编入**, 按选型补:

```
# 方式二 (pcf8563):
CONFIG_RTC_DRV_PCF8563=y

# 方式三 (hym8563):
CONFIG_RTC_DRV_HYM8563=y

# 方式四 (SoC 内置 mmp-rtc, 一般不用):
CONFIG_RTC_DRV_SA1100=y    # Kconfig 依赖已含 SOC_SPACEMIT, 可选
```

## 4. 设备树配置

### 4.1 方式一: rpmi_rtc (默认路径, 零改动)

　　k3.dtsi 基座已 `status = "okay"`, defconfig 已带驱动, **什么都不用做**
系统即有 /dev/rtc。局限: 断电时间丢失 (RCPU 掉电), 适合不需要保持的形态。
验证 NTP 场景 (开机网络对时 + 关机前 hwclock 写回) 下够用。

### 4.2 方式二: 外部 pcf8563 (aibox-k3 方案)

　　参考板: aibox-k3 (FF_RTC 分支, 挂 i2c1)。自研板完整写法 (i2c1 总线使能
+ RTC 节点 + 关 rpmi_rtc):

```dts
&i2c1 {
	pinctrl-names = "default";
	pinctrl-0 = <&i2c1_1_cfg>;        /* 基座组: pad54 scl / pad55 sda, func5 */
	status = "okay";

	pcf8563: pcf8563@51 {
		compatible = "nxp,pcf8563";
		reg = <0x51>;
		#clock-cells = <0>;
		clock-frequency = <32768>;
		clock-output-names = "pcf8563";
		pinctrl-names = "default";
		pinctrl-0 = <&pcf8563_int_cfg>;
		interrupt-parent = <&gpio>;
		interrupts = <K3_GPIO(101) IRQ_TYPE_LEVEL_LOW>;
		wakeup-source;                /* 闹钟可唤醒 suspend */
	};
};

&rpmi_rtc {
	status = "disabled";              /* 让 pcf8563 当 rtc0, 别抄参考板的错拼 */
};

&pinctrl {
	pcf8563_int_cfg: pcf8563-int-cfg {
		pcf8563-int-pin {
			pinmux = <K3_PADCONF(101, 0)>;
			bias-pull-up;             /* INT 开漏, 内部上拉兜底 */
			drive-strength = <25>;
			power-source = <1800>;
		};
	};
};
```

　　内核配置补 `CONFIG_RTC_DRV_PCF8563=y`。

### 4.3 方式三: 外部 hym8563 + 定时开机 (itx-k3l 方案)

　　参考板: itx-k3l (FF_RTC 分支, 挂 i2c6, 与 ctf2301 风扇/eeprom 同总线)。

```dts
&i2c6 {
	pinctrl-names = "default";
	pinctrl-0 = <&i2c6_0_cfg>;        /* 基座组: pad151 scl / pad152 sda, func2 */
	status = "okay";

	hym8563: hym8563@51 {
		compatible = "haoyu,hym8563";
		reg = <0x51>;
		#clock-cells = <0>;
		clock-frequency = <32768>;
		clock-output-names = "hym8563";
		pinctrl-names = "default";
		pinctrl-0 = <&hym8563_int_cfg>;
		interrupt-parent = <&gpio>;
		interrupts = <K3_GPIO(41) IRQ_TYPE_EDGE_FALLING>;
		spacemit,p1;                  /* 闹钟 INT 保持低 1s, 供定时开机电源电路 */
		wakeup-source;
		status = "okay";
	};
};

&rpmi_rtc {
	status = "disabled";
};

&pinctrl {
	hym8563_int_cfg: hym8563-int-cfg {
		hym8563-int-pin {
			pinmux = <K3_PADCONF(41, 0)>;
			bias-pull-up;
			drive-strength = <25>;
			power-source = <1800>;
		};
	};
};
```

　　内核配置补 `CONFIG_RTC_DRV_HYM8563=y`。定时开机的使用链: 用户态
`hwclock --set --date=...` + `rtcwake -m off -t <time>` 触发闹钟 → 断电 →
到点 INT 拉低 1s (spacemit,p1) → 电源电路上电。

### 4.4 属性速查与陷阱

| 属性 | 说明 |
|---|---|
| reg = <0x51> | pcf8563/hym8563 固定地址 |
| #clock-cells=0 + clock-frequency=32768 | 把 RTC 的 CLKOUT 脚注册成时钟源 (clkout_32k), 别处可引用 |
| interrupts | 闹钟中断; 不用闹钟可整段省 (连同 pinctrl 组) |
| wakeup-source | 闹钟唤醒 suspend |
| spacemit,p1 | hym8563 专属: INT 保持低 1s, 定时开机用 |

陷阱清单:

- **"disalbed" 拼写错误** (aibox-k3 原文): 设备树 status 只认 "okay"/"ok",
  其余一律按 disabled 处理, 所以错拼恰好"歪打正着"地生效了 — 照抄会埋雷
  (校验工具会报 warning), 一定写对。
- 外部 RTC 配了但 `hwclock` 读到的还是丢时间的那个: rtc0 被 rpmi_rtc 占了
  (1.2 节), 必须 disable rpmi_rtc; 可用 `ls -l /dev/rtc*` 核对谁是 rtc0。
- CONFIG 忘开 (PCF8563/HYM8563 缺省都不在): 节点无驱动匹配, i2cdetect 能
  扫到 0x51 但 /dev/rtc1 不出现。
- SoC 内置 `rtc@d4010000` 节点默认 okay 但驱动没编 — 它不是"已经在工作",
  别被 status 迷惑。

## 5. 验证测试

```bash
# 1. RTC 设备与归属
ls -l /dev/rtc*                 # rtc -> rtc0 指向谁
cat /sys/class/rtc/rtc0/name    # 应显示 pcf8563-rtc / hym8563-rtc (而非 rpmi-rtc)

# 2. 写读时间 (系统 -> 硬件 -> 系统回环)
date -s "2026-10-29 12:00:00"
hwclock -w                      # 写入 rtc0
hwclock -r                      # 读回核对

# 3. 断电保持验证 (核心!)
#    拔电源 (保留纽扣电池) 等 5 分钟, 重新上电后:
hwclock -r                      # 时间应连续, 不是重置成 1970/出厂值

# 4. 闹钟唤醒 (suspend 场景)
echo 0 > /sys/class/rtc/rtc0/wakealarm   # 清
echo $(( $(date +%s) + 60 )) > /sys/class/rtc/rtc0/wakealarm
systemctl suspend ; sleep 1     # 60 秒后应被闹钟唤醒

# 5. I2C 层面排查 (无 rtc 设备时)
i2cdetect -y 1                  # aibox-k3 接法: 0x51 应显示 U (在用) 或 51
dmesg | grep -iE "rtc|hym8563|pcf8563" | head
zcat /proc/config.gz | grep -E "RTC_DRV_PCF8563|RTC_DRV_HYM8563|RTC_DRV_RPMI"
```
