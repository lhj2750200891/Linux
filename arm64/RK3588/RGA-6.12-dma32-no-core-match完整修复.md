# RK3588 Linux 6.12 RGA dma32 修复指南

本文记录从初始 SDK 修复 RGA 老化/压力测试中 `rga: no core match` 的完整方法。对应本仓库已验证提交：

```text
367d4da35ee8 drivers: fixed aging rga error,refer to kernel 6.1.118
```

## 原理

RK3588 的 RGA2 MMU 只能访问 4GiB 以下物理地址。大内存板卡如果只使用普通 `system`、`system-uncached` 或 `cma` heap，压力测试缓冲可能落在 4GiB 以上，RGA2 会被调度策略排除；而部分任务只能由 RGA2 执行，最终没有可用核心并打印 `no core match`。

正确修复是恢复 Rockchip 标准 DMA-BUF dma32 heap：

```text
/dev/dma_heap/system-dma32
/dev/dma_heap/system-uncached-dma32
```

用户态 librga/MPP/测试程序使用标准 `/dev/dma_heap/`，不能用 `/dev/rk_dma_heap/` 替代。

## 初始 SDK 诊断

```bash
cd kernel-6.12
cat drivers/dma-buf/heaps/Makefile
ls drivers/dma-buf/heaps/page_pool.c drivers/dma-buf/heaps/deferred-free-helper.c
ls /dev/dma_heap/
```

如果 Makefile 只编译 `system_heap.o/cma_heap.o`，或者缺少两个辅助文件，并且缺少 `system-dma32`、`system-uncached-dma32`，就是本文问题。

## 推荐：直接应用已验证提交

```bash
cd /path/to/rk3588_6.12.69_sdk/kernel-6.12
git status --short
git cherry-pick 367d4da35ee8
```

也可以导出并应用：

```bash
git format-patch -1 --stdout 367d4da35ee8 > /tmp/rga-dma32-fix.patch
cd /path/to/another/kernel-6.12
git apply /tmp/rga-dma32-fix.patch
```

该提交修改：

```text
arch/arm64/configs/firefly-linux.config
drivers/dma-buf/heaps/Kconfig
drivers/dma-buf/heaps/Makefile
drivers/dma-buf/heaps/page_pool.c
drivers/dma-buf/heaps/page_pool.h
drivers/dma-buf/heaps/deferred-free-helper.c
drivers/dma-buf/heaps/deferred-free-helper.h
drivers/dma-buf/heaps/rk_system_heap.c
drivers/dma-buf/heaps/rk_cma_heap.c
```

## 手工接线

`drivers/dma-buf/heaps/Makefile` 必须包含：

```make
obj-$(CONFIG_DMABUF_HEAPS_DEFERRED_FREE) += deferred-free-helper.o
obj-$(CONFIG_DMABUF_HEAPS_PAGE_POOL)     += page_pool.o
obj-$(CONFIG_DMABUF_HEAPS_SYSTEM)        += rk_system_heap.o
obj-$(CONFIG_DMABUF_HEAPS_CMA)           += rk_cma_heap.o
obj-$(CONFIG_DMABUF_HEAPS_SRAM)           += sram_heap.o
```

关键是使用 `rk_system_heap.o` 和 `rk_cma_heap.o`，而不是主线的 `system_heap.o/cma_heap.o`。

`drivers/dma-buf/heaps/Kconfig` 需要新增：

```kconfig
menuconfig DMABUF_HEAPS_DEFERRED_FREE
	bool "DMA-BUF heaps deferred-free library"

menuconfig DMABUF_HEAPS_PAGE_POOL
	bool "DMA-BUF heaps page-pool library"
```

并让 system heap select 两个库：

```kconfig
config DMABUF_HEAPS_SYSTEM
	bool "DMA-BUF System Heap"
	depends on DMABUF_HEAPS
	select DMABUF_HEAPS_PAGE_POOL
	select DMABUF_HEAPS_DEFERRED_FREE
```

