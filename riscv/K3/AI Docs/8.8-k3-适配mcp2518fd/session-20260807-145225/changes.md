# 代码修改记录

- 工作目录: `/media/lhj/data/t-chip/7.code/spacemiT/K3_Linux_SDK_6.18/bsp-src/linux-6.18/arch/riscv/boot/dts/spacemit`
- 生成时间: 2026-08-07 14:52:26

## 修改概览 (git status)

```
 M Makefile
 M ../../../configs/firefly-linux.config
 M ../../../../../drivers/misc/Kconfig
 M ../../../../../drivers/misc/Makefile
?? can_test.sh
?? "k3-firefly-aibox-pro copy.dtsi"
?? k3-firefly-aibox-pro.dts
?? k3-firefly-aibox-pro.dtsi
?? session-20260807-145225/
?? "subject_\346\250\241\345\235\227\345\274\225\350\204\232\345\257\271\345\272\224\350\241\250.md"
?? ../../../../../drivers/misc/firefly-led.c
```

## 改动 (git diff HEAD)

```diff
diff --git a/arch/riscv/boot/dts/spacemit/Makefile b/arch/riscv/boot/dts/spacemit/Makefile
index c0f62f22d997..68bf48438210 100644
--- a/arch/riscv/boot/dts/spacemit/Makefile
+++ b/arch/riscv/boot/dts/spacemit/Makefile
@@ -12,3 +12,4 @@ dtb-$(CONFIG_SOC_SPACEMIT_K3) += k3-firefly-aibox-k3.dtb
 dtb-$(CONFIG_SOC_SPACEMIT_K3) += k3_com260_kit_v02.dtb
 dtb-$(CONFIG_SOC_SPACEMIT_K3) += k3_gemini_c0.dtb k3_gemini_c1.dtb
 dtb-$(CONFIG_SOC_SPACEMIT_K3) += k3_BS01DCMA.dtb
+dtb-$(CONFIG_SOC_SPACEMIT_K3) += k3-firefly-aibox-pro.dtb
diff --git a/arch/riscv/configs/firefly-linux.config b/arch/riscv/configs/firefly-linux.config
index 52719996b3e6..ed197a1b4950 100644
--- a/arch/riscv/configs/firefly-linux.config
+++ b/arch/riscv/configs/firefly-linux.config
@@ -46,3 +46,11 @@ CONFIG_KEYBOARD_GPIO=y
 CONFIG_POWER_RESET=y
 CONFIG_POWER_RESET_GPIO=y
 CONFIG_TYPEC_HUSB311=y
+CONFIG_FIREFLY_LED=y
+CONFIG_CAN=y
+CONFIG_CAN_RAW=y
+CONFIG_CAN_DEV=y
+CONFIG_SPI=y
+CONFIG_SPI_K1=y
+CONFIG_REGMAP_SPI=y
+CONFIG_CAN_MCP251XFD=y
diff --git a/drivers/misc/Kconfig b/drivers/misc/Kconfig
index e0f8f3772db5..10722f6d527f 100644
--- a/drivers/misc/Kconfig
+++ b/drivers/misc/Kconfig
@@ -659,6 +659,12 @@ config MCHP_LAN966X_PCI
 	    - lan966x-miim (MDIO_MSCC_MIIM)
 	    - lan966x-switch (LAN966X_SWITCH)
 
+config FIREFLY_LED
+	tristate "Firefly GPIO LED character driver"
+	depends on OF && GPIOLIB
+	help
+	  Character device driver for the Firefly GPIO LED.
+
 source "drivers/misc/c2port/Kconfig"
 source "drivers/misc/eeprom/Kconfig"
 source "drivers/misc/cb710/Kconfig"
diff --git a/drivers/misc/Makefile b/drivers/misc/Makefile
index cf10617e7eeb..379c69cc8691 100644
--- a/drivers/misc/Makefile
+++ b/drivers/misc/Makefile
@@ -77,3 +77,4 @@ obj-$(CONFIG_MCHP_LAN966X_PCI)	+= lan966x-pci.o
 obj-y				+= keba/
 obj-y				+= amd-sbi/
 obj-$(CONFIG_MISC_RP1)		+= rp1/
+obj-$(CONFIG_FIREFLY_LED)       += firefly-led.o
```
