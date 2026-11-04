# 03 系统层: 让 rootfs 能开机、能登录、能上网

> 本层完成 = 最小可用系统。每一节对应一个"没有它就开不了机/没法用"的部件。
> 命令都在 chroot 内执行 (`sudo $W/enter-chroot.sh`)。

## 1. apt 源: 换国内镜像

```
cat > /etc/apt/sources.list.d/ubuntu.sources <<'EOF'
Types: deb
URIs: http://mirrors.aliyun.com/ubuntu-ports
Suites: resolute resolute-updates resolute-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
apt update
```

- 三段 Suites: resolute=正式版, -updates=bug/安全更新, -security=安全修复;
- Components: main=官方维护, universe=社区, restricted/multiverse=受限/非自由软件;
- 先用 http 不用 https: 骨架可能没有 ca-certificates; 想换 https 先装它再改;
- 这一步与 rootfs_build 的 `change_apt_source` 同源 (它的 res/ 目录就是按配置分发这个文件)。

## 2. 把骨架翻新一遍

```
apt update && apt upgrade -y
```

骨架发布与你构建隔了数月, upgrade 补齐安全与 bug 修复。
生产镜像同样以"骨架+upgrade"开局 —— rootfs_build 的 base 组第一件事就是它。

## 3. 必装系统件 (一次说清每个为什么)

```
apt install -y locales tzdata sudo ca-certificates \
               openssh-client openssh-server network-manager
```

| 包 | 没有它会 |
| --- | --- |
| locales / tzdata | 没有 UTF-8 locale 与时区, 日志时间戳混乱 |
| sudo | 普通用户无法提权 (骨架只有被锁定的 root) |
| openssh-server | 板子没屏幕时唯一的远程入口消失 |
| network-manager | 网卡没人管, 网线插了也不通 (骨架只有内核, 没有网络配置层) |

**故意不装的**: linux-image* / initramfs-tools —— RK 平台内核+dtb 在 boot 分区单独烧录,
rootfs 里装 Ubuntu 内核反而可能与 boot 冲突。这是 RK rootfs 与 PC 发行版最大的认知差异。

## 4. 用户与权限

```
useradd -m -s /bin/bash firefly
passwd firefly                                  # 设一个已知密码 (调试期)
usermod -aG sudo,video,audio,input,render firefly
```

- 骨架没有普通用户, 手动造一个; 生产镜像由 rootfs_build 的 oem 组自动做同样的事;
- video/render 组: 后面 GPU/桌面要求用户在这些组里才能访问 /dev/dri 等节点;
- root 保持锁定 (骨架默认), 一切走 sudo —— 与生产镜像一致。

## 5. locale 与时区

```
locale-gen en_US.UTF-8
# 中文环境加: locale-gen zh_CN.UTF-8
update-locale LANG=en_US.UTF-8
ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
echo Asia/Shanghai > /etc/timezone
```

## 6. 串口控制台: RK3588 = ttyFIQ0 (关键差异)

```
systemctl enable serial-getty@ttyFIQ0.service
```

- PC 串口是 ttyS0; RK3588 的调试串口由 FIQ 调试器固件虚拟成 **ttyFIQ0**, 波特率 1500000;
- 没有它: 首启串口上能看到启动日志, 然后永远等不到登录提示符;
- systemd 本会按内核 cmdline 的 console= 自动拉一个 serial-getty, 显式 enable 是保险
  —— 烧录调试期串口是唯一可靠窗口, 不赌自动行为。

## 7. /etc/fstab: 第二个"开不了机"高发点

骨架的 fstab 基本是空的, 必须自己写根挂载, 且设备名要与 boot 传的 root= 参数一致。
最稳的做法: 先在现有能开机的 24.04 板上看一眼再抄:

```
# 在现有板子上执行, 记下结果:
cat /etc/fstab
```

模板 (设备名以你板子为准):

```
/dev/mmcblk0p8  /    ext4  defaults,noatime  0  1
tmpfs           /tmp tmpfs  defaults,nosuid    0  0
```

字段复习: defaults,noatime 常用组合; 第 5 列 dump=0 (备份工具用); 第 6 列 pass=1 (根分区开机 fsck)。
fstab 写错的症状是开机掉 emergency mode, 会提示哪一行挂载失败 —— 06 §4 有对照表。

## 8. machine-id 复位 (镜像排产常识)

```
: > /etc/machine-id
```

不复位: 打出的每块板共享同一 machine-id, DHCP/journald 等按它区分设备的地方全部串台。
置空文件 = 每块板首次开机自己生成, 这是镜像类产品的标准动作。

## 9. 首启自动扩容 (可选, 生产镜像都有)

rootfs 分区通常比镜像大, 首启把文件系统扩满分区。两个文件照抄:

`/usr/local/sbin/resize-rootfs.sh`:

```bash
#!/bin/bash
# 只在板子上首启运行一次, chroot 里不用测
set -e
DEV=$(findmnt -n -o SOURCE /)          # 如 /dev/mmcblk0p8
DISK=${DEV%p*}                          # /dev/mmcblk0
PART=${DEV##*p}                         # 8
growpart "$DISK" "$PART"                # 分区扩到整盘 (来自 cloud-guest-utils)
resize2fs "$DEV"                        # 文件系统扩到整分区
rm -f /etc/resize-rootfs.pending        # 摘掉开关, 只跑一次
```

`/etc/systemd/system/resize-rootfs.service`:

```
[Unit]
Description=Expand root filesystem on first boot
ConditionPathExists=/etc/resize-rootfs.pending
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/resize-rootfs.sh

[Install]
WantedBy=multi-user.target
```

启用:

```
apt install -y cloud-guest-utils        # 提供 growpart
chmod +x /usr/local/sbin/resize-rootfs.sh
touch /etc/resize-rootfs.pending
systemctl enable resize-rootfs.service
```

理解点: `ConditionPathExists` 是 systemd 的条件开关, 标记文件在才执行 —— 这是
"只跑一次"的最小实现; 生产镜像里的 rockchip resize 服务是同一思路的工业版。

## 10. 阶段验收 (06 烧板后回看)

本层做对的标志: 串口出日志 -> 出登录符 -> firefly 登录 -> ip addr 有地址 -> ssh 可连。
