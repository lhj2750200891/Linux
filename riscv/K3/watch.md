# 看门狗

　　K3 平台看门狗适配笔记: SoC 内置 watchdog (k1-wdt) 与外置 I2C 看门狗芯片
PC9202 两条路径。以 Firefly AIBOX-PRO-K3 (内置狗 + PC9202 都配了) 为参考板,
覆盖"驱动在但狗没开"的基座语义、外置狗的字符设备用法与内核配置陷阱。

## 1. 原理

### 1.1 SoC 内置看门狗 (spacemit-k1-wdt)

　　k3.dtsi 基座 (`watchdog: watchdog@d4014000`, compatible "spacemit-k1,wdt"),
驱动 `drivers/watchdog/spacemit-k1-wdt.c` (CONFIG_SPACEMIT_K1_WATCHDOG,
k3_defconfig 已 =y)。基座节点原样 (注意它**默认处于"驱动在、狗没启动"态**):

```c
watchdog: watchdog@d4014000 {
	compatible = "spacemit-k1,wdt";
	clocks = <&syscon_apbc CLK_APBC_TIMERS0>,
		 <&syscon_apbc CLK_APBC_TIMERS0_BUS>;
	clock-names = "clk", "clk-bus";
	resets = <&syscon_apbc RESET_APBC_TIMERS0>;
	reg = <0x0 0xd4014000 0x0 0xff>,
	      <0x0 0xd4050000 0x0 0x1024>;
	interrupts = <35 4>;
	interrupt-parent = <&saplic>;
	spa,wdt-disabled;                 /* 有此属性: probe 后不启动喂狗 (ctrl=0) */
	spa,wdt-enable-restart-handler;   /* 注册 restart 处理器: reboot 走 wdt 复位 */
	status = "okay";
};
```

　　两个布尔属性的语义 (驱动 `spa_wdt_dt_init`):

| 属性 | 有 → | 无 → |
|---|---|---|
| spa,wdt-disabled | ctrl=0, **狗不启动** (只注册设备) | ctrl=1, probe 即启动硬件狗, 内核 hrtimer 自动喂 |
| spa,wdt-enable-restart-handler | 注册 restart handler, reboot 命令经狗复位 | reboot 走普通复位路径 |

　　也就是说: 想启用内置狗, 设备树只需**删掉 spa,wdt-disabled 一行**; 内核
正常时驱动自动喂狗, 内核挂死/喂狗定时器停摆即触发复位。用户态程序还可
通过标准 `/dev/watchdog` 接管 (标准 watchdog API, 写字符喂狗)。

### 1.2 外置 I2C 看门狗 (PC9202)

　　Firefly 在带"母板"形态的机器 (AIBOX-PRO 的 i2c3、itx-k3l 基板) 上放了
一颗 PC9202 (地址 0x3c), 驱动 `drivers/watchdog/pc9202_wdt.c`
(CONFIG_PC9202_WATCHDOG, **k3_defconfig 未编入**)。与标准 watchdog 子系统
不同, 这个驱动是**私有字符设备**实现:

- probe 时按设备树 `driver-names` 字符串注册 chrdev (`register_chrdev(0,
  "wdt_base", &wdt_fops)`), 用户态喂狗走 `/dev/wdt_base`, 不出现
  `/dev/watchdogN`。
- 用途定位: 外置狗独立于 SoC 电源域, SoC 彻底挂死 (连内置狗都失效, 如时钟
  崩掉) 时由外部芯片对整机断电重启, 冗余等级更高。

## 2. 硬件连接

### 2.1 内置看门狗

　　无外部引脚, 纯 SoC 内部外设; 复位效果 = 整片 SoC 复位, 与 reset 按键
等效。

### 2.2 PC9202 外置狗

　　参考板: AIBOX-PRO-K3 (FF_WATCHDOG 分支, 挂 i2c3):

| 信号 | pad 全局号 | 复用功能号 | 说明 |
|---|---|---|---|
| i2c3 SCL | pad 82 | func 6 | i2c3_2_cfg (基座组) |
| i2c3 SDA | pad 83 | func 6 | 同上 |
| PC9202 RST_OUT | - | - | 接主板电源控制电路 (拉低 → 断电重启), 硬件设计项 |

接线核对要点:

- PC9202 的复位输出脚必须串进主板**电源使能/复位电路**, 这是外置狗有意义
  的前提 (软件层面只是 I2C 喂狗)。
- 地址 0x3c 固定; i2cdetect 先确认 0x3c 有 ACK 再谈驱动。
- itx-k3l 的同款节点挂在基板总线, 注释原文 "watch dog on mother base" —
  布线在母板, 自研板按自己拓扑选 I2C 口。

## 3. 内核配置

```
# k3_defconfig 已有:
CONFIG_WATCHDOG=y
CONFIG_SPACEMIT_K1_WATCHDOG=y     # SoC 内置狗, 开箱可用

# 用 PC9202 时追加 (缺省未编入):
CONFIG_PC9202_WATCHDOG=y          # bool, 依赖 I2C
```

