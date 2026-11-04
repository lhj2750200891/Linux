# Ubuntu 26.04 根文件系统从零手工构建 (RK3588)

> 目标: 不用 rootfs_build, 只凭公网上的 ubuntu-base 骨架 + apt 仓库, 亲手做出一个
> 能在 RK3588 板上启动的 Ubuntu 26.04 (resolute) arm64 根文件系统镜像。
> 目的不是省事, 是把 rootfs_build 封装掉的每个环节亲手展开一遍。

## 产出与去处

| 项 | 值 |
| --- | --- |
| 教程 (本目录) | `/home/lhj/Linux/roots/ubuntu26.04/` |
| 构建工作区 (你自建) | `/media/lhj/data/t-chip/7.code/rootfs/ubuntu26.04/from-scratch/` |
| 产物 | 工作区/`ubuntu26-rootfs.img` (ext4, 手工打包) |
| 对照框架 | `../ubuntu24.04/` (rootfs_build 七份教程) |

## 全过程六阶段

```
阶段0  骨架下载   ubuntu-base 官方最小 rootfs tar.gz       <- 01
阶段1  解包       最小目录树 (apt/dpkg/systemd, 无内核)     <- 01
阶段2  chroot     x86 宿主 + qemu 转译运行 arm64           <- 02
阶段3  系统层     源/用户/网络/串口/fstab -> 能开机登录     <- 03
阶段4  硬件层     内核模块/固件/BSP -> 硬件可用 (可选)      <- 04
阶段5  桌面层     GNOME + gdm 自动登录 (可选)              <- 05
阶段6  打包烧录   dd/mkfs.ext4 -> .img -> 上板验证          <- 06
```

## 两条路, 本教程走哪条

| 路线 | 说明 |
| --- | --- |
| 本教程 (手工从0) | 每条命令亲手敲, 理解每一层; 产物能烧能用 |
| 生产路线 (框架复用) | 给 rootfs_build 新增 26.04 配置 —— 见 06 §6, 一张表说明改动点 |

## 写作约定

- 所有构建命令都由你自己执行; 教程只负责讲清"这条命令在干什么、为什么需要它";
- rootfs_build 仓库全程只读参照, 不改动;
- 宿主 = 本机 x86_64; chroot 内命令与宿主命令在代码块注释里区分;
- `W` = 工作区路径, 在 01 §3 定义, 换终端要重设。

## 硬要求 (先确认再动手)

```
qemu-aarch64-static --version     # 必须 >= 8.x, 旧版会卡死在 systemd-sysusers (见 06 §7)
df -h /media/lhj/data             # 工作区所在盘, 留 15G 以上
```

## 进度清单

- [ ] 01 环境准备与基础骨架
- [ ] 02 chroot 跨架构运行原理
- [ ] 03 系统层: 让 rootfs 能开机
- [ ] 04 硬件层: 内核模块/固件/BSP (可选)
- [ ] 05 桌面层: GNOME (可选)
- [ ] 06 打包烧录验证 + 与 rootfs_build 对照
