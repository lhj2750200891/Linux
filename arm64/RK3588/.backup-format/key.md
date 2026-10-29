# 按键 (Key) 适配笔记

## 1. 硬件连接

```
PWRON(电源键)    ====> RK806 PMIC 的 PWRON 引脚 (长按 6~8s 芯片强制下电,与软件无关)
RECOVERY(恢复键) ====> SARADC 通道1 (按下接地,分压后约 0V)
```

## 2. 设备树配置

### 2.1 电源键 (RK806 PWRON)

RK806 挂在 SPI2 上,直接引用瑞芯微原厂 dtsi:

```
#include "rk3588-rk806-single.dtsi"   // 内部已包含 pwrkey { status = "okay"; }
```

原厂 dtsi 中相关节点(无需修改,确认存在即可):

```
&spi2 {
	rk806single: rk806single@0 {
		compatible = "rockchip,rk806";
		spi-max-frequency = <1000000>;
		reg = <0x0>;
		interrupt-parent = <&gpio0>;
		interrupts = <7 IRQ_TYPE_LEVEL_LOW>;
		...
		pwrkey {                // 电源键子节点,驱动: CONFIG_INPUT_RK805_PWRKEY
			status = "okay";
		};
	};
};
```

短按上报 KEY_POWER 事件,由系统处理休眠/关机。

### 2.2 Recovery 键 (ADC 按键)

基础 dtsi 中 saradc 默认 disabled,必须先打开:

```
&saradc {
	status = "okay";
	vref-supply = <&vcc_1v8_s0>;
};
```

按键节点(按键按下接地,分压约 0V):

```
/ {
	adc_keys: adc-keys {
		status = "okay";
		compatible = "adc-keys";              // 驱动: CONFIG_KEYBOARD_ADC
		io-channels = <&saradc 1>;            // SARADC 通道1
		io-channel-names = "buttons";
		keyup-threshold-microvolt = <1800000>; // 松开判定阈值 = vref
		poll-interval = <100>;

		recovery-key {
			label = "F12";                    // 用于 recovery 组合键判断
			linux,code = <KEY_F12>;
			press-threshold-microvolt = <17000>; // 按下时 ADC < 17mV 判定为按下
		};
	};
};
```

注意:
- U-Boot 也有对应的 recovery 按键检测,进 loader/recovery 模式需要同步配置 U-Boot 设备树
- 如需多个 ADC 按键,在 adc-keys 下按不同 press-threshold-microvolt 分压添加

## 3. 验证测试

```
# 内核配置确认
zcat /proc/config.gz | grep -E "KEYBOARD_ADC|RK805_PWRKEY"
#   CONFIG_KEYBOARD_ADC=y
#   CONFIG_INPUT_RK805_PWRKEY=y

# evtest 测试(需 apt install evtest)
evtest
#   选择 "rk805 pwrkey" 设备, 短按电源键应打印 KEY_POWER 事件
#   选择 "adc-keys" 设备, 按 recovery 键应打印 KEY_F12 事件
```
