# AIBOX-PRO-K3 厂测接入与执行指南

## 1. 文档目的

本文档说明如何在 `linux-qa` 工程中为自己的板子接入厂测，包括：

1. 确认板型名称。
2. 新建板级厂测 INI 和老化 INI。
3. 了解 INI 中的 section 如何匹配 `*.t` 测试脚本。
4. 不修改公共脚本，仅为自己的板子替换或新增测试脚本。
5. 构建 Linux-QA 测试包。
6. 制作首次部署卡和普通厂测卡。
7. 将测试包、INI 和自定义脚本部署到板端正确目录。
8. 通过显示终端、ADB、网络 ADB 或调试串口执行厂测。
9. 查看和判定厂测结果。

本文档以 `AIBOX-PRO-K3` 为实例，同样的方法也可用于其他新板型。

## 2. 厂测框架的核心调用链

厂测的核心链路如下：

```text
板型名称
  -> part/<MODEL>.Factory.ini 或 part/<MODEL>.ini
  -> 读取 [section] 的 activated 和 mod
  -> 生成测试组名
  -> 在工程根目录匹配 <mod>*.t
  -> 执行匹配到的全部 .t 脚本
  -> 汇总结果到 /userdata/FactoryTest/
```

对应的核心代码文件为：

```text
scripts/launch-factory-test.sh
lib/sharness.d/part-test.sh
lib/sharness.d/test-groups.sh
```

其中：

- `part-test.sh` 负责确定板型和导入 INI。
- `test-groups.sh` 负责将 INI section 转换为测试组，并匹配 `*.t`。
- `launch-factory-test.sh` 负责运行测试组、显示菜单和保存结果。

## 3. 确认板型名称

### 3.1 板型名称的获取顺序

框架按以下顺序获取板型：

1. `/etc/board_model`
2. `/sys/firmware/devicetree/base/model`
3. x86_64 调试环境使用 `pc`

在板端执行：

```sh
cat /etc/board_model 2>/dev/null
tr -d '\0' </sys/firmware/devicetree/base/model
```

对本板来说，框架最终获得的名称必须是：

```text
AIBOX-PRO-K3
```

如果识别出的名称不是 `AIBOX-PRO-K3`，则 `AIBOX-PRO-K3.ini` 不会被自动选中。应先修正固件的 `/etc/board_model` 或设备树 model，不要通过修改公共厂测脚本来规避板型错误。

### 3.2 INI 文件命名

源码中的板级文件：

```text
part/AIBOX-PRO-K3.ini
part/AIBOX-PRO-K3.aging.ini
```

用途：

| 文件 | 用途 |
| --- | --- |
| `AIBOX-PRO-K3.ini` | 普通功能厂测配置 |
| `AIBOX-PRO-K3.aging.ini` | 老化测试配置 |
| `AIBOX-PRO-K3.Factory.ini` | 厂测卡上使用的厂测优先配置 |

注意：

- 源码中保留 `AIBOX-PRO-K3.ini`。
- 制作厂测卡时，将它复制并改名为 `AIBOX-PRO-K3.Factory.ini`。
- 板端存在 Factory INI 时，Factory INI 优先于普通 INI。
- 板端不应同时保留多个包含同一 model 名称的 `*.Factory.ini`，否则框架会排序后选取最后一个，容易误选配置。

## 4. 新建板级 INI

### 4.1 建立基本结构

新增板型时，可先参考相同 SoC 或接口相近的板型 INI，然后创建：

```sh
cp part/K3.ini part/AIBOX-PRO-K3.ini
cp part/K3.aging.ini part/AIBOX-PRO-K3.aging.ini
```

之后只修改新建的板级 INI，不修改被参考的公共板型文件。

厂测 section 的基本格式：

```ini
[usb]
activated=1
usb3_port_list="2-1.3 2-1.4"
usb3_location_list="USB3-A USB3-B"
usb3_min_read_mbps=90
usb3_min_write_mbps=30
```

`activated` 含义：

```text
activated=1  启用该测试组
activated=0  不将该测试组加入厂测菜单
```

