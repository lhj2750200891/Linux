#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UART 长时间压力测试 (针对 uart3p 固件: 收帧原样回显)

测试协议 (自验证, 无需与发送记录比对):
    帧格式:  @<6位序号>|<随机可打印数据>|<4位校验和>
    校验和 = sum(数据字节) & 0xFFFF, 十六进制大写
    板子回显整帧 -> 脚本校验序号连续性 + 校验和 + 时延

能发现的问题:
    - 字节丢失/损坏 (校验和失败)
    - 整帧丢失     (序号超时未回显)
    - 回显延迟抖动 (发送->回显时延统计)

用法:
    python3 tools/uart_stress.py                    # 直到 Ctrl+C
    python3 tools/uart_stress.py -d 3600            # 跑 1 小时
    python3 tools/uart_stress.py -p /dev/ttyUSB1 -d 0 --min-gap 1.2

注意: 发送间隔默认 >=1.1s, 匹配 uart3p 主循环 1s 轮询 +
      128 字节环形缓冲区的设计边界, 多帧堆积超过缓冲区会触发
      "覆盖最旧"的设计行为 (不是 bug)。
"""
import argparse
import os
import random
import re
import select
import string
import subprocess
import sys
import threading
import time
from collections import deque

MARK_RE = re.compile(rb'\$@(\d{6})\|([!-~]+)\|([0-9A-F]{4})~')  # 自验证帧 (带哨兵)
GOT_RE = re.compile(rb'got (\d+) bytes:')                      # 固件回显事件
# 数据字符集: 可打印、排除 $ @ | ~ (帧定界) 与 CR/LF
DATA_CHARS = (string.ascii_letters + string.digits +
              ' ,.:;?!#%&*+-/=<>()[]{}_').encode()
MISS_TIMEOUT = 8.0     # 序号超过该秒数未回显 => 判定丢失


def fmt_dur(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


class Stress:
    def __init__(self, args):
        self.args = args
        self.stop = threading.Event()
        self.lock = threading.Lock()
        # 统计
        self.sent = 0
        self.tx_bytes = 0
        self.verified = 0
        self.rx_bytes = 0          # 固件 "got N bytes" 累计
        self.bad_csum = 0
        self.coalesced = 0         # 固件 1s 轮询导致同秒多帧合并回显 (非错误)
        self.missing = []          # 丢失序号
        self.lat_sum = 0.0
        self.lat_max = 0.0
        self.last_rx_time = time.time()
        self.io_error = False
        self.events = deque(maxlen=6)          # 面板最近事件
        self.error_events = deque(maxlen=200)  # 最终报告用
        # 状态: 已发送未回显 {seq: 发送时刻}
        self.pending = {}
        self.seq = 0
        self.t0 = 0.0
        self.log = open(args.log, 'a', encoding='utf-8')

    def note(self, msg, is_error=False):
        line = f'[{time.strftime("%H:%M:%S")}] {msg}'
        self.events.appendleft(line)
        if is_error:
            self.error_events.append(line)
        self.log.write(line + '\n')
        self.log.flush()

    # ---------------- 发送线程 ----------------
    def sender(self, ser):
        rng = random.SystemRandom()
        while not self.stop.is_set():
            # 帧长 = 头(8) + 数据 + 尾(5)
            payload_len = rng.randint(self.args.min_len, self.args.max_len)
            data = bytes(rng.choice(DATA_CHARS) for _ in range(payload_len))
            with self.lock:
                self.seq += 1
                seq = self.seq
                self.pending[seq] = time.time()
                self.sent += 1
                self.tx_bytes += payload_len + 15
            csum = f'{sum(data) & 0xFFFF:04X}'
            frame = b'$@%06d|' % seq + data + b'|' + csum.encode() + b'~'
            try:
                ser.write(frame)
                ser.flush()
            except OSError as e:
                self.note(f'发送失败: {e}', is_error=True)
                self.io_error = True
                self.stop.set()
                return
            self.log.write(f'[{time.strftime("%H:%M:%S")}] TX seq={seq} len={payload_len}\n')
            self.log.flush()
            self.stop.wait(rng.uniform(self.args.min_gap, self.args.max_gap))

    # ---------------- 接收线程 ----------------
    def reader(self, ser):
        buf = b''
        while not self.stop.is_set():
            r, _, _ = select.select([ser], [], [], 0.5)
            if not r:
                continue
            try:
                chunk = os.read(ser.fileno(), 4096)
            except OSError as e:
                self.note(f'接收失败: {e}', is_error=True)
                self.stop.set()
                return
            if not chunk:
                self.note('串口被拔出或被其他程序占用', is_error=True)
                self.stop.set()
                return
            buf += chunk
            now = time.time()
            self.last_rx_time = now
            # 固件回显事件计数 (合并帧时事件数 < 帧数)
            events = len(GOT_RE.findall(buf))
            # 校验所有完整帧
            marks = list(MARK_RE.finditer(buf))
            for m in marks:
                seq = int(m.group(1))
                data = m.group(2)
                csum = int(m.group(3), 16)
                with self.lock:
                    sent_t = self.pending.pop(seq, None)
                ok = (sum(data) & 0xFFFF) == csum
                if not ok:
                    self.bad_csum += 1
                    self.note(f'帧损坏: seq={seq} 校验和不符 (数据可能被改写)', is_error=True)
                    continue
                if sent_t is not None:
                    lat = now - sent_t
                    self.lat_sum += lat
                    self.lat_max = max(self.lat_max, lat)
                self.verified += 1
            if marks and events:
                merged = len(marks) - events
                if merged > 0:
                    self.coalesced += merged   # 设计内行为, 只作提示
            # 固件侧实收字节
            for n in GOT_RE.findall(buf):
                self.rx_bytes += int(n)
            # 只保留结尾一段 (半帧可能跨读)
            buf = buf[-1024:]
        return

    # ---------------- 丢失扫描 ----------------
    def scan_missing(self):
        now = time.time()
        with self.lock:
            late = [s for s, t in self.pending.items() if now - t > MISS_TIMEOUT]
            for s in late:
                del self.pending[s]
                self.missing.append(s)
        for s in late:
            self.note(f'帧丢失: seq={s} 超过 {MISS_TIMEOUT:.0f}s 未回显', is_error=True)

    # ---------------- 面板 ----------------
    def render(self):
        el = time.time() - self.t0
        with self.lock:
            pend = len(self.pending)
            lines = [
                f'=== UART 压力测试  {self.args.port} @ {self.args.baud} ===',
                f'运行时长     {fmt_dur(el)}',
                f'发送帧       {self.sent}  ({self.tx_bytes} B, {self.tx_bytes/el:.1f} B/s)',
                f'回显验证通过 {self.verified}',
                f'帧损坏       {self.bad_csum}   丢失 {len(self.missing)}   待回显 {pend}',
            ]
            if self.missing:
                shown = ','.join(map(str, self.missing[:15]))
                more = '' if len(self.missing) <= 15 else ' ...'
                lines.append(f'丢失序号     {shown}{more}')
            if self.verified:
                lines.append(f'回显延迟     avg {self.lat_sum/self.verified:.2f}s   max {self.lat_max:.2f}s')
            else:
                lines.append('回显延迟     -')
            if self.coalesced:
                lines.append(f'合并回显帧   {self.coalesced} (同秒多帧, 设计内行为)')
            idle = time.time() - self.last_rx_time
            lines.append(f'串口空闲     {idle:.0f}s' + ('   <<< 无数据! 检查接线/口被占' if idle > 5 else ''))
            lines.append('最近事件     ' + (self.events[0] if self.events else '-'))
        return lines

    def run(self):
        # 配置并打开串口
        try:
            subprocess.run(['stty', '-F', self.args.port,
                            str(self.args.baud), 'raw', '-echo'],
                           check=True, capture_output=True)
            ser = open(self.args.port, 'r+b', buffering=0)
        except (subprocess.CalledProcessError, OSError) as e:
            print(f'错误: 无法打开 {self.args.port} ({e})\n'
                  f'      确认设备存在且未被占用 (VOFA+ 等工具请先关闭)', file=sys.stderr)
            return 2

        self.note(f'=== 压测开始: {self.args.port} @ {self.args.baud}, '
                  f'帧长 {self.args.min_len}~{self.args.max_len}B, '
                  f'间隔 {self.args.min_gap}~{self.args.max_gap}s ===')
        # 丢弃开机残留输出
        time.sleep(0.3)
        try:
            os.set_blocking(ser.fileno(), False)
            os.read(ser.fileno(), 65536)
            os.set_blocking(ser.fileno(), True)
        except OSError:
            pass

        self.t0 = time.time()
        ths = [threading.Thread(target=f, args=(ser,), daemon=True)
               for f in (self.sender, self.reader)]
        for t in ths:
            t.start()

        tty = sys.stdout.isatty()
        if tty:
            sys.stdout.write('\x1b[?25l')   # 隐藏光标
        try:
            prev_n = 0
            last_scan = 0.0
            while not self.stop.is_set():
                if self.args.duration > 0 and time.time() - self.t0 >= self.args.duration:
                    break
                if time.time() - last_scan > 2.0:
                    self.scan_missing()
                    last_scan = time.time()
                lines = self.render()
                if tty:
                    out = []
                    if prev_n:
                        out.append(f'\x1b[{prev_n}A')     # 光标回到块首
                    for ln in lines:
                        out.append('\x1b[2K' + ln)         # 清行重画
                    prev_n = len(lines)
                    sys.stdout.write('\n'.join(out) + '\n')
                    sys.stdout.flush()
                else:
                    # 非终端: 每 10s 输出一行摘要 (便于重定向/后台)
                    if int(time.time() - self.t0) % 10 == 0:
                        s = lines
                        print(f'{s[1]}  发送 {s[2]}  通过 {s[3]}  {s[4]}')
                        sys.stdout.flush()
                        time.sleep(1)
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop.set()
            self.scan_missing()
            if tty:
                sys.stdout.write('\x1b[?25h')             # 恢复光标
            for t in ths:
                t.join(timeout=2)
            ser.close()

        # 最终报告
        self.report()
        return 1 if (self.bad_csum or self.missing) else 0

    def report(self):
        el = max(time.time() - self.t0, 1e-9)
        print('\n========== 压测报告 ==========')
        print(f'时长         {fmt_dur(el)}')
        print(f'发送帧       {self.sent} ({self.tx_bytes} B)')
        print(f'验证通过     {self.verified}')
        ok_rate = (self.verified / self.sent * 100) if self.sent else 0
        print(f'通过率       {ok_rate:.2f}%')
        print(f'帧损坏       {self.bad_csum}')
        print(f'帧丢失       {len(self.missing)}')
        if self.verified:
            print(f'回显延迟     avg {self.lat_sum/self.verified:.2f}s  max {self.lat_max:.2f}s')
        if self.coalesced:
            print(f'合并回显     {self.coalesced} 帧 (设计内行为)')
        if self.error_events:
            print('--- 错误明细 (最多 200 条) ---')
            for e in self.error_events:
                print(f'  {e}')
        verdict = '通过 ✓' if (self.sent and not self.io_error and
                                not self.bad_csum and not self.missing) \
            else '失败 ✗ (未完成/存在损坏或丢失/串口错误)'
        print(f'结论         {verdict}')
        print(f'日志         {self.args.log}')
        self.note(f'=== 压测结束: sent={self.sent} verified={self.verified} '
                  f'bad={self.bad_csum} missing={len(self.missing)} ===')
        self.log.close()


def main():
    ap = argparse.ArgumentParser(description='uart3p 长时间压力测试 (回显自验证)')
    ap.add_argument('-p', '--port', default='/dev/ttyUSB0', help='串口设备')
    ap.add_argument('-b', '--baud', type=int, default=115200)
    ap.add_argument('-d', '--duration', type=float, default=0,
                    help='时长(秒), 0 = 直到 Ctrl+C')
    ap.add_argument('--min-len', type=int, default=8, help='随机帧数据最小字节')
    ap.add_argument('--max-len', type=int, default=100, help='随机帧数据最大字节')
    ap.add_argument('--min-gap', type=float, default=1.1, help='发送最小间隔(秒)')
    ap.add_argument('--max-gap', type=float, default=1.4, help='发送最大间隔(秒)')
    ap.add_argument('--log', default=f'/tmp/uart_stress_{time.strftime("%Y%m%d_%H%M%S")}.log')
    args = ap.parse_args()

    if os.geteuid() != 0 and not os.access(args.port, os.R_OK | os.W_OK):
        print(f'错误: 无权限访问 {args.port} (试试 sudo 或加入 dialout 组)', file=sys.stderr)
        return 2

    print(f'日志: {args.log}')
    return Stress(args).run()


if __name__ == '__main__':
    sys.exit(main())