## 4. 设备树配置

### 4.1 方式一: 启用 SoC 内置看门狗

　　在自研板 dts 覆盖基座节点, 删掉 spa,wdt-disabled (覆盖法删不了单条属
性, 直接重写整个节点):

```dts
&watchdog {
	clocks = <&syscon_apbc CLK_APBC_TIMERS0>,
		 <&syscon_apbc CLK_APBC_TIMERS0_BUS>;
	clock-names = "clk", "clk-bus";
	resets = <&syscon_apbc RESET_APBC_TIMERS0>;
	reg = <0x0 0xd4014000 0x0 0xff>,
	      <0x0 0xd4050000 0x0 0x1024>;
	interrupts = <35 4>;
	interrupt-parent = <&saplic>;
	/* spa,wdt-disabled 已删: probe 即启动, 内核自动喂狗 */
	spa,wdt-enable-restart-handler;   /* reboot 走狗复位, 保留 */
	status = "okay";
};
```

　　只想要 reboot 硬复位但不要常开狗 → 保持基座原样 (什么都不写)。

### 4.2 方式二: PC9202 外置看门狗

　　参考板: AIBOX-PRO-K3 (FF_WATCHDOG 分支)。完整写法:

```dts
&i2c3 {
	pinctrl-names = "default";
	pinctrl-0 = <&i2c3_2_cfg>;        /* 基座组: pad82 scl / pad83 sda, func6 */
	status = "okay";

	pc9202_base: pc9202_base@3c {
		status = "okay";
		compatible = "firefly,pc9202";
		reg = <0x3c>;
		index = <1>;                  /* 驱动不解析, 遗留属性, 可删 */
		driver-names = "wdt_base";    /* chrdev 设备名: /dev/wdt_base */
	};
};
```

　　配套内核配置 `CONFIG_PC9202_WATCHDOG=y`。喂狗 (参考 Firefly 用户态逻辑,
写任意字符即喂):

```bash
exec 3<>/dev/wdt_base
while :; do echo 1 >&3; sleep 5; done    # 周期按芯片规格调
```

### 4.3 属性速查与陷阱

| 属性/节点 | 说明 |
|---|---|
| spa,wdt-disabled (内置狗) | 存在即不启动; **删它才是开狗**, 不是改 status |
| spa,wdt-enable-restart-handler | reboot 复位链; 建议保留 |
| compatible = "firefly,pc9202" | 唯一匹配串 (驱动表里就这一条) |
| driver-names | **必填**, chrdev 名字; 缺失时 probe 走 err 分支 |
| index | 驱动不解析 (grep 无匹配), 遗留属性 |
| interrupts (内置狗) | 基座已带, 覆写别丢 |

陷阱清单:

- "改 status = disabled 来关狗"是反的: 内置狗默认就不启动, status 控制的是
  驱动要不要 probe; 开狗靠删 spa,wdt-disabled。
- PC9202 忘了 `CONFIG_PC9202_WATCHDOG=y`: i2cdetect 能看到 0x3c, 但 /dev 下
  无 wdt_base, dmesg 无 probe 记录。
- `driver-names` 没写: 驱动直接注册失败 (register_chrdev 拿到 NULL 名),
  probe 报 "Unable to register wdt character device"。
- 外置狗接了但复位电路没串电源: 一切正常但挂死不断电, 形同虚设 — 硬件
  评审项。
- 内置狗启用后系统 boot 慢 (如 netfilter 大规则) 也会被咬: 先确认喂狗定时
  器随 CPU 调度, 关键路径 (suspend/smp 旱灾) 是否可能饿死, 再决定用内置还
  是外置。

## 5. 验证测试

### 5.1 内置狗

```bash
# 1. 设备出现
ls -l /dev/watchdog* ; dmesg | grep -i watchdog | head

# 2. 自动喂狗确认 (启用 spa,wdt-disabled 删除后, 系统正常时应永不复位)
uptime                              # 挂机 10 分钟不重启 = 内核喂狗正常

# 3. 咬人测试 (危险: 会真复位, 存好工作!)
#    阻塞 CPU 让 hrtimer 喂狗失败, 观察整机复位
echo c > /proc/sysrq-trigger        # 主动 panic, 观察 reboot 是否发生
#    或: 关调度喂狗路径的极端负载测试按自研标准来

# 4. reboot 走狗复位验证
reboot                              # 复位后看 U-Boot 时间戳/复位原因寄存器
```

### 5.2 PC9202

```bash
# 1. I2C 在位
i2cdetect -y 3 | grep -w 3c         # 3c 应显示 U (在用)

# 2. 字符设备出现
ls -l /dev/wdt_base

# 3. 喂狗链验证 (先与硬件确认芯片超时周期, 再做停止喂狗复位测试)
exec 3<>/dev/wdt_base; echo 1 >&3   # 手动喂一次, 观察芯片计数器/复位脚
#    停止喂狗 → 等到超时周期 → 整机断电重启 = 全链路 OK
```
