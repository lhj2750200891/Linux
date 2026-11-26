# 6.12 SDK AB 系统

## 1. 新建板级 AB defconfig

### 1.1 新建 `$SDK/device/rockchip/.chips/rk3588/firefly_rk3588_lga-3588l-mini-ab_defconfig`

```
RK_KERNEL_DTS_NAME="rk3588-firefly-lga-3588l-mini-duo-rk182x"
RK_PRODUCT_MODEL="AIBOX-DUO"
RK_KERNEL_CFG_FRAGMENTS="firefly-linux.config firefly-net.config firefly-rk182x.config"
RK_AB_UPDATE=y
RK_UBOOT_CFG_FRAGMENTS="rk-ab firefly-linux"
RK_ROOTFS_SYSTEM_DEBIAN=y
RK_ROOTFS_PREBUILT=y
RK_ROOTFS_PREBUILT_PATH="prebuilt_rootfs/ubuntu_rootfs.img"
RK_DEBIAN_LINUX_HEADERS=n
RK_DEBIAN_UNIFIED_IMAGE=y
RK_DEBIAN_USER="firefly"
RK_DEBIAN_PASSWORD="firefly"
RK_EXTRA_PARTITION_NUM=1
RK_EXTRA_PARTITION_1_DEV="oem"
RK_EXTRA_PARTITION_1_NAME="oem"
RK_EXTRA_PARTITION_1_FSTYPE="ext4"
RK_EXTRA_PARTITION_1_SRC="rk1828-policy"
RK_EXTRA_PARTITION_1_SIZE="128M"
```

必须核对的检查项:
- **不要** `#include "firefly.config"`(USE_EXTBOOT/parameter-firefly 与 AB 冲突),需要的内容已展开进上面文件;
- **不要**写 `USE_EXTBOOT`(缺省 n,走 FIT boot 流);
- `RK_UBOOT_CFG_FRAGMENTS` 必须含 `rk-ab`(U-Boot AB 开关,无自动联动);保留 `firefly-linux`(板上的 LT9211C/PCA953X/ADC 选 DTB 依赖它);
- kernel fragments 是原 defconfig 两行的合并去重结果(`firefly-linux.config firefly-net.config` + `firefly-rk182x.config`);
- `RK_EXTRA_PARTITION_1_*` 五行原样保留(oem=rk1828-policy,风扇/后摩栈安装物料);
- `RK_PARAMETER` 不用写(AB 下自动取 parameter-ab.txt);
- `RK_DEBIAN_USER/Password` 改成你外部 rootfs 的实际用户。



### 1.2 确认 DTS 为已修复版本(开机 logo hdmi0 修复,2025-10-26 之后)

```bash
cd $SDK/kernel-6.12
git log --oneline -3 -- arch/arm64/boot/dts/rockchip/rk3588-firefly-lga-3588l-mini-duo-rk182x.dts
grep -c "hdmi0_in_vp1" arch/arm64/boot/dts/rockchip/rk3588-firefly-lga-3588l-mini-duo-rk182x.dtsi
# 若 hdmi0_in_vp1 双端点仍在(10/17-10/26 坏窗口的代码),先修 dts 再继续
```

### 1.3 切换配置

```bash
cd $SDK
./build.sh firefly_rk3588_lga-3588l-mini-ab_defconfig
```

---

## 2. 分区表

默认 `parameter-ab.txt`(system 7GiB×2,userdata 起点 14.3GiB)只适合 ≥32GB 卡。

### 2.1 32GB 及以上: 默认即可

### 2.2 16GB 卡: parameter-ab-16g.txt`

```
FIRMWARE_VER: 1.0
MACHINE_MODEL: RK3588
MACHINE_ID: 007
MANUFACTURER: RK3588
MAGIC: 0x5041524B
ATAG: 0x00200800
MACHINE: 0xffffffff
CHECK_MASK: 0x80
PWR_HLD: 0,0,A,0,1
TYPE: GPT
GROW_ALIGN: 0
CMDLINE: mtdparts=:0x00002000@0x00004000(uboot),0x00002000@0x00006000(misc),0x00040000@0x00008000(boot_a),0x00040000@0x00048000(boot_b),0x00010000@0x00088000(backup),0x00800000@0x00098000(system_a),0x00800000@0x00898000(system_b),0x00040000@0x00C98000(oem),-@0x00CD8000(userdata:grow)
```

