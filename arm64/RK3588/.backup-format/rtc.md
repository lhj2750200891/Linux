# RTC (HYM8563) 适配笔记

## 1. 硬件连接

```
HYM8563 RTC:
  SCL  ====> I2C2_SCL_M0 ====> GPIO0_B7
  SDA  ====> I2C2_SDA_M0 ====> GPIO0_C0
  INT  ====> GPIO0_B0 (低有效,上拉)
  CLKOUT (32.768KHz) ====> WiFi/BT 模块时钟输入 (被 wireless-bluetooth 引用)
  纽扣电池维持掉电计时
```

## 2. 设备树配置

```
&i2c2 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c2m0_xfer>;

	hym8563: hym8563@51 {
		compatible = "haoyu,hym8563";       // 驱动: CONFIG_RTC_DRV_HYM8563
		reg = <0x51>;
		#clock-cells = <0>;                 // 同时作为 32.768K 时钟源
		clock-frequency = <32768>;
		clock-output-names = "hym8563";
		pinctrl-names = "default";
		pinctrl-0 = <&hym8563_int>;
		interrupt-parent = <&gpio0>;
		interrupts = <RK_PB0 IRQ_TYPE_LEVEL_LOW>;  // 闹钟中断
		wakeup-source;                      // 支持休眠唤醒
		status = "okay";
	};
};

&pinctrl {
	rtc {
		hym8563_int: hym8563-int {
			rockchip,pins = <0 RK_PB0 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};
```

注意:
- clock-output-names = "hym8563" 输出的 32.768K 时钟被 wireless-bluetooth 节点
  引用为 ext_clock (clocks = <&hym8563>), WiFi/BT 模块依赖此节点
- 若硬件没有 RTC 芯片,删除此节点即可,系统用 rk806 内部 RTC (CONFIG_RTC_DRV_RK808)

## 3. 验证测试

```
# 检查 rtc 节点
cat /proc/driver/rtc
ls /sys/class/rtc/

# 读写时间验证
date 010203042027.00      # 设置系统时间 2027-01-02 03:04
hwclock -w                # 同步到 RTC
hwclock -r                # 读回
重启后 date 检查时间保持

# 闹钟唤醒测试 (休眠后)
echo +60 > /sys/class/rtc/rtc0/wakealarm
echo mem > /sys/power/state  # 60秒后应被 RTC 闹钟唤醒
```
