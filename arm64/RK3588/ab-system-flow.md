# AB 系统流程详解(源码级,跟着日志走一遍)

> **读代码前必看**:文中代码摘自本机 SDK。`$SDK` = `/media/lhj/data/t-chip/7.code/arm64/rockchip/rk3588_6.12.69_sdk`(amd-epyc 服务器上是 `/home4/lhj/arm64/rockchip/rk3588_6.12.69_sdk`)。行号为摘录时的位置,可能有 ±几行漂移,**以函数名为准**。

**源码地图**(想自己翻代码,按这张表找):

| 链路 | 文件:行 | 函数 |
|---|---|---|
| SPL 选槽 | `$SDK/u-boot/common/spl/spl_ab.c` 199-266 | `spl_slot_is_bootable()` `spl_ab_get_current_slot()` |
| SPL 递减/归一化 | `$SDK/u-boot/common/spl/spl_ab.c` 380+ | `spl_ab_decrease_tries()` `spl_slot_normalize()` |
| U-Boot proper 递减调用点 | `$SDK/u-boot/arch/arm/mach-rockchip/board.c` 445 | `ab_decrease_tries()` |
| 分区名自动带槽 | `$SDK/u-boot/disk/part.c` 695 | `part_get_info_by_name_option()` |
| 读 boot FIT | `$SDK/u-boot/arch/arm/mach-rockchip/fit.c` 153 | `fit_get_blob()` |
| 过滤 DTB root= | `$SDK/u-boot/arch/arm/mach-rockchip/bootargs.c` 344-375 | `bootargs_add_dtb_dtbo()` |
| 注入 root= | `$SDK/u-boot/boot/android_ab.c` 618-717 | `ab_update_root_uuid()` `ab_update_root_partition()` |
| 标记成功 | `$SDK/external/recovery/app/engine/cmd_slot.c`、`core/slot.c` 200 | `cmd_slot_now()` → `set_slot_succeed()` |
| OTA 主流程 | `$SDK/external/recovery/app/engine/cmd_upgrade.c` 133-242 | `upgrade_run()` |
| OTA 条目过滤 | `$SDK/external/recovery/core/slot.c` 340、`app/engine/upgrade_plan.c` 82 | `slot_filter()` |
| OTA 切槽 | `$SDK/external/recovery/core/slot.c` 172 | `set_slot_activity()` |
| 挂载守卫 | `$SDK/external/recovery/app/engine/upgrade_precheck.c` 552 | `is_device_mounted()` |
| misc 偏移与常量 | `$SDK/external/recovery/include/recovery/bootmsg.h` 20-35 | `MISC_OFFSET_AB` 等 |

---

## 0. 一张总图:四条链路

```
【启动链路】每次上电
  SPL 选槽(读 misc)→ 递减 tries(未确认槽)→ U-Boot 按槽加载 boot → 按槽改 root= → 内核挂载对应 system

【标记链路】每次成功启动
  systemd → bootcontrol.service → updateEngine --misc=now → 当前槽 successful=1

【OTA 链路】人工触发
  updateEngine 读包 → 只写"非活动槽"的 boot/system → MD5 校验 → 切槽(对侧变活动,tries=7)→ 重启

【回退链路】自动发生
  活动槽未确认(successful=0)时每次启动 tries-1 → 减到 0 → SPL 换选另一槽
```

记住一句话:**misc 分区的 32 字节元数据是整个 AB 的大脑,三方(SPL / U-Boot / updateEngine)读写同一份,谁也不许用自己的格式。**

---

## 1. 存储布局:分区表 + misc 元数据

### 1.1 GPT 分区(parameter-ab.txt,板上实测 mmcblk0p1~p9)

```
p1 uboot   p2 misc   p3 boot_a   p4 boot_b   p5 backup
p6 system_a   p7 system_b   p8 oem(共享,rk1828-policy)   p9 userdata(共享,用户数据)
```

