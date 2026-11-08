#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_devicetree.py —— 解析 DTB, 生成 devicetree_generated.h (编译期设备树)

流程: cpp 预处理 .dts -> dtc 编译成 .dtb -> 本脚本解析 dtb(扁平设备树 FDT 格式),
按 compatible 识别硬件节点, 生成驱动可直接使用的 C 宏。

status 属性 (与 Linux 语义一致, 控制"是否初始化", 而编译裁剪由 Kconfig 控制):
  status = "okay" (或缺省)   节点启用, 生成实例表, 驱动经 DEVICE_INIT 自动初始化
  status = "disabled"        节点禁用, 只生成 COUNT 0, 驱动不初始化(API 为空实现)

status 可写在两级:
  容器节点 (uarts/leds/...)  整类硬件的总开关, disabled 时整类不生成实例
  实例子节点 (uart1/led1/...) 单个实例开关, disabled 时该实例不进实例表,
                              其余实例下标自动重排, 不用它就关, 不必注释整段节点
  (两级都写时子节点可覆盖容器: 容器 okay + 子节点 disabled = 只关这一个)

count 属性为可选: 未写时按启用的子节点个数自动计数; 写了则校验一致
  (校验口径 = 启用(status != disabled)的子节点个数)

支持的节点类型(由 compatible 区分):
  gd,gpio-leds        子节点 = LED。   容器属性: count;  子节点: gpios = <&gpio 引脚 模式>, init-level = <0|1>
  gd,gpio-keys        子节点 = 按键。   容器属性: count;  子节点: gpios = ..., active-level = <按下电平>
  gd,gpio-matrix-keys 容器属性: row-count, col-count;  row-gpios = <...>, <...>...;  col-gpios = <...>
  gd,gd32-uart        子节点 = 串口实例。容器属性: count;
                      子节点(两种引脚描述方式二选一):
                        pgroup = <&usart0 0>   引用 dtsi 预定义引脚组(组号 0=m0, 1=m1...)
                        tx-gpios = <&gpioa 9>, rx-gpios = <&gpiob 7>   用户手动组合引脚
                        (数据手册 2.6 节中标了 USARTx_TX/RX 复用功能的引脚均可)
                      子节点其他属性: baud-rate, line-ctl = <数据位 停止位 校验>,
                      dma-mode = <0|1>, int-mode = <GD32_UART_INT_xxx>, rx-pull = <0|1>,
                      console = <1>(printf 重定向到该实例)
  gd,gd32-uart-pingroup  SoC dtsi 中的引脚组容器, groups 属性描述:
                      <组号 &tx端口 tx引脚 &rx端口 rx引脚 是否重映射> ...
  gd,gd32-general-timer  子节点 = 通用定时器实例 (TIMER1~4)。容器属性: count;
                      子节点: timer-idx = <1~4>, mode = <TIMEBASE/PWM/FREQ/PWMCAP>,
                      clock-hz, prescaler, period-us, irq-mode, remap;
                      通道子节点 chN: channel = <0~3>, gpios = <&gpiox 引脚 模式>,
                      duty-tenk(pwm), pwm-mode(pwm), polarity(freq)

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
CLASS_UART = 'gd,gd32-uart'
CLASS_BASIC_TIMER = 'gd,gd32-basic-timer'
CLASS_GENERAL_TIMER = 'gd,gd32-general-timer'
CLASS_UART_PINGROUP = 'gd,gd32-uart-pingroup'
CLASS_UART_PERIPH = 'gd,gd32-uart-periph'


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
    if declared is not None and declared != actual:
        raise FdtError('节点 %s: 属性 %s = %d 与实际个数 %d 不一致, 请修改设备树'
                       % (node.path(), prop_name, declared, actual))


def child_enabled(child):
    """实例子节点是否启用: status 缺省/\"okay\" 启用, \"disabled\" 跳过"""
    st = prop_string(child, 'status', 'okay')
    if st not in ('okay', 'disabled'):
        raise FdtError('节点 %s: status 应为 \"okay\"/\"disabled\", 当前 \"%s\"'
                       % (child.path(), st))
    return st != 'disabled'


