# LGA-3588L-MINI 后摩 LLM 部署指南(从无驱动到 llama-server 运行)

　　2026-11-10 依据对 172.16.11.216(工程师已搭好的验证板)网络 adb 全链路逆向整理。
所有路径、版本、输出均为该板**实测**;标注 **[推断]** 的为合理推断、未在本板直接观察到执行过程。
目标:在下一块新板上照此从零部署并验证 Qwen3.6-35B 推理服务。

## 0. 架构总览

```
后摩 LLM 推理链(2026-11-10 实测 ldd 全链,不含任何 rknn 组件):
应用层      llama-server(后摩魔改 llama.cpp,OpenAI API :8081)
  模型      HiModel gguf(Qwen3.6-35B-A3B,W5A8 量化,256k ctx,按 2 芯片切分)
LLM 运行时  houmo-HLIELLama-xh2 2.2.2(bin/lib)
芯片接入    libtcim_runtime_lite / libtcimblas(tcim 1.4.0 用户态库)
内核驱动    xh2a_drv v1.5.0(DKMS 编译,源码 /usr/src/xh2_driver-v1.5.0,PCIe 主机驱动)
系统层      Ubuntu 24.04.5 + 内核 6.12.81(SDK kernel-6.12) + 版本精确匹配的 headers
硬件        RK3588L SoC + 2×RK182X 存算一体芯片,各走一条 PCIe
            (dmesg: houmo,xh2a 0000:01:00.0 与 0001:11:00.0;PCIe 8.0 GT/s x2lane)

另一条平行通路(与后摩 LLM 无关,勿混淆,2026-11-10 修正):
rknn3 栈    rknn3-rk182x-m2 deb 1.1.0a:rknn-smi/rknn3_* 工具、rknn3_transfer_proxy:18898、
            固件 rknn3_rk1820.img + pcie-rkep 驱动(本板 ko 与 /dev/pcie-rkep-* 均不存在,空转)
```

自启动链(本板实况):

```
rc-local.service → /etc/rc.local → (后台) /usr/local/bin/firefly-hm-test.sh
  ├─ 所有 CPU governor 写 performance
  ├─ taskset -c 4-7 ./bin/llama-server -m <模型> --port 8081 --device 0,1 &
  └─ 死循环每 3s curl 一次本机压测(刷屏源头,可去掉)
```

## 1. 物料清单

后摩 HM SW V1.5.0 SDK 全套,本板留存位置如下(新板部署前先收集齐):

| # | 物料 | 本板参考位置 | 作用 |
|---|------|-------------|------|
| 1 | 基础镜像(Ubuntu24.04 + 内核 6.12.81 + headers) | /boot/linux-headers-6.12-arm64_arm64.deb(6.12-rockchip) | 跑系统 + 供 DKMS 编译 |
| 2 | houmo-drv-xh2_v1.5.0_linux_aarch64.run | /root/ | 驱动安装器(dkms+服务+modprobe 一条龙) |
| 3 | rknn3-rk182x-m2_1.1.0a_arm64.deb(**可选**) | 板上已装,原始 deb 未留档 | rknn 模型通路运行时 + 工具(rknn-smi 出自这里);**后摩 LLM 不需要** |
| 4 | houmo-HLIELLama-xh2_2.2.2_linux_aarch64.tar.gz | /home/firefly/ | LLM 运行时(llama-server/llama-cli/llama-bench/ollama) |
| 5 | 模型 gguf(30G) | /home/firefly/houmo-HLIELLama-xh2/models/ | HiModel_xh2_qwen3.6-35b-a3b_w5a8_256_256k_b1_2chips_2cores_v1.5.0_20260824.gguf |
| 6 | M50_DM2_fw-xh2_v1.5.0.tar.gz | /root/ | 芯片侧固件升级包 [推断:pcie_upgrade_tool 用;rknn-smi 显示 HMSW V1.5.0 即已配套,无需动] |
| 7 | Dadao-deploy-docker-xh2-v1.5.0-ubuntu24.04-aarch64.tar | /root/ | 大道工具链 docker,模型 W5A8 量化转换(x86/aarch64) |
| 8 | houmo_tcim_runtime_xh2_linux_aarch64-1.5.0.tar.gz | /root/ | TCIM python 运行时(可选,测试用) |
| 9 | houmo-examples-xh2_v1.5.0.zip | /root/ | 官方示例(带宽测试等,可选) |

