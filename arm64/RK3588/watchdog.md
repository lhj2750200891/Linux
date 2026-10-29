# 看门狗

　　SoC 内置 DW 看门狗与外扩 I2C 看门狗 (PC9202/PC9204, 原厂 SDK 无驱动需移植)。

## 1. SoC 内置看门狗 (DW watchdog)

### 1.1 硬件连接

```
RK3588 内置 DW watchdog (watchdog@feaf0000), 无外部引脚
wdt 使用 TCLK_WDT0 时钟, POR 之后仍在运行
```

### 1.2 设备树配置

　　基础 dtsi (rk3588s.dtsi) 中默认 disabled, 使能即可:

```
&wdt {
	status = "okay";
};
```

　　内核配置 (defconfig 中默认已开):

```
CONFIG_WATCHDOG=y
CONFIG_DW_WATCHDOG=y
```

　　注意:
- 使能后设备树只是注册了 /dev/watchdog, 只有被打开后看门狗才开始计数
- 用户态需要喂狗程序 (systemd 的 RuntimeWatchdogSec / busybox watchdog)
- U-Boot 阶段看门狗默认关闭, kernel 启动后由驱动接管

### 1.3 验证测试

```
# 查看设备
ls /dev/watchdog*
dmesg | grep -i watchdog

# 手动喂狗测试 (打开设备后看门狗开始计数)
cat /dev/watchdog        # 读取一次即喂狗一次

# 安全关闭看门狗 (写 V 后关闭文件, 看门狗停止计数)
echo V > /dev/watchdog

# 测试超时复位 (危险! 会重启系统, 且喂狗程序必须停止)
# 打开 /dev/watchdog 后不做任何操作, 默认超时(60s)后系统复位

# systemd 喂狗 (推荐生产环境使用)
# /etc/systemd/system.conf 中设置:
#   RuntimeWatchdogSec=30        # 30s 无响应判定系统卡死,硬件复位
```

## 2. 外扩 I2C 看门狗 (PC9202/PC9204)

　　Firefly 部分板卡 (如 core-3588jd4) 外扩了一颗 I2C 看门狗芯片 PC9202/PC9204。

### 2.1 硬件连接 (以 core-3588jd4 为例)

```
PC9202 看门狗芯片:
  SCL     ====> I2C0_SCL_M2 ====> GPIO0_D1
  SDA     ====> I2C0_SDA_M2 ====> GPIO0_D2
  WDT_EN  ====> GPIO2_C5 (高有效, 芯片看门狗使能脚)
```

　　参考配置 (其他 Firefly 板卡):
- aio-3588jd4 底板: i2c4(m1) + GPIO0_C4 高有效, driver-names = "wdt_base"
- aio-3588l-qua-rk182x: i2c0 + GPIO2_C5 低有效(注意区别), driver-names = "wdt_core"

### 2.2 驱动移植 (瑞芯微原厂 SDK 无此驱动!)

　　驱动位于 firefly 内核 drivers/watchdog/pc9202_wdt.c (firefly 私有),
瑞芯微原厂 SDK 需要移植以下 3 处:
- 复制 drivers/watchdog/pc9202_wdt.c
- drivers/watchdog/Kconfig 增加: config PC9202_WATCHDOG
- drivers/watchdog/Makefile 增加: obj-$(CONFIG_PC9202_WATCHDOG) += pc9202_wdt.o

　　内核配置:

```
CONFIG_PC9202_WATCHDOG=y
```

### 2.3 设备树配置

```
&i2c0 {
	status = "okay";
	pinctrl-0 = <&i2c0m2_xfer>;

	pc9202@3c {
		status = "okay";
		compatible = "firefly,pc9202";   // 兼容 pc9204, 驱动自动识别 ChipID
		reg = <0x3c>;
		index = <0>;
		wd-en-gpios = <&gpio2 RK_PC5 GPIO_ACTIVE_HIGH>;
		driver-names = "wdt_core";       // 生成 /dev/wdt_core
	};
};
```

### 2.4 验证测试 (传统字符设备, 非标准 watchdog 框架)

```
# 查看设备 (driver-names 决定设备名)
ls /dev/wdt_core
dmesg | grep -i "pc9202\|Detected chip"    # 应看到 "Detected chip: PC9202"

# 喂狗 + 设置超时 (write 命令字)
echo 0 > /dev/wdt_core    # 0.64s 超时档
echo 1 > /dev/wdt_core    # 2.56s 超时档
echo 2 > /dev/wdt_core    # 10.24s 超时档
echo 3 > /dev/wdt_core    # 40.96s 超时档

# 使能/禁用硬件看门狗 (GPIO 控制)
echo e > /dev/wdt_core    # 使能
echo d > /dev/wdt_core    # 禁用

# 测试超时复位 (危险! 会重启系统)
# echo e > /dev/wdt_core && echo 0 > /dev/wdt_core 后停止喂狗, 0.64s 后复位
```

　　注意:
- 不是标准 /dev/watchdog, systemd RuntimeWatchdogSec 不适用于此设备
- 喂狗周期必须小于所选超时档, 例: 选 '3' 档需 40s 内至少喂一次
- 驱动 probe 时会读 ChipID 寄存器(0xA1) 自动区分 PC9202(0x01)/PC9204(0xFF),
  并自动选择对应控制寄存器 (PC9202:0x01 / PC9204:0x02)
