#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kconfigconf.py —— 极简 Kconfig 处理器(零第三方依赖)

处理的 Kconfig 语法子集(与内核 Kconfig 语法兼容, 可平滑切换到 kconfiglib):

    mainmenu "标题"
    config NAME
        bool "提示" | int "提示" | string "提示"
        default y|n|<数值>|"字符串" [if <表达式>]
        depends on <表达式>
        help
            ...帮助文本...
    menu "标题" / endmenu
    if <表达式> / endif
    source "相对路径"

表达式支持: 符号名 / y / n / 数字, 运算符 ! && || ()
string 类型: .config 中不带引号存储(make 可直接使用), autoconf.h 中带引号输出

用法:
    python3 scripts/kconfigconf.py \
        --kconfig Kconfig \
        --config .config \
        --autoconf build/generated/autoconf.h

输出:
    --autoconf  生成 C 头文件(启用项: #define CONFIG_xxx 1 / 数值项: #define CONFIG_xxx n)
    --config    把补全默认值后的完整配置回写(Makefile 会 include 它来裁剪驱动)
"""

import argparse
import os
import re
import sys


class KconfigError(Exception):
    pass


class Symbol(object):
    def __init__(self, name, stype, order):
        self.name = name
        self.type = stype            # 'bool' | 'int' | 'string'
        self.prompt = ''
        self.defaults = []           # [(值token, 条件表达式或None), ...]
        self.depends = []            # [表达式AST, ...] (包含外层 if 块的依赖)
        self.user_value = None       # 来自 .config 的值
        self.value = None            # 最终值: bool -> 'y'/'n', int -> 十进制字符串, string -> 不带引号
        self.order = order           # 声明顺序, 用于 .config 输出排序


_EXPR_TOKEN = re.compile(r'\(|\)|!|&&|\|\||[A-Za-z_][A-Za-z0-9_]*|[0-9]+')


def strip_comment(line):
    """去掉行注释, 不处理引号内的 #"""
    out = []
    in_quote = False
    for idx, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        if ch == '#' and not in_quote and (idx == 0 or line[idx - 1] in ' \t'):
            break
        out.append(ch)
    return ''.join(out)


def strip_quotes(text):
    """去掉首尾成对的双引号"""
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


class ExprParser(object):
    """表达式递归下降解析器: or -> and -> unary -> primary"""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def advance(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def parse(self):
        node = self.parse_or()
        if self.peek() is not None:
            raise KconfigError('表达式有多余内容: %s' % ' '.join(self.tokens))
        return node

    def parse_or(self):
        node = self.parse_and()
        while self.peek() == '||':
            self.advance()
            node = ('or', node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_unary()
        while self.peek() == '&&':
            self.advance()
            node = ('and', node, self.parse_unary())
        return node

    def parse_unary(self):
        if self.peek() == '!':
            self.advance()
            return ('not', self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        tok = self.advance()
        if tok is None:
            raise KconfigError('表达式不完整')
        if tok == '(':
            node = self.parse_or()
            if self.advance() != ')':
                raise KconfigError('缺少右括号')
            return node
        if tok in ('!', '&&', '||', ')'):
            raise KconfigError('表达式中有非法记号: %s' % tok)
        return ('sym', tok)


def tokenize_expr(text):
    tokens = _EXPR_TOKEN.findall(text)
    if not tokens:
        raise KconfigError('空表达式: %r' % text)
    return tokens


def eval_expr(node, symbols, warned):
    op = node[0]
    if op == 'sym':
        name = node[1]
        if name == 'y':
            return True
        if name == 'n':
            return False
        sym = symbols.get(name)
        if sym is None or sym.value is None:
            if name not in warned:
                warned.add(name)
                sys.stderr.write('警告: 表达式引用了未定义符号 %s, 按假处理\n' % name)
            return False
        if sym.type == 'int':
            try:
                return int(sym.value) != 0
            except ValueError:
                return False
        return sym.value == 'y'
    if op == 'not':
        return not eval_expr(node[1], symbols, warned)
    if op == 'and':
        return eval_expr(node[1], symbols, warned) and eval_expr(node[2], symbols, warned)
    if op == 'or':
        return eval_expr(node[1], symbols, warned) or eval_expr(node[2], symbols, warned)
    raise KconfigError('未知表达式节点: %r' % (node,))


def parse_kconfig_file(path, symbols, inherited_deps, visited, order_counter):
    abspath = os.path.abspath(path)
    if abspath in visited:
        return
    visited.add(abspath)
    if not os.path.isfile(abspath):
        raise KconfigError('找不到 Kconfig 文件: %s' % path)

    with open(abspath, 'r', encoding='utf-8') as f:
        raw_lines = f.read().splitlines()

    cur = None
    in_help = False
    if_stack = list(inherited_deps)   # 当前 if 块链上的依赖

    i = 0
    while i < len(raw_lines):
        raw = raw_lines[i]
        i += 1

        if in_help:
            # help 文本块: 吞掉缩进行与空行, 直到出现顶格关键字
            if raw[:1] in (' ', '\t') or not raw.strip():
                continue
            in_help = False

        line = strip_comment(raw).strip()
        if not line:
            continue

        parts = line.split(None, 1)
        keyword = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ''

        if keyword == 'config':
            if not rest:
                raise KconfigError('%s: config 缺少符号名' % path)
            if rest in symbols:
                raise KconfigError('%s: 重复定义的符号 %s' % (path, rest))
            cur = Symbol(rest, 'bool', order_counter[0])
            cur.depends.extend(list(if_stack))
            order_counter[0] += 1
            symbols[rest] = cur
        elif keyword in ('bool', 'int', 'string'):
            if cur is None:
                raise KconfigError('%s: %s 出现在 config 之前' % (path, keyword))
            cur.type = keyword
            m = re.match(r'^%s(?:\s+"([^"]*)")?\s*$' % keyword, line)
            if m and m.group(1):
                cur.prompt = m.group(1)
        elif keyword == 'default':
            if cur is None:
                raise KconfigError('%s: default 出现在 config 之前' % path)
            cond = None
            m = re.match(r'^(.*?)\s+if\s+(.+)$', rest)
            if m:
                value_text, cond_text = m.group(1).strip(), m.group(2).strip()
            else:
                value_text, cond_text = rest, None
            if cond_text:
                cond = ExprParser(tokenize_expr(cond_text)).parse()
            cur.defaults.append((value_text, cond))
        elif keyword == 'depends':
            m = re.match(r'^depends\s+on\s+(.+)$', line)
            if not m:
                raise KconfigError('%s: 无法解析: %s' % (path, line))
            if cur is None:
                raise KconfigError('%s: depends 出现在 config 之前' % path)
            cur.depends.append(ExprParser(tokenize_expr(m.group(1))).parse())
        elif keyword == 'help':
            in_help = True
        elif keyword == 'if':
            if not rest:
                raise KconfigError('%s: if 缺少表达式' % path)
            if_stack.append(ExprParser(tokenize_expr(rest)).parse())
        elif keyword == 'endif':
            if if_stack:
                if_stack.pop()
            else:
                sys.stderr.write('警告: %s: 多余的 endif\n' % path)
        elif keyword == 'mainmenu':
            pass    # 顶层菜单标题, 仅展示用
        elif keyword == 'menu':
            pass    # menu 只作分组展示, 不产生依赖
        elif keyword == 'endmenu':
            pass
        elif keyword == 'source':
            rel = rest.strip('"')
            parse_kconfig_file(os.path.join(os.path.dirname(abspath), rel),
                               symbols, list(if_stack), visited, order_counter)
        else:
            raise KconfigError('%s: 无法识别的行: %s' % (path, line))

    if if_stack:
        sys.stderr.write('警告: %s: if 块没有用 endif 关闭\n' % path)


def parse_config_file(path, symbols):
    """读取 .config / defconfig 格式的配置, 写入各符号的 user_value"""
    unknown = []
    if not os.path.isfile(path):
        raise KconfigError('找不到配置文件: %s' % path)

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                m = re.match(r'^#\s*CONFIG_([A-Za-z0-9_]+)\s+is not set$', line)
                if m and m.group(1) in symbols and symbols[m.group(1)].type == 'bool':
                    symbols[m.group(1)].user_value = 'n'
                continue
            m = re.match(r'^CONFIG_([A-Za-z0-9_]+)=(.*)$', line)
            if not m:
                continue
            name, value = m.group(1), m.group(2).strip()
            sym = symbols.get(name)
            if sym is None:
                unknown.append(name)
                continue
            if sym.type == 'bool':
                if value in ('y', 'n'):
                    sym.user_value = value
                else:
                    sys.stderr.write('警告: %s: CONFIG_%s 不是合法的 bool 值(%s)\n' % (path, name, value))
            elif sym.type == 'string':
                sym.user_value = strip_quotes(value)
            else:
                try:
                    sym.user_value = str(int(value, 0))
                except ValueError:
                    sys.stderr.write('警告: %s: CONFIG_%s 不是合法的整数值(%s)\n' % (path, name, value))
    return unknown


def initial_value(sym, symbols, warned):
    if sym.user_value is not None:
        return sym.user_value
    for value_text, cond in sym.defaults:
        if cond is not None and not eval_expr(cond, symbols, warned):
            continue
        if sym.type == 'string':
            return strip_quotes(value_text)
        if sym.type == 'bool':
            if value_text in ('y', 'n'):
                return value_text
            raise KconfigError('CONFIG_%s: bool 的 default 只支持 y/n, 不支持 %r' % (sym.name, value_text))
        try:
            return str(int(value_text, 0))
        except ValueError:
            raise KconfigError('CONFIG_%s: int 的 default 必须是数字, 不支持 %r' % (sym.name, value_text))
    return 'n' if sym.type == 'bool' else '0'


def resolve(symbols):
    """求值: 用户值 > 满足条件的第一个 default > 类型默认值; 依赖不满足的强制关闭"""
    warned = set()
    for sym in symbols.values():
        sym.value = initial_value(sym, symbols, warned)

    # 迭代应用 depends on (本框架的依赖都很简单, 少量迭代即可收敛)
    for _ in range(8):
        changed = False
        for sym in symbols.values():
            met = all(eval_expr(d, symbols, warned) for d in sym.depends)
            if not met:
                if sym.type == 'bool':
                    forced = 'n'
                elif sym.type == 'int':
                    forced = '0'
                else:
                    forced = ''
                if sym.value != forced:
                    sym.value = forced
                    changed = True
        if not changed:
            break


def write_config(path, symbols):
    lines = ['# 自动由 scripts/kconfigconf.py 生成并补全, 手动修改后重新编译即可生效',
             '# 恢复出厂默认: make defconfig', '']
    for sym in sorted(symbols.values(), key=lambda s: s.order):
        if sym.type == 'bool':
            if sym.value == 'y':
                lines.append('CONFIG_%s=y' % sym.name)
            else:
                lines.append('# CONFIG_%s is not set' % sym.name)
        elif sym.type == 'string':
            lines.append('CONFIG_%s=%s' % (sym.name, sym.value))   # 不带引号, make 可直接使用
        else:
            lines.append('CONFIG_%s=%s' % (sym.name, sym.value))
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def write_autoconf(path, symbols):
    lines = ['/* 自动由 scripts/kconfigconf.py 生成, 请勿手改 */',
             '#ifndef BUILD_GENERATED_AUTOCONF_H',
             '#define BUILD_GENERATED_AUTOCONF_H', '']
    for sym in sorted(symbols.values(), key=lambda s: s.order):
        if sym.type == 'bool':
            if sym.value == 'y':
                lines.append('#define CONFIG_%s 1' % sym.name)
            else:
                lines.append('/* CONFIG_%s is not set */' % sym.name)
        elif sym.type == 'string':
            lines.append('#define CONFIG_%s "%s"' % (sym.name, sym.value))
        else:
            lines.append('#define CONFIG_%s %s' % (sym.name, sym.value))
    lines += ['', '#endif']
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser(description='极简 Kconfig 处理器')
    ap.add_argument('--kconfig', default='Kconfig', help='顶层 Kconfig 文件')
    ap.add_argument('--config', default='.config', help='输入/回写的 .config')
    ap.add_argument('--autoconf', default='build/generated/autoconf.h', help='输出的 C 头文件')
    ap.add_argument('--report', action='store_true', help='打印最终配置值')
    args = ap.parse_args()

    symbols = {}
    parse_kconfig_file(args.kconfig, symbols, [], set(), [0])

    unknown = parse_config_file(args.config, symbols)
    for name in unknown:
        sys.stderr.write('警告: CONFIG_%s 在 Kconfig 中未定义, 已忽略\n' % name)

    resolve(symbols)
    write_config(args.config, symbols)
    write_autoconf(args.autoconf, symbols)

    enabled = sum(1 for s in symbols.values() if s.value == 'y' or (s.type == 'int' and int(s.value) != 0))
    print('Kconfig 处理完成: %d 个符号, %d 个启用' % (len(symbols), enabled))
    if args.report:
        for sym in sorted(symbols.values(), key=lambda s: s.order):
            print('  CONFIG_%-24s = %-6s %s' % (sym.name, sym.value, sym.prompt))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KconfigError as e:
        sys.stderr.write('错误: %s\n' % e)
        sys.exit(1)