# disabled 实例的哨兵下标: 所有驱动 API 均校验 idx < DT_xxx_COUNT, 越界即安全空操作
DT_IDX_DISABLED = 0xFF


def emit_idx_macros(out, node, used_macros, enabled_idents, disabled_idents):
    """生成 DT_<子节点名>_IDX 宏。

    enabled_idents:  启用实例, 依次编号 0,1,2...
    disabled_idents: status="disabled" 的实例, 固定哨兵下标 DT_IDX_DISABLED(0xFF),
                     引用它的应用代码无需修改 —— 驱动 API 越界校验后安全空操作。
    """
    for idx, ident in enumerate(enabled_idents):
        macro = 'DT_%s_IDX' % sanitize(ident)
        if macro in used_macros:
            raise FdtError('重复的节点名: %s' % ident)
        used_macros.add(macro)
        out.append('#define %s %d' % (macro, idx))
    for ident in disabled_idents:
        macro = 'DT_%s_IDX' % sanitize(ident)
        if macro in used_macros:
            raise FdtError('重复的节点名: %s' % ident)
        used_macros.add(macro)
        out.append('#define %s DT_IDX_DISABLED   /* status=\\"disabled\\" 实例, 驱动 API 安全空操作 */'
                   % macro)


def emit_instances(out, macro_base, specs, levels, extras=None):
    """生成 DT_<base>_COUNT / _INSTANCES 宏。

    extras: 可选的每实例扩展字段 (如按键 trigger), 追加 .trigger = n。
    """
    out.append('#define DT_%s_COUNT %d' % (macro_base, len(specs)))
    if not specs:
        return    # 容器为空(或节点缺失)时只输出 COUNT 0, 驱动按 0 个实例走空实现
    out.append('#define DT_%s_INSTANCES \\' % macro_base)
    for idx, (port, pin, mode) in enumerate(specs):
        line = '\t{ .port = %u, .pin = %u, .mode = 0x%02X, .level = %u' % (port, pin, mode, levels[idx])
        if extras is not None and idx < len(extras):
            line += ', .trigger = %u' % extras[idx]
        line += ' }'
        if idx != len(specs) - 1:
            line += ', \\'
        out.append(line)
    out.append('')


# ---------------------------------------------------------------- UART ----

def collect_uart_pingroups(root, phandles):
    """解析 dtsi 中所有 gd,gd32-uart-pingroup 节点。

    返回 {uart-idx: {组号: (tx_port, tx_pin, rx_port, rx_pin, remap)}}。
    groups 属性每个条目 6 个单元:
      <组号 &tx端口 tx引脚 &rx端口 rx引脚 是否重映射>
    (&gpiox 引用经 dtc 变成 phandle 数值)
    """
    table = {}
    for node in walk(root):
        if prop_string(node, 'compatible') != CLASS_UART_PINGROUP:
            continue
        idx = prop_u32(node, 'uart-idx')
        cells = prop_u32_list(node, 'groups')
        if len(cells) % 6:
            raise FdtError('节点 %s: groups 属性单元数不是 6 的倍数' % node.path())
        entry = {}
        for i in range(0, len(cells), 6):
            grp, tx_ph, tx_pin, rx_ph, rx_pin, remap = cells[i:i + 6]
            tx_node = phandles.get(tx_ph)
            rx_node = phandles.get(rx_ph)
            if tx_node is None or rx_node is None:
                raise FdtError('节点 %s: groups 中的 phandle 无法解析' % node.path())
            entry[grp & 0xFF] = (prop_u32(tx_node, 'port-idx'), tx_pin,
                                 prop_u32(rx_node, 'port-idx'), rx_pin,
                                 remap & 0x01)
        table[idx] = entry
    return table