defconfig 追加一行:`RK_PARAMETER="parameter-ab-16g.txt"`
(system 4GiB×2,boot 各 128MB,oem 128MB,userdata 约 8GiB;rootfs 镜像必须 < 4GiB)

### 2.3 8GB 卡: `parameter-ab-8g.txt`,CMDLINE 换成:

```
CMDLINE: mtdparts=:0x00002000@0x00004000(uboot),0x00002000@0x00006000(misc),0x00040000@0x00008000(boot_a),0x00040000@0x00048000(boot_b),0x00010000@0x00088000(backup),0x00400000@0x00098000(system_a),0x00400000@0x00498000(system_b),0x00040000@0x00898000(oem),-@0x008D8000(userdata:grow)
```

defconfig 追加:`RK_PARAMETER="parameter-ab-8g.txt"`
(rootfs 镜像必须 < 2GiB)

### 2.4 禁止改动

- 分区名(`boot_a/boot_b/system_a/system_b/misc/oem`)一字不改;
- 不给任何分区加 `:bootable`;
- misc 留空,不做 misc.img。

---

## 3. 编 U-Boot 和内核

```bash
cd $SDK
./build.sh uboot
./build.sh kernel
cat kernel-6.12/include/config/kernel.release    # 记下版本号,第 5 步用
```

编完核对:
```bash
grep -E "CONFIG_ANDROID_AB=|CONFIG_SPL_AB=" u-boot/.config
# 期望:两行都 =y
grep -E "CONFIG_LT9211C_DRIVER=|CONFIG_DM_PCA953X=|CONFIG_CHECK_VERSION_CHOOSE_DTB=" u-boot/.config
# 期望:三行都 =y(板上 LT9211C/PCA953X/ADC 选 DTB 不丢)
ls -l output/firmware/MiniLoaderAll.bin output/firmware/uboot.img \
      output/firmware/boot.img output/firmware/resource.img
```

---

## 4. 编译 updateEngine(升级引擎,AB 必需)

```bash
cd $SDK/external/recovery
TC=/home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk/prebuilts/gcc/linux-x86/aarch64/arm-gnu-toolchain-14.3.rel1-x86_64-aarch64-none-linux-gnu    # 设置交叉编译路径
make clean
make CC=$TC/bin/aarch64-none-linux-gnu-gcc \
     CFLAGS="--sysroot=$TC/aarch64-none-linux-gnu/libc" \
     LDFLAGS="--sysroot=$TC/aarch64-none-linux-gnu/libc" \
     RecoveryNoUi=true \
     RECOVERY_DISABLE_FEATURES="RK_SOURCE_URL RK_DIFF_UPDATE" updateEngine
ls -l updateEngine
file updateEngine    # 必须是aarch64才行
```

---

## 5. 构造 rootfs(挂载)

这里展示的是挂载根文件系统的方式进行构造,下一章节展示的是通过根文件系统的源码构造,直接编译出可用的AB系统固件

