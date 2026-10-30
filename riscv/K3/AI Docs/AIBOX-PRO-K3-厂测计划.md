# AIBOX-PRO-K3 厂测计划

## 1. 适用范围

- 机型：AIBOX-PRO-K3
- 配置文件：`part/AIBOX-PRO-K3.ini`（本版只开启用户指定的测试模块）
- 硬件依据：`k3-firefly-aibox-pro.dts` 和 `k3-firefly-aibox-pro.dtsi`
- 目的：检查生产装配、器件焊接、外部接口及主要 SoC 功能。

## 2. 测试环境和治具

1. 刷入待量产的系统镜像和与之匹配的设备树。
2. 准备 2 个 USB 3.0 测速 U 盘和 UHS SD 卡，两个 USB 口各插 1 只 U 盘；连接 DP 显示器及其音频设备。
3. 准备一个千兆网口对端，当前使用 Ubuntu `172.16.10.143`。
4. 准备 2.4 GHz/5 GHz AP、已插 SIM 卡的 USB 4G/5G 模组和天线。
5. U 盘容量必须大于当前 `fio_size`（`part/local.ini` 当前为 10G）。当前 USB 项只执行直接读取测速，不执行整盘写入。

## 3. 首件枚举确认

设备树能确认控制器和功能已启用，但 Linux 设备名称由驱动、内核和 rootfs 共同决定。批量开测前在首件上执行：

```sh
lsblk -o NAME,SIZE,MODEL,TRAN
lspci -Dnn
lspci -Dtv
ip -br link
iw dev
ls -l /dev/ttyUSB*
ls -l /dev/ttyS* /dev/input/by-path/
ls /sys/class/drm/
aplay -l
lsusb -t
readlink -f /sys/class/hwmon/hwmon*/device
```

根据实机 ADB 读取的当前值，本版预置为 `eth0`、`wlan0`、`ttyUSB2`、`mmcblk0`、USB 端口 `2-1.3/2-1.4` 和 `/sys/class/hwmon/hwmon7/pwm1`。两只 U 盘分别识别为 `/dev/sdb` 和 `/dev/sdc`，两路均为 SuperSpeed `5000M`。DP 实机节点为 `card1-DP-1`，状态为 `connected`，声卡为 `snddp1`。

本版关闭 CPU、RTC、DDR、UFS、PCIe 存储、蓝牙、NPU、HDMI/VPU、RS485、CAN、隔离 GPIO 等未指定项；DP 和看门狗已开启。

本次实际执行的测试项为：单网口、Wi-Fi、USB 4G 模组、风扇、3 个 LED、Power/Boot 键、SD 卡、两个 USB 存储口、DP 和看门狗。

PCIe 首件必须保存 `lspci -Dtv` 结果，建立下表的 PCI domain/BDF 与物理接口映射。若产线固定插入 3 个 NVMe 测试端点，`expected_nvme_count=3` 会防止缺任意一路时误判通过。

| PCIe 位置 | 设备树路径 | 链路 | 厂测覆盖 |
| --- | --- | --- | --- |
| PCIe 接口 1 | `pcie0_rc` | x4 | 插 NVMe/标准端点，检查枚举和性能 |
| PCIe 接口 2 | `pcie4_rc` | x1 | 插 NVMe/标准端点，检查枚举和性能 |
| PCIe 接口 3 | `pcie3_rc -> ASM1182e -> M.2` | x1 Gen2 上行 | 插 NVMe 测试盘，检查交换芯片与下游口 |
| PCIe 接口 4 | `pcie3_rc -> ASM1182e -> Wi-Fi` | x1 Gen2 上行 | 检查 Wi-Fi PCIe 枚举、2.4G/5G 连接和测速 |

## 4. 厂测项目及判定