大文件传输建议:rsync/scp 走网线(千兆约 5 分钟/30G),或 U 盘;`adb push` 较慢。

## 2. 阶段一:烧录基础镜像

要求(实测依据):

- 内核 6.12.x。驱动 dkms.conf 的 `BUILD_EXCLUSIVE_KERNEL` 支持
  `6.1/6.6/6.8/6.11/6.12/6.14/6.17/6.18`、`5.4/5.10/5.15`、`4.19`、`7.0`
- **headers 与 `uname -r` 逐字一致**,否则 DKMS 编不了驱动:
  `/usr/src/linux-headers-$(uname -r)/` 必须存在(本板 6.12.81-g6d79b8ab05eb-dirty,
  由 linux-headers-6.12-arm64 deb 提供;本 SDK kernel-6.12 源码正是 6.12.81,可复现)
- extlinux 引导;镜像预装 adb(network adb 5555 默认开)、docker、GNOME

操作:

- 优先:直接复用工程师构建的同版本镜像(向他要 update.img 或构建配置)
- 或:在本 SDK 按 Firefly 流程构建 Ubuntu24.04 镜像(内核出 Image + headers deb 一起产出)

烧录后验证:

```bash
uname -r                                         # 6.12.81-g6d79b8ab05eb-dirty
ls /usr/src/linux-headers-$(uname -r)/Makefile   # 存在才行
adb connect <新板IP>:5555 && adb shell           # 网络 adb 通
```

## 3. 阶段二:安装 xh2 内核驱动

```bash
# 物料传到板子后,root 执行:
sh /root/houmo-drv-xh2_v1.5.0_linux_aarch64.run
```

安装器实际动作(从脚本逆向,实测代码):`dkms add` → `dkms build/install` →
生成并 `enable dkms_xh2a.service`(ExecStart=`dkms autoinstall` + ExecStartPost=`modprobe xh2a_drv`)→
立即重启服务加载模块。

产物:

- `/usr/src/xh2_driver-v1.5.0/`(驱动源码,子模块 ctl/ipu/pcie/qspi/i2c/rpmsg_lite/memory_*/transport…)
- `/etc/systemd/system/dkms_xh2a.service`
- `/lib/modules/<内核>/updates/dkms/xh2a_drv.ko`

验证(逐条,期望输出见注释):

```bash
dkms status        # xh2_driver/v1.5.0, <uname -r>: installed
lsmod | grep xh2a  # xh2a_drv  319488  11
ls /dev/xh2a_*     # 21 个节点:ctl0 + 每颗芯片各 ~10 个(fast_memory/i2c/ipu/
                   #   memory_allocator_{ddr,spm0,spm1}/memory_transfer/qspi/rpmsg/system)
dmesg | grep -i xh2a | head -25
```

dmesg 期望(**两颗芯片各一组,都出现才算过**):

```
xh2a_host_init: installing xh2a driver version v1.5.0
houmo,xh2a 0001:11:00.0: xh2a_pcie_probe pcie init done. notify each sub-module
xh2a_ipu xh2a_ipu0: niu connect ok.
xh2a_sys_probe: sys device probed successfully 0
houmo,xh2a 0000:01:00.0: ...(device1 同样一组,niu connect ok,probed successfully 1)
xh2a_ctl_ctc_check_linkup: check dev_id=0 ... fail_info=0x1
xh2a_ctl_ctc_check_linkup: check dev_id=1 ... fail_info=0x10000
```

注:`check_linkup` 行带 fail_info 数值属正常流程打印,本板 device1 显示 0x10000 但功能完好。

芯片状态快照:

```bash
rknn-smi
# 期望(对照本板 /home/firefly/save.txt):HMSW_Version V1.5.0;device0/1 两颗;
# PCIe 8.0 GT/s x2lane;DVFS_Mode performance;Cur_Ipu_Freq 1300.0 MHz
```

坑:

- 换/升内核后开机 dkms_xh2a.service 会自动重编,但前提是**新内核 headers 已先装好**
- 本板 /usr/src 残留两个版本 headers(g6d79b… 与旧 ga3517…)= 换过一次内核,属正常痕迹

## 4. 阶段三(可选):rknn3 运行时 —— 与后摩 LLM 无关

> **2026-11-10 修正**:初版误把 rknn3 当作后摩栈必需层。实测澄清:
> - llama-server 及 libtcim_\* 全链 ldd,**无任何 librknn3 依赖**;
> - rknn3_startup 走的是 **pcie-rkep 驱动 + rknn3_rk1820.img**(rknn 模型通路),
>   本板 pcie-rkep.ko 与 /dev/pcie-rkep-\* 均不存在,rknn3_transfer_proxy 只在 18898 空转;
> - 结论:**后摩 LLM 部署不需要 rknn3**。它是平行存在的 rknn 模型通路
>   (本板 QA 演示用:Qwen2.5-3B.rknn、rknn3_model_test;芯片 SKU 对应关系以平台资料为准)。

如确需 rknn 演示/QA 通路再装:

```bash
dpkg -i rknn3-rk182x-m2_1.1.0a_arm64.deb
```

postinst 自动执行:ldconfig;`systemctl enable rknn3.service rknn-mdns.service`;
reload udev 规则(`75-rknn3-coprocessor.rules`,USB VID 2207:180b 热插拔触发脚本);
尝试调 /usr/share/pcie-rkep-dkms/pcie-rkep-postinst(本板无此目录,静默跳过)。

产物:`/usr/bin/` 下 rknn-smi、rknn-console、rknn3_llm_demo、rknn3_model_test、
pcie_upgrade_tool 等;`librknn3_api.so`、gstreamer 插件 libgstrknn.so;
`/usr/lib/firmware/rknn3_rk1820.img`;`/etc/profile.d/rknn3-env.sh`。
rknn3_transfer_proxy 监听 127.0.0.1:18898。

注意一个便利点:查后摩芯片状态的 `rknn-smi`(save.txt 快照即出自它)**来自这个 deb**。
不装的话看芯片状态用 `dmesg | grep xh2a` 和 /dev/xh2a_\* 节点替代即可。

## 5. 阶段四:部署 LLM 运行时(houmo-HLIELLama-xh2)

```bash
tar xzf houmo-HLIELLama-xh2_2.2.2_linux_aarch64.tar.gz -C /home/firefly/
cd /home/firefly/houmo-HLIELLama-xh2
cat version.txt
# llama.cpp=2.1.1 / description=lanyue2.1.0 / tcim_version=1.4.0
LD_LIBRARY_PATH=lib ./bin/llama-server --version
# 期望: version: 6097 (802b14491)
# (与 API 流式 chunk 的 system_fingerprint "b6097-802b14491" 对应,可确认跑的就是这个 bin)
```

目录结构:bin/(llama-server、llama-cli、llama-bench、llama-gguf-split、hlaw_ollama、model-cli…)、
lib/(libggml\*.so、libllama.so、**libtcim_\*.so 芯片接入层**)、models/(放模型)、
scripts/(convert_hm_to_gguf.py + gguf-py)、service/(官方安装/卸载脚本)、include/。

## 6. 阶段五:部署模型

- 放 `models/` 下,本板结构(目录名建议带模型/量化/ctx/芯片切分信息):

```
models/Qwen3.6_35b-a3b_256k_b1_2core_2chips(dynamic)/HiModel_xh2_qwen3.6-35b-a3b_w5a8_256_256k_b1_2chips_2cores_v1.5.0_20260824.gguf   (30G)
models/Qwen3.8_27b-dflash2_256k_b1_2core_2chips()/…(23G,本板未加载,备用)
```

- **空间**:双模型 53G,eMMC 不够时放 NVMe/SD,启动 `-m` 指绝对路径即可
- 来源二选一:
  - **a) 从已验证板拷贝**(最稳):rsync/adb pull 整个 models 目录
  - b) 后摩发布包直接拿 HiModel gguf;或 Dadao docker 对 HF 原始模型做 W5A8 量化、
    再 `scripts/convert_hm_to_gguf.py` 打包 **[b 路径本板未实操,推断]**