- **槽内**:boot_a/b(FIT:内核+DTB+resource)、system_a/b(根文件系统)——OTA 更换的对象;
- **共享**:misc、oem、userdata——跨槽保留,**OTA 包不允许包含这三行**;
- boot_a/b、system_a/b **是裸分区,没有文件系统**(boot 是 FIT 二进制,system 是 ext4 整盘镜像)。

### 1.2 misc 分区布局(updateEngine 侧定义:`external/recovery/include/recovery/bootmsg.h:21-23`)

```
0x0000  预留(全零)
0x0800  AvbABData —— AB 元数据,32 字节 ★整个 AB 的"大脑"
0x1800  Wipe cmdline
0x2800  Custom cmdline
0x4000  BCB(bootloader_message,旧 recovery 流残留会落在这里 → U-Boot 读到会进 recovery 模式)
```

这张表就是源码里这几行(`external/recovery/include/recovery/bootmsg.h:20-34`):

```c
/* ---- MISC partition offsets ---- */
#define MISC_OFFSET_AB          0x0800  /* AvbABData */
#define MISC_OFFSET_CMDLINE     0x1800  /* Wipe command */
#define MISC_OFFSET_CUSTOM      0x2800  /* Custom cmdline */
#define MISC_OFFSET_BCB         0x4000  /* bootloader_message */

/* ---- AVB A/B constants ---- */
#define AVB_AB_MAGIC            "\0AB0"
#define AVB_AB_MAGIC_LEN        4
#define AVB_AB_DATA_SIZE        32
#define AVB_AB_MAX_PRIORITY     15
#define AVB_AB_MAX_TRIES_REMAINING 7
```

### 1.3 AvbABData 逐字段(板上 dd 实测 + 源码双确认)

```
偏移   字段                实测值            含义
0x00   magic[4]            00 41 42 30       "\0AB0"(u-boot/include/android_avb/avb_ab_flow.h:40)
0x04   version_major       01                元数据格式版本
0x05   version_minor       00
0x06   last_boot           00                上次启动的槽(0=A,1=B),--misc=now 时记录
0x07   reserved            00
0x08   slot[0] (A)         0f 00 01 00       priority=15 tries=0 successful=1 verity=0
0x0C   slot[1] (B)         0e 07 00 00       priority=14 tries=7 successful=0
0x10   rollback_major[4]   00 00 00 00
0x14   rollback_minor[4]   00 00 00 00
0x18   crc32[4]            dc 9d d8 15       前 28 字节的标准 CRC32,**大端存储**
```

常量(u-boot/include/android_avb/avb_ab_flow.h:51、recovery/bootmsg.h:34):
`AVB_AB_MAX_PRIORITY = 15`,`AVB_AB_MAX_TRIES_REMAINING = 7`。

**槽状态速查表**(读懂 SPL 打印的钥匙):

| priority | tries | successful | 含义 |
|---|---|---|---|
| 15 | 7→0 递减中 | 0 | **活动槽·未确认**(OTA 刚切过来,每次启动 -1)|
| 15 | 0 | 1 | **活动槽·已确认**(bootcontrol 标记过,稳定运行)|
| 14 | 7 | 0/1 | 备用槽(通常是标记过成功的旧系统)|
| 0 | 0 | 0 | 不可启动(非法状态被 normalize 后的样子)|

**bootable 判定**(`spl_slot_is_bootable`):`priority > 0 && (successful == 1 || tries > 0)`。

---

## 2. 启动链路(跟着日志走)

### 2.1 SPL 阶段:选槽 + 打印

源码:`$SDK/u-boot/common/spl/spl_ab.c` → `spl_ab_get_current_slot()`(210 行起)

bootable 判定只有一行(spl_ab.c:199):

```c
static bool spl_slot_is_bootable(AvbABSlotData *slot)
{
	return slot->priority > 0 &&
		(slot->successful_boot || (slot->tries_remaining > 0));
}
```

选槽本体(`spl_ab_get_current_slot`,spl_ab.c 约 210-266 行;省掉的中间一段是 thunderboot 直启内核用的 `CONFIG_SPL_KERNEL_BOOT` 静态缓存,我们的流不经过):