| 测试项 | DTS 依据 | 测试方法 | 通过标准 |
| --- | --- | --- | --- |
| CPU | K3 SoC | 检查 16 核在线及大小核频率 | 核数正确，频率达到 INI 门限 |
| DDR | K3 SoC | 检查容量并运行内存测试 | 可用容量不低于 `16019 MiB` 配置门限，无报错 |
| RTC | common DTS | 设置时间、掉电后重启读取 | 时间保持正常 |
| UFS | common DTS | 检查 128 GB UFS 并读写测速 | 容量符合规格，读取 >= 62 MiB/s，写入 >= 50 MiB/s |
| SD | `FF_SDCARD` | 插拔识别、读写测速 | 能识别和挂载，HS 读/写 >= 20/10 MiB/s，UHS >= 35/15 MiB/s |
| 4 路 PCIe | `pcie0_rc`、`pcie4_rc`、`pcie3_rc` + ASM1182e | 3 路插 NVMe/端点并测速，1 路装 Wi-Fi 并做无线测试 | 3 个 NVMe/端点均枚举，对应存储读/写均 >= 300 MiB/s；Wi-Fi 枚举和测速通过 |
| 千兆网口 | `FF_GMAC1` -> `&eth1`、RGMII PHY@1 | 连接唯一的物理网口，实机枚为 `eth0`，Ping `172.16.10.143` 并检查媒体速率 | 获取 IP、Ping 通，链路协商 1000 Mb/s 全双工 |
| Wi-Fi | PCIe Wi-Fi + rfkill | 连接 2.4G/5G AP，Ping 及双向测速 | 2.4G 上/下行 >= 20/50 Mb/s；5G >= 100/150 Mb/s |
| 蓝牙 | USB BT + rfkill | rfkill 解锁后扫描 | `hci0` 存在并能扫描到设备 |
| USB 4G 模组 | `FF_4G_5G_MODULE`、3.3V 模组供电、5V USB2 Hub 供电 | 检查 USB 枚举和 AT 串口，执行 `ATI`、`AT+CFUN=1`、运营商和 SIM 卡查询 | `/dev/ttyUSB*` 节点齐全，AT 应答为 OK，SIM 卡可识别 |
| NPU | K3 NPU | 运行 spacemit NPU 用例 | 模型运行结果正确，无驱动错误 |
| LED | `gpio-leds` | 依次点亮 `blue:power`、`green:user`、`red:user1` | 蓝/绿/红三灯与指令一致 |
| 按键 | `gpio-keys` | 依提示按 Power 和 Boot | 分别收到 KEY_POWER 和 KEY_F12 |
| DP 音视频 | `FF_DP1` | 检查 `card1-DP-1` 连接和 `snddp1` 声卡，人工确认画面/声音 | DRM 状态为 `connected`，DP 声卡存在，画面和声音正常 |
| 2 路外置 USB 3.0 | `FF_USB30_TYPEA`、`usb3_porta` Host/Hub | 在 `2-1.3`（接口 A）和 `2-1.4`（接口 B）各插 1 只 U 盘 | 两路均以 SuperSpeed 枚举，读取 >= 90 MiB/s；4G 模组不计入这两路 |
| CAN FD | `mcp251xfd` | 与对端回传 CAN 帧 | `can0` 存在，250 kbit/s FD 帧收发一致 |
| RS485 | `uart6` + 方向 GPIO | 与对端或治具收发字符串 | 9600 baud 收发内容一致 |
| 隔离数字输入 DI | `FF_RS232_UART1`、GPIO120 | 治具先断开、再施加额定有效输入，分别读取 GPIO | 断开和有效输入时的逻辑电平能正确反转；厂测程序在有效输入状态期望读到 `1` |
| 隔离数字输出 DO | `FF_RS232_UART1`、GPIO121 | 程序周期性输出 0/1，治具检测外部输出端通断 | 外部输出状态随 GPIO121 翻转，无常通、常断或无法驱动 |
| 风扇 | I2C6 `ctf2301@4c` | 切换低/高 PWM 并人工观察 | 风扇转速随指令明显变化，无异响 |
| 看门狗 | I2C3 `pc9202@3c` | 运行 `/dev/wdt_base` 测试 | 设备节点存在，喂狗/复位逻辑正常 |
| 关机 | `gpio-poweroff` | 执行正常关机 | 3 s 内拉低关机信号，设备断电 |

## 5. 不纳入当前自动厂测的项目

- RS232 串口通信：该接口的 UART1 TX/RX 引脚已复用为 GPIO121/GPIO120，分别用于光耦隔离输出和输入；厂测执行隔离 DI/DO 测试，不执行 RS232 串口收发测试。
- HDMI/VPU 仍关闭；DP 已开启（`[dp] activated=1`），使用 `card1-DP-1` 和 `snddp1` 测试。
- EEPROM：设备树有 `FF_EEPROM` 配置，但当前 QA 计划没有专用 EEPROM 测试段；建议后续增加板卡 ID/MAC 读取校验。

## 6. 出厂判定

所有已激活项目通过，无内核 Oops、I/O error、接口掉线或异常复位。任一接口枚举失败、性能低于门限、人工交互项失败，均判定为不合格。

## 7. 实际厂测步骤

> 首次部署说明：板子正常从 UFS 根文件系统启动，SD 卡只是更新介质，不会替代根文件系统。要让插卡重启后自动进入厂测，系统必须有 `/usr/local/bin/firefly-test.sh`，并且 `/etc/rc.local` 必须调用它；仅把文件复制到 SD 卡而没有这个启动钩子时，系统会正常进入根文件系统。