如果辅助文件不存在，可从已验证提交恢复：

```bash
git show 367d4da35ee8:drivers/dma-buf/heaps/page_pool.c > drivers/dma-buf/heaps/page_pool.c
git show 367d4da35ee8:drivers/dma-buf/heaps/page_pool.h > drivers/dma-buf/heaps/page_pool.h
git show 367d4da35ee8:drivers/dma-buf/heaps/deferred-free-helper.c > drivers/dma-buf/heaps/deferred-free-helper.c
git show 367d4da35ee8:drivers/dma-buf/heaps/deferred-free-helper.h > drivers/dma-buf/heaps/deferred-free-helper.h
```

## 6.12 API 注意事项

如果使用未经适配的 6.1 源码，必须检查：

| 旧代码 | 6.12 修复 |
|---|---|
| `register_shrinker(&shrinker, name)` | `shrinker_alloc()`、赋回调、`shrinker_register()` |
| `void *vmap(dmabuf)` | 使用本树 `int vmap(dmabuf, struct iosys_map *)` |
| `unsigned long fd_flags/heap_flags` | `.allocate` 使用 `u32 fd_flags, u64 heap_flags` |
| `.get_pool_size` | 删除，6.12 `dma_heap_ops` 无该成员 |
| `dma_heap_put()` | 删除 |
| `swiotlb_max_segment()` | 删除 |
| `dma_set_max_seg_size()` 返回值 | 6.12 返回 void，直接调用 |

推荐使用 `367d4da35ee8` 的已适配版本，不要直接复制 6.1 文件。

## 配置

在 `arch/arm64/configs/firefly-linux.config` 加入：

```text
CONFIG_DMABUF_HEAPS_SYSTEM=y
CONFIG_DMABUF_HEAPS_CMA=y
CONFIG_DMABUF_HEAPS_ROCKCHIP_SYSTEM_HEAP=y
```

最终配置应包含：

```text
CONFIG_DMABUF_HEAPS=y
CONFIG_DMABUF_HEAPS_SYSTEM=y
CONFIG_DMABUF_HEAPS_CMA=y
CONFIG_DMABUF_HEAPS_PAGE_POOL=y
CONFIG_DMABUF_HEAPS_DEFERRED_FREE=y
```

只改生成后的 `.config` 不够，必须改产品 fragment。

## 编译与验证

```bash
cd /path/to/rk3588_6.12.69_sdk
./build.sh kernel
./build.sh firmware
```

板上验证：

```bash
ls -l /dev/dma_heap/
dmesg | grep -c 'no core match'
grep -E 'CONFIG_DMABUF_HEAPS_(SYSTEM|CMA|PAGE_POOL|DEFERRED_FREE)=' /proc/config.gz 2>/dev/null || true
```

预期节点：

```text
cma
cma-uncached
system
system-dma32
system-uncached
system-uncached-dma32
```

`no core match` 计数应为 `0`，压力程序应优先使用：

```text
/dev/dma_heap/system-uncached-dma32
```

需要调试时：

```bash
echo msg > /sys/kernel/debug/rkrga/debug
cat /sys/kernel/debug/rkrga/scheduler_status
dmesg | grep -i -E 'rga|core match|under 4G|resolution'
```

开机日志中的 `DMA32 empty` 不代表失败；GFP_DMA32 可以回退到低于 4GiB 的 ZONE_DMA，关键是 dma32 heap 节点存在并且 RGA2-only 任务成功。

## 回滚

```bash
git revert 367d4da35ee8
```

回滚后标准 dma32 heap 会消失，RGA2-only 压测可能重新出现 `no core match`。

## 一句话检查

```bash
test -e /dev/dma_heap/system-uncached-dma32 && test "$(dmesg | grep -c 'no core match')" -eq 0 && echo 'RGA dma32 heap fix is active'
```

