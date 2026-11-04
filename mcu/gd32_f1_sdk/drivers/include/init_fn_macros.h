/**
 * @file  init_fn_macros.h
 * @brief 自动初始化机制 —— 裸机版 Linux probe
 *
 * 驱动不需要应用在 main() 里逐个调用 xxx_init():
 *   DEVICE_INIT(fn, level) 把 fn 注册进链接段, 由启动代码在 main 之前
 *   经 __libc_init_array() 自动执行(顺序见启动文件 Reset_Handler)。
 *
 * "匹配" 语义与 Linux 驱动模型一致, 两层条件各管一件事:
 *   1) Kconfig (CONFIG_DRIVER_xxx)          -> 该驱动的 .c 是否参与编译(编译裁剪)
 *   2) 设备树 status = "okay"/"disabled"     -> 是否执行初始化(是否 probe)
 * 两层都满足时 DEVICE_INIT 才生效; 不满足时驱动整体不编入/不初始化。
 *
 * level 保证执行顺序(链接器按数值排序段, 同级按链接顺序):
 *   EARLY(1)   : 最先执行 (systick 等基础服务)
 *   PREINIT(2) : GPIO 等内核级资源
 *   DEVICE(3)  : 外设驱动 (led / key / matrix_key, 依赖前两级)
 *   APPLICATION(4) : 应用级构造
 */
#ifndef DRIVERS_INIT_FN_MACROS_H
#define DRIVERS_INIT_FN_MACROS_H

#ifndef __ASSEMBLER__

/* 优先级: 数值小的先执行(链接段按数值升序 SORT) */
#define GD_INIT_EARLY       1
#define GD_INIT_PREINIT     2
#define GD_INIT_DEVICE      3
#define GD_INIT_APPLICATION 4

/* 定义一个 init 函数并放入 .init_array, 供 __libc_init_array() 在 main 前调用
 *
 * name  : 本注册项的唯一标识(用于生成符号名, 同一文件内不得重复)
 * fn    : 返回 void 无参的初始化函数
 * level : 上面的 GD_INIT_xxx 优先级(其数值参与段名, 保证排序)
 *
 * 用 __attribute__((used)) 保证 -ffunction-sections + --gc-sections 下
 * 没被引用的 init 函数不被裁掉(段被 ld 脚本 KEEP)。
 */
#define _GD_STR2(x)  #x
#define _GD_STR(x)   _GD_STR2(x)

#define DEVICE_INIT(name, fn, level) \
    static void (*_gd_init_##name)(void) __attribute__((used)) \
        __attribute__((section(_GD_INIT_SECT(level, name)))) = fn

#define _GD_INIT_SECT(level, name) \
    _GD_STR(_GD_CONCAT(.init_array., level)) "." #name
#define _GD_CONCAT(a, b) a##b

#endif /* __ASSEMBLER__ */
#endif