```bash
su
cd /home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk/prebuilt_rootfs
mkdir rootfs
mount rk3588_debian_rootfs.img rootfs
install -m 0755 ../external/recovery/updateEngine rootfs/usr/bin/updateEngine
cd rootfs
vim bootcontrol.service    # 填写如下内容
[Unit]
Description=A/B successful boot marking
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/updateEngine --misc=now
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target

# 安装在etc/systemd/下:设置开机服务
install -m 0644 bootcontrol.service etc/systemd/system/bootcontrol.service
mkdir -p etc/systemd/system/multi-user.target.wants
ln -sf etc/systemd/bootcontrol.service etc/systemd/system/multi-user.target.wants/bootcontrol.service
rm bootcontrol.service

# 注入 /dev/block/by-name udev 规则
install -m 0644 ../../device/rockchip/common/overlays/common/udev-rules/lib/udev/rules.d/61-persistent-internal-storage.rules lib/udev/rules.d/61-persistent-internal-storage.rules

# 覆盖/etc/fstab
vim etc/fstab     # 不保留原来的内容,写入下面的内容
/dev/root   /                   auto       defaults        0 1
proc        /proc               proc       defaults        0 0
devtmpfs    /dev                devtmpfs   defaults        0 0
devpts      /dev/pts            devpts     mode=0620,ptmxmode=0666,gid=5   0 0
tmpfs       /dev/shm            tmpfs      nosuid,nodev,noexec     0 0
sysfs       /sys                sysfs      defaults        0 0
debugfs     /sys/kernel/debug   debugfs    defaults        0 0
pstore      /sys/fs/pstore      pstore     defaults        0 0
/dev/disk/by-partlabel/oem      /oem       ext4    defaults,nofail,x-systemd.automount,x-systemd.device-timeout=1s 0 2
/dev/disk/by-partlabel/userdata /userdata  ext4    defaults,nofail   0 2

# 新建 userdata 分区
mkdir -p userdata

# 加入rknn3和hm的自动安装
vim rk182x-installer.service    # 写入下面的内容
[Unit]
Description=RK182X accelerator stack installer (from /oem)
After=local-fs.target
RequiresMountsFor=/oem
ConditionPathExists=!/var/lib/rk182x-installed

[Service]
Type=oneshot
ExecStart=/bin/sh /oem/RK182x-installer.sh
ExecStartPost=/bin/touch /var/lib/rk182x-installed
RemainAfterExit=yes
TimeoutStartSec=1800

[Install]
WantedBy=multi-user.target

install -m 0644 rk182x-installer.service etc/systemd/system/rk182x-installer.service
ln -sf etc/systemd/system/rk182x-installer.service etc/systemd/system/multi-user.target.wants/rk182x-installer.service
rm rk182x-installer.service
# 标记文件 /var/lib/rk182x-installed 在 **rootfs 内部**,所以 OTA 换槽后新 rootfs 没有标记,会自动重新安装 hm

# 灌入内核模块
cd ../../kernel-6.12/
make ARCH=arm64 \
     CROSS_COMPILE=../prebuilts/gcc/linux-x86/aarch64/arm-gnu-toolchain-14.3.rel1-x86_64-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu- \
     modules_install \
     INSTALL_MOD_PATH=../prebuilt_rootfs/rootfs \
     INSTALL_MOD_STRIP=1
cd ../prebuilt_rootfs/rootfs     
ls lib/modules/               # 应与 kernel.release 一致

# 串口控制台
ln -sf /usr/lib/systemd/system/serial-getty@.service  etc/systemd/system/getty.target.wants/serial-getty@ttyFIQ0.service
ls etc/systemd/system/getty.target.wants/ | grep ttyFIQ0      # 存在即可

# 检查步骤是否完成
ls usr/bin/updateEngine
ls etc/systemd/system/multi-user.target.wants/bootcontrol.service
ls etc/systemd/system/multi-user.target.wants/rk182x-installer.service
ls lib/udev/rules.d/61-persistent-internal-storage.rules
grep -E "dev/root|PARTLABEL" etc/fstab
ls lib/modules/
grep ttyFIQ0 -r etc/systemd/system/getty.target.wants/
```



---

## 6. 打包 rootfs 