### 4.2 section 名称和变量前缀

INI 导入后，变量名由以下两部分组成：

```text
<section>_<key>
```

例如：

```ini
[usb]
usb3_port_list="2-1.3 2-1.4"
```

脚本中使用：

```sh
$usb_usb3_port_list
```

再如：

```ini
[aibox_pro_k3_ai]
model_path="data/model/K3"
```

脚本中使用：

```sh
$aibox_pro_k3_ai_model_path
```

section 名称决定参数变量前缀；`mod` 只决定匹配哪些测试脚本。

## 5. INI 如何匹配 `.t` 脚本

### 5.1 没有 `mod` 时

如果 section 没有配置 `mod`，框架使用 section 名作为脚本前缀。

```ini
[usb]
activated=1
```

匹配：

```text
usb*.t
```

当前工程中实际匹配：

```text
usb-001-check-port-devices-and-rw-speed.t
```

### 5.2 有 `mod` 时

如果 section 配置了 `mod`，框架使用 `mod` 值作为脚本前缀。

```ini
[wdt]
activated=1
mod=aibox-3576-wdt-check
```

匹配：

```text
aibox-3576-wdt-check*.t
```

当前工程中实际匹配：

```text
aibox-3576-wdt-check.t
```

### 5.3 一个测试组可以匹配多个 `.t`

例如：

```ini
[wifi]
activated=1
```

会匹配所有 `wifi*.t`：

```text
wifi-001-scanning.t
wifi-002-check-freq.t
wifi-003-24g-iperf3-ping.t
```

一个测试组只有在所有被匹配的 `.t` 都通过时才会判定成功。

### 5.4 AIBOX-PRO-K3 当前匹配关系

| section | `mod` | 匹配的脚本前缀 |
| --- | --- | --- |
| `sd` | 未设置 | `sd*.t` |
| `led` | 未设置 | `led*.t` |
| `key` | 未设置 | `key*.t` |
| `wdt` | `aibox-3576-wdt-check` | `aibox-3576-wdt-check*.t` |
| `fan` | `rockchip-misc-fan` | `rockchip-misc-fan*.t` |
| `usb` | 未设置 | `usb*.t` |
| `modem` | 未设置 | `modem*.t` |
| `wifi` | 未设置 | `wifi*.t` |
| `wifi_5g` | `5g-wifi` | `5g-wifi*.t` |
| `dp` | `rockchip-dp` | `rockchip-dp*.t` |

## 6. 新增板级 `.t` 脚本

### 6.1 存放目录

源码中的厂测 `.t` 脚本放在：

```text
test_proj/
```

例如：

```text
test_proj/aibox-pro-k3-usb-001-check.t
```

构建时，`build.sh` 会将 `test_proj/*` 复制到板端测试工程根目录。板端最终路径是：

```text
/var/cache/firefly/proj/aibox-pro-k3-usb-001-check.t
```

`.t` 脚本不要放在 `part/` 中。

### 6.2 脚本命名

推荐使用板型独有前缀：

```text
aibox-pro-k3-<module>-<number>-<description>.t
```

例如：

```text
aibox-pro-k3-usb-001-check.t
aibox-pro-k3-fan-001-check.t
aibox-pro-k3-wifi-001-connect.t
aibox-pro-k3-wifi-002-iperf3.t
```

不要给板级专用脚本使用 `usb-`、`wifi-` 或 `fan-` 这类公共前缀，否则其他板型也可能匹配到它。

### 6.3 基本脚本模板

```sh
#!/bin/sh

test_description="AIBOX-PRO-K3 USB 测试"

. lib/sharness.sh

error_if_undefined \
    usb_usb3_port_list \
    usb_usb3_location_list

test_expect_success "检查 AIBOX-PRO-K3 USB 配置" '
    test -n "$usb_usb3_port_list" &&
    test -n "$usb_usb3_location_list"
'

test_done
```

添加执行权限：

```sh
chmod +x test_proj/aibox-pro-k3-usb-001-check.t
```

