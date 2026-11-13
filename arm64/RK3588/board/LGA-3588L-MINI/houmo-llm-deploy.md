# LGA-3588L-MINI 后摩 LLM 部署步骤

　　板卡 Firefly LGA-3588L-MINI-DUO-RK182X(RK3588L + 2×RK182X 存算芯片,各走一条 PCIe)。
栈:xh2a_drv 驱动(DKMS)→ tcim 用户态 → houmo-HLIELLama(llama-server,OpenAI API)。
所有路径/版本均在 172.16.11.216 板实测。

　　注意:板上若见 rknn3 相关件(rknn-smi、rknn3_transfer_proxy、Qwen2.5-3B.rknn),
那是镜像和 QA 环境自带的另一套(rk1828/rknn 通路),与后摩无关:**不装、不用**。

## 1. 物料

| 物料 | 作用 |
|------|------|
| 基础镜像:Ubuntu 24.04 + 内核 6.12.x + 匹配 headers | 系统 + DKMS 编译环境 |
| houmo-drv-xh2_v1.5.0_linux_aarch64.run | 内核驱动安装器 |
| houmo-HLIELLama-xh2_2.2.2_linux_aarch64.tar.gz | LLM 运行时 |
| 模型 gguf(约 30G/个) | 推理模型 |
| M50_DM2_fw-xh2_v1.5.0.tar.gz(可选) | 芯片固件升级包,hm_smi 显示 V1.5.0 即已配套,无需动 |
| Dadao-deploy-docker-xh2-v1.5.0(可选) | 模型 W5A8 量化转换工具链 |

大文件走 rsync/scp 网线或 U 盘,adb push 慢。

## 2. 烧录镜像

要求:

- 内核 6.12.x(驱动另支持 6.1/6.6/6.8/6.11/6.14/6.17/6.18、5.4/5.10/5.15、4.19)
- `/usr/src/linux-headers-$(uname -r)/` 存在,与 `uname -r` **逐字一致**

烧录后检查:

```bash
uname -r                                         # 参考:6.12.81-g6d79b8ab05eb-dirty
ls /usr/src/linux-headers-$(uname -r)/Makefile   # 必须存在
```

## 3. 装驱动

前置(root):

```bash
apt update && apt install -y build-essential gcc-14 g++-14
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-14 100   # 驱动编译要求 gcc>=14
update-alternatives --config gcc                                     # 选 gcc-14
ls /usr/src/linux-headers-$(uname -r)/Makefile                       # headers 必须在
# 编过内核的板常见 bug:build 软链接指向编译机路径(/home4/lhj/...),修:
ln -sfn /usr/src/linux-headers-$(uname -r)/ /lib/modules/$(uname -r)/build
```

安装:

```bash
bash houmo-drv-xh2_v1.5.0_linux_aarch64.run --build-host false install all
```

失败重试:先 `bash <同.run> uninstall all` + `dkms remove xh2_driver/v1.5.0 --all` 再装。
若卡在 waiting(apt 被占):`killall unattended-upgr` → 清 /var/lib/apt/lists/lock、
/var/cache/apt/archives/lock、/var/lib/dpkg/lock* → `dpkg --configure -a`。

验证(两颗芯片都要出):

```bash
dkms status        # xh2_driver/v1.5.0, <uname -r>: installed
ls /dev/xh2a_*     # 两颗芯片共 21 个节点(_device0/_device1 各半)
dmesg | grep xh2a  # 两颗各一组:pcie init done → niu connect ok → probed successfully 0/1
hm_smi             # HMSW_Version V1.5.0;PCIe 8.0 GT/s x2lane;IPU 1300MHz
```

hm_smi / hm_upgrade_cli / hm_upgrade_gui 在 /usr/local/bin(随驱动安装器带入),
hm_upgrade_* 配 M50 固件包做芯片固件升级。换内核后 dkms_xh2a.service 开机自动重编,
前提是新内核 headers 已先装。

## 4. 部署运行时

```bash
tar xzf houmo-HLIELLama-xh2_2.2.2_linux_aarch64.tar.gz -C /home/firefly/
cd /home/firefly/houmo-HLIELLama-xh2
cat version.txt                                    # llama.cpp=2.1.1 / lanyue2.1.0 / tcim 1.4.0
LD_LIBRARY_PATH=lib ./bin/llama-server --version   # version: 6097 (802b14491)
```

## 5. 放模型

```bash
mkdir -p "models/Qwen3.6_35b-a3b_256k_b1_2core_2chips(dynamic)"
# 放入 HiModel_xh2_qwen3.6-35b-a3b_w5a8_256_256k_b1_2chips_2cores_v1.5.0_20260824.gguf
```

单模型约 30G,eMMC 不够放 NVMe,启动 `-m` 指绝对路径。来源:从已验证板 rsync 整个
models/ 最稳;量化转换走 Dadao docker。

## 6. 开机自启

`/usr/local/bin/firefly-hm-test.sh`:

```bash
#!/bin/bash
cd /home/firefly/houmo-HLIELLama-xh2/
echo performance | tee $(find /sys/devices -name *governor)
taskset -c 4-7 ./bin/llama-server \
  -m ./models/Qwen3.6_35b-a3b_256k_b1_2core_2chips\(dynamic\)/HiModel_xh2_qwen3.6-35b-a3b_w5a8_256_256k_b1_2chips_2cores_v1.5.0_20260824.gguf \
  --port 8081 --device 0,1 &
```

要点:

- `--device 0,1` 两颗都要:模型按 2chips 切分,单颗加载不了
- 在包目录下执行即可,依赖库全在包内 lib,无需装任何东西
- 8081 绑 0.0.0.0 无鉴权,注意网络暴露
- 原工程脚本尾部还有每 3s 的 curl 压测死循环(刷满 journal、芯片常载),上面版本已去掉

`chmod +x` 后,/etc/rc.local 在 `exit 0` 前加:

```sh
[ -x /usr/local/bin/firefly-hm-test.sh ] && /usr/local/bin/firefly-hm-test.sh &
```

正式部署可换包内官方 systemd 方式:`cd service && bash install_llama-server.sh`
(端口 17701,Restart=always,卸载 uninstall_llama-server.sh)。

## 7. 重启验证

```bash
ss -tlnp | grep 8081
curl -s 127.0.0.1:8081/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"你好"}],"stream":false,"temperature":0}'
```

有正常回答即部署完成。

## 附:卸载

```bash
pkill -f firefly-hm-test.sh                                # 服务
rm -rf /home/firefly/houmo-HLIELLama-xh2                   # 运行时
systemctl disable --now dkms_xh2a.service                  # 驱动
dkms remove xh2_driver/v1.5.0 --all && rm -rf /usr/src/xh2_driver-v1.5.0
modprobe -r xh2a_drv
```