```bash
cd /home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk/prebuilt_rootfs
IMAGE_SIZE_MB=$(( $(du --apparent-size -sm rootfs | cut -f1) + $(find rootfs | wc -l) * 4 / 1024 + 64 ))
IMAGE_SIZE_MB=$(( IMAGE_SIZE_MB * 110 / 100 ))
echo "镜像大小: ${IMAGE_SIZE_MB}M"
mkfs.ext4 -Fq -d rootfs rootfs_ab.img "${IMAGE_SIZE_MB}M"

# 本目录下的rootfs_ab.img 就是重新构建的镜像文件
umount rootfs  # 取消实体的挂载
mount rootfs_ab.img rootfs    # 挂载新镜像
cd rootfs
ls usr/bin/updateEngine
ls etc/systemd/system/multi-user.target.wants/bootcontrol.service
ls etc/systemd/system/multi-user.target.wants/rk182x-installer.service
ls lib/udev/rules.d/61-persistent-internal-storage.rules
grep -E "oem|userdata" etc/fstab
ls lib/modules/
ls etc/systemd/system/getty.target.wants/ | grep ttyFIQ0
cd ..
umount rootfs
ln -sf rootfs_ab.img rootfs.img
exit
```

硬约束:`IMAGE_SIZE_MB` 必须 **小于** system_a 大小(16G 表 4GiB / 8G 表 2GiB / 默认表 7GiB)。超了就裁 rootfs 或换表。

---

## 7. Ubuntu24.04 构造AB镜像