否则厂测框架使用 `./<script>.t` 运行时会报权限错误。

## 7. 不修改公共脚本，为自己的板子替换测试

### 7.1 只修改参数时

如果公共脚本的逻辑可用，只是设备节点、端口、阈值或延时不同，只修改自己的 INI：

```ini
[usb]
activated=1
usb3_port_list="2-1.3 2-1.4"
usb3_min_read_mbps=90
startup_delay=5
```

这是优先选择，因为不需要复制公共测试逻辑。

### 7.2 使用工程中已有的另一个脚本

如果工程中已经存在适合本板的其他脚本，可以只在自己的 INI 中改 `mod`：

```ini
[fan]
activated=1
mod=rockchip-misc-m2-fan
```

这会使 `[fan]` 匹配：

```text
rockchip-misc-m2-fan*.t
```

### 7.3 使用自己的板级脚本替换公共脚本

以 USB 为例，原配置为：

```ini
[usb]
activated=1
```

它会匹配公共的 `usb*.t`。

要仅为 AIBOX-PRO-K3 替换 USB 测试，改为：

```ini
[usb]
activated=1
mod=aibox-pro-k3-usb

usb3_port_list="2-1.3 2-1.4"
usb3_location_list="USB3-A USB3-B"
usb3_min_read_mbps=90
```

然后新增：

```text
test_proj/aibox-pro-k3-usb-001-check.t
```

此时框架只匹配：

```text
aibox-pro-k3-usb*.t
```

不再匹配公共的 `usb*.t`。

此方法没有修改或覆盖任何原脚本，其他板型仍然使用原有 USB 测试。

### 7.4 替换 Wi-Fi 这类包含多个 `.t` 的测试组

原 `[wifi]` 会匹配多个 `wifi*.t`。将 `mod` 改为板级前缀后，原来的全部 `wifi*.t` 都不再执行。

因此要在板级前缀下提供所有需要的脚本：

```ini
[wifi]
activated=1
mod=aibox-pro-k3-wifi
```

```text
test_proj/aibox-pro-k3-wifi-001-scan.t
test_proj/aibox-pro-k3-wifi-002-check-freq.t
test_proj/aibox-pro-k3-wifi-003-iperf3.t
```

不能只添加一个不完整的替换脚本，同时误以为公共脚本还会自动运行。

### 7.5 新增独立测试项

如果不是替换现有项目，而是新增板子专用项目，可增加新 section：

```ini
[aibox_pro_k3_ai]
activated=1
mod=aibox-pro-k3-ai
model_path="data/model/K3"
loop=10
```

对应：

```text
test_proj/aibox-pro-k3-ai-001-check.t
```

脚本中使用：

```sh
$aibox_pro_k3_ai_model_path
$aibox_pro_k3_ai_loop
```

### 7.6 板级厂测初始化脚本

框架在厂测开始前会尝试运行：

```text
factory_<MODEL>_init.sh
```

对 AIBOX-PRO-K3，可新增：

```text
test_proj/factory_AIBOX-PRO-K3_init.sh
```

并赋予执行权限：

```sh
chmod +x test_proj/factory_AIBOX-PRO-K3_init.sh
```

该脚本适合用于：

- 加载板级专用内核模块。
- 设置板级 GPIO 或接口模式。
- 启动本板才有的依赖服务。
- 准备测试临时目录。
- 在所有 `.t` 之前执行板级环境检查。

不要在该初始化脚本中修改公共 `.t` 文件。

## 8. 老化 INI 的匹配方式

老化测试不是通过 `.t` 运行，而是通过 `aging_*.sh` 运行。

例如：

```ini
[aging_npu]
activated=1
mod=spacemit_npu
```

会运行：

```text
aging_spacemit_npu.sh
```

源码中应存放在：

```text
test_proj/aging_spacemit_npu.sh
```

厂测的 `.t` 匹配和老化的 `aging_*.sh` 匹配是两套不同逻辑，不要混用。

## 9. 构建测试包

### 9.1 构建前检查

确认文件存在：