```c
int spl_ab_get_current_slot(struct blk_desc *dev_desc, char *partition, char *slot)
{
	static int last_slot_index = -1;
	size_t slot_index_to_boot;
	AvbABData ab_data;
	int ret;

	ret = spl_ab_data_read(dev_desc, &ab_data, partition);  /* 读 misc,偏移 4 扇区=0x800 字节(spl_ab.h:14) */
	if (ret)
		return ret;

	if (spl_slot_is_bootable(&ab_data.slots[0]) &&
	    spl_slot_is_bootable(&ab_data.slots[1])) {
		if (ab_data.slots[1].priority > ab_data.slots[0].priority)
			slot_index_to_boot = 1;
		else
			slot_index_to_boot = 0;          /* 双槽可用:priority 高者胜 */
	} else if (spl_slot_is_bootable(&ab_data.slots[0])) {
		slot_index_to_boot = 0;                  /* 只有 A 可用:选 A */
	} else if (spl_slot_is_bootable(&ab_data.slots[1])) {
		slot_index_to_boot = 1;
	} else {
		printf("No bootable slots found, use lastboot.\n");
		if (spl_get_lastboot(&ab_data) == 0) {   /* 双槽全挂:last_boot 兜底 */
			memcpy(slot, "_a", 2);
			goto out;
		} else if (spl_get_lastboot(&ab_data) == 1) {
			memcpy(slot, "_b", 2);
			goto out;
		} else {
			printf("SPL: No valid last_boot. Boot from slot-A by default.\n");
			memcpy(slot, "_a", 2);               /* 再兜底:默认 _a */
			goto out;
		}
	}

	if (slot_index_to_boot == 0)
		memcpy(slot, "_a", 2);
	else if (slot_index_to_boot == 1)
		memcpy(slot, "_b", 2);

	if (last_slot_index != slot_index_to_boot) {     /* 只在槽变化后的首启打印 */
		int i;

		last_slot_index = slot_index_to_boot;
		for (i = 0; i < 2; i++)
			printf("SPL: A/B-slot: %s, successful: %d, tries-remain: %d%s\n",
			       i == 0 ? "_a" : "_b",
			       ab_data.slots[i].successful_boot,
			       ab_data.slots[i].tries_remaining,
			       slot_index_to_boot == i ? " (select)" : "");
	}

out:
	return 0;
}
```

板上日志对照(选槽打印只在**槽发生切换后的首次启动**出现):
```
SPL: A/B-slot: _a, successful: 1, tries-remain: 0 (select)   ← "(select)"=本次选了 A
SPL: A/B-slot: _b, successful: 0, tries-remain: 7
```

### 2.2 递减:发生在两个位置

| 位置 | 条件 | 源码 |
|---|---|---|
| SPL(仅 thunderboot 直启内核路径)| `next_stage == KERNEL` | `u-boot/common/spl/spl_fit.c:1389` |
| **U-Boot proper(我们的 FIT 流走这里)** | 每次启动 | `u-boot/arch/arm/mach-rockchip/board.c:445` |

调用点(U-Boot proper,我们的 FIT 流走这里):

```c
/* u-boot/arch/arm/mach-rockchip/board.c:445(last_stage_init 尾部) */
	if (ab_is_enabled() && ab_decrease_tries())
		printf("Decrease ab tries count fail!\n");
```

递减本体(`spl_ab.c` 的 `spl_ab_decrease_tries`;U-Boot proper 的 `ab_decrease_tries` 是对它的包装,判定完全一致):

```c
	/* 先复用选槽逻辑定位当前槽,再读元数据 */
	ret = spl_ab_get_current_slot(dev_desc, "misc", slot_suffix);
	...
	/* Ensure data is normalized, e.g. illegal states will be marked as
	 * unbootable and all unbootable states are represented with
	 * (priority=0, tries_remaining=0, successful_boot=0).
	 */
	spl_slot_normalize(&ab_data.slots[0]);
	spl_slot_normalize(&ab_data.slots[1]);

	/* ... and decrement tries remaining, if applicable. */
	if (!ab_data.slots[slot_index].successful_boot &&
	    ab_data.slots[slot_index].tries_remaining > 0)
		ab_data.slots[slot_index].tries_remaining -= 1;

	ret = spl_save_metadata_if_changed(dev_desc, &ab_data, &ab_data_orig);
```