```bash
# 1. 拷贝SDK/external/recovery/编译出来的updateEngine
cd /media/lhj/data/t-chip/7.code/rootfs/ubuntu24.04/rootfs_build
mkdir -p chroot/ubuntu24/firefly/5_ab-system.overlay/usr/local/bin      # 新建一个overlay
cp /home/lhj/updateEngine chroot/ubuntu24/firefly/5_ab-system.overlay/usr/local/bin/updateEngine

# 2. 增加规则(从debian中复制过来)
mkdir -p chroot/ubuntu24/firefly/5_ab-system.overlay/lib/udev/rules.d
cp /media/lhj/data/t-chip/7.code/rootfs/debian13/debian/overlay-firefly/etc/udev/rules.d/70-block-byname.rules \
   chroot/ubuntu24/firefly/5_ab-system.overlay/lib/udev/rules.d/
   
# 3. oem分区后面新增userdata分区(这里是替换,没办法追加)
mkdir -p chroot/ubuntu24/firefly/5_ab-system.overlay/etc/
vim chroot/ubuntu24/firefly/5_ab-system.overlay/etc/fstab  # 写入下面的内容
# OEM is optional so images without an OEM partition continue booting.
/dev/disk/by-partlabel/oem /oem ext4 defaults,nofail,x-systemd.automount,x-systemd.device-timeout=1s 0 2
/dev/disk/by-partlabel/userdata /userdata ext4 defaults,nofail 0 2

# 4. 新增规则和boot服务
mkdir -p chroot/ubuntu24/firefly/5_ab-system.overlay/etc/udev/rules.d
mkdir -p chroot/ubuntu24/firefly/5_ab-system.overlay/etc/systemd/system/multi-user.target.wants
mkdir -p chroot/ubuntu24/firefly/5_ab-system.overlay/etc/systemd/system/getty.target.wants

cp /media/lhj/data/t-chip/7.code/rootfs/debian13/debian/overlay-firefly/etc/udev/rules.d/70-block-byname.rules chroot/ubuntu24/firefly/5_ab-system.overlay/etc/udev/rules.d/

vim chroot/ubuntu24/firefly/5_ab-system.overlay/etc/systemd/system/bootcontrol.service # 写入下面的内容
[Unit]
Description=A/B successful boot marking
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/updateEngine --misc=now
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target


vim chroot/ubuntu24/firefly/5_ab-system.overlay/etc/systemd/system/rk182x-installer.service           # 写入下面的内容
[Unit]
Description=RK182X accelerator stack installer (from /oem)
After=local-fs.target
RequiresMountsFor=/oem
ConditionPathExists=!/var/lib/rk182x-installed

[Service]
Type=oneshot
ExecStart=/bin/sh /oem/RK182x-installer.sh
ExecStartPost=/bin/touch /var/lib/rk182x-installed
RemainAfterExit=yes
TimeoutStartSec=1800

[Install]
WantedBy=multi-user.target

# 5. 创建规则软链接
cd /media/lhj/data/t-chip/7.code/rootfs/ubuntu24.04/rootfs_build/chroot/ubuntu24/firefly/5_ab-system.overlay/etc/systemd/system/multi-user.target.wants
ln -sf /etc/systemd/system/bootcontrol.service      bootcontrol.service
ln -sf /etc/systemd/system/rk182x-installer.service rk182x-installer.service
# 检查软链接
OVL=/media/lhj/data/t-chip/7.code/rootfs/ubuntu24.04/rootfs_build/chroot/ubuntu24/firefly/5_ab-system.overlay

for l in bootcontrol.service rk182x-installer.service; do
    t=$(readlink "$l")
    case "$t" in
        /*)  test -f "$OVL$t" && echo "$l OK  -> $t" || echo "$l 坏: 目标不在 overlay 内 ($t)" ;;
        *)   echo "$l 坏: 相对路径 ($t)" ;;
    esac
done

# 6. ttyFIQ0链接
cd /media/lhj/data/t-chip/7.code/rootfs/ubuntu24.04/rootfs_build/chroot/ubuntu24/firefly/5_ab-system.overlay/etc/systemd/system/getty.target.wants/

ln -sf /usr/lib/systemd/system/serial-getty@.service serial-getty@ttyFIQ0.service

# 7. 增加扩容和格式化脚本
mkdir -p chroot/ubuntu24/firefly/5_ab-system.overlay/usr/local/sbin
vim chroot/ubuntu24/firefly/5_ab-system.overlay/usr/local/sbin/resize-rootfs.sh   # 写入下面的内容
#!/bin/bash
# 首启扩容:root 在线扩到分区大小;userdata 无 fs 则格式化;补挂载点
mkdir -p /oem /userdata
ROOTDEV=$(findmnt -n -o SOURCE /)
resize2fs "$ROOTDEV" 2>/dev/null || true

for PART in userdata oem; do
    DEV=/dev/block/by-name/$PART
    if [ -b "$DEV" ] && ! blkid -o value -s TYPE "$DEV" >/dev/null 2>&1; then
        mkfs.ext4 -F -q "$DEV"
    fi
done
mount -a 2>/dev/null || true
exit 0

# 给执行权限
chmod +x chroot/ubuntu24/firefly/5_ab-system.overlay/usr/local/sbin/resize-rootfs.sh

# 8. 新增扩容服务
vim chroot/ubuntu24/firefly/5_ab-system.overlay/etc/systemd/system/resize-rootfs.service  # 写入下面的内容
[Unit]
Description=First-boot resize and format (root/userdata/oem)
After=local-fs.target
ConditionPathExists=!/var/lib/resize-done

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/resize-rootfs.sh
ExecStartPost=/bin/touch /var/lib/resize-done
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target

# 9. 创建扩容的软链接
ln -sf /etc/systemd/system/resize-rootfs.service chroot/ubuntu24/firefly/5_ab-system.overlay/etc/systemd/system/multi-user.target.wants/resize-rootfs.service

# 10. 创建oem和userdata目录
mkdir chroot/ubuntu24/firefly/5_ab-system.overlay/oem
mkdir chroot/ubuntu24/firefly/5_ab-system.overlay/userdata

# 7. 构建img
sudo ./build.sh resume    # 因为之前有编译固件,所以要使用resume,否则会全量编译,选择 ubuntu24_firefly_5_ab-system.overlay
```



## 8. Debian13 构造AB镜像