```sh
ls -l part/AIBOX-PRO-K3.ini
ls -l part/AIBOX-PRO-K3.aging.ini
find test_proj -maxdepth 1 -name 'aibox-pro-k3-*.t' -ls
```

检查脚本语法：

```sh
for script in test_proj/aibox-pro-k3-*.t; do
    [ -e "$script" ] || continue
    sh -n "$script" || exit 1
done
```

### 9.2 执行构建

```sh
cd /media/lhj/data/t-chip/7.code/linux-qa
./build.sh local
```

`local` 表示使用：

```text
part/local.ini
```

其中包含 Wi-Fi SSID、密码、iperf3 服务器和串口等环境参数。量产前必须按工厂环境核对这些参数。

构建输出位于：

```text
out/linuxqa_<date>_<commit>.tar.gz
out/firefly-test.sh
out/rc.local
out/install.sh
out/firefly-recovery.sh
```

### 9.3 检查自定义脚本是否进入包

```sh
tar -tzf out/linuxqa_*.tar.gz | grep 'proj.tar.gz'
```

外层包中的实际工程是 `proj.tar.gz`。可解包到临时目录进一步检查：

```sh
CHECK_DIR=$(mktemp -d)
tar -xzf out/linuxqa_*.tar.gz -C "$CHECK_DIR"
tar -tzf "$CHECK_DIR/proj.tar.gz" | grep -E 'AIBOX-PRO-K3|aibox-pro-k3'
```

## 10. 厂测卡的制作

### 10.1 首次部署卡

如果板端还没有 `/var/cache/firefly/proj/`，或者没有安装 `firefly-test.sh`，需要准备完整部署卡。

建议卡根目录放置：

```text
linuxqa_<date>_<commit>.tar.gz
firefly-test.sh
rc.local
install.sh
local.ini
AIBOX-PRO-K3.Factory.ini
```

在主机上准备 Factory INI：

```sh
cp part/AIBOX-PRO-K3.ini /path/to/sdcard/AIBOX-PRO-K3.Factory.ini
cp part/local.ini /path/to/sdcard/local.ini
cp out/linuxqa_*.tar.gz /path/to/sdcard/
cp out/firefly-test.sh out/rc.local out/install.sh /path/to/sdcard/
sync
```

首次部署时需要将启动钩子安装到板端。可以在板端登录后，进入 SD 卡挂载目录执行：

```sh
sudo ./install.sh
```

也可通过 ADB 手动部署，见第 12 章。

### 10.2 普通厂测卡

如果板端已经安装 Linux-QA 和开机启动钩子，普通厂测卡根目录只需：

```text
local.ini
AIBOX-PRO-K3.Factory.ini
```

插卡重启后，`firefly-test.sh` 会：

1. 挂载 SD 卡。
2. 将卡根目录下的 INI 复制到 `/var/cache/firefly/`。
3. `start.sh` 将 INI 移动到 `/var/cache/firefly/proj/part/`。
4. 删除旧的 `*.Factory.ini`。
5. 检测到新 Factory INI 后创建 `factory_test.mark`。
6. 进入厂测流程。

### 10.3 老化 INI 是否需要放在卡根目录

`AIBOX-PRO-K3.aging.ini` 已经通过 `build.sh` 打进 Linux-QA 包的 `part/` 目录，通常不需要再单独放在厂测卡根目录。

只有需要使用卡上的新老化配置覆盖板端包内配置时，才需要把它也放到卡根目录。

## 11. 板端目录和文件对应关系

