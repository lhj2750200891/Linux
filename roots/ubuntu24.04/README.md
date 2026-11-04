# Ubuntu 24.04 根文件系统构建教程 (Firefly rootfs_build)

> 目标: 从一份原始源码出发, 一步一步构建出 RK3588 板子用的 Ubuntu 24.04 arm64
> 根文件系统镜像; 理解每个部件的作用; 构建完成后会挂载、修改、部署。

## 源码位置

| 项 | 值 |
| --- | --- |
| 本机源码 | `/media/lhj/data/t-chip/7.code/rootfs/ubuntu24.04/rootfs_build` |
| 仓库来源 | `ssh://git@git.t-firefly.com:8022/misc-develop/rootfs_build.git` (master 分支) |
| 产物 | `rootfs_build/output/<镜像名>-<日期时间>.img` (ext4) |
| 仓库自带文档 | `AGENTS.md` + `aidocs/` (架构性修改必须同步更新, 规则见 AGENTS.md) |

## 教程目录

| 文件 | 内容 |
| --- | --- |
| [01-源码获取与环境准备.md](01-源码获取与环境准备.md) | 拉代码、子模块、基础包、宿主依赖 (qemu/btrfs/端口) |
| [02-架构与目录职责.md](02-架构与目录职责.md) | 三层架构、每个目录干什么、一次构建的数据流、自编译包供应链 |
| [03-配置与功能组.md](03-配置与功能组.md) | config 五个变量、六个配置、ubuntu24 各功能组每一步在做什么 |
| [04-构建流程详解.md](04-构建流程详解.md) | build.sh 每一步机制、btrfs 断点续跑、加速、清理、打包 |
| [05-产物挂载与部署.md](05-产物挂载与部署.md) | 镜像挂载修改、构建现场调试、进 SDK 打固件、烧录 |
| [06-开发扩展与排障.md](06-开发扩展与排障.md) | 加包/加步骤/加功能组/加配置、自编译包工作流、排障速查 |

## 一页速览

```
仓库作用 : x86_64 宿主上用 qemu-user-static + binfmt_misc 转译, chroot 分步构建
           RK3588 (Firefly) 的 arm64 Linux rootfs 镜像
产品线   : Ubuntu 24.04 (GNOME-Wayland, kernel 6.12)  <- 本教程主线
           另有 GNOME(X11/5.10) 与银河麒麟两条线, 机制相同
构建方式 : ubuntu-base 最小骨架 -> 按"功能组"逐步叠加 -> 打包成 ext4 镜像
入口     : ./build.sh config 选配置; sudo ./build.sh 构建
当前配置 : config/.config -> ubuntu24_gnome_kernel6.12 (菜单第 5 项)
产物     : output/ubuntu24_gnome_kernel6.12-<YYYYMMDD>-<HHMM>.img
日志     : output/log/log_<时间戳>/log (细节全在日志, 控制台只有进度条)
```

## 快速上手 (完整步骤)

```
# 0. 宿主依赖 (详见 01)
qemu-aarch64-static --version        # 必须 >= 8.x
sudo apt install -y btrfs-progs      # 断点快照用
sudo modprobe btrfs                  # WSL2 内核带模块

# 1. 首次准备: 子模块 + 基础包
git submodule update --init src_deb/firefly-reprepro
ls base-package/ubuntu-base-24.04.3-base-arm64.tar.gz   # 不在则见 01

# 2. 选配置 (交互菜单, 本机选 5 = ubuntu24_gnome_kernel6.12)
./build.sh config

# 3. 构建 (root 必须; 时间长; 每步成功自动打快照)
sudo ./build.sh

# 4. 中断/失败后重跑 (自动从最后完成步骤的快照续跑)
sudo ./build.sh resume

# 5. 产物
ls output/*.img
```
