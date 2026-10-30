# AIBOX-PRO-K3 串口厂测修改记录

本次修改目标：无显示屏时，使用板端调试串口 `/dev/ttyS0`、115200 baud 自动进入厂测，并避免等待 DRM、启动 `onboard` 或启动 `xterm`。

## 修改清单

### 1. `part/local.ini`

原内容：

```ini
[serial_console]
enabled = 0
dev=ttyS1
baud=115200
```

现内容：

```ini
[serial_console]
enabled = 1
dev=ttyS0
baud=115200
```

作用：开启厂测框架的串口 I/O，并使用启动日志确认的 `ttyS0`。

### 2. `part/AIBOX-PRO-K3.ini`

将 `[dp]` 的 `activated` 从 `1` 改为 `0`。

作用：当前没有显示器时不执行 DP 显示测试。连接 DP 显示器并需要测试时，将其改回 `activated=1`。

### 3. `scripts/start.sh`

新增串口厂测启动逻辑：

- 读取 `proj/env.ini` 的 `[serial_console]` 配置。
- 检测到 `factory_test.mark` 且串口模式开启时，跳过桌面、DRM、`onboard` 和 `xterm` 分支。
- 停止占用调试 UART 的 `serial-getty` 或 `getty`，避免与厂测菜单抢输入。
- 直接将 `startup.sh` 的输入、输出和错误输出连接到配置的串口。
- 厂测退出后恢复原来处于 active 状态的 getty。
- 串口初始化明确关闭 `ixon`、`ixoff` 和 `crtscts`，使用无软件流控、无硬件流控的串口模式。
- 按运行架构选择 `bin/get_info` 或 `bin/riscv64/get_info`，并在调用前覆盖安装到 `/usr/local/bin/get_info`，避免在 RISC-V 系统上误执行旧的 ARM 版本。

### 4. `lib/sharness.d/io.sh`

将串口 I/O 初始化从 `ixoff` 改为同时关闭 `ixon`、`ixoff` 和 `crtscts`，确保厂测菜单使用无流控串口。

### 5. `build.sh`

增加对当前工作区 `lib/sharness.d/io.sh` 的显式覆盖复制。原因是构建脚本的基础包来自 `git archive HEAD`，否则上述库文件的未提交修改不会进入最终的 `linuxqa` 包。

## 使用方式

重新构建并制作厂测卡：

```sh
./build.sh local
```

卡插入板子后执行原来的安装流程并重启。串口参数为：

```text
115200 8N1，无流控，设备节点 ttyS0
```

启动后，厂测菜单应直接出现在串口终端。菜单中直接回车运行全部已启用项目；结果保存在：

```text
/userdata/FactoryTest/factoryTest_result.txt
/userdata/FactoryTest/factoryTest_details.txt
```

## 回退方式

仅回退本次串口功能配置和显示测试配置：

```sh
git diff -- build.sh lib/sharness.d/io.sh part/local.ini part/AIBOX-PRO-K3.ini scripts/start.sh
```

手工恢复：

```ini
[serial_console]
enabled = 0
dev=ttyS1
baud=115200
```

并将 `part/AIBOX-PRO-K3.ini` 的 `[dp]` 改回：

```ini
activated=1
```

然后删除 `scripts/start.sh` 中本记录所述的 `serial_console_setting`、`serial_factory_mode`、`run_serial_factory` 三个函数，以及 Factory 标志判断分支即可。不要删除或覆盖工作区中原有的其他未提交文件。

## 原始问题对应关系

- `skip run Factory in console. wait for drm connect.`：由 `start.sh` 的无显示器等待分支导致，本次新增串口分支绕过。
- `onboard: command not found` 和 `No such schema “org.onboard.window”`：由图形输入法启动逻辑导致，本次串口分支不再执行。
- `xterm: Xt error: Can't open display`：由图形终端启动逻辑导致，本次串口分支不再执行。
- `qemu-aarch64: Could not open '/lib/ld-linux-aarch64.so.1'`：这是旧的 ARM `get_info` 可执行文件被系统尝试运行的伴随问题，不是 DRM 等待的根因。本次已修复为先按当前架构选择并安装 `bin/riscv64/get_info`，再调用它。