| 内容 | 主机源码位置 | 板端位置 |
| --- | --- | --- |
| 厂测工程 | `out/linuxqa_*.tar.gz` | `/var/cache/firefly/proj/` |
| 普通板级 INI | `part/AIBOX-PRO-K3.ini` | `/var/cache/firefly/proj/part/AIBOX-PRO-K3.ini` |
| Factory INI | `part/AIBOX-PRO-K3.ini` 改名 | `/var/cache/firefly/proj/part/AIBOX-PRO-K3.Factory.ini` |
| 老化 INI | `part/AIBOX-PRO-K3.aging.ini` | `/var/cache/firefly/proj/part/AIBOX-PRO-K3.aging.ini` |
| 环境 INI | `part/local.ini` | `/var/cache/firefly/proj/env.ini` 或 `/var/cache/firefly/proj/part/local.ini` |
| 公共和板级 `.t` | `test_proj/*.t` | `/var/cache/firefly/proj/*.t` |
| 板级初始化 | `test_proj/factory_AIBOX-PRO-K3_init.sh` | `/var/cache/firefly/proj/factory_AIBOX-PRO-K3_init.sh` |
| 厂测启动标志 | 无 | `/var/cache/firefly/proj/factory_test.mark` |
| 老化启动标志 | 无 | `/var/cache/firefly/proj/aging_test.mark` |
| 厂测结果 | 无 | `/userdata/FactoryTest/` |
| 老化结果 | 无 | `/userdata/AgingTest/` |

构建包中的 `local.ini` 通过符号链接作为 `env.ini` 导入。单独更新板端环境参数时，应确认：

```sh
ls -l /var/cache/firefly/proj/env.ini
```

如果 `env.ini` 仍指向旧配置，应同步更新它，而不是只在 `part/` 中放一份未被导入的 `local.ini`。

## 12. 通过 ADB 手动部署

### 12.1 首次部署完整工程

```sh
BOARD=172.16.11.41:5555
PKG=$(ls out/linuxqa_*.tar.gz | head -n 1)

adb connect "$BOARD"
adb -s "$BOARD" shell 'mkdir -p /var/cache/firefly'
adb -s "$BOARD" push "$PKG" /var/cache/firefly/linuxqa.tar.gz
adb -s "$BOARD" shell 'tar -xzf /var/cache/firefly/linuxqa.tar.gz -C /var/cache/firefly'
adb -s "$BOARD" shell 'tar -xzf /var/cache/firefly/proj.tar.gz -C /var/cache/firefly'
```

安装开机入口：

```sh
adb -s "$BOARD" push out/firefly-test.sh /usr/local/bin/firefly-test.sh
adb -s "$BOARD" shell 'chmod 755 /usr/local/bin/firefly-test.sh'
```

确认 `/etc/rc.local` 在开机时调用 `firefly-test.sh`：

```sh
adb -s "$BOARD" shell 'grep -n "firefly-test.sh" /etc/rc.local'
```

如果固件没有该启动钩子，需要由固件或工厂安装流程补充。

### 12.2 更新 Factory INI

先清理旧 Factory INI：

```sh
adb -s "$BOARD" shell \
  'rm -f /var/cache/firefly/proj/part/*AIBOX-PRO-K3*.Factory.ini'
```

推送新配置：

```sh
adb -s "$BOARD" push part/AIBOX-PRO-K3.ini \
  /var/cache/firefly/proj/part/AIBOX-PRO-K3.Factory.ini

adb -s "$BOARD" push part/AIBOX-PRO-K3.aging.ini \
  /var/cache/firefly/proj/part/AIBOX-PRO-K3.aging.ini
```

如果需要更新环境配置：

```sh
adb -s "$BOARD" push part/local.ini /var/cache/firefly/proj/local.ini
adb -s "$BOARD" shell \
  'cd /var/cache/firefly/proj && ln -sfn local.ini env.ini'
```

### 12.3 仅更新板级 `.t` 脚本

调试阶段不必每次重新部署整个包，可以只推送板级脚本：

```sh
adb -s "$BOARD" push test_proj/aibox-pro-k3-usb-001-check.t \
  /var/cache/firefly/proj/aibox-pro-k3-usb-001-check.t

adb -s "$BOARD" shell \
  'chmod 755 /var/cache/firefly/proj/aibox-pro-k3-usb-001-check.t'
```

这种方式只能覆盖或更新自己的 `aibox-pro-k3-*` 脚本，不应覆盖公共脚本。

## 13. 执行厂测

### 13.1 自动插卡启动

前提：