normalize(顺带解释"非法状态为什么会被清成不可启动",spl_ab.c):

```c
static void spl_slot_normalize(AvbABSlotData* slot)
{
	if (slot->priority > 0) {
		if (slot->tries_remaining == 0 && !slot->successful_boot) {
			/* We've exhausted all tries -> unbootable. */
			spl_slot_set_unbootable(slot);
		}
		if (slot->tries_remaining > 0 && slot->successful_boot) {
			/* Illegal state - avb_ab_mark_slot_successful() and so on
			 * will clear tries_remaining when setting successful_boot.
			 */
			spl_slot_set_unbootable(slot);
		}
	} else {
		spl_slot_set_unbootable(slot);
	}
}
```

**这就是"标记成功之后 tries 不再动"的源码依据**(递减条件 `successful_boot==0 && tries>0`,标记过的槽直接跳过),也是回退测试必须先停用 bootcontrol 的原因。

### 2.3 U-Boot proper:按槽加载 boot + 改 root=

关键机制:**分区名查找自动带槽后缀**——查 "boot"/"system" 时,AB 启用会先拼上当前槽后缀再去查分区表(`u-boot/disk/part.c:695` `part_get_info_by_name_option`):

```c
	/* 1. Query partition with A/B slot suffix */
	name_len = strlen(name);

	if (name_len >= 2 &&
	    (!strcmp(name + name_len - 2, "_a") ||
	     !strcmp(name + name_len - 2, "_b")))
		goto lookup;                      /* 名字已带 _a/_b:原样查 */

	if (!ab_is_enabled())
		goto lookup;                      /* 未开 AB:原样查 */
#ifdef CONFIG_LIBAVB_USER
	if (ab_append_part_slot(name, name_slot)) /* "boot" → "boot_a"/"boot_b" */
		return -1;
	full_name = name_slot;
#endif
```

流程(带源码位置):
```
① u-boot/arch/arm/mach-rockchip/fit.c:153  fit_get_blob():part_name = PART_BOOT
   → part_get_info_by_name → 解析为 boot_a(或 boot_b)→ 读出 FIT(内核+DTB+resource)
   → 板上日志:RESC: 'boot_a'
② u-boot/arch/arm/mach-rockchip/bootargs.c:368  bootargs_add_dtb_dtbo
   → AB 启用时过滤掉 DTB 自带的 root=(env_update_filter "root=")
③ u-boot/boot/android_ab.c:653  ab_update_root_partition
   → part_get_info_by_name("system") → 得到当前槽分区号/PARTUUID
   → env_update("bootargs", "root=PARTUUID=<当前槽>")
④ cmdline 成形(板上实测):
   android_slotsufix=_a ... root=PARTUUID=a26ad83c-...(=system_a)
⑤ 内核挂载 mmcblk0p6(=system_a)→ /  ← 板上日志:VFS: Mounted root on device 179:6
```

②③ 的源码(节选,注释是原文):

```c
/* u-boot/arch/arm/mach-rockchip/bootargs.c:368  bootargs_add_dtb_dtbo() 内
 * If use AB system, delete default "root=" which route
 * to rootfs. Then the ab bootctl will choose the
 * high priority system to boot and add its UUID
 * to cmdline. The format is "roo=PARTUUID=xxxx...".
 */
if (ab_is_enabled())
	env_update_filter("bootargs", bootargs, "root=");
else
	env_update("bootargs", bootargs);
```

```c
/* u-boot/boot/android_ab.c:618 */
static void ab_update_root_uuid(void)
{
	char root_partuuid[70] = "root=PARTUUID=";
	char *boot_args = env_get("bootargs");
	char guid_buf[UUID_SIZE] = {0};
	...
	/* cmdline 里还没有 root= 才注入;eMMC(GPT)走 PARTUUID这条路 */
	if (!strstr(boot_args, "root=")) {
		get_partition_unique_uuid(ANDROID_PARTITION_SYSTEM, /* "system",part.c 自动带槽 */
					  guid_buf, UUID_SIZE);
		strcat(root_partuuid, guid_buf);
		env_update("bootargs", root_partuuid);
	}
}
```

