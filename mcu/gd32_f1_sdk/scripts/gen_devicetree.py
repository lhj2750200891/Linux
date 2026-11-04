#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_devicetree.py —— 解析 DTB, 生成 devicetree_generated.h (编译期设备树)

流程: cpp 预处理 .dts -> dtc 编译成 .dtb -> 本脚本解析 dtb(扁平设备树 FDT 格式),
按 compatible 识别硬件节点, 生成驱动可直接使用的 C 宏。

status 属性 (与 Linux 语义一致, 控制"是否初始化", 而编译裁剪由 Kconfig 控制):
  status = "okay" (或缺省)   节点启用, 生成实例表, 驱动经 DEVICE_INIT 自动初始化
  status = "disabled"        节点禁用, 只生成 COUNT 0, 驱动不初始化(API 为空实现)

支持的节点类型(由 compatible 区分):
  gd,gpio-leds        子节点 = LED。   容器属性: count;  子节点: gpios = <&gpio 引脚 模式>, init-level = <0|1>
  gd,gpio-keys        子节点 = 按键。   容器属性: count;  子节点: gpios = ..., active-level = <按下电平>
  gd,gpio-matrix-keys 容器属性: row-count, col-count;  row-gpios = <...>, <...>...;  col-gpios = <...>

外设个数(count 等)必须在设备树中描述, 本脚本校验它与实际子节点/引脚列表一致, 不一致则报错。

