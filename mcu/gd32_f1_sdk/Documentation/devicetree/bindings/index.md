# 设备树绑定文档索引

按 Linux 内核 `Documentation/devicetree/bindings/` 框架组织。
每份 `.yaml` 描述一类节点的属性、约束与示例; 解释器为
`scripts/gen_devicetree.py` (编译期生成 C 实例表)。

| 绑定 | 节点 | 驱动 |
|---|---|---|
| [serial/gd,gd32-uart](serial/gd,gd32-uart.yaml) | `uarts` 容器 + periph/pingroup (SoC) | `drivers/uart/` |
| [leds/gd,gpio-leds](leds/gd,gpio-leds.yaml) | `leds` 容器 | `drivers/led/` |
| [input/gd,gpio-keys](input/gd,gpio-keys.yaml) | `keys` 容器 | `drivers/key/` |
| [input/gd,gpio-matrix-keys](input/gd,gpio-matrix-keys.yaml) | `matrix-keys` 容器 | `drivers/matrix_key/` |
| [timer/gd,cortex-m-systick](timer/gd,cortex-m-systick.yaml) | `systick` (SoC) | `drivers/systick/` |

通用约定:
- `status = "disabled"`: 不生成实例表, 驱动 API 退化为空实现
  (是否参与编译由 Kconfig `CONFIG_DRIVER_xxx` 裁剪, 两层独立)
- `status` 支持两级: 容器节点 (uarts/leds/...) 整类开关;
  实例子节点 (uart1/led1/key1/btim1/gtim1...) 单个实例开关 ——
  disabled 实例不进实例表, 其 `DT_xxxn_IDX` 宏仍生成 (哨兵值 0xFF),
  驱动 API 收到哨兵下标安全空操作, 应用代码无需修改;
  timer 通道子节点 (chN) 同样支持
- GPIO 引用格式: `<&gpio端口 引脚号 模式>`, 模式取
  `arm/include/dt-bindings/gpio/gd32f10x-gpio.h`
- 串口数据位/停止位/校验/中断模式取
  `arm/include/dt-bindings/serial/gd32f10x-uart.h`
  (UART 引脚组在型号级 dtsi `arm/core/gd32f103xx.dtsi` 中预定义,
  板级也可用 tx-gpios/rx-gpios 手动组合)
- 个数类属性 (`count` / `row-count` / `col-count`): 可选, 缺省按启用
  (status != "disabled") 的子节点/引脚个数自动计数; 显式写出时脚本
  校验须与启用个数一致, 不符报错