class UartInstance(object):
    """设备树 uart 子节点解析结果 (字段与 struct gd32_uart_cfg 一一对应)"""

    def __init__(self):
        self.periph = 0            # USART0/1/2, UART3/4 基址宏名 (来自父 SoC 节点 reg)
        self.uart_idx = 0
        self.tx_port = 0
        self.tx_pin = 0
        self.rx_port = 0
        self.rx_pin = 0
        self.remap = 0
        self.rx_pull = 0
        self.data_bits = 0
        self.stop_bits = 0
        self.parity = 0
        self.dma_mode = 0
        self.int_mode = 0
        self.console = 0
        self.baud_rate = 115200
        self.rx_buf_size = 128

    def emit_line(self):
        return ('{ .periph = %s, .uart_idx = %u, '
                '.tx_port = %u, .tx_pin = %u, .rx_port = %u, .rx_pin = %u, '
                '.remap = %u, .rx_pull = %u, .data_bits = %u, .stop_bits = %u, '
                '.parity = %u, .dma_mode = %u, .int_mode = %u, .console = %u, '
                '.baud_rate = %u, .rx_buf_size = %u }'
                % (self.periph, self.uart_idx, self.tx_port, self.tx_pin,
                   self.rx_port, self.rx_pin, self.remap, self.rx_pull,
                   self.data_bits, self.stop_bits, self.parity,
                   self.dma_mode, self.int_mode, self.console,
                   self.baud_rate, self.rx_buf_size))


# uart-idx (引用的 SoC uart 节点) -> 外设基址宏名
def uart_periph_macro(idx):
    names = ['USART0', 'USART1', 'USART2', 'UART3', 'UART4']
    if idx >= len(names):
        raise FdtError('uart-idx %d 超出范围 (0~4)' % idx)
    return names[idx]


def uart_parse_instance(node, root, phandles, pingroups):
    """解析一个 uart 子节点 (uarts 容器的直接子节点)。

    引脚两种写法 (二选一, 都写以 pgroup 为准):
      pgroup = <&usart0 1>                    预定义引脚组 (dtsi 中的 pin-group 节点)
      tx-gpios = <&gpioa 9>, rx-gpios = <&gpiob 7>   手动组合 (数据手册 2.6 节复用脚)
    """
    inst = UartInstance()

    # ---- 引脚与外设序号: pgroup 优先 ----
    if 'pgroup' in node.props:
        cells = prop_u32_list(node, 'pgroup')
        if len(cells) != 2:
            raise FdtError('节点 %s: pgroup 应为 <&uartx 组号> 两个单元' % node.path())
        grp_node = phandles.get(cells[0])
        if grp_node is None:
            raise FdtError('节点 %s: pgroup 引用无法解析' % node.path())
        grp = cells[1] & 0xFF
        # 从被引用的 SoC uart 外设节点取 uart-idx (决定 periph 宏名)
        inst.uart_idx = prop_u32(grp_node, 'uart-idx')
        table = pingroups.get(inst.uart_idx)
        if table is None or grp not in table:
            raise FdtError('节点 %s: 串口 %d 的引脚组 %d 不存在 (检查 dtsi pin-group 节点)'
                           % (node.path(), inst.uart_idx, grp))
        tx_port, tx_pin, rx_port, rx_pin, remap = table[grp]
        inst.tx_port, inst.tx_pin = tx_port, tx_pin
        inst.rx_port, inst.rx_pin = rx_port, rx_pin
        inst.remap = remap
    elif 'tx-gpios' in node.props and 'rx-gpios' in node.props:
        # 手动组合: tx/rx 各一个 gpio 引用; uart-idx 必须由本节点 uart-idx 属性给出
        if 'uart-idx' in node.props:
            inst.uart_idx = prop_u32(node, 'uart-idx')
        else:
            raise FdtError('节点 %s: 手动组合引脚时必须提供 uart-idx 属性 '
                           '(标明属于 USART0~UART4 中哪个串口)' % node.path())
        tx = parse_gpio_specs(node, 'tx-gpios', root, phandles)
        rx = parse_gpio_specs(node, 'rx-gpios', root, phandles)
        if len(tx) != 1 or len(rx) != 1:
            raise FdtError('节点 %s: tx-gpios/rx-gpios 应各只有一组引脚' % node.path())
        inst.tx_port, inst.tx_pin = tx[0][0], tx[0][1]
        inst.rx_port, inst.rx_pin = rx[0][0], rx[0][1]
        inst.remap = prop_u32(node, 'remap', 0)    # 手动组合时由用户指明是否重映射
    else:
        raise FdtError('节点 %s: 缺少引脚描述 (pgroup 或 tx-gpios+rx-gpios 二选一)'
                       % node.path())

    inst.periph = uart_periph_macro(inst.uart_idx)

    # ---- 其余属性 (均有缺省值) ----
    inst.baud_rate = prop_u32(node, 'baud-rate', 115200)
    inst.data_bits = prop_u32(node, 'data-bits', 0)       # GD32_UART_DATA_8/9
    inst.stop_bits = prop_u32(node, 'stop-bits', 0)       # GD32_UART_STOP_1/0_5/2
    inst.parity = prop_u32(node, 'parity', 0)             # GD32_UART_PM_NONE/EVEN/ODD
    inst.dma_mode = prop_u32(node, 'dma-mode', 0)         # 0=关 1=开 (UART4 无 DMA 自动退化)
    inst.int_mode = prop_u32(node, 'int-mode', 0)         # GD32_UART_INT_xxx
    inst.rx_pull = prop_u32(node, 'rx-pull', 0)           # RX 输入: 0=浮空 1=上拉
    inst.console = prop_u32(node, 'console', 0)           # 1=printf 重定向到本实例
    inst.rx_buf_size = prop_u32(node, 'rx-buf-size', 128)

    if inst.baud_rate == 0 or inst.baud_rate > 4000000:
        raise FdtError('节点 %s: baud-rate %d 不合理' % (node.path(), inst.baud_rate))
    return inst