gpios 单元格式: <&gpio控制器 引脚号 模式>  (控制器节点声明 #gpio-cells = <2>)

生成宏约定(字段与 drivers/gpio/gpio_gd32.h 中 struct gd32_gpio_cfg 一一对应):
  DT_<容器名大写>_COUNT            实例个数
  DT_<容器名大写>_INSTANCES        实例列表(C 结构初始化器)
  DT_<子节点名大写>_IDX            该子节点在列表中的下标(0 起)

用法:
  python3 scripts/gen_devicetree.py --dtb build/dts/gd32f103re.dtb \
      --out build/generated/devicetree_generated.h
"""

import argparse
import os
import re
import struct
import sys

FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9

FDT_MAGIC = 0xD00DFEED

CLASS_LED = 'gd,gpio-leds'
CLASS_KEY = 'gd,gpio-keys'
CLASS_MATRIX = 'gd,gpio-matrix-keys'
CLASS_SYSTICK = 'gd,cortex-m-systick'


class FdtError(Exception):
    pass


class Node(object):
    def __init__(self, name, parent):
        self.name = name
        self.parent = parent
        self.props = {}          # 属性名 -> 原始字节
        self.children = []       # 子节点, 保持声明顺序

    def path(self):
        parts = []
        node = self
        while node is not None:
            if node.name:
                parts.append(node.name)
            node = node.parent
        return '/' + '/'.join(reversed(parts))


def align4(x):
    return (x + 3) & ~3


def parse_dtb(data):
    """解析 FDT (扁平设备树) 二进制, 返回根节点"""
    if len(data) < 40 or struct.unpack_from('>I', data, 0)[0] != FDT_MAGIC:
        raise FdtError('不是合法的 DTB 文件 (magic 不匹配)')

    off_struct, off_strings = struct.unpack_from('>2I', data, 8)

    pos = off_struct
    root = None
    cur = None
    stack = []

    while True:
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4

        if token == FDT_BEGIN_NODE:
            end = data.index(b'\x00', pos)
            name = data[pos:end].decode('utf-8', 'replace')
            pos = align4(end + 1)
            node = Node(name, cur)
            if cur is None:
                if root is not None:
                    raise FdtError('DTB 中出现多个根节点')
                root = node
            else:
                cur.children.append(node)
            stack.append(cur)
            cur = node
        elif token == FDT_END_NODE:
            cur = stack.pop()
        elif token == FDT_PROP:
            length, nameoff = struct.unpack_from('>2I', data, pos)
            pos += 8
            value = data[pos:pos + length]
            pos = align4(pos + length)
            end = data.index(b'\x00', off_strings + nameoff)
            pname = data[off_strings + nameoff:end].decode('utf-8', 'replace')
            cur.props[pname] = value
        elif token == FDT_NOP:
            pass
        elif token == FDT_END:
            break
        else:
            raise FdtError('未知的 FDT token: %d' % token)

    if root is None:
        raise FdtError('DTB 中没有根节点')
    return root


def walk(node):
    """深度优先遍历整棵树"""
    yield node
    for child in node.children:
        for n in walk(child):
            yield n


def prop_u32(node, name, default=None):
    val = node.props.get(name)
    if val is None:
        if default is None:
            raise FdtError('节点 %s 缺少必需属性 %s' % (node.path(), name))
        return default
    if len(val) != 4:
        raise FdtError('节点 %s 的属性 %s 不是 32 位单元' % (node.path(), name))
    return struct.unpack('>I', val)[0]


def prop_u32_list(node, name):
    val = node.props.get(name)
    if val is None or len(val) % 4:
        raise FdtError('节点 %s 缺少属性 %s (或长度不是 4 的倍数)' % (node.path(), name))
    return [v[0] for v in struct.iter_unpack('>I', val)]


def prop_string(node, name, default=''):
    val = node.props.get(name)
    if val is None:
        return default
    return val.split(b'\x00')[0].decode('utf-8', 'replace')


def build_phandle_map(root):
    """phandle 值 -> 节点"""
    table = {}
    for node in walk(root):
        if 'phandle' in node.props:
            table[prop_u32(node, 'phandle')] = node
    return table


def parse_gpio_specs(node, prop_name, root, phandles):
    """解析形如 <&gpioa 7 MODE>, <&gpiob 3 MODE> 的属性, 返回 [(port_idx, pin, mode), ...]"""
    cells = prop_u32_list(node, prop_name)
    specs = []
    i = 0
    while i < len(cells):
        phandle = cells[i]
        i += 1
        gpio_node = phandles.get(phandle)
        if gpio_node is None:
            raise FdtError('节点 %s: %s 中的 phandle 0x%x 无法解析' % (node.path(), prop_name, phandle))
        ncells = prop_u32(gpio_node, '#gpio-cells')
        args = cells[i:i + ncells]
        if len(args) < ncells:
            raise FdtError('节点 %s: %s 中的 gpio 参数不足 (#gpio-cells=%d)' % (node.path(), prop_name, ncells))
        i += ncells
        port_idx = prop_u32(gpio_node, 'port-idx')
        pin = args[0]
        mode = args[1] if ncells > 1 else 0
        specs.append((port_idx, pin, mode))
    return specs


def sanitize(name):
    macro = re.sub(r'[^A-Za-z0-9]', '_', name).upper()
    if not re.match(r'^[A-Z][A-Z0-9_]*$', macro):
        raise FdtError('节点名 %r 无法转换为 C 宏名' % name)
    return macro


def check_count(node, prop_name, declared, actual):
    """校验设备树中声明的个数与实际解析到的实例个数一致"""
    if declared != actual:
        raise FdtError('节点 %s: 属性 %s = %d 与实际个数 %d 不一致, 请修改设备树'
                       % (node.path(), prop_name, declared, actual))


def emit_instances(out, macro_base, specs, levels):
    out.append('#define DT_%s_COUNT %d' % (macro_base, len(specs)))
    if not specs:
        return    # 容器为空(或节点缺失)时只输出 COUNT 0, 驱动按 0 个实例走空实现
    out.append('#define DT_%s_INSTANCES \\' % macro_base)
    for idx, (port, pin, mode) in enumerate(specs):
        line = '\t{ .port = %u, .pin = %u, .mode = 0x%02X, .level = %u }' % (port, pin, mode, levels[idx])
        if idx != len(specs) - 1:
            line += ', \\'
        out.append(line)
    out.append('')


def generate(root, src_note):
    out = []
    out.append('/*')
    out.append(' * devicetree_generated.h —— 由 scripts/gen_devicetree.py 自动生成, 请勿手改')
    out.append(' * %s' % src_note)
    out.append(' * 修改硬件请编辑 boards/ 下设备树(.dts), 重新编译即可。')
    out.append(' */')
    out.append('#ifndef BUILD_GENERATED_DEVICETREE_H')
    out.append('#define BUILD_GENERATED_DEVICETREE_H')
    out.append('')
    out.append('/* 根节点信息 */')
    out.append('#define DT_MODEL "%s"' % prop_string(root, 'model', 'unknown'))
    out.append('#define DT_ROOT_COMPATIBLE "%s"' % prop_string(root, 'compatible', 'unknown'))
    out.append('')

    used_macros = set()
    present = set()          # 设备树中实际出现的容器 (宏基名)
    phandles = build_phandle_map(root)
    stats = []

    for node in walk(root):
        compat = prop_string(node, 'compatible')

        # status = "disabled": 节点不生成实例表(驱动不初始化), 与 Linux 语义一致
        if prop_string(node, 'status', 'okay') == 'disabled':
            if compat in (CLASS_LED, CLASS_KEY, CLASS_MATRIX, CLASS_SYSTICK):
                stats.append((node.name, compat + ' [disabled]', 0))
            continue

        if compat == CLASS_LED:
            base = sanitize(node.name)
            present.add(base)
            count = prop_u32(node, 'count')    # 个数由设备树描述
            specs, levels, idents = [], [], []
            for child in node.children:
                spec = parse_gpio_specs(child, 'gpios', root, phandles)[0]
                specs.append(spec)
                levels.append(prop_u32(child, 'init-level', 0))
                idents.append(child.name)
            check_count(node, 'count', count, len(specs))
            emit_instances(out, base, specs, levels)
            for idx, ident in enumerate(idents):
                macro = 'DT_%s_IDX' % sanitize(ident)
                if macro in used_macros:
                    raise FdtError('重复的节点名: %s' % ident)
                used_macros.add(macro)
                out.append('#define %s %d' % (macro, idx))
            out.append('')
            stats.append((node.name, compat, len(specs)))
        elif compat == CLASS_KEY:
            base = sanitize(node.name)
            present.add(base)
            count = prop_u32(node, 'count')    # 个数由设备树描述
            specs, levels, idents = [], [], []
            for child in node.children:
                spec = parse_gpio_specs(child, 'gpios', root, phandles)[0]
                specs.append(spec)
                levels.append(prop_u32(child, 'active-level', 0))
                idents.append(child.name)
            check_count(node, 'count', count, len(specs))
            emit_instances(out, base, specs, levels)
            for idx, ident in enumerate(idents):
                macro = 'DT_%s_IDX' % sanitize(ident)
                if macro in used_macros:
                    raise FdtError('重复的节点名: %s' % ident)
                used_macros.add(macro)
                out.append('#define %s %d' % (macro, idx))
            out.append('')
            stats.append((node.name, compat, len(specs)))
        elif compat == CLASS_MATRIX:
            base = sanitize(node.name)
            present.add(base + '_ROW')
            present.add(base + '_COL')
            rows = parse_gpio_specs(node, 'row-gpios', root, phandles)
            cols = parse_gpio_specs(node, 'col-gpios', root, phandles)
            check_count(node, 'row-count', prop_u32(node, 'row-count'), len(rows))
            check_count(node, 'col-count', prop_u32(node, 'col-count'), len(cols))
            emit_instances(out, base + '_ROW', rows, [0] * len(rows))
            emit_instances(out, base + '_COL', cols, [0] * len(cols))
            out.append('')
            stats.append((node.name, compat, len(rows) * len(cols)))
        elif compat == CLASS_SYSTICK:
            freq = prop_u32(node, 'clock-frequency')    # CPU 时钟(Hz), SysTick 延时基准
            out.append('#define DT_SYSTICK_CLOCK_FREQUENCY %d' % freq)
            present.add('SYSTICK')
            out.append('')
            stats.append((node.name, compat, 1))

    # 兜底: 某类容器节点在设备树中不存在(或 status="disabled")时补 0 宏,
    # 驱动侧 #if DT_xxx_COUNT > 0 会走空实现, "驱动开了但板上没这硬件"也能编译
    # (systick 特殊: disabled 时频率补 0, 驱动的 #error 会拦住)
    for base in ('LEDS', 'KEYS', 'MATRIX_KEYS_ROW', 'MATRIX_KEYS_COL'):
        if base not in present:
            emit_instances(out, base, [], [])
    if 'SYSTICK' not in present:
        out.append('#define DT_SYSTICK_CLOCK_FREQUENCY 0')
        out.append('')

    out.append('#endif')
    return '\n'.join(out) + '\n', stats


def main():
    ap = argparse.ArgumentParser(description='DTB -> devicetree_generated.h')
    ap.add_argument('--dtb', required=True, help='dtc 生成的 .dtb 文件')
    ap.add_argument('--out', required=True, help='输出的 C 头文件路径')
    args = ap.parse_args()

    with open(args.dtb, 'rb') as f:
        root = parse_dtb(f.read())

    content, stats = generate(root, '源: %s' % args.dtb)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(content)

    print('设备树解析完成 -> %s' % args.out)
    for name, compat, count in stats:
        print('  %-12s (%s): %d 个实例' % (name, compat, count))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except FdtError as e:
        sys.stderr.write('设备树错误: %s\n' % e)
        sys.exit(1)