- `/usr/local/bin/firefly-test.sh` 已安装。
- `/etc/rc.local` 或等价服务会启动它。
- 厂测卡根目录有 `AIBOX-PRO-K3.Factory.ini`。
- 没有多余的 Factory INI。

步骤：

1. 连接 DP 显示器、USB 测试盘、SD 卡、Wi-Fi 天线和 4G/5G 模组。
2. 插入厂测卡。
3. 上电或重启。
4. `firefly-test.sh` 更新配置并创建 `factory_test.mark`。
5. 系统进入厂测菜单。
6. 直接回车执行全部已激活项目。

### 13.2 通过 USB ADB 执行

```sh
adb shell -t 'cd /var/cache/firefly/proj && ./launch-factory-test.sh'
```

如果需要让 `startup.sh` 通过 mark 选择厂测：

```sh
adb shell 'touch /var/cache/firefly/proj/factory_test.mark'
adb shell -t 'cd /var/cache/firefly/proj && ./startup.sh'
```

启动优先级为：

```text
reboot_count.mark
  > stress_reboot_test.mark
  > factory_test.mark
  > aging_test.mark
```

如果存在更高优先级的 mark，`startup.sh` 不会进入厂测。

### 13.3 通过网络 ADB 执行

```sh
BOARD=172.16.11.41:5555

adb connect "$BOARD"
adb -s "$BOARD" shell \
  'touch /var/cache/firefly/proj/factory_test.mark'
adb -s "$BOARD" shell -t \
  'cd /var/cache/firefly/proj && ./network-launch-factory-test.sh'
```

网络 ADB 方式更适合无显示器但网络已经正常的板子。

### 13.4 厂测菜单命令

| 输入 | 功能 |
| --- | --- |
| 直接回车 | 重测全部项目 |
| `-` | 只重测失败项 |
| `N` | 只测试第 N 个测试组 |
| `N*` | 显示第 N 个测试组的日志 |
| `*` | 显示测试汇总 |
| `0` | 显示帮助 |
| `**` | 进入调试 Shell |
| `/` | 退出厂测 |
| `--` | 切换到老化模式，操作前需确认 |

菜单编号由 INI 中 `activated=1` section 的出现顺序决定。修改 INI 后不要继续使用旧文档中的固定编号，应以当前厂测菜单为准。

## 14. 无显示屏时使用串口终端厂测

### 14.1 串口方式的适用范围

无显示屏时，推荐通过板子调试 UART 登录 Shell，然后在当前串口终端直接执行厂测入口。

要区分：

- 调试串口：用于登录系统和显示厂测菜单。
- INI 中的 `[rs485]`、`[serial]` 等功能测试串口：用于测试板上功能接口。

两者不是同一个概念。

### 14.2 确认调试串口参数

根据固件和原理图确认：

```text
串口设备：例如 ttyFIQ0、ttyS0 或 ttyS1
波特率：例如 115200 或 1500000
数据位：8
停止位：1
校验：None
流控：None
```

可在板端检查：

```sh
cat /proc/cmdline
systemctl list-units 'serial-getty@*' 'getty@*'
ls -l /dev/ttyFIQ* /dev/ttyS* 2>/dev/null
```

AIBOX-PRO-K3 当前老化 INI 中使用 `ttyFIQ0` 和 `1500000`，但厂测调试串口仍必须以当前固件实际 console/getty 配置为准，不能仅根据老化 INI 推断。

### 14.3 推荐：从串口登录后手动启动

主机上可使用 `minicom`、`picocom` 或 `screen`。例如：

```sh
sudo picocom -b <BAUD> /dev/ttyUSB0
```

登录板端后：

```sh
cd /var/cache/firefly/proj

ls -l part/AIBOX-PRO-K3.Factory.ini
cat /etc/board_model 2>/dev/null

./launch-factory-test.sh
```

这种方式不需要开启 `local.ini` 的 `[serial_console]`。因为厂测程序是从当前串口 Shell 启动的，标准输入输出已经在该串口上。

如果上次结果存在，界面会先显示上次汇总。可直接回车重测全部项目，或者在调试阶段先清理：

