# 04 硬件层: 内核模块 / 固件 / BSP 用户态

> CLI 系统到 03 就够了; 本章让板上的 WiFi/GPU/视频硬解活过来。
> 可选, 但建议全做一遍 —— "内核与 rootfs 的分工"是 RK 平台最容易迷糊的地方。

## 1. 分工原理: 什么在 boot 分区, 什么在 rootfs

```
boot 分区 (SDK 单独烧)             rootfs 分区 (本教程在做的)
├─ 内核 Image                       ├─ /lib/modules/6.12.69/   <- 内核模块 (驱动代码)
└─ 设备树 rk3588-xxx.dtb            ├─ /lib/firmware/          <- 固件 (给硬件的数据)
                                    └─ 用户态库/工具           <- libmali / mpp / gst...
```

- 内核 (主体) 在 boot; 可加载模块、固件、用户态库在 rootfs;
- 版本约束: `/lib/modules` 下的目录名必须 == 板上 `uname -r`; 固件只认文件名, 无版本约束;
- 换内核时两处同步: boot 重烧 + rootfs 重新 modules_install。

## 2. 内核模块 (必做)

```
# 宿主上, SDK 内核源码树 (先确认编过: ls $S/kernel/.config 存在)
S=/media/lhj/data/t-chip/7.code/arm64/rockchip/rk3588_6.12.69_sdk
W=/media/lhj/data/t-chip/7.code/rootfs/ubuntu26.04/from-scratch
cd $S/kernel
make ARCH=arm64 modules_install INSTALL_MOD_PATH=$W/rootfs

# 验证
ls $W/rootfs/lib/modules            # -> 6.12.69, 必须与板上 uname -r 一致
```

- modules_install 自带 depmod (生成 modules.dep 等索引), 不用手动;
- 内核树从未编过的话: 先按 SDK 适配笔记把内核编一遍再回来;
- 版本不一致的症状: 首启刷屏 `failed to load module`, WiFi/GPU/USB 外设全灭。

## 3. 固件 (按板选做)

原理一行: 内核驱动运行时向用户态要固件 → udev 从 /lib/firmware 按文件名取。

```
# WiFi/BT (以 AP6275P 为例): 从现有能用的 24.04 板子/镜像拷对应子目录
#   板子在线:  scp -r root@<板IP>:/lib/firmware/brcm $W/rootfs/lib/firmware/
#   或 loop 挂载旧镜像拷贝
```

- GPU 不需要固件: Mali 是纯用户态库 (下一节);
- 图省事可 `apt install linux-firmware` (全量, 1G 级); 精确做法是按模组拷子目录。

## 4. BSP 用户态: GPU/视频 (可选, 26.04 风险区)

**前提认知**: Firefly/Rockchip 的 BSP 包 (libmali/mpp/rga/gstreamer-rockchip) 目前只有
noble (24.04) 套件, 没有 26.04 的 resolute 套件 (2026-11 核实官方仓库 dists 仅
bionic/focal/jammy/noble)。本章 = "拿 noble 的包装进 resolute", 大概率能跑
(预编译 so 向后兼容), 不保证 —— 这正是 26.04 生产化要自编译替换的部分。

加 firefly 源 + 高优先级 pin (与生产镜像同款机制):

```
cat > /etc/apt/sources.list.d/firefly.list <<'EOF'
deb http://wiki.t-firefly.com/firefly-ubuntu-repo noble main
EOF

cat > /etc/apt/preferences.d/firefly <<'EOF'
Package: *
Pin: release n=noble
Pin-Priority: 1001
EOF

apt update
apt-cache search libmali                              # 看有哪些变体, 选 wayland+gbm 版
apt-cache policy <选定的包名>                          # 确认 pin 1001 生效
```

- pin 1001 > 1000: 即使版本号更低也强制优先 —— 保证 BSP 包不被 Ubuntu 同名包顶掉;
- 风险症状: 装包时报依赖断裂 (libc/gst 版本不满足), 或装上后运行段错误;
  出现即停, 别硬修 —— 正路只有两条: 回退 24.04, 或用 src_deb 工作流重编 BSP 包
  (见 ../ubuntu24.04/06 §4)。

安装示例 (包名一律以 search 结果为准):

```
apt-cache search rockchip | grep -E 'mpp|rga|gst'
# 选好后: apt install -y libmali-xxx librockchip-mpp1 librga-x gstreamer1.0-rockchip-x
# gst 基础栈: apt install -y gstreamer1.0-plugins-bad gstreamer1.0-gl
```

## 5. 阶段验收 (烧板后回看)

```
lsmod | grep -E 'brcm|mali'       # WiFi/BT 模块已加载
ls /dev/dri                       # GPU 节点在
glmark2-es2-wayland               # 装了 libmali 后测 GPU 分数
gst-play-1.0 <h264文件>           # 硬解路径 (装了 mpp/gst-rockchip 后)
```