## 7. 阶段六:启动服务

### 方式 A —— 本板实际采用(rc.local + 手写脚本)

`/usr/local/bin/firefly-hm-test.sh`(全文见附录 A),要点:

- 所有 CPU governor → performance
- `taskset -c 4-7`:绑 4 核(3588L 大核簇 **[推断]**)
- `--device 0,1`:**两颗芯片都要指定**,模型按 2chips 切分,单颗加载不了
- `--port 8081`,监听 0.0.0.0(**无鉴权,局域网任何人可用**)

`/etc/rc.local` 末尾(exit 0 之前)追加:

```sh
[ -n `which firefly-hm-test.sh` ] && firefly-hm-test.sh &
```

> **警告**:脚本尾部 while-true 每 3s 压测循环会把 journal/dmesg 刷满(rc.local[PID] 前缀
> 的 chat.completion.chunk 流),且让推理芯片常年带载。不需要压测就把循环注释掉,
> 只留 llama-server 启动行。已验证板当时就是它刷的屏。

### 方式 B —— 包内官方脚本(systemd,正式部署推荐)

```bash
cd /home/firefly/houmo-HLIELLama-xh2/service
sudo bash install_llama-server.sh
# 生成 /etc/systemd/system/llama-server.service:
#   ExecStart=<目录>/bin/llama-server --models-dir models --no-context-shift \
#             --reasoning-format auto --log-prefix --log-timestamps --embeddings
#   端口 17701,User=执行 sudo 的用户,Restart=always,WantedBy=multi-user.target
# 卸载:uninstall_llama-server.sh(同目录另有 install_ollama.sh 装 ollama 版)
```

两方式对比:方式 B 有 systemd 守护重启、日志进 journalctl -u,但按 `--models-dir` 由客户端
指定模型名;方式 A 直接 `-m` 指定单一模型路径更直白,但 rc.local 无守护、且自带压测循环。
新板验证建议:先用方式 A 跑通(与已验证板一致,便于对参数),正式用再切方式 B。

## 8. 阶段七:整体验证清单

```bash
# 1. 驱动层
lsmod | grep xh2a_drv && ls /dev/xh2a_ctl0
# 2. 芯片层(rknn-smi 出自可选的 rknn3 deb;没装就看 dmesg + /dev/xh2a_*)
rknn-smi || dmesg | grep -i "probed successfully"
# 3. 服务层
ss -tlnp | grep -E "8081|17701"
# 4. 推理功能(非流式,等完整回答)
curl -s 127.0.0.1:8081/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"你好,一句话自我介绍"}],"stream":false,"temperature":0}' \
  | head -c 600
# 5. 速度粗测(对比基线):35B-A3B MoE(激活 3B)w5a8 双芯片
#    首包延迟看推理启动,稳定后 tokens/s 可再压;基线数值本板未记录,新板可自测留档
```

## 9. 坑清单(实测汇总)

1. **headers 必须与 uname -r 逐字一致**,DKMS 才能编驱动;换内核先装 headers 再启 dkms_xh2a
2. llama-server 要 `LD_LIBRARY_PATH=lib`(或 cd 到包目录跑),libtcim_\*/libggml\* 全在包内 lib
3. `--device 0,1` 缺一不可:模型按 2chips_2cores 切分,单颗芯片加载不了
4. firefly-hm-test.sh 压测循环输出直达 journal/dmesg,排查其它问题前先 `pkill -f firefly-hm-test.sh`(llama-server 是它的后台子进程,杀脚本不影响服务)
5. 8081/17701 都绑 0.0.0.0 无鉴权,注意网络暴露面
6. `dpkg -S /lib/firmware/rknn3_rk1820.img` 查不到归属是正常的:Ubuntu24.04 usrmerge,/lib→/usr/lib 符号链接,查 `/usr/lib/firmware/...` 才找得到
7. rc.local 是 `#!/bin/sh -e`:脚本任何一行非 0 退出会中断后续;firefly-hm-test.sh 是后台 `&` 所以不阻塞
8. M50_DM2_fw 包是芯片侧固件(pcie_upgrade_tool 升级);rknn-smi 显示 HMSW V1.5.0 即已配套,别乱升 **[推断]**
9. uboot/ATF 固件版本(cmdline 可见 fwver=ddr-v1.24,bl31-v1.56,bl32-v1.23)属镜像层,与后摩栈无关但换镜像时留意配套
10. **rknn3 ≠ 后摩栈,别混为一谈**(2026-11-10 实测修正):llama-server 全链 ldd 零 rknn 依赖;rknn3_transfer_proxy 在 18898 跑着 ≠ LLM 在用它;后摩推理走 tcim→xh2a_drv 自己的通路