```sh
rm -rf /var/cache/firefly/proj/test-results
```

### 14.4 由其他入口启动，但将菜单重定向到专用串口

框架支持在环境 INI 中配置：

```ini
[serial_console]
enabled=1
dev=<DEBUG_TTY>
baud=<BAUD>
```

例如，只有在实机已确认为 `ttyFIQ0/1500000` 时才配置：

```ini
[serial_console]
enabled=1
dev=ttyFIQ0
baud=1500000
```

此时，从 ADB、启动服务或其他终端启动 `launch-factory-test.sh` 后，程序会将标准输入输出重定向到 `/dev/<DEBUG_TTY>`。

使用该模式前必须确认：

- 设备节点和波特率正确。
- 该 UART 没有被其他测试脚本同时使用。
- getty、内核 console 输出和厂测菜单不会相互抢占输入。
- `env.ini` 已经指向开启了 `serial_console` 的环境 INI。

如果操作员已经从该调试串口登录，通常应使用第 14.3 节的手动启动方式，保持 `serial_console.enabled=0`，避免重复打开和重定向同一个 UART。

### 14.5 无显示屏时的测试项调整

串口终端只解决厂测菜单的显示和交互问题，不会使需要显示器的测试自动通过。

如果本次生产流程确实不连接 DP 显示器，应在本板 Factory INI 中关闭显示测试：

```ini
[dp]
activated=0
```

如果要测试 DP 接口，即使菜单通过串口操作，也仍然需要连接 DP 显示器和音频设备，再在串口界面中人工确认画面和声音。

## 15. 无显示屏时避免图形启动流程阻塞

`start.sh` 中包含等待桌面和 DRM 显示器的逻辑。完全无显示设备的产线环境不应仅依赖图形终端自动弹出。

推荐流程：

1. 使用厂测卡完成工程和 INI 部署。
2. 通过调试串口登录板端。
3. 直接进入 `/var/cache/firefly/proj/`。
4. 直接运行 `./launch-factory-test.sh`。

这条路径绕过了 `start.sh` 中的桌面终端创建逻辑，但仍然使用原有厂测框架、INI 加载、`.t` 匹配和结果汇总逻辑。

## 16. 厂测前检查清单

在每个批次开测前执行或人工确认：

```sh
cd /var/cache/firefly/proj

cat /etc/board_model 2>/dev/null
ls -l part/AIBOX-PRO-K3*.ini
ls -l env.ini
find . -maxdepth 1 -name 'aibox-pro-k3-*.t' -ls
```

检查硬件枚举：

```sh
lsblk -o NAME,SIZE,MODEL,TRAN
lsusb -t
ip -br link
iw dev
ls -l /dev/ttyUSB*
ls -l /dev/input/by-path/
ls /sys/class/drm/
aplay -l
readlink -f /sys/class/hwmon/hwmon*/device
```

检查网络服务：

```sh
ping -c 1 <IPERF3_SERVER>
```

检查 Factory INI 是否优先加载：

```sh
cd /var/cache/firefly/proj
./launch-factory-test.sh
```

界面顶部 `TESTFILE` 应显示：

```text
AIBOX-PRO-K3.Factory.ini
```

如果显示 `AIBOX-PRO-K3.ini` 或其他文件，应先处理 Factory INI 命名或多文件冲突，不要继续批量厂测。

## 17. 查看厂测结果

厂测结果目录：

```text
/userdata/FactoryTest/
```

主要文件：

```text
/userdata/FactoryTest/factoryTest_result.txt
/userdata/FactoryTest/factoryTest_details.txt
/userdata/FactoryTest/factory_details.tar.gz
```

查看汇总：

```sh
cat /userdata/FactoryTest/factoryTest_result.txt
```

通过 ADB 拉取：

```sh
adb -s "$BOARD" pull /userdata/FactoryTest ./FactoryTest
```

整机合格的最低判定条件：

```text
失败项目: 0
厂测结果: 成功
```

同时必须确认 LED、按键、风扇、显示和声音等人工交互项目已按实际硬件状态判定，不能仅根据最终文本汇总替代人工检查。

