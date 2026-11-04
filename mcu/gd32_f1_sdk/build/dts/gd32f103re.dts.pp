# 0 "boards/gd32f103re/gd32f103re.dts"
# 0 "<built-in>"
# 0 "<command-line>"
# 1 "boards/gd32f103re/gd32f103re.dts"
/dts-v1/;

# 1 "./dts/gd32f103re.dtsi" 1
# 9 "./dts/gd32f103re.dtsi"
# 1 "./dts/include/dt-bindings/gpio/gd32f10x-gpio.h" 1
# 10 "./dts/gd32f103re.dtsi" 2

/ {
 #address-cells = <1>;
 #size-cells = <1>;

 soc {
  compatible = "gd,gd32f103";
  #address-cells = <1>;
  #size-cells = <1>;



  systick: systick@e000e010 {
   compatible = "gd,cortex-m-systick";
   reg = <0xe000e010 0x10>;
   clock-frequency = <108000000>;
  };

  gpioa: gpio@40010800 {
   compatible = "gd,gd32-gpio";
   reg = <0x40010800 0x400>;
   port-idx = <0>;
   #gpio-cells = <2>;
   gpio-controller;
  };

  gpiob: gpio@40010c00 {
   compatible = "gd,gd32-gpio";
   reg = <0x40010C00 0x400>;
   port-idx = <1>;
   #gpio-cells = <2>;
   gpio-controller;
  };

  gpioc: gpio@40011000 {
   compatible = "gd,gd32-gpio";
   reg = <0x40011000 0x400>;
   port-idx = <2>;
   #gpio-cells = <2>;
   gpio-controller;
  };

  gpiod: gpio@40011400 {
   compatible = "gd,gd32-gpio";
   reg = <0x40011400 0x400>;
   port-idx = <3>;
   #gpio-cells = <2>;
   gpio-controller;
  };

  gpioe: gpio@40011800 {
   compatible = "gd,gd32-gpio";
   reg = <0x40011800 0x400>;
   port-idx = <4>;
   #gpio-cells = <2>;
   gpio-controller;
  };
 };
};
# 4 "boards/gd32f103re/gd32f103re.dts" 2

/ {
 model = "GD32F103RE generic board";
 compatible = "gd,gd32f103re-generic";

 leds {
  compatible = "gd,gpio-leds";
  status = "okay";
  count = <3>;

  led1 {
   gpios = <&gpioc 13 0x10>;
   init-level = <1>;
  };

  led2 {
   gpios = <&gpioc 9 0x10>;
   init-level = <1>;
  };

  led3 {
   gpios = <&gpioc 8 0x10>;
   init-level = <1>;
  };
 };

 keys {
  compatible = "gd,gpio-keys";
  status = "okay";
  count = <4>;

  key1 {
   gpios = <&gpioa 7 0x48>;
   active-level = <0>;
  };

  key2 {
   gpios = <&gpioc 4 0x48>;
   active-level = <0>;
  };

  key3 {
   gpios = <&gpioc 5 0x48>;
   active-level = <0>;
  };

  key4 {
   gpios = <&gpioa 0 0x28>;
   active-level = <1>;
  };
 };

 matrix-keys {
  compatible = "gd,gpio-matrix-keys";
  status = "okay";
  row-count = <4>;
  col-count = <3>;

  row-gpios = <&gpioc 0 0x10>,
       <&gpioc 1 0x10>,
       <&gpioc 2 0x10>,
       <&gpioc 3 0x10>;

  col-gpios = <&gpioa 4 0x48>,
       <&gpioa 5 0x48>,
       <&gpioa 6 0x48>;
 };
};