> `ab_update_root_partition()`(android_ab.c:653)是入口:按存储类型分流——eMMC/SCSI 的 GPT 分区走上面的 `ab_update_root_uuid()`(PARTUUID),裸设备走 `root=/dev/mmcblk0pN` 等;最终都落到 `env_update("bootargs", ...)`。

### 2.4 内核/系统阶段:被动

内核和 rootfs **对 AB 完全无感知**——它只是被 U-Boot 喂了正确的 root= 而已。槽信息对用户态只通过 `android_slotsufix=_a` 这个参数可见。

---

## 3. 标记链路(每次成功启动的收尾)

```
systemd(Debian:sysv 兼容 / Ubuntu:systemd 单元)
  → bootcontrol.service
      ExecStart=/usr/bin/updateEngine --misc=now        # Debian;Ubuntu 在 /usr/local/bin
  → external/recovery/app/engine/cmd_slot.c  cmd_slot_now()
  → external/recovery/core/slot.c:200       set_slot_succeed()
      当前槽 successful=1、tries=0,重算 CRC,写回 misc+0x800
```

入口只有三行(app/engine/cmd_slot.c):

```c
int cmd_slot_now(struct storage_mgr *mgr)
{
    pr_info(“--misc=now: marking current slot as successful\n”);
    return set_slot_succeed(mgr);
}
```

标记本体(core/slot.c:200,节选处已标注):

```c
int set_slot_succeed(struct storage_mgr *mgr)
{
    int slot = get_current_slot();          /* 取当前槽 */
    if (slot < 0)
        return -1;

    struct avb_ab_data info;
    if (read_ab_misc(mgr, &info) != 0)      /* 读 misc+0x800,先验 CRC(slot.c:118) */
        return -1;

    if (avb_safe_memcmp(info.magic, AVB_AB_MAGIC, AVB_AB_MAGIC_LEN) != 0) {
        pr_err(“A/B magic mismatch\n”);
        return -1;
    }

    if (info.slots[slot].priority != AVB_AB_MAX_PRIORITY) {
        pr_warn(“slot %d priority %d != %d, correcting\n”, ...);  /* ...处为格式化参数 */
        info.slots[slot].priority = AVB_AB_MAX_PRIORITY;    /* 顺手把 priority 纠回 15 */
    }

#ifdef SUCCESSFUL_BOOT   /* 默认编译分支:确认 */
    info.slots[slot].tries_remaining = 0;
    info.slots[slot].successful_boot = 1;
#endif
#ifdef RETRY_BOOT        /* 显式开 RETRY_BOOT 才走这里:退回 tries=7 未确认 */
    info.slots[slot].tries_remaining = AVB_AB_MAX_TRIES_REMAINING;
    info.slots[slot].successful_boot = 0;
#endif
    info.last_boot = (uint8_t)slot;

    avb_ab_update_crc(&info);
    return write_ab_misc(mgr, &info);
}
```

> 编译期二选一(external/recovery/Makefile:70-84):`RK_AB_SUPPORT` 开启时,若两个开关都没设,**兜底 else 加 `-DSUCCESSFUL_BOOT`**;显式设 `RETRY_BOOT=y` 则优先。也就是说我们板上 `--misc=now` = 永久确认;若想改成”每次 --misc=now 都回到 7 次重试”,重编 updateEngine 时加 `RETRY_BOOT=y` 即可。