## 18. 常见问题

### 18.1 提示找不到 INI

检查：

```sh
cat /etc/board_model
ls -l /var/cache/firefly/proj/part/
```

板型名、文件名和大小写必须一致。

### 18.2 新 `.t` 没有执行

检查：

1. 对应 section 是否 `activated=1`。
2. `mod` 是否与 `.t` 文件前缀一致。
3. `.t` 是否位于 `/var/cache/firefly/proj/`。
4. `.t` 是否有执行权限。
5. 是否实际加载了新 Factory INI。

```sh
ls -l /var/cache/firefly/proj/aibox-pro-k3-*.t
```

### 18.3 同一组多执行了其他脚本

原因通常是 `mod` 前缀过短。例如 `mod=usb` 会匹配所有 `usb*.t`。

板级替换应使用：

```ini
mod=aibox-pro-k3-usb
```

### 18.4 插卡重启后没有自动进入厂测

检查：

```sh
ls -l /usr/local/bin/firefly-test.sh
grep -n firefly-test /etc/rc.local
ls -l /var/cache/firefly/proj/factory_test.mark
ls -l /var/cache/firefly/proj/part/*Factory.ini
```

首次仅把文件放到 SD 卡上，但板端没有安装 `firefly-test.sh` 开机钩子时，系统不会自动执行厂测卡内容。

### 18.5 无显示屏时卡在等待桌面或 DRM

通过调试串口登录后直接执行：

```sh
cd /var/cache/firefly/proj
./launch-factory-test.sh
```

不要继续等待图形终端自动出现。

### 18.6 厂测显示上次结果

这表示 `/var/cache/firefly/proj/test-results/` 存在。可以在菜单中直接回车重测，调试阶段也可先清理：

```sh
rm -rf /var/cache/firefly/proj/test-results
```

## 19. 推荐的板级定制结构

```text
part/
  AIBOX-PRO-K3.ini
  AIBOX-PRO-K3.aging.ini

test_proj/
  factory_AIBOX-PRO-K3_init.sh
  aibox-pro-k3-usb-001-check.t
  aibox-pro-k3-fan-001-check.t
  aibox-pro-k3-wifi-001-scan.t
  aibox-pro-k3-wifi-002-iperf3.t
```

定制原则：

1. 参数差异放在自己的 INI。
2. 逻辑差异使用独立 `mod` 和板级 `.t`。
3. 板级脚本使用 `aibox-pro-k3-` 独有前缀。
4. 不覆盖、不重命名、不修改公共 `.t`。
5. 不修改 `launch-factory-test.sh`、`part-test.sh` 和 `test-groups.sh`。
6. 构建后检查包内文件，部署后检查板端文件和执行权限。
7. 以厂测界面显示的 `TESTFILE` 和当前菜单顺序为准。

## 20. AIBOX-PRO-K3 快速执行摘要

```sh
# 1. 构建
cd /media/lhj/data/t-chip/7.code/linux-qa
./build.sh local

# 2. 连接板子
BOARD=172.16.11.41:5555
adb connect "$BOARD"

# 3. 更新 Factory INI
adb -s "$BOARD" shell \
  'rm -f /var/cache/firefly/proj/part/*AIBOX-PRO-K3*.Factory.ini'
adb -s "$BOARD" push part/AIBOX-PRO-K3.ini \
  /var/cache/firefly/proj/part/AIBOX-PRO-K3.Factory.ini

# 4. 启动网络 ADB 厂测
adb -s "$BOARD" shell -t \
  'cd /var/cache/firefly/proj && ./network-launch-factory-test.sh'

# 5. 查看结果
adb -s "$BOARD" shell \
  'cat /userdata/FactoryTest/factoryTest_result.txt'
```

无显示屏且使用调试串口时：

```sh
cd /var/cache/firefly/proj
./launch-factory-test.sh
```

进入菜单后直接回车运行全部已激活项目，最终以 `/userdata/FactoryTest/factoryTest_result.txt` 和人工交互项的实际确认结果为准。