## 10. 卸载/回退

```bash
# 服务层
pkill -f firefly-hm-test.sh
cd /home/firefly/houmo-HLIELLama-xh2/service && bash uninstall_llama-server.sh   # 装过方式B才需要
# 运行时
rm -rf /home/firefly/houmo-HLIELLama-xh2
# rknn3(可选件,与后摩 LLM 无关,装没装/卸不卸都不影响推理)
dpkg -r rknn3-rk182x-m2
# 驱动
systemctl disable --now dkms_xh2a.service
dkms remove xh2_driver/v1.5.0 --all
rm -rf /usr/src/xh2_driver-v1.5.0
modprobe -r xh2a_drv
```

## 附录 A:firefly-hm-test.sh 全文(本板实况)

```bash
#!/bin/bash

cd /home/firefly/houmo-HLIELLama-xh2/

echo performance | tee $(find /sys/devices -name *governor)

taskset -c 4-7 ./bin/llama-server -m ./models/Qwen3.6_35b-a3b_256k_b1_2core_2chips\(dynamic\)/HiModel_xh2_qwen3.6-35b-a3b_w5a8_256_256k_b1_2chips_2cores_v1.5.0_20260824.gguf --port 8081 --presence_penalty 1.5 --device 0,1 &

# ↓ 以下压测循环,新板上建议注释掉(留服务去刷屏)
while true; do curl --location '127.0.0.1:8081/v1/chat/completions' --header 'Content-Type: application/json' --data '{"messages":[{"role":"system","content":"you are a helpful assistant. Answer the question in language of the question."}, {"role":"user","content":"Write a C++ program to find the nth Fibonacci number using recursion."}],"stream":true,"model":" qwen3-8b","temperature":0,"presence_penalty":0,"frequency_penalty":0,"top_p":1}'; sleep 3; done
```

注:curl 里 `"model":" qwen3-8b"`(带前导空格)与 `--presence_penalty 1.5` 是压测随手参数,
llama-server 单模型模式不校验该名字,不影响运行。

## 附录 B:关键文件速查

| 内容 | 路径 |
|------|------|
| 开机入口 | /etc/rc.local → /usr/local/bin/firefly-hm-test.sh |
| LLM 运行时 | /home/firefly/houmo-HLIELLama-xh2/(发布包 2.2.2 在 /home/firefly/) |
| 驱动源码 | /usr/src/xh2_driver-v1.5.0(DKMS 名 xh2_driver/v1.5.0) |
| 驱动服务 | /etc/systemd/system/dkms_xh2a.service |
| 驱动模块 | /lib/modules/\<内核\>/updates/dkms/xh2a_drv.ko |
| 协处理器固件 | /usr/lib/firmware/rknn3_rk1820.img(rknn3 deb 提供) |
| rknn3 工具/库 | /usr/bin/rknn-smi 等、librknn3_api.so(rknn3-rk182x-m2 deb 1.1.0a) |
| 芯片状态基线 | /home/firefly/save.txt(rknn-smi 快照,PCIe 8GT/s x2,IPU 1300MHz) |
| 后摩 SDK 原始物料 | /root/(drv .run、M50 固件、Dadao docker、tcim runtime、examples) |
| 内核 headers deb | /boot/linux-headers-6.12-arm64_arm64.deb |
| rknn 演示模型(QA 用) | /home/firefly/Qwen2.5-3B.rknn + install.sh/md5sum.txt(升级卡脚本,另一套 rknn3 栈) |
```