**为什么 stamp(/var/lib/*)必须放 rootfs 内部**:标记服务与新槽安装触发器(rk182x-installer)都以 rootfs 内文件为”已做过的凭证”——OTA 换槽后新 rootfs 没有凭证,自动重装/重新标记。放共享分区会让新槽被误判为”已处理”。

---

## 4. OTA 链路(updateEngine 全流程)

入口:`updateEngine --update --image_url=... --upgrade=all [--reboot]`
源码:`external/recovery/app/engine/cmd_upgrade.c  upgrade_run()`(100 行起),按执行顺序:

```
① stage:把镜像拷到 savepath(本地文件已在位则跳过)
② image_parse:解析 RKFW 头 + 内嵌 package-file 条目
③ get_current_slot():读 misc+0x800(core/slot.c:118)
④ build_upgrade_list:遍历包内条目
   slot_filter(core/slot.c):无后缀条目→保留(uboot);
                            _a/_b 条目→只留"非当前槽"那个
   ab_fallback:包里只有 _a 时,自动映射为对侧 _b 的写入目标
⑤ precheck(upgrade_precheck.c):挂载守卫——目标已挂载(oem/userdata)→ 拒绝并中止整包
⑥ 逐分区写 + MD5 回读校验(任一失败即中止,不切槽)
⑦ set_slot_activity(core/slot.c:172):
      当前槽 priority 15→14(降级)
      对侧槽 priority →15、tries=7、successful=0(未确认状态)
⑧ reboot → SPL 按 priority 选新槽 → 走"未确认"启动 → 成功后 bootcontrol 标记
```

upgrade_run 主骨架(app/engine/cmd_upgrade.c:133,只留步骤行,节选):

```c
int upgrade_run(struct upgrade_context *ctx)
{
    pr_info("=== upgrade_run start ===\n");
    ...
    /* 4. Get current A/B slot */
    ctx->current_slot = get_current_slot();
    pr_info("current slot: %d\n", ctx->current_slot);
    ...
    if (precheck_items(ctx, items, count) != 0)   /* ⑤ 挂载守卫在这一步 */
        ...
    /* 9. Switch A/B slot */
    if (ctx->current_slot >= 0) {
        pr_info("switching A/B slot\n");
        set_slot_activity(ctx->storage, ctx->current_slot);
    }
    ...
    pr_info("=== upgrade_run complete ===\n");
}
```

④ 的过滤逻辑(core/slot.c:340,原样;true=跳过该条目,upgrade_plan.c:82 组清单时逐条调用):

```c
bool slot_filter(char ab_suffix, int current_slot)
{
    if (current_slot < 0)
        return (ab_suffix != 0);        /* 非 AB:留无后缀,跳过一切 _a/_b */
    if (ab_suffix == 0)
        return false;                   /* 无后缀条目(uboot 等):共享,保留 */
    if (current_slot == 0 && ab_suffix == 'b')
        return false;   /* A active → update B */
    if (current_slot == 1 && ab_suffix == 'a')
        return false;   /* B active → update A */
    return true;        /* skip same-slot partitions */
}
```

⑦ 的切槽本体(core/slot.c:172,原样):

```c
int set_slot_activity(struct storage_mgr *mgr, int current_slot)
{
    ...
    struct avb_ab_data info;
    if (read_ab_misc(mgr, &info) != 0)      /* 同样先验 CRC */
        return -1;
    ...
    int other = 1 - current_slot;
    info.slots[current_slot].priority = AVB_AB_MAX_PRIORITY - 1;    /* 15 → 14 */
    info.slots[other].priority = AVB_AB_MAX_PRIORITY;               /* → 15 */
    info.slots[other].tries_remaining = AVB_AB_MAX_TRIES_REMAINING; /* → 7 */
    info.slots[other].successful_boot = 0;                          /* 未确认 */

    avb_ab_update_crc(&info);
    return write_ab_misc(mgr, &info);
}
```

⑤ 的挂载守卫(app/engine/upgrade_precheck.c:552,原样):

```c
        if (is_device_mounted(it->dev_path, it->whole_device)) {
            pr_err("precheck: %s target %s is mounted (or a partition of it is)"
                   " — abort before writing\n", it->name, it->dev_path);
            ...
            return -1;      /* 任何目标处于挂载状态 → 整包中止,一个字节都不写 */
        }