```bash
# 1. 拷贝源码目录下的updateEngine文件
cd /media/lhj/data/t-chip/7.code/rootfs/debian13/debian
cp /home/lhj/updateEngine overlay-firefly/usr/local/bin/

# 2. 新建bootconttrol.service
vim overlay-firefly/etc/systemd/system/bootcontrol.service   # 写入下面的内容
[Unit]
Description=A/B successful boot marking
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/updateEngine --misc=now
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target

# 3. 新建 rk182x-installer.service
vim overlay-firefly/etc/systemd/system/rk182x-installer.service      # 写入下面的内容
[Unit]
Description=RK182X accelerator stack installer (from /oem)
After=local-fs.target
RequiresMountsFor=/oem
ConditionPathExists=!/var/lib/rk182x-installed

[Service]
Type=oneshot
ExecStart=/bin/sh /oem/RK182x-installer.sh
ExecStartPost=/bin/touch /var/lib/rk182x-installed
RemainAfterExit=yes
TimeoutStartSec=1800

[Install]
WantedBy=multi-user.target

# 4. 创建wants链接
mkdir -p overlay-firefly/etc/systemd/system/multi-user.target.wants
mkdir -p overlay-firefly/etc/systemd/system/getty.target.wants
ln -sf /etc/systemd/system/bootcontrol.service  overlay-firefly/etc/systemd/system/multi-user.target.wants/bootcontrol.service
ln -sf /usr/lib/systemd/system/serial-getty@.service overlay-firefly/etc/systemd/system/getty.target.wants/serial-getty@ttyFIQ0.service
ln -sf /etc/systemd/system/rk182x-installer.service \
   overlay-firefly/etc/systemd/system/multi-user.target.wants/rk182x-installer.service
   
# 5. 新增fstab下的userdata
vim post-build.sh   # 在oem后新增userdata(大概102行)
fixup_device_part "/dev/disk/by-partlabel/userdata:/userdata:ext4:defaults,nofail"

# 6. 构建
./firefly-build.sh 2 3     # overlay是第2步,post-build是第3步
```



## 7. 编译固件

```bash
# 编译
# 删除 misc.img
cd /home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk
rm -f output/firmware/misc.img output/misc.img
grep -E "RK_MISC" output/.config    # 不等于y就行

# 生成 userdata.img
truncate -s 64M output/firmware/userdata.img
mkfs.ext4 -F -q output/firmware/userdata.img

./build.sh rootfs
ls -l output/firmware/rootfs.img     # 指向 rootfs_ab.img
./build.sh firmware      # 尺寸检查,超 system_a 直接报错;同时产出 oem.img(rk1828-policy)
ls -l output/firmware/oem.img               # 确认 oem.img 已生成
./build.sh updateimg                        # 产出 update-ab.img(全量,两槽同镜像,含 oem)
ls -l output/firmware/update-ab.img         # 查看全量包
 
# 定制OTA包(ota包中需要去掉oem分区)
./build.sh edit-ota-package-file     # 弹出的编辑器中删除oem,misc,userdata三个分区
./build.sh ota-updateimg
ls -l output/firmware/update-ota.img

# 核对产物
cat output/update-ota/package-file
cat device/rockchip/.chips/rk3588/ota-package-file   # 不应再有 oem,misc,userdata 行
ls -l output/firmware/update-ab.img output/firmware/update-ota.img   
```

oem 在运行系统中挂载在 /oem,updateEngine 的挂载守卫会拒绝写入已挂载分区,导致整包 OTA 中止,所以 OTA 包必须去掉 oem,以后 oem 内容(rk1828-policy)有变更时:走 `update-ab.img` 全量刷,或单独刷 oem 分区,不走 OTA。



---

## 8. 烧录验证

