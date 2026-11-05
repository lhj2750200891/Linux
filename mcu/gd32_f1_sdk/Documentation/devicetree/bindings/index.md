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
- GPIO 引用格式: `<&gpio端口 引脚号 模式>`, 模式取
  `dts/include/dt-bindings/gpio/gd32f10x-gpio.h`
- 个数类属性 (`count` / `row-count` / `col-count`) 必须与实际
  子节点/引脚列表一致, 脚本校验不符报错