```

板上日志对照(OTA 那次):
```
[I][cmd:upgrade] current slot: 0
[I][upgrade:plan] plan: [0] uboot → by-name/uboot        ← 你们的包保留了 uboot 行,OTA 会同步刷
[I][upgrade:plan] plan: [1] boot_b                        ← 写对侧
[I][upgrade:plan] plan: [2] system_b
verify boot_b OK / verify system_b OK
switching A/B slot
```

重启后板上验证(那次实测):
```
SPL: A/B-slot: _b, successful: 0, tries-remain: 7 (select)   ← 新槽未确认
RESC: 'boot_b', blk@0x0003d1b9                                ← boot 分区换到 B
cmdline: android_slotsufix=_b root=PARTUUID=48c6a675...       ← root 换到 system_b(p7)
kernel: EXT4-fs (mmcblk0p7): mounted                          ← 挂载 system_b
resize-all / resize-rootfs: 新槽镜像扩容到分区大小
bootcontrol: Finished                                         ← 标记 _b successful=1
```

**注意你们配置的一个特例**:ota-package-file 保留了 uboot 行 → OTA 会同步刷 U-Boot 分区。新旧 U-Boot 相同时无感,发布 OTA 前务必确认包内 uboot 与板上兼容。

---

## 5. 回退链路(全自动,无需人工)

```
新槽处于未确认(successful=0)状态时,每次启动 U-Boot 阶段 tries-1
  → tries 减到 0 后,该槽不再 bootable
  → SPL 选槽逻辑自动落到另一槽(它是 successful=1 的)
  → 旧系统恢复;新槽保持"失败现场"(tries=0/successful=0)等待下次 OTA 或人工处理
极端情况(两槽都不可用):SPL 按 last_boot 兜底,再兜底 _a;
                         U-Boot proper 双槽全挂时进 fastboot(board.c:651)
```

"tries 减到 0 → 不再 bootable"的机制就是 §2.2 的 `spl_slot_normalize`:tries==0 且 successful==0 且 priority>0 → `spl_slot_set_unbootable()`(priority 清 0);于是 §2.1 的 `spl_slot_is_bootable()` 对它返回 false,SPL 自动落到另一槽——**整条回退链路没有任何一行"回退"代码,全部由"选槽规则 + 递减规则"组合自动涌现**。

**测试回退的唯一正确姿势**(已实测):让被测槽保持未确认——
```
systemctl disable bootcontrol.service     # mask 会因单元文件实体存在而失败,disable 才有效
updateEngine --misc=other                 # 切到对侧,制造 tries=7 未确认状态
reboot ×7                                 # 串口观察 SPL:_b successful:0, tries-remain 6→5→...→0
# 第 8 次:SPL select 换回旧槽,cmdline PARTUUID 变化
systemctl enable bootcontrol.service      # 恢复
```

**常见误判**:看不到 tries 递减,九成是因为当前槽 `successful=1`(bootcontrol 已经标记过)——标记过的槽永远不递减。先 `updateEngine --misc=display` 看状态再测。

---

## 6. 三方读写 misc 对照表(谁在什么时候写)

| 角色 | 读 | 写 | 时机 |
|---|---|---|---|
| SPL | 选槽(spl_ab_get_current_slot)| 首启初始化 / 归一化非法状态 | 每次上电最前 |
| U-Boot proper | 解析 boot/system 分区名、root= | **每次启动递减 tries**(board.c:445)| 每次启动 |
| bootcontrol(updateEngine --misc=now)| 读当前槽 | set_slot_succeed:successful=1, tries=0 | 每次成功启动 |
| updateEngine OTA | 读当前槽 | set_slot_activity:切槽、对侧 tries=7;OTA 过程不写 AB 元数据以外的 misc 区域 | 人工触发 OTA |

三方格式完全一致(AvbABData @ 0x800,大端 CRC32=前 28 字节的标准 CRC32,板上 zlib 实测吻合)——**历史上出现过“每次开机元数据被重置”,根因是当时 updateEngine 是坏的 x86 二进制,从未正确写 misc,并非格式不兼容**(金丝雀法实测:SPL 读到有效元数据不重写)。

---

## 7. 跟着自己的日志走一遍(标准首启全流程)

```
[串口 SPL]     SPL: A/B-slot: _a, successful: 1, tries-remain: 0 (select)
               → 元数据有效,选 A(A 已标记过)