```bash
sudo upgrade_tool uf output/firmware/update-ab.img

# 验证
cat /proc/cmdline    # 有 slot_suffix=_a和 root=PARTUUID=<system_a即可
ls /dev/block/by-name/    # boot_a boot_b system_a system_b oem userdata 全部在
updateEngine --misc=display   # current_slot: a;tries_remaining=7, successful_boot=0
sleep 60
updateEngine --misc=display     #  bootcontrol 跑过后:slot A successful_boot=1
systemctl status bootcontrol.service    #  需要是激活 active (exited)
mount | grep -E "on /(oem|userdata)"    #  两分区已挂载
ls /oem/         # 后摩和1828的deb和脚本等在就行

# 换槽验证(使用的是ota包)
adb push /home/lhj/update-ota.img /userdata/   # (或者使用scp)
updateEngine --update --image_url=/userdata/update-ota.img --upgrade=all --reboot
cat /proc/cmdline            # android_slotsufix=_b,root= 指向 system_b 的 PARTUUID
updateEngine --misc=display  # 查看元数据:slot B: tries=7→bootcontrol标记后 successful=1

# 失败回退验证
systemctl disable bootcontrol.service     1. 禁用标记服务,代表没能正常进入内核启动服务
updateEngine --misc=other  # 切槽: 现在是a,则把b设置为未确认状态(successful=0, tries=7)
reboot  # 连续重启 7 次:可以进入系统以后重启,也可以在启动阶段使用复位按键
cat /proc/cmdline        # android_slotsufix 应回到 _b
updateEngine --misc=display   # 应看到 A 槽 tries=0 successful=0(尝试失败的现场)
systemctl enable bootcontrol.service    # 恢复服务
systemctl start bootcontrol.service    
```



---

## 9. 常用调试命令

```bash
updateEngine --misc=display        # 双槽状态/元数据 CRC
updateEngine --misc=now            # 手动标记当前槽成功
updateEngine --misc=other          # 手动切槽(配 reboot)
updateEngine --misc=wipe_userdata  # 清 userdata
updateEngine --misc=other --reboot # 手动切换测试
```

---

## 14. 迭代流程

### 14.1 只改 rootfs

```bash
cp /home4/lhj/debian_ab_rootfs.img /home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk/prebuilt_rootfs/
rm rootfs.img
ln -sf debian_ab_rootfs.img rootfs.img
cd /home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk
bash build.sh firmware updateimg     # 重新构建即可
```

### 14.2 改了内核

```bash
cd /home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk
bash build.sh kernel
```

### 14.3 改了 oem 内容(rk1828-policy)

```bash
cd /home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk
bash build.sh firmware updateimg
# oem 非槽分区:走 update-ab.img 全量刷,或单独刷:
sudo upgrade_tool wl 0x00CD8000 output/firmware/oem.img   # 偏移按你的分区表
```

### 14.4 铁律

- 手工单独刷过 system_a 后,必须同法刷 system_b;
- update-ota.img 不能当全量包烧;
- OTA 不升级 U-Boot;U-Boot 变更用 update-ab.img 全量刷或单独刷 uboot 分区;
- OTA 包里永远不要有 oem(挂载守卫会中止整包)。

---

## 15. 本文档对应的 SDK 关键文件(出问题时查)

| 作用 | 文件 |
|---|---|
| AB 总开关定义 | `device/rockchip/common/configs/Config.in.update` |
| AB 分区表 | `device/rockchip/.chips/rk3588/parameter-ab.txt` |
| U-Boot AB fragment | `u-boot/configs/rk-ab.config` |
| 板 U-Boot fragment | `u-boot/configs/firefly-linux.config` |
| 槽选择/元数据 | `u-boot/boot/android_ab.c` |
| root= 切换 | `u-boot/arch/arm/mach-rockchip/bootargs.c`、`u-boot/boot/android_ab.c` |
| 分区名→槽解析 | `u-boot/disk/part.c`(`part_get_info_by_name_option`) |
| 预置镜像直链 | `device/rockchip/common/scripts/mk-rootfs.sh`(`RK_ROOTFS_PREBUILT` 分支) |
| OTA 打包(跳 _b) | `device/rockchip/common/scripts/mk-updateimg.sh`(`gen_package_file`) |
| 挂载守卫(拒写已挂载分区) | `external/recovery/app/engine/upgrade_precheck.c` |
| oem 安装物料 | `device/rockchip/.chips/rk3588/oem/rk1828-policy/` |
| 升级引擎 | `external/recovery/`(`app/engine/`) |
| 尺寸检查 | `device/rockchip/common/scripts/mk-firmware.sh` + `partition-helper` |
| hm 栈部署对照 | `board/LGA-3588L-MINI/houmo-llm-deploy.md`(笔记目录) |
