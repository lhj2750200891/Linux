# 02 chroot: 让 x86 宿主跑 arm64

## 1. 这一阶段你将理解

- chroot 的本质: 换根目录, 而不是换机器;
- 为什么必须挂 proc/sys/dev 才算"可用的系统";
- 为什么骨架里的 DNS 在 chroot 里会失效。

## 2. 原理一页

```
宿主 x86_64 Linux
 └─ chroot(rootfs/)  -- 进程看到的 "/" 变成 rootfs 目录
     └─ bash (aarch64)  -- CPU 不认识 arm64 指令
         └─ 内核 binfmt_misc 查 ELF 魔数
             └─ 交给 rootfs 内的 /usr/bin/qemu-aarch64-static
                 └─ qemu 翻译指令, 系统调用原样发给宿主 x86 内核
```

三个推论, 都会在 §5 亲手验证:

1. 必须先把 qemu-aarch64-static 放进 rootfs —— binfmt 按这个路径调它;
2. chroot 里 `uname -m` 显示 aarch64, 但 `/proc/cpuinfo` 是宿主 CPU
   —— 内核还是宿主的, 只是 uname 的结果被 qemu 改写;
3. 网络一切走宿主; 骨架的 resolv.conf 指向 systemd-resolved 的运行时文件,
   chroot 里没有 resolved 在跑 —— 必须临时换成宿主的 (06 出镜像前还原)。

## 3. 进出脚本 (一次写好, 后面每章都用)

存成 `$W/enter-chroot.sh`:

```bash
#!/bin/bash
# 用法: sudo ./enter-chroot.sh
W=/media/lhj/data/t-chip/7.code/rootfs/ubuntu26.04/from-scratch
R=$W/rootfs
cp -f /usr/bin/qemu-aarch64-static $R/usr/bin/          # 幂等, 06 清理时会摘掉
mountpoint -q $R/dev      || mount --bind /dev      $R/dev
mountpoint -q $R/dev/pts  || mount --bind /dev/pts  $R/dev/pts
mountpoint -q $R/proc     || mount -t proc  proc    $R/proc
mountpoint -q $R/sys      || mount --bind /sys      $R/sys
cp -f /etc/resolv.conf $R/etc/resolv.conf               # 临时 DNS
chroot $R /bin/bash
```

存成 `$W/leave-chroot.sh` (chroot 内 exit 之后执行):

```bash
#!/bin/bash
W=/media/lhj/data/t-chip/7.code/rootfs/ubuntu26.04/from-scratch
R=$W/rootfs
umount $R/dev/pts $R/proc $R/sys $R/dev
# 报 busy 时: fuser -vm $R/dev 找进程; 一般是哪个 chroot 没退干净
```

`chmod +x` 两个脚本。此后: 进 = `sudo $W/enter-chroot.sh`, 出 = `exit` + `sudo $W/leave-chroot.sh`。

## 4. 四个挂载各干什么

| 挂载 | 不挂会怎样 |
| --- | --- |
| proc | ps/systemctl/apt 读内核状态全失败, apt 可能起不来 |
| sys | udev/内核设备视图缺失, 部分包的配置脚本失败 |
| dev | 没有设备节点, 任何碰 /dev 的步骤失败 |
| dev/pts | chroot 内没法分配伪终端, 交互异常 |

## 5. 进入并验证 (逐条是理解点)

```
sudo $W/enter-chroot.sh        # 进入 chroot, 下面在 chroot 内
uname -m                       # -> aarch64, qemu 改写的结果
head -3 /proc/cpuinfo          # -> 还是宿主 CPU! /proc 是宿主的, 印证"内核没换"
dpkg -l | wc -l                # -> 百级包数 (对比装完桌面后的千级, 05)
apt update                     # DNS+源+签名全链路自检, 通过才算这章过关
exit                           # 退出 chroot
sudo $W/leave-chroot.sh
```

注意: 此时 apt 用的还是骨架自带官方源 (ports.ubuntu.com), 能通就说明链路没问题;
下一章再换国内镜像。

## 6. 自查

- [ ] apt update 无报错 (能过 = binfmt/qemu/挂载/DNS/源 五件事全对)
- [ ] 两个脚本工作正常, 反复进出无残留挂载 (`mount | grep rootfs` 应为空)
- [ ] 能解释为什么 /proc/cpuinfo 显示的是宿主 CPU
