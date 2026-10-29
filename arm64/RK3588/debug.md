# 串口 (UART)

　　UART2 调试串口 (fiq-debugger, 1500000 波特率) 与 uart0/3/4/5 普通串口的配置与回环验证。

## 1. 硬件连接

```
调试串口 (fiq-debugger):
  UART2_RX_M0 ====> GPIO0_B6
  UART2_TX_M0 ====> GPIO0_B5

BT 串口 (wifi-bt 模块使用):
  uart9m2: RX=GPIO3_D4 TX=GPIO3_D5 (CTS/RTS 流控, 详见 wifi-bt 模块)

扩展排针串口:
  uart0m2: RX=GPIO4_A4 TX=GPIO4_A3   (RS232)
  uart3m2: RX=GPIO4_A6 TX=GPIO4_A5   (RS485)
  uart4m0: RX=GPIO1_D3 TX=GPIO1_D2   (排针)
  uart5m1: RX=GPIO3_C5 TX=GPIO3_C4   (排针)
```

## 2. 调试串口 (UART2 + fiq-debugger)

　　rk3588-linux.dtsi (原厂文件,被公共层 include) 已定义好,
fiq-debugger 独占 UART2, uart2 节点保持 disabled (fiq_debugger
直接操作硬件,不走 8250 驱动):

```
#include "rk3588-linux.dtsi"    // 已包含以下节点,无需修改

/ {
	fiq_debugger: fiq-debugger {
		compatible = "rockchip,fiq-debugger";
		rockchip,serial-id = <2>;            // 绑定 UART2
		rockchip,wake-irq = <0>;
		rockchip,irq-mode-enable = <1>;      // 用 irq 而非 fiq
		rockchip,baudrate = <1500000>;       // 只支持 115200 和 1500000
		interrupts = <GIC_SPI 423 IRQ_TYPE_LEVEL_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&uart2m0_xfer>;         // RX=GPIO0_B6 TX=GPIO0_B5
		status = "okay";
	};
};
```

　　注意:
- 若串口调试脚不是 GPIO0_B5/B6, 改 pinctrl-0 引用对应 m0/m1/m2 组
- android 版 SDK 用 rk3588-android.dtsi, linux 版用 rk3588-linux.dtsi
- 不要同时使能 &uart2 和 fiq-debugger, 会冲突 (fiq-debugger 抢占)

## 3. 普通串口 (uart0/3/4/5)

　　普通串口只需两步: status + pinmux, dmas 基础 dtsi 已配置:

```
&uart0 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&uart0m2_xfer>;
};

&uart3 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&uart3m2_xfer>;
};

&uart4 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&uart4m0_xfer>;
};

&uart5 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&uart5m1_xfer>;
};
```

　　中断号/地址等均在 rk3588s.dtsi 中已定义, 只需使能。

## 4. 验证测试

```
# 查看已注册串口
cat /proc/tty/driver/serial
ls /dev/ttyS*

# 调试串口 (fiq-debugger 控制台, 波特率 1500000)
# 接上 USB 转 TTL (1.5M 波特率) 后输入回车, 应显示 fiq-debugger 提示符:
#   fiq_debugger> help
#   可用命令: help cpu ps bt regs allregs pc pcsr irqs
#             kmsg sysrq sleep nosleep console version

# 普通串口回环测试 (TX-RX 短接)
stty -F /dev/ttyS0 115200 raw -echo
cat /dev/ttyS0 &
echo "test" > /dev/ttyS0     # TX-RX 短接应收到 test
```