[串口 U-Boot]  A/B-slot: _a ... (select) → RESC: 'boot_a' → DTB: rk-kernel.dtb OK
               → boot mode: normal(BCB 干净的标志;出现 recovery 说明 BCB 有残留)
[内核 cmdline] android_slotsufix=_a ... root=PARTUUID=a26ad83c...
               → U-Boot 已完成 root= 切换
[内核]         EXT4-fs (mmcblk0p6): mounted ... VFS: Mounted root on device 179:6
               → p6=system_a,挂的就是当前槽
[systemd]      Mounting oem.mount / userdata.mount → OK
               → 共享分区跨槽保留
[systemd]      rk182x-installer.service → Finished(新槽 rootfs 无 stamp 才会跑)
               → hm 栈随槽重装(设计如此)
[systemd]      bootcontrol.service → Finished
               → 当前槽 successful=1(之后重启不再递减)
[验证]         updateEngine --misc=display → current_slot=0, slot A successful=1, crc OK
```

对照检查法:每段日志都能在上表找到对应的源码动作;某段缺失/异常时,按源码位置去查。

---

## 8. 常见疑问速查(全部源码实证)

| 现象/疑问 | 答案 | 源码位置 |
|---|---|---|
| 为什么标记成功后 tries 不递减? | 递减条件是 `successful==0 && tries>0` | spl_ab.c / android_ab.c |
| OTA 后新槽 tries 为什么是 7? | set_slot_activity 写入 MAX_TRIES_REMAINING | slot.c:189 |
| successful=1 的槽会被 OTA 覆盖吗? | 会(OTA 写对侧,不管对侧状态),标记随镜像重写丢失——新槽要靠 bootcontrol 重新标记 | cmd_upgrade.c |
| 为什么 OTA 包不能含 misc? | 会重置 AB 元数据(中途断电退回旧槽)且 updateEngine 自管 misc | update_precheck/设计 |
| 为什么 OTA 包不能含 oem? | 挂载守卫:目标已挂载 → 中止整包 | upgrade_precheck.c:552 |
| --misc=other 干什么的? | set_slot_activity:对侧升为活动(tries=7 未确认),手动模拟"OTA 刚切完" | slot.c:172 |
| --misc=now 干什么的? | set_slot_succeed:标记当前槽成功 | slot.c:200 |
| --misc=clean 动什么? | 只清 0x2800 的 1024 字节,不碰 AB(0x800)/BCB(0x4000)| bootmsg.c:202 |
| U-Boot 怎么知道查 boot_a 还是 boot_b? | part_get_info_by_name 的 AB 感知封装,内部读 misc 元数据 | disk/part.c:695 |
| DTB 自带的 root= 会不会打架? | AB 启用时 U-Boot 过滤 DTB 的 root=,只用自己的 | bootargs.c:368 |
| SPL 打印 tries 后还减吗? | 打印的是递减前快照;我们的流在 U-Boot proper 递减 | board.c:445 |

---

## 9. 一页速记

```
misc+0x800 的 32 字节 = 唯一真相源
  slot = {priority, tries, successful}   bootable = priority>0 && (successful || tries>0)
  活动槽:priority=15;备用槽:priority=14;新槽起步:tries=7

启动 = SPL选槽 → U-Boot递减未确认槽 → boot_a/b 取 FIT → system_a/b 取 rootfs → root= 注入
标记 = bootcontrol → --misc=now → successful=1(之后永不递减)
OTA  = 只写对侧 boot+system(+uboot) → 校验 → 切槽(对侧 tries=7)→ 重启
回退 = 未确认槽 tries 递减到 0 → 自动换槽(无需任何人工)

测试口诀:测回退先 disable bootcontrol;制造未确认状态用 --misc=other;
        看状态永远先 --misc=display;标记过的槽不会回退。
```