def generate(root, src_note):
    out = []
    out.append('/*')
    out.append(' * devicetree_generated.h —— 由 scripts/gen_devicetree.py 自动生成, 请勿手改')
    out.append(' * %s' % src_note)
    out.append(' * 修改硬件请编辑 arm/boards/ 下设备树(.dts), 重新编译即可。')
    out.append(' */')
    out.append('#ifndef BUILD_GENERATED_DEVICETREE_H')
    out.append('#define BUILD_GENERATED_DEVICETREE_H')
    out.append('')
    out.append('/* status="disabled" 实例的哨兵下标: 驱动 API 均校验 idx < DT_xxx_COUNT,')
    out.append(' * 传入哨兵即安全空操作 —— 应用代码引用被裁剪实例时无需修改 */')
    out.append('#define DT_IDX_DISABLED 0xFF')
    out.append('')
    out.append('/* 根节点信息 */')
    out.append('#define DT_MODEL "%s"' % prop_string(root, 'model', 'unknown'))
    out.append('#define DT_ROOT_COMPATIBLE "%s"' % prop_string(root, 'compatible', 'unknown'))
    out.append('')

    used_macros = set()
    present = set()          # 设备树中实际出现的容器 (宏基名)
    phandles = build_phandle_map(root)
    pingroups = collect_uart_pingroups(root, phandles)
    stats = []

    for node in walk(root):
        compat = prop_string(node, 'compatible')

        # status = "disabled": 节点不生成实例表(驱动不初始化), 与 Linux 语义一致
        # (子节点级 status 由各容器分支的 child_enabled() 处理, 可关单个实例)
        st = prop_string(node, 'status', 'okay')
        if st not in ('okay', 'disabled'):
            raise FdtError('节点 %s: status 应为 "okay"/"disabled", 当前 "%s"'
                           % (node.path(), st))
        if st == 'disabled':
            if compat in (CLASS_LED, CLASS_KEY, CLASS_MATRIX, CLASS_SYSTICK,
                      CLASS_UART, CLASS_BASIC_TIMER, CLASS_GENERAL_TIMER):
                stats.append((node.name, compat + ' [disabled]', 0))
            continue

        if compat == CLASS_LED:
            base = sanitize(node.name)
            present.add(base)
            count = prop_u32(node, 'count') if 'count' in node.props else None    # 可选, 缺省按启用子节点个数
            specs, levels, idents, dis = [], [], [], []
            for child in node.children:
                if not child_enabled(child):
                    dis.append(child.name)
                    continue
                spec = parse_gpio_specs(child, 'gpios', root, phandles)[0]
                specs.append(spec)
                levels.append(prop_u32(child, 'init-level', 0))
                idents.append(child.name)
            check_count(node, 'count', count, len(specs))
            emit_instances(out, base, specs, levels)
            emit_idx_macros(out, node, used_macros, idents, dis)
            out.append('')
            stats.append((node.name, compat, len(specs)))
        elif compat == CLASS_KEY:
            base = sanitize(node.name)
            present.add(base)
            count = prop_u32(node, 'count') if 'count' in node.props else None    # 可选, 缺省按启用子节点个数
            # 工作方式: 0=EXTI 中断(默认, KEY_MODE_IRQ)  1=轮询(KEY_MODE_POLL)
            key_mode = prop_u32(node, 'key-mode', 0)
            if key_mode not in (0, 1):
                raise FdtError('节点 %s: key-mode 应为 KEY_MODE_IRQ(0)/KEY_MODE_POLL(1), dt-bindings/input/gd32f10x-key.h'
                               % node.path())
            # 轮询消抖时间 ms (仅轮询模式使用, 默认 20)
            debounce = prop_u32(node, 'debounce-ms', 20)
            specs, levels, idents, triggers, dis = [], [], [], [], []
            for child in node.children:
                if not child_enabled(child):
                    dis.append(child.name)
                    continue
                spec = parse_gpio_specs(child, 'gpios', root, phandles)[0]
                specs.append(spec)
                # ---- 有效电平 active-level: 显式配置优先, 缺省按上下拉推导 ----
                #   IPU 上拉(0x4x) -> 按下接地 -> 低有效(0)
                #   IPD 下拉(0x2x) -> 按下接高 -> 高有效(1)
                #   浮空/模拟输入 -> 无法推导, 默认低有效(0)
                if 'active-level' in child.props:
                    lvl = prop_u32(child, 'active-level', 0)
                    if lvl not in (0, 1):
                        raise FdtError('节点 %s: active-level 应为 0(低有效)/1(高有效)'
                                       % child.path())
                else:
                    lvl = 1 if (spec[2] & 0x20) else 0
                levels.append(lvl)
                # ---- 中断触发类型 trigger: 显式配置优先, 缺省按有效电平推导 ----
                #   低有效 -> 按下产生下降沿 KEY_TRIG_FALLING(1)
                #   高有效 -> 按下产生上升沿 KEY_TRIG_RISING(0)
                # 轮询模式不使用 trigger (电平判定走 active-level, 高/低有效均可)
                if 'trigger' in child.props:
                    trig = prop_u32(child, 'trigger', 1)
                else:
                    trig = 1 if lvl == 0 else 0
                if trig not in (0, 1, 2):
                    raise FdtError('节点 %s: trigger 应为 KEY_TRIG_RISING(0)/KEY_TRIG_FALLING(1)/KEY_TRIG_BOTH(2)'
                                   % child.path())
                triggers.append(trig)
                idents.append(child.name)
            check_count(node, 'count', count, len(specs))
            emit_instances(out, base, specs, levels, triggers)
            out.append('#define DT_%s_MODE %d' % (base, key_mode))
            out.append('#define DT_%s_DEBOUNCE_MS %d' % (base, debounce))
            emit_idx_macros(out, node, used_macros, idents, dis)
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
        elif compat == CLASS_BASIC_TIMER:
            # 基本定时器 TIMER5/6: 实例 = 每个子节点一个, 属性
            #   timer-idx:  硬件号 5 或 6
            #   clock-hz:   输入时钟 (APB1 定时器时钟, 板级可覆写)
            #   prescaler:  想要的分频目标 (1 = 分到 1MHz); 实际 PSC = clock-hz/(prescaler*1e6) - 1
            #   period-us:  周期 (us), 重装值 = period-us * prescaler - 1
            #   irq-mode:   1=溢出中断(默认, 需配回调) 0=纯计数无中断
            base = sanitize(node.name)
            present.add(base)
            count = prop_u32(node, 'count') if 'count' in node.props else None    # 可选, 缺省按启用子节点个数
            idents, inst_lines, dis = [], [], []
            for child in node.children:
                if not child_enabled(child):
                    dis.append(child.name)
                    continue
                tidx = prop_u32(child, 'timer-idx')
                if tidx not in (5, 6):
                    raise FdtError('节点 %s: 基本定时器 timer-idx 只能是 5 或 6 (TIMER5/6)'
                                   % child.path())
                clk = prop_u32(child, 'clock-hz', 54000000)
                psc = prop_u32(child, 'prescaler', 1)
                period = prop_u32(child, 'period-us')
                if psc == 0 or period == 0:
                    raise FdtError('节点 %s: prescaler/period-us 必须为正整数'
                                   % child.path())
                # 换算 (prescaler=N 为分频比: 计数时钟 = clock/N, 1 tick = N/clock 秒):
                #   PSC 装入值 = N - 1          (16 位, N <= 65536)
                #   CAR 装入值 = period_us * clock / (N * 1e6) - 1   (16 位)
                # 例: clock=108MHz, N=10800 -> 10kHz, 1tick=100us,
                #     period-us=500000 -> CAR+1 = 5000 (500ms)
                if psc > 0x10000:
                    raise FdtError('节点 %s: prescaler=%d 超出 16 位 (最大 65536)'
                                   % (child.path(), psc))
                psc_reg = psc - 1
                # tick 数 (即 CAR+1) = period(us) * 计数时钟(Hz) / 1e6
                #   计数时钟 = clk / psc
                arr_reg = (period * clk + psc * 1000000 - 1) // (psc * 1000000)
                if arr_reg == 0 or arr_reg > 0x10000:
                    raise FdtError('节点 %s: period-us=%d 超出 16 位重装值 (prescaler=%d 时最长 %d us),'
                                   ' 增大 prescaler'
                                   % (child.path(), period, psc,
                                      0x10000 * psc * 1000000 // clk))
                irq = prop_u32(child, 'irq-mode', 1)
                inst_lines.append('\t{ .timer_idx = %d, .clock_hz = %u, .psc_reg = %u, '
                                  '.arr_reg = %u, .irq_mode = %u }'
                                  % (tidx, clk, psc_reg, arr_reg - 1, irq)
                                  )
                idents.append(child.name)
            check_count(node, 'count', count, len(inst_lines))
            out.append('#define DT_%s_COUNT %d' % (base, len(inst_lines)))
            if inst_lines:
                out.append('#define DT_%s_INSTANCES \\' % base)
                for i, line in enumerate(inst_lines):
                    if i != len(inst_lines) - 1:
                        line += ', \\'
                    out.append(line)
                out.append('')
            emit_idx_macros(out, node, used_macros, idents, dis)
            out.append('')
            stats.append((node.name, compat, len(inst_lines)))
        elif compat == CLASS_GENERAL_TIMER:
            # 通用定时器 TIMER1~4: 实例 = 每个子节点一个, 子节点属性:
            #   timer-idx:  硬件号 1~4
            #   clock-hz:   输入时钟 (APB1 定时器时钟, 默认 108MHz)
            #   mode:       GD32_TIMER_MODE_TIMEBASE(0)/PWM(1)/FREQ(2)/PWMCAP(3)
            #   prescaler:  分频比 N (计数时钟 = clock-hz/N)
            #   period-us:  周期 us (timebase/pwm 必配)
            #   irq-mode:   1=开中断(默认) 0=纯计数
            #   remap:      0=默认 1=部分重映射 2=完全重映射 (TIMER3 仅 1, TIMER4 无)
            # 通道子节点 chN (pwm 1~4 个 / freq 1 个 / pwmcap 2 个相邻对 / timebase 无):
            #   channel:  通道号 0~3
            #   gpios:    <&gpiox 引脚 模式>; pwm=GD32_MODE_AF_PP, 捕获=浮空/IPU/IPD
            #   duty-tenk: (pwm) 万分比占空 1~9999, 缺省 5000
            #   pwm-mode:  (pwm) 0=PWM0(默认) 1=PWM1
            #   polarity:  (freq) 0=上升沿(默认) 1=下降沿; pwmcap 固定双边沿不配
            base = sanitize(node.name)
            present.add(base)
            count = prop_u32(node, 'count') if 'count' in node.props else None    # 可选, 缺省按启用子节点个数
            seen_hw = {}
            idents, inst_lines, dis = [], [], []
            for child in node.children:
                if not child_enabled(child):
                    dis.append(child.name)
                    continue
                tidx = prop_u32(child, 'timer-idx')
                if tidx not in (1, 2, 3, 4):
                    raise FdtError('节点 %s: 通用定时器 timer-idx 只能是 1~4 (TIMER1~4)'
                                   % child.path())
                if tidx in seen_hw:
                    raise FdtError('节点 %s: TIMER%d 已由节点 %s 使用, 一个硬件定时器只能一个实例'
                                   % (child.path(), tidx, seen_hw[tidx]))
                seen_hw[tidx] = child.name
                mode = prop_u32(child, 'mode', 0)
                if mode not in (0, 1, 2, 3):
                    raise FdtError('节点 %s: mode 应为 GD32_TIMER_MODE_TIMEBASE(0)/PWM(1)/'
                                   'FREQ(2)/PWMCAP(3), 见 dt-bindings/timer/gd32f10x-timer.h'
                                   % child.path())
                clk = prop_u32(child, 'clock-hz', 108000000)
                psc = prop_u32(child, 'prescaler', 1)
                period = prop_u32(child, 'period-us', 0)
                irq = prop_u32(child, 'irq-mode', 1)
                remap = prop_u32(child, 'remap', 0)
                if remap not in (0, 1, 2):
                    raise FdtError('节点 %s: remap 应为 0(默认)/1(部分)/2(完全)' % child.path())
                if remap and tidx == 4:
                    raise FdtError('节点 %s: TIMER4 无重映射引脚' % child.path())
                if remap == 2 and tidx == 3:
                    raise FdtError('节点 %s: TIMER3 只有部分重映射 (remap=1)' % child.path())
                # PSC/CAR 换算 (与 basic-timer 相同公式)
                if psc == 0 or psc > 0x10000:
                    raise FdtError('节点 %s: prescaler=%d 非法 (1~65536)' % (child.path(), psc))
                psc_reg = psc - 1
                arr_reg = 0
                if mode in (0, 1):
                    if period == 0:
                        raise FdtError('节点 %s: timebase/pwm 模式必须配 period-us' % child.path())
                    arr_reg = (period * clk + psc * 1000000 - 1) // (psc * 1000000)
                    if arr_reg == 0 or arr_reg > 0x10000:
                        raise FdtError('节点 %s: period-us=%d 超出 16 位重装值 (prescaler=%d 时'
                                       ' 最长 %d us), 增大 prescaler'
                                       % (child.path(), period, psc,
                                          0x10000 * psc * 1000000 // clk))
                    arr_reg -= 1
                # ---- 通道子节点 -> 4 个槽位 (ch=0xFF 表示未用) ----
                slots = [{'ch': 0xFF, 'port': 0, 'pin': 0, 'pinmode': 0,
                          'aux': 0, 'val': 0} for _ in range(4)]
                for gch in child.children:
                    if not child_enabled(gch):
                        continue
                    chan = prop_u32(gch, 'channel')
                    if chan not in (0, 1, 2, 3):
                        raise FdtError('节点 %s: channel 应为 0~3' % gch.path())
                    if slots[chan]['ch'] != 0xFF:
                        raise FdtError('节点 %s: 通道 %d 重复配置' % (gch.path(), chan))
                    spec = parse_gpio_specs(gch, 'gpios', root, phandles)[0]
                    slot = slots[chan]
                    slot['ch'], slot['port'], slot['pin'], slot['pinmode'] = (
                        chan, spec[0], spec[1], spec[2])
                    if mode == 1:      # pwm: duty-tenk 万分比 -> 比较值 tick
                        dval = prop_u32(gch, 'duty-tenk', 5000)
                        if dval < 1 or dval > 9999:
                            raise FdtError('节点 %s: duty-tenk 应为 1~9999 (5000=50%%)'
                                           % gch.path())
                        val = dval * (arr_reg + 1) // 10000
                        slot['val'] = max(1, min(val, arr_reg))
                        slot['aux'] = prop_u32(gch, 'pwm-mode', 0)
                    elif mode == 2:    # freq: 捕获边沿
                        pol = prop_u32(gch, 'polarity', 0)
                        if pol not in (0, 1):
                            raise FdtError('节点 %s: polarity 应为 0(上升沿)/1(下降沿)'
                                           % gch.path())
                        slot['aux'] = pol
                used = [s for s in slots if s['ch'] != 0xFF]
                # ---- 模式与通道个数校验 ----
                if mode == 0 and used:
                    raise FdtError('节点 %s: timebase 模式不配通道(无引脚输出/输入)'
                                   % child.path())
                if mode == 1 and not used:
                    raise FdtError('节点 %s: pwm 模式必须配 chN 通道子节点' % child.path())
                if mode == 2 and len(used) != 1:
                    raise FdtError('节点 %s: freq 模式必须恰好配一个 chN 通道' % child.path())
                if mode == 3:
                    chs = sorted(s['ch'] for s in used)
                    if chs not in ([0, 1], [2, 3]):
                        raise FdtError('节点 %s: pwmcap 模式必须配一对相邻通道'
                                       ' (CH0+CH1 或 CH2+CH3), 低号直连上升沿/高号交叉下降沿'
                                       % child.path())
                # ---- 输出行 ----
                chs_str = ', '.join('{%d, %d, %d, 0x%02X, %d, %d}'
                                    % (s['ch'], s['port'], s['pin'], s['pinmode'],
                                       s['aux'], s['val']) for s in slots)
                inst_lines.append('\t{ .timer_idx = %d, .clock_hz = %u, .psc_reg = %u, '
                                  '.arr_reg = %u, .mode = %u, .irq_mode = %u, .remap = %u, '
                                  '.chans = { %s } }'
                                  % (tidx, clk, psc_reg, arr_reg, mode, irq, remap, chs_str))
                idents.append(child.name)
            check_count(node, 'count', count, len(inst_lines))
            out.append('#define DT_%s_COUNT %d' % (base, len(inst_lines)))
            if inst_lines:
                out.append('#define DT_%s_INSTANCES \\' % base)
                for i, line in enumerate(inst_lines):
                    if i != len(inst_lines) - 1:
                        line += ', \\'
                    out.append('\t' + line)
                out.append('')
            emit_idx_macros(out, node, used_macros, idents, dis)
            out.append('')
            stats.append((node.name, compat, len(inst_lines)))
        elif compat == CLASS_UART:
            base = sanitize(node.name)
            present.add(base)
            count = prop_u32(node, 'count') if 'count' in node.props else None    # 可选, 缺省按启用子节点个数
            idents = []
            inst_lines = []
            max_buf = 1
            dis = []
            for child in node.children:
                if not child_enabled(child):
                    dis.append(child.name)
                    continue
                inst = uart_parse_instance(child, root, phandles, pingroups)
                if inst.rx_buf_size > max_buf:
                    max_buf = inst.rx_buf_size
                idents.append(child.name)
                inst_lines.append(inst.emit_line())
            check_count(node, 'count', count, len(inst_lines))
            out.append('#define DT_%s_COUNT %d' % (base, len(inst_lines)))
            if inst_lines:
                out.append('#define DT_%s_INSTANCES \\' % base)
                for i, line in enumerate(inst_lines):
                    if i != len(inst_lines) - 1:
                        line += ', \\'
                    out.append('\t' + line)
                out.append('')
            # 驱动的静态接收缓冲数组按最大实例缓冲区对齐
            out.append('#define DT_%s_MAX_BUF_SIZE %d' % (base, max_buf))
            emit_idx_macros(out, node, used_macros, idents, dis)
            out.append('')
            stats.append((node.name, compat, len(inst_lines)))

    # 兜底: 某类容器节点在设备树中不存在(或 status="disabled")时补 0 宏,
    # 驱动侧 #if DT_xxx_COUNT > 0 会走空实现, "驱动开了但板上没这硬件"也能编译
    # (systick 特殊: disabled 时频率补 0, 驱动的 #error 会拦住)
    for base in ('LEDS', 'KEYS', 'MATRIX_KEYS_ROW', 'MATRIX_KEYS_COL'):
        if base not in present:
            emit_instances(out, base, [], [])
    if 'UARTS' not in present:
        out.append('#define DT_UARTS_COUNT 0')
        out.append('#define DT_UARTS_MAX_BUF_SIZE 1')
        out.append('')
    if 'BASIC_TIMERS' not in present:
        out.append('#define DT_BASIC_TIMERS_COUNT 0')
        out.append('')
    if 'GENERAL_TIMERS' not in present:
        out.append('#define DT_GENERAL_TIMERS_COUNT 0')
        out.append('')
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