1. Wi-Fi 吞吐量仍使用 `part/local.ini` 中的 `192.168.1.85:8001`。以太网使用独立对端 `172.16.10.143`，板端 eth0 地址为 `172.16.11.41`，两台设备经交换机互通。由于 Ubuntu 端 iperf3 3.9/3.11 与板端 3.20 建立数据流失败，当前 `[eth0] enable_speed_test=0`，以 IP、Ping 和 1000M 媒体速率作为厂测判定。
2. 如果板端还没有 QA 工程，先部署 `out/linuxqa_*.tar.gz`；已部署时跳过。部署完成后，将本配置放到板端并命名为 `AIBOX-PRO-K3.Factory.ini`，确保 `/var/cache/firefly/proj/part/` 中没有旧的同名 Factory 配置：

```sh
adb connect 172.16.11.41:5555
adb -s 172.16.11.41:5555 shell 'mkdir -p /var/cache/firefly'
PKG=out/linuxqa_*.tar.gz
adb -s 172.16.11.41:5555 push "$PKG" /var/cache/firefly/linuxqa.tar.gz
adb -s 172.16.11.41:5555 shell 'tar -xvf /var/cache/firefly/linuxqa.tar.gz -C /var/cache/firefly'
adb -s 172.16.11.41:5555 shell 'tar -xvf /var/cache/firefly/proj.tar.gz -C /var/cache/firefly'
adb -s 172.16.11.41:5555 push out/firefly-test.sh /usr/local/bin/firefly-test.sh
adb -s 172.16.11.41:5555 shell 'chmod 755 /usr/local/bin/firefly-test.sh; grep -q "firefly-test.sh" /etc/rc.local || sed -i "/^exit 0$/i [ -x /usr/local/bin/firefly-test.sh ] \&\& /usr/local/bin/firefly-test.sh \&" /etc/rc.local'
adb -s 172.16.11.41:5555 shell 'rm -f /var/cache/firefly/proj/part/AIBOX-PRO-K3*.Factory.ini'
adb -s 172.16.11.41:5555 push part/local.ini /var/cache/firefly/proj/part/local.ini
adb -s 172.16.11.41:5555 push part/AIBOX-PRO-K3.ini /var/cache/firefly/proj/part/AIBOX-PRO-K3.Factory.ini
adb -s 172.16.11.41:5555 shell "ping -c 1 <iperf3服务器IP>"
```

如果板端已经存在 `/var/cache/firefly/proj/`，跳过 QA 包解压，仍要执行 `firefly-test.sh` 推送、权限/`rc.local` 配置、Factory 配置清理推送和连通性检查。

3. 要准备厂测环境：保持 SD 卡插入，执行重启。系统会从 UFS 启动，`rc.local` 调用 `firefly-test.sh` 挂载 SD 卡并更新 `/var/cache/firefly`，随后由 `Factory.ini` 创建 `factory_test.mark`。由于本轮 `[dp] activated=0` 且没有 DRM 显示器，修正版 `start.sh` 会正常跳过图形入口并退出，不会卡在等待屏幕；随后通过网络 ADB 启动厂测菜单。

```sh
adb -s 172.16.11.41:5555 reboot
```

无 DP 时或不想重启时，通过网络 ADB 运行当前厂测：

```sh
adb -s 172.16.11.41:5555 shell touch /var/cache/firefly/proj/factory_test.mark
adb -s 172.16.11.41:5555 shell -t 'cd /var/cache/firefly/proj && ./network-launch-factory-test.sh'
```

4. 厂测界面出现后直接回车运行全部已激活项目。当前共 11 项：`1` SD、`2` Wi-Fi 2.4G、`3` Wi-Fi 5G、`4` 4G、`5` 以太网、`6` LED、`7` 按键、`8` DP、`9` 看门狗、`10` USB、`11` 风扇。也可以输入编号单独重测；输入 `*` 查看汇总，输入 `N*` 查看第 N 项日志，输入 `/` 退出。测试结束后拔出 SD 卡，避免下次重启重复进入厂测。
5. USB 测试时两个外置口各插 1 只 U 盘。脚本会按 `2-1.3`（接口 A）、`2-1.4`（接口 B）的顺序检查；两路都必须显示 `5000M`，且读取达到 `90 MiB/s`。当前关闭整盘写测试，不会因为第二只 U 盘的写入性能较低误判 USB 接口失败。
6. DP 测试时保持显示器连接，按提示确认显示和声音正常。看门狗项检查 `/dev/wdt_base` 字符设备存在。
7. LED、Power/Boot 键和风扇属于人工交互项目，必须按界面提示逐项确认。4G 项目确认 `/dev/ttyUSB2` 的 AT 应答、SIM 卡识别和模组信息。
8. 全部项目通过后，检查 `/userdata/FactoryTest/factoryTest_result.txt`；只有“失败项目: 0”且所有人工项目确认通过，才判定整机合格。
