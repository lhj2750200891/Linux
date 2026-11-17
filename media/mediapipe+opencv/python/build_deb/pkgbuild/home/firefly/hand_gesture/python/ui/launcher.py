#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""launcher.py — Firefly 展会UI启动器 (RK3588 手势识别 · 灵巧手演示)

科技风全屏界面: 动态透视网格 + 萤火虫粒子 + 扫描光带, 左上角贴 ui/logo.png 真实徽标.
五区块中心对称: 左右各两张 demo 卡片 + 正中央公司宣传视频位(点击播放, 播完或按ESC返回).
四个 demo: 数字识别 / 灵巧手跟随 / 固定手势识别 / 石头剪刀布(gpu/rps_game.py, 灵巧手必胜).
demo 原文件零改动; 本目录只依赖 opencv/numpy(PIL 仅用于中文渲染, 缺失时自动英文降级).
宣传视频: 把文件放成 ui/promo.mp4 (或 ui/media/*.mp4) 即被自动识别; 板上有 mpv/vlc/
gst-play/ffplay 时调外部播放器(带音频), 都没有则用内置 cv2 无声播放.
布局自带展会电视"过扫描"安全边距(顶/底内容自动内收, 不会被电视机切掉).

用法:
    python3 launcher.py             # 全屏启动器(板端/有显示器的PC)
    python3 launcher.py --shot 目录 # 无窗口, 渲染预览图(设计验证用)
    python3 launcher.py --size 1920x1080 --shot 目录

交互:  鼠标/触摸点击卡片启动 | 数字键1~4启动demo | s 切换灵巧手串口 | ESC 退出(带确认)
布局:  本目录与 npu/ gpu/ 平级(板端目录结构一致), 路径按 ui/ 所在位置自动解析.
"""
import argparse
import glob
import os
import subprocess
import sys
import time

import numpy as np

UI_DIR = os.path.dirname(os.path.abspath(__file__))


def _setup_display():
    """与各demo一致的环境(必须在 import cv2 之前)"""
    os.environ.setdefault("DISPLAY", ":0")
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
    _a = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
    if _a:
        os.environ.setdefault("XAUTHORITY", _a[-1])


# ============================== 演示模块配置 ==============================
# scripts: 依次尝试的脚本(相对 ui/ 的路径), 第一个存在的生效 —— 在roi版与原版间一键切换
# 屏上布局(中心对称): [demo0] [demo1] [宣传视频] [demo2] [demo3]
DEMOS = [
    dict(cn="数字手势识别", en="DIGIT GESTURE",
         desc=("数字 1~9 · 拳头 · OK · 点赞", "识别后灵巧手实时模仿"),
         desc_en=("DIGITS 1-9 · FIST · OK · LIKE", "CYBERHAND MIMICS INSTANTLY"),
         icon="digits",
         scripts=["../npu/fixed_gesture_npu.py"],
         win="fixed gesture"),
    dict(cn="灵巧手跟随", en="HAND FOLLOW",
         desc=("21 关键点实时解算", "灵巧手逐关节连续跟随"),
         desc_en=("21 KEYPOINTS SOLVED LIVE", "JOINTS FOLLOW CONTINUOUSLY"),
         icon="follow",
         scripts=["../npu/hand_control_npu_roi.py", "../npu/hand_control_npu.py"],
         win="hand control"),
    dict(cn="固定手势识别", en="POSE RECOGNITION",
         desc=("四模型融合 · 六种固定手势", "识别即触发标准手姿"),
         desc_en=("4-MODEL FUSION · 6 POSES", "TRIGGERED LIVE ON DETECTION"),
         icon="pose",
         scripts=["../npu/4_models/gesture_pose_4_models_roi.py",
                  "../npu/4_models/gesture_pose_4_models.py"],
         win="gesture pose"),
    dict(cn="石头剪刀布", en="RPS CHALLENGE",
         desc=("NPU 识别你的出招", "灵巧手永远克制 · 从不落败"),
         desc_en=("NPU READS YOUR THROW", "CYBERHAND COUNTERS · NEVER LOSES"),
         icon="rps",
         scripts=["../npu/rps_game_npu.py", "../gpu/rps_game.py"],
         win=("rps npu", "rps")),
]

# 正中央: 公司宣传视频位
VIDEO_INFO = dict(cn="欢迎了解 Firefly", en="WELCOME TO FIREFLY",
                  desc=("点击播放公司宣传影片", "ESC 或播完自动返回"),
                  desc_en=("TAP TO PLAY THE COMPANY FILM", "ESC OR AUTO-RETURN AT END"),
                  icon="video")
VIDEO_MISSING_DESC = ("放入 ui/promo.mp4 即自动识别", "DROP ui/promo.mp4 HERE")

WIN_NAME = "firefly launcher"


def resolve_video():
    """宣传视频探测: ui/promo.mp4 -> ui/promo.* -> ui/media/*.mp4|mov"""
    cands = [os.path.join(UI_DIR, "promo.mp4")]
    cands += sorted(glob.glob(os.path.join(UI_DIR, "promo.*")))
    cands += sorted(glob.glob(os.path.join(UI_DIR, "media", "*.mp4")))
    cands += sorted(glob.glob(os.path.join(UI_DIR, "media", "*.mov")))
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


def find_player():
    """外部视频播放器探测(带音频), 都没有则返回 (None, None) -> 内置无声播放"""
    import shutil
    for name, pre in (("mpv", ("--fullscreen", "--osc=no", "--keep-open=no")),
                      ("vlc", ("--fullscreen", "--no-video-title", "--play-and-exit")),
                      ("gst-play-1.0", ("--fullscreen",)),
                      ("ffplay", ("-fs", "-noborder", "-autoexit",
                                  "-hide_banner", "-loglevel", "quiet"))):
        try:
            if shutil.which(name):
                return name, list(pre)
        except Exception:
            pass
    return None, None


def resolve_script(demo):
    for rel in demo["scripts"]:
        p = os.path.normpath(os.path.join(UI_DIR, rel))
        if os.path.exists(p):
            return p
    return None


def npu_available():
    try:
        import rknnlite  # noqa: F401
        return True
    except Exception:
        return False


def find_serial():
    devs = sorted(glob.glob("/dev/ttyACM*")) + sorted(glob.glob("/dev/ttyUSB*"))
    return devs[0] if devs else None


def screen_size():
    """屏幕分辨率: xrandr 读, 失败按 1920x1080 兜底(与demo同一套)"""
    try:
        import re
        out = subprocess.check_output(["xrandr", "--current"], timeout=2).decode()
        m = re.search(r"(\d+)x(\d+)\+0\+0", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 1920, 1080


# ============================== 启动器本体 ==============================
class Launcher:
    def __init__(self, W=1920, H=1080):
        import cv2
        import ui_style as U
        self.cv2, self.U = cv2, U
        U.init_fonts()
        self.W, self.H = int(W), int(H)
        self.bg = U.Background(self.W, self.H)
        # 状态
        self.mode = "menu"                 # menu / confirm / loading / demo
        self.chosen = 0
        self.proc = None
        self.spawn_t = 0.0
        self.win_found_t = None
        self._last_win_check = 0.0
        self.fail = (-1, 0.0)              # (卡片idx, 失败提示截止时刻)
        self.serial_dev = find_serial()
        self.serial_on = self.serial_dev is not None
        self.npu_ok = npu_available()
        self.hover = [0.0] * 5             # 卡位悬停动画插值(4 demo + 中央视频)
        self.mx = self.my = -1
        self.zones = {}                    # 每帧由渲染函数填充
        self.fps = 0.0
        self._fps_n, self._fps_t = 0, time.time()
        self.scale = min(self.W / 1920, self.H / 1080)
        self.quit = False
        # 展会电视过扫描安全边距: 靠边内容统一内收, 防止顶/底被电视机切掉
        self.safe_x = int(self.W * 0.032)
        self.safe_y = int(self.H * 0.045)
        # 宣传视频
        self.pending_video = False         # loading态等待的是外部播放器
        self.video_exit = False            # 内置播放的返回信号
        self.player = find_player()

    # ---------- 窗口 ----------
    def create_window(self):
        cv2, U = self.cv2, self.U
        cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN_NAME, self.W, self.H)
        try:                               # Qt后端多半忽略, 但无害; EWMH在下面兜底
            cv2.setWindowProperty(WIN_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        except Exception:
            pass
        cv2.imshow(WIN_NAME, np.zeros((self.H, self.W, 3), np.uint8))
        cv2.waitKey(150)
        try:
            import win_fullscreen
            win_fullscreen.make_fullscreen(WIN_NAME, wait=3)
        except Exception as e:
            print("[fullscreen] fail:", e, flush=True)
        cv2.setMouseCallback(WIN_NAME, self.on_mouse)

    def on_mouse(self, event, x, y, flags, param):
        if event == self.cv2.EVENT_MOUSEMOVE:
            self.mx, self.my = x, y
        elif event == self.cv2.EVENT_LBUTTONDOWN:
            self.mx, self.my = x, y
            self.click(x, y)

    def click(self, x, y):
        if self.mode == "video":           # 内置播放中: 点画面任意处返回
            self.video_exit = True
            return
        for name, (x1, y1, x2, y2) in self.zones.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                if self.mode == "menu":
                    if name.startswith("card"):
                        self.launch(int(name[4:]))
                    elif name == "video":
                        self.launch_video()
                    elif name == "serial":
                        self.serial_on = not self.serial_on
                    elif name == "exit":
                        self.mode = "confirm"
                elif self.mode == "confirm":
                    if name == "yes":
                        self.quit = True
                    elif name == "no":
                        self.mode = "menu"
                return

    # ---------- 启动demo ----------
    def launch(self, idx):
        demo = DEMOS[idx]
        script = resolve_script(demo)
        if script is None:
            self.fail = (idx, time.time() + 4.0)
            return
        cmd = [sys.executable, script]
        if self.serial_on and self.serial_dev:
            cmd.append(self.serial_dev)          # demo约定: 第一个参数=灵巧手串口
        try:
            self.proc = subprocess.Popen(cmd, cwd=os.path.dirname(script),
                                         stdin=subprocess.DEVNULL,
                                         start_new_session=True)
        except Exception as e:
            print("[launch] 启动失败:", e, flush=True)
            self.fail = (idx, time.time() + 4.0)
            return
        self.chosen = idx
        self.mode = "loading"
        self.spawn_t = time.time()
        self.win_found_t = None
        print(f"[launch] {demo['cn']} -> {os.path.basename(script)} "
              f"({'串口' + self.serial_dev if self.serial_on and self.serial_dev else '干跑'})", flush=True)

    # ---------- 播放宣传视频 ----------
    def launch_video(self):
        """中央视频位: 优先外部播放器(带音频), 播完自动回菜单; 没有则内置无声播放"""
        path = resolve_video()
        if path is None:
            self.fail = ("video", time.time() + 4.0)
            return
        self.chosen = "video"
        name, pre = self.player
        if name:
            try:
                self.proc = subprocess.Popen([name] + pre + [path], cwd=UI_DIR,
                                             stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL,
                                             start_new_session=True)
            except Exception as e:
                print("[video] 外部播放器启动失败, 改用内置播放:", e, flush=True)
                self.proc = None
            if self.proc is not None:
                self.mode = "loading"
                self.spawn_t = time.time()
                print(f"[video] {os.path.basename(path)} -> {name} 全屏播放 "
                      f"(ESC/q 或播完自动返回)", flush=True)
                return
        self.video_exit = False
        self.mode = "video"
        print(f"[video] {os.path.basename(path)} -> 内置播放 "
              f"(无外部播放器, 无音频; 点击画面/按任意键返回)", flush=True)

    def poll_loading(self):
        """loading态: 等 demo 窗口出现就熄掉自己的窗口, 把屏幕完全交给 demo/播放器"""
        cv2, U = self.cv2, self.U
        now = time.time()
        if self.pending_video:
            # 外部播放器: 稍候即让出屏幕, 播放器退出(播完/ESC)后自动回到菜单
            if now - self.spawn_t < 1.0:
                return
            ret = self.proc.poll() if self.proc else 0
            if ret is not None and now - self.spawn_t < 3.0:
                print(f"[video] 播放器提前退出(code={ret}), 请看终端日志", flush=True)
                self.fail = ("video", now + 4.0)
                self.proc = None
                self.pending_video = False
                self.mode = "menu"
                return
            cv2.destroyWindow(WIN_NAME)
            cv2.waitKey(30)
            code = self.proc.wait() if self.proc else 0
            print(f"[video] 播放器退出(code={code}), 回到启动器", flush=True)
            self.proc = None
            self.pending_video = False
            self.create_window()
            self.mode = "menu"
            return
        demo = DEMOS[self.chosen]
        wins = demo["win"] if isinstance(demo["win"], (tuple, list)) else (demo["win"],)
        found = False
        if now - self.spawn_t > 1.0 and now - (self._last_win_check if hasattr(self, "_last_win_check") else 0) > 0.4:
            self._last_win_check = now
            try:
                import win_fullscreen
                found = any(win_fullscreen._find_win_by_title(w) is not None for w in wins)
            except Exception:
                found = False
            if found:
                self.win_found_t = now
        ret = self.proc.poll() if self.proc else 0
        if found or (self.win_found_t is not None) or ret is not None \
                or now - self.spawn_t > 12.0:
            if ret is not None and self.win_found_t is None and now - self.spawn_t < 6.0:
                # 秒退且没出现过窗口: 启动失败, 回菜单
                print(f"[launch] demo 提前退出(code={ret}), 请看终端日志", flush=True)
                self.fail = (self.chosen, now + 4.0)
                self.mode = "menu"
                self.proc = None
                return
            cv2.destroyWindow(WIN_NAME)          # 让位给demo全屏窗口
            cv2.waitKey(30)
            code = self.proc.wait() if self.proc else 0
            print(f"[demo] 退出(code={code}), 回到启动器", flush=True)
            self.proc = None
            self.serial_dev = find_serial()      # 重新探测(可能中途插拔)
            self.create_window()
            self.mode = "menu"

    def play_video_cv(self):
        """内置视频播放(cv2, 无声): 循环读帧铺满屏幕, 点击/任意键返回菜单"""
        cv2 = self.cv2
        path = resolve_video()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            print("[video] 内置播放打开失败:", path, flush=True)
            self.fail = ("video", time.time() + 4.0)
            self.mode = "menu"
            return
        self.zones = {}
        t0 = time.time()
        print("[video] 内置播放中 — 点击画面或按任意键返回", flush=True)
        while not self.quit and not self.video_exit:
            ok, fr = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # 播完回到菜单
                break
            fh, fw = fr.shape[:2]
            k = min(self.W / fw, self.H / fh)          # 等比缩放+黑边, 画面不变形
            nw, nh = max(2, int(fw * k)) // 2 * 2, max(2, int(fh * k)) // 2 * 2
            if (nw, nh) != (fw, fh):
                fr = cv2.resize(fr, (nw, nh), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((self.H, self.W, 3), np.uint8)
            y0, x0 = (self.H - nh) // 2, (self.W - nw) // 2
            canvas[y0:y0 + nh, x0:x0 + nw] = fr
            dt = time.time() - t0
            if dt < 3.5:                               # 开头3.5秒提示如何返回
                y1, x1 = self.H - 96, self.W - 580
                canvas[y1:self.H - 28, x1:self.W - 36] = \
                    (canvas[y1:self.H - 28, x1:self.W - 36] * 0.42).astype(np.uint8)
                cv2.putText(canvas, "TAP / ANY KEY TO RETURN", (x1 + 12, self.H - 46),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85, (235, 245, 255), 2, cv2.LINE_AA)
            cv2.imshow(WIN_NAME, canvas)
            if (cv2.waitKey(25) & 0xFF) not in (0, 255):
                break
        cap.release()
        self.video_exit = False
        self.mode = "menu"

    # ---------- 渲染 ----------
    def render_frame(self, t):
        U = self.U
        img = self.bg.draw(t)
        self.zones = {}
        if self.mode in ("menu", "confirm"):
            self.draw_menu(img, t)
        if self.mode == "confirm":
            self.draw_confirm(img, t)
        elif self.mode == "loading":
            self.draw_loading(img, t)
        return np.clip(img, 0, 1)

    # ---- 顶栏 ----
    def draw_topbar(self, img, t):
        U, W, H, s = self.U, self.W, self.H, self.scale
        sx, sy = self.safe_x, self.safe_y
        # 左: 真实徽标(ui/logo.png, 透明) + Firefly 字标; 缺徽标文件则回退程序绘制logo
        lw = U.blit_png_logo(img, sx + int(10 * s), sy + int(8 * s), int(80 * s), glow=0.3)
        if lw is None:
            U.blit_logo(img, sx + int(6 * s), sy + int(2 * s), int(88 * s), pulse=np.sin(t * 2.2))
            lw = int(88 * s)
        x = sx + int(10 * s) + lw + int(18 * s)
        U.text(img, (x, sy + int(48 * s)), "Firefly", int(27 * s), C_TXT, anchor="lm",
               spacing=int(5 * s), glow=C_CYAN, glow_gain=0.45)
        # 右侧: 徽章行 + 时钟(固定按 UTC+8 北京时间显示, 不依赖板子系统时区)
        bj = time.gmtime(time.time() + 8 * 3600)
        hhmm = time.strftime("%H:%M", bj)
        cw = U.text_size(hhmm, int(30 * s))[0]
        xr = W - sx - int(44 * s) - cw - int(30 * s)
        items = [(f"{self.fps:.0f} FPS", C_TXT),
                 ("NPU READY" if self.npu_ok else "NPU --", U.C.GREEN if self.npu_ok else C_MUT)]
        for label, rgb in items:
            xr = self.badge(img, xr, sy + int(26 * s), label, rgb, int(30 * s), t) - int(16 * s)
        U.text(img, (W - sx - int(44 * s), sy + int(22 * s)), hhmm,
               int(30 * s), C_TXT, anchor="rt", glow=C_CYAN, glow_gain=0.3)
        week_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][bj.tm_wday]
        date = time.strftime("%Y-%m-%d ", bj) + U.T(week_cn, time.strftime("%a", bj))
        U.text(img, (W - sx - int(44 * s), sy + int(62 * s)), date,
               int(12.5 * s), C_SUB, anchor="rt", spacing=int(1.5 * s))
        U.hline_fade(img, sy + int(98 * s), sx, W - sx, U.C.CYAN, 0.08)     # 顶栏分割线
        U.hline_fade(img, sy + int(98 * s), W - sx, sx, U.C.CYAN, 0.08, flip=True)

    def badge(self, img, xr, y, label, rgb, h, t):
        """右侧小徽章(右对齐), 返回左边界x"""
        U, s = self.U, self.scale
        px = int(12 * s)
        tw = U.text_size(label, px)[0]
        w = tw + int(h * 1.7)
        x1 = xr - w
        img[y:y + h, x1:xr] += np.array(U.C.bgr(rgb, 0.10), np.float32)
        U.rrect(img, (x1, y, xr, y + h), h // 2, rgb, th=1, alpha=0.45)
        dot = 0.5 + 0.5 * np.sin(t * 2.6)
        cv2 = self.cv2
        cv2.circle(img, (x1 + int(h * 0.52), y + h // 2), int(h * 0.13),
                   U.C.bgr(rgb, 0.4 + 0.6 * dot), -1, self.cv2.LINE_AA)
        U.text(img, (x1 + int(h * 1.05), y + h / 2), label, px, rgb, anchor="lm")
        return x1

    # ---- 标题区 ----
    def draw_title(self, img, t):
        U, W, s = self.U, self.W, self.scale
        y = int(134 * s) + self.safe_y
        title = U.T("手势识别 × 灵巧手", "GESTURE × CYBERHAND")
        U.text(img, (W / 2, y), title, int(48 * s), C_TXT, anchor="mt", glow=C_CYAN, glow_gain=0.5)
        lw = U.text_size(title, int(48 * s))[0]
        ly = y + int(34 * s)
        for sgn in (-1, 1):                      # 标题两侧渐隐装饰线
            x1 = W / 2 + sgn * (lw / 2 + int(36 * s))
            x2 = W / 2 + sgn * (lw / 2 + int(170 * s))
            U.hline_fade(img, ly, int(x1), int(x2), U.C.CYAN, 0.5, flip=(sgn < 0))
            dx = W / 2 + sgn * (lw / 2 + int(182 * s))
            cv2 = self.cv2
            cv2.drawMarker(img, (int(dx), ly), U.C.bgr(U.C.CYAN, 0.7),
                           self.cv2.MARKER_DIAMOND, int(9 * s), 1, self.cv2.LINE_AA)
        U.text(img, (W / 2, y + int(72 * s)),
               "Firefly RK3588 NPU · GESTURE RECOGNITION · CYBERHAND CONTROL · ROCK-PAPER-SCISSORS",
               int(13.5 * s), C_SUB, anchor="mt", spacing=int(4 * s))
        U.text(img, (W / 2, y + int(104 * s)),
               U.T("— 点击卡片启动演示 · 中央了解 Firefly —", "— TAP A CARD · CENTER TO KNOW FIREFLY —"),
               int(13 * s), C_MUT, anchor="mt", spacing=int(2 * s))

    # ---- 五区块: [demo0] [demo1] [宣传视频] [demo2] [demo3] 中心对称 ----
    def draw_cards(self, img, t):
        U, W, H, s = self.U, self.W, self.H, self.scale
        cw, ch = int(308 * s), int(430 * s)
        gap = int(46 * s)
        y0 = int(H * 0.325) + self.safe_y
        n = len(DEMOS) + 1                       # 4 demo + 中央视频位
        total = n * cw + (n - 1) * gap
        x0 = (W - total) // 2
        for k in range(n):
            x = x0 + k * (cw + gap)
            tgt = 1.0 if (x <= self.mx <= x + cw and y0 <= self.my <= y0 + ch) else 0.0
            self.hover[k] += (tgt - self.hover[k]) * 0.20
            if k == 2:                           # 正中央: 公司宣传视频
                self.draw_video_tile(img, x, y0, cw, ch, t)
                self.zones["video"] = (x, y0, x + cw, y0 + ch)
            else:
                i = k if k < 2 else k - 1
                self.draw_card(img, i, DEMOS[i], x, y0, cw, ch, t, self.hover[k])
                self.zones[f"card{i}"] = (x, y0, x + cw, y0 + ch)

    def _card_panel(self, img, x, y, cw, ch, accent, hov, t, k):
        """卡片公共面板: 底色/描边/角括弧/顶部色条"""
        U, s = self.U, self.scale
        img[y:y + ch, x:x + cw] += np.array(U.C.bgr(accent, 0.040 + 0.055 * hov), np.float32)
        U.rrect(img, (x, y, x + cw, y + ch), int(16 * s), accent,
                th=1 + int(1.6 * hov), alpha=0.32 + 0.5 * hov)
        breathe = int(3 * s * np.sin(t * 2.0 + k * 2.1))
        U.brackets(img, (x, y, x + cw, y + ch), int((24 + 8 * hov) * s) + breathe,
                   accent, 2, 0.40 + 0.55 * hov)
        img[y:y + int(3 * s), x + int(22 * s):x + cw - int(22 * s)] += \
            np.array(U.C.bgr(accent, 0.85), np.float32)

    def _card_button(self, img, x, y, cw, ch, accent, hov, label, s):
        """卡片底部启动按钮(加高到50*s, 文字垂直居中, 防止顶部被裁)"""
        U = self.U
        bw, bh = int(190 * s), int(50 * s)
        bx, by = x + (cw - bw) // 2, y + int(356 * s)
        U.rrect(img, (bx, by, bx + bw, by + bh), int(12 * s), accent, th=-1,
                alpha=0.10 + 0.72 * hov)
        U.rrect(img, (bx, by, bx + bw, by + bh), int(12 * s), accent, th=1, alpha=0.5 + 0.4 * hov)
        U.text(img, (bx + bw / 2, by + bh / 2), label,
               int(16 * s), C_TXT if hov > 0.45 else accent, anchor="mm")
        return bx, by, bx + bw, by + bh

    def draw_card(self, img, i, demo, x, y, cw, ch, t, hov):
        U, s = self.U, self.scale
        accent = [U.C.CYAN, U.C.AMBER, U.C.VIOLET, U.C.GREEN][i]
        script = resolve_script(demo)
        missing = script is None
        self._card_panel(img, x, y, cw, ch, accent, hov, t, i)
        if missing:
            img[y:y + ch, x:x + cw] *= 0.5       # 模块缺失: 整卡压暗
        bob = int(5 * s * np.sin(t * 1.3 + i * 2.1))
        U.icon_dispatch(demo["icon"], img, x + cw / 2, y + int(118 * s) + bob, t, s * 0.76, accent)
        U.text(img, (x + cw / 2, y + int(228 * s)), demo["cn"], int(27 * s), C_TXT,
               anchor="mt", glow=accent, glow_gain=0.5)
        U.text(img, (x + cw / 2, y + int(268 * s)), demo["en"], int(11.5 * s), C_SUB,
               anchor="mt", spacing=int(3 * s))
        for j, (line_cn, line_en) in enumerate(zip(demo["desc"], demo["desc_en"])):
            U.text(img, (x + cw / 2, y + int(296 * s) + j * int(24 * s)),
                   U.T(line_cn, line_en), int(13.5 * s), C_SUB, anchor="mt")
        bx1, by1, bx2, by2 = self._card_button(img, x, y, cw, ch, accent, hov,
                                               U.T("启动 START", "START"), s)
        # 状态标记
        now = time.time()
        if missing:
            U.rrect(img, (bx1, by1, bx2, by2), int(12 * s), U.C.RED, th=-1, alpha=0.75)
            U.text(img, ((bx1 + bx2) / 2, (by1 + by2) / 2), U.T("模块缺失", "OFFLINE"),
                   int(15 * s), C_TXT, anchor="mm")
        elif self.fail[0] == i and now < self.fail[1]:
            U.rrect(img, (bx1, by1, bx2, by2), int(12 * s), U.C.RED, th=-1, alpha=0.8)
            U.text(img, ((bx1 + bx2) / 2, (by1 + by2) / 2), U.T("启动失败 · 见终端", "START FAILED"),
                   int(14 * s), C_TXT, anchor="mm")

    def draw_video_tile(self, img, x, y, cw, ch, t):
        """正中央: 公司宣传视频位"""
        U, s = self.U, self.scale
        accent = U.C.CORAL
        hov = self.hover[2]
        path = resolve_video()
        missing = path is None
        self._card_panel(img, x, y, cw, ch, accent, hov, t, 2)
        if missing:
            img[y:y + ch, x:x + cw] *= 0.5
        bob = int(5 * s * np.sin(t * 1.3 + 2.1))
        U.icon_dispatch("video", img, x + cw / 2, y + int(118 * s) + bob, t, s * 0.76, accent)
        if missing:
            lines = [VIDEO_MISSING_DESC]
        else:
            lines = list(zip(VIDEO_INFO["desc"], VIDEO_INFO["desc_en"]))
        U.text(img, (x + cw / 2, y + int(228 * s)), VIDEO_INFO["cn"], int(27 * s), C_TXT,
               anchor="mt", glow=accent, glow_gain=0.5)
        U.text(img, (x + cw / 2, y + int(268 * s)), VIDEO_INFO["en"], int(11.5 * s), C_SUB,
               anchor="mt", spacing=int(3 * s))
        for j, (line_cn, line_en) in enumerate(lines):
            U.text(img, (x + cw / 2, y + int(296 * s) + j * int(24 * s)),
                   U.T(line_cn, line_en), int(13.5 * s), C_SUB, anchor="mt")
        bx1, by1, bx2, by2 = self._card_button(img, x, y, cw, ch, accent, hov,
                                               U.T("播放 PLAY", "PLAY"), s)
        now = time.time()
        if missing:
            U.rrect(img, (bx1, by1, bx2, by2), int(12 * s), U.C.RED, th=-1, alpha=0.75)
            U.text(img, ((bx1 + bx2) / 2, (by1 + by2) / 2), U.T("视频未就绪", "NO VIDEO"),
                   int(15 * s), C_TXT, anchor="mm")
        elif self.fail[0] == "video" and now < self.fail[1]:
            U.rrect(img, (bx1, by1, bx2, by2), int(12 * s), U.C.RED, th=-1, alpha=0.8)
            U.text(img, ((bx1 + bx2) / 2, (by1 + by2) / 2), U.T("播放失败 · 见终端", "PLAY FAILED"),
                   int(14 * s), C_TXT, anchor="mm")

    # ---- 底栏 ----
    def draw_bottombar(self, img, t):
        U, W, H, s = self.U, self.W, self.H, self.scale
        cv2 = self.cv2
        sx, sy = self.safe_x, self.safe_y
        # 左: 品牌
        U.text(img, (sx + int(46 * s), H - sy - int(76 * s)), "T-CHIP · Firefly",
               int(15 * s), C_TXT, spacing=int(2.5 * s), glow=C_CYAN, glow_gain=0.3)
        U.text(img, (sx + int(46 * s), H - sy - int(44 * s)),
               "RK3588 · 6 TOPS NPU · REALTIME 30FPS", int(11 * s), C_MUT, spacing=int(2.5 * s))
        # 中: 灵巧手串口开关
        if self.serial_on:
            label = U.T(f"灵巧手  {self.serial_dev or '等待设备'}",
                        f"HAND  {self.serial_dev or 'WAITING'}")
            rgb = U.C.GREEN if self.serial_dev else U.C.AMBER
        else:
            label = U.T("灵巧手  已关闭(干跑)", "HAND  OFF (DRY-RUN)")
            rgb = C_MUT
        px = int(14.5 * s)
        tw = U.text_size(label, px)[0]
        bw, bh = tw + int(88 * s), int(44 * s)
        bx, by = (W - bw) // 2, H - sy - int(78 * s)
        img[by:by + bh, bx:bx + bw] += np.array(U.C.bgr(rgb, 0.07), np.float32)
        U.rrect(img, (bx, by, bx + bw, by + bh), int(10 * s), rgb, th=1, alpha=0.45)
        dot = 0.5 + 0.5 * np.sin(t * 2.6)
        cv2.circle(img, (bx + int(26 * s), by + bh // 2), int(5 * s),
                   U.C.bgr(rgb, 0.35 + 0.65 * dot), -1, cv2.LINE_AA)
        U.text(img, (bx + int(46 * s), by + bh / 2), label, px, C_TXT, anchor="lm")
        self.zones["serial"] = (bx, by, bx + bw, by + bh)
        # 右: 退出
        ex1, ey1 = W - sx - int(160 * s), H - sy - int(78 * s)
        ex2, ey2 = W - sx - int(46 * s), H - sy - int(34 * s)
        img[ey1:ey2, ex1:ex2] += np.array(U.C.bgr(U.C.RED, 0.07), np.float32)
        U.rrect(img, (ex1, ey1, ex2, ey2), int(10 * s), U.C.RED, th=1, alpha=0.5)
        U.text(img, ((ex1 + ex2) / 2, (ey1 + ey2) / 2), U.T("退出 EXIT", "EXIT"),
               int(14.5 * s), U.C.RED, anchor="mm")
        self.zones["exit"] = (ex1, ey1, ex2, ey2)
        # 底边装饰刻度(避开两侧文字)
        U.hline_fade(img, H - sy - int(14 * s), sx + int(360 * s), sx + int(620 * s), U.C.CYAN, 0.12)
        U.hline_fade(img, H - sy - int(14 * s), W - sx - int(360 * s), W - sx - int(620 * s),
                     U.C.CYAN, 0.12, flip=True)

    def draw_menu(self, img, t):
        self.scale = s = min(self.W / 1920, self.H / 1080)
        U = self.U
        # 背景水印大字
        U.text(img, (self.W / 2, self.H * 0.60), "Firefly", int(150 * s), U.C.CYAN,
               anchor="mm", spacing=int(30 * s), alpha=0.025)
        self.draw_topbar(img, t)
        self.draw_title(img, t)
        self.draw_cards(img, t)
        self.draw_bottombar(img, t)

    # ---- 退出确认弹窗 ----
    def draw_confirm(self, img, t):
        U, W, H, s = self.U, self.W, self.H, self.scale
        img *= 0.42                                   # 全屏压暗
        pw, ph = int(520 * s), int(210 * s)
        px0, py0 = (W - pw) // 2, (H - ph) // 2
        U.rrect(img, (px0, py0, px0 + pw, py0 + ph), int(14 * s), (24, 32, 52), th=-1, alpha=1.0)
        U.rrect(img, (px0, py0, px0 + pw, py0 + ph), int(14 * s), U.C.CYAN, th=1, alpha=0.4)
        U.brackets(img, (px0, py0, px0 + pw, py0 + ph), int(22 * s), U.C.CYAN, 2, 0.7)
        U.text(img, (W / 2, py0 + int(52 * s)), U.T("退出演示系统 ?", "EXIT THE DEMO SYSTEM ?"),
               int(25 * s), C_TXT, anchor="mm", glow=C_CYAN, glow_gain=0.5)
        bw, bh, gap = int(190 * s), int(48 * s), int(40 * s)
        y1 = py0 + int(110 * s)
        # 确认(红)
        bx = W // 2 - gap // 2 - bw
        U.rrect(img, (bx, y1, bx + bw, y1 + bh), int(10 * s), U.C.RED, th=-1, alpha=0.18)
        U.rrect(img, (bx, y1, bx + bw, y1 + bh), int(10 * s), U.C.RED, th=1, alpha=0.7)
        U.text(img, (bx + bw / 2, y1 + bh / 2), U.T("确认退出", "EXIT"), int(17 * s), U.C.RED, anchor="mm")
        self.zones["yes"] = (bx, y1, bx + bw, y1 + bh)
        # 返回(青)
        bx = W // 2 + gap // 2
        U.rrect(img, (bx, y1, bx + bw, y1 + bh), int(10 * s), U.C.CYAN, th=-1, alpha=0.14)
        U.rrect(img, (bx, y1, bx + bw, y1 + bh), int(10 * s), U.C.CYAN, th=1, alpha=0.7)
        U.text(img, (bx + bw / 2, y1 + bh / 2), U.T("继续演示", "BACK"), int(17 * s), C_TXT, anchor="mm")
        self.zones["no"] = (bx, y1, bx + bw, y1 + bh)

    # ---- 启动过渡 ----
    def draw_loading(self, img, t):
        U, W, H, s = self.U, self.W, self.H, self.scale
        cv2 = self.cv2
        img *= 0.30
        if self.chosen == "video":
            accent = U.C.CORAL
            cn, en = VIDEO_INFO["cn"], VIDEO_INFO["en"]
            footer = "Firefly RK3588 · MEDIA PLAYER"
        else:
            demo = DEMOS[self.chosen]
            accent = [U.C.CYAN, U.C.AMBER, U.C.VIOLET, U.C.GREEN][self.chosen]
            cn, en = demo["cn"], demo["en"]
            footer = "Firefly RK3588 · NPU BOOTING"
        # 真实徽标 + 呼吸(缺文件回退程序绘制logo)
        sz = U.png_logo_size(int(150 * s))
        if sz is not None:
            U.blit_png_logo(img, (W - sz[0]) // 2, int(H * 0.15) + self.safe_y,
                            int(150 * s), glow=0.4)
        else:
            U.blit_logo(img, (W - int(120 * s)) // 2, int(H * 0.22), int(120 * s),
                        pulse=np.sin(t * 2.4))
        # 旋转弧(双弧)
        cx, cy, r = int(W / 2), int(H * 0.52), int(52 * s)
        cv2.circle(img, (cx, cy), r, U.C.bgr(U.C.CYAN, 0.15), 3, cv2.LINE_AA)
        a0 = t * 300
        cv2.ellipse(img, (cx, cy), (r, r), 0, a0 % 360, a0 % 360 + 120,
                    U.C.bgr(U.C.CYAN, 0.9), 4, cv2.LINE_AA)
        cv2.ellipse(img, (cx, cy), (int(r * 0.72), int(r * 0.72)), 0, -a0 % 360, -a0 % 360 + 80,
                    U.C.bgr(accent, 0.8), 3, cv2.LINE_AA)
        cv2.circle(img, (cx, cy), int(6 * s), U.C.bgr(C_TXT, 0.9), -1, cv2.LINE_AA)
        # 文案
        verb = U.T("正在播放", "NOW PLAYING") if self.chosen == "video" else U.T("正在启动模块", "STARTING MODULE")
        U.text(img, (W / 2, H * 0.52 + r + int(66 * s)), verb,
               int(23 * s), C_TXT, anchor="mm", glow=C_CYAN, glow_gain=0.5)
        U.text(img, (W / 2, H * 0.52 + r + int(104 * s)), f"{cn}  ·  {en}",
               int(19 * s), accent, anchor="mm", glow=accent, glow_gain=0.4)
        if self.chosen == "video":
            tips = [U.T("视频播完自动返回", "AUTO-RETURN AT END OF FILM"),
                    U.T("播放器内按 ESC/q 可提前返回", "PRESS ESC/q IN PLAYER TO SKIP"),
                    U.T("点击启动器卡片可随时换节目", "TAP ANY CARD TO SWITCH SHOW")]
        else:
            tips = [U.T("手请保持在画面中央", "KEEP YOUR HAND IN FRAME"),
                    U.T("识别结果将实时下发灵巧手", "GESTURES STREAM TO CYBERHAND LIVE"),
                    U.T("退出演示请用画面内按钮", "USE IN-DEMO BUTTON TO EXIT")]
        tip = tips[int(t * 0.6) % 3]
        U.text(img, (W / 2, H * 0.52 + r + int(148 * s)), tip, int(14 * s), C_MUT, anchor="mm")
        U.text(img, (W / 2, H - self.safe_y - int(56 * s)), footer,
               int(12 * s), C_MUT, anchor="mm", spacing=int(3 * s))

    # ---------- 主循环 ----------
    def run(self):
        cv2 = self.cv2
        print(f"[launcher] {self.W}x{self.H} | 中文:{'有' if self.U.T('是', '') else '无'} | "
              f"NPU:{'ready' if self.npu_ok else '--'} | 串口:{self.serial_dev or '无'}", flush=True)
        self.create_window()
        try:
            while not self.quit:
                if self.mode == "video":         # 内置视频播放(自循环imshow)
                    self.play_video_cv()
                    continue
                now = time.time()
                img = self.render_frame(now)
                # fps 统计
                self._fps_n += 1
                if now - self._fps_t >= 1.0:
                    self.fps = self.fps * 0.5 + (self._fps_n / (now - self._fps_t)) * 0.5
                    self._fps_n, self._fps_t = 0, now
                cv2.imshow(WIN_NAME, (np.clip(img, 0, 1) * 255).astype(np.uint8))
                if self.mode == "loading":
                    self.poll_loading()          # demo窗口出现->交接屏幕; demo退出->重建窗口
                key = cv2.waitKey(1) & 0xFF
                self.handle_key(key)
        except KeyboardInterrupt:
            pass
        finally:
            if self.proc is None:
                cv2.destroyAllWindows()
            else:
                self.proc.wait()
                cv2.destroyAllWindows()

    def handle_key(self, key):
        if self.mode == "loading":
            return
        if key in (27, ord("q")):
            self.mode = "confirm" if self.mode == "menu" else "menu"
        elif self.mode == "confirm" and key in (ord("y"), ord("Y")):
            self.quit = True
        elif self.mode == "confirm" and key in (ord("n"), ord("N"), 27):
            self.mode = "menu"
        elif self.mode == "menu":
            if ord("1") <= key <= ord("4"):
                idx = key - ord("1")
                if idx < len(DEMOS):
                    self.launch(idx)
            elif key in (ord("s"), ord("S")):
                self.serial_on = not self.serial_on


# 配色快捷名(render 函数里用)
def _bind_colors():
    global C_TXT, C_SUB, C_MUT, C_CYAN
    C_TXT = LC.C.TXT
    C_SUB = LC.C.SUB
    C_MUT = LC.C.MUT
    C_CYAN = LC.C.CYAN


def main():
    ap = argparse.ArgumentParser(description="Firefly 展会UI启动器")
    ap.add_argument("--shot", metavar="DIR", help="无窗口渲染预览图到指定目录")
    ap.add_argument("--size", default=None, help="WxH, 默认xrandr/1920x1080")
    args = ap.parse_args()

    if args.size:
        w, h = args.size.lower().split("x")
        W, H = int(w), int(h)
    else:
        W, H = screen_size()

    global LC
    import ui_style as LC
    _bind_colors()

    lau = Launcher(W, H)
    if args.shot:
        os.makedirs(args.shot, exist_ok=True)
        lau.serial_dev, lau.serial_on, lau.npu_ok = "/dev/ttyACM0", True, True
        lau.fps = 31.6
        shots = [("menu", "menu", -1, -1, 0),
                 ("menu_hover", "menu", 960, 540, 0),
                 ("confirm", "confirm", -1, -1, 0),
                 ("loading", "loading", -1, -1, 1),
                 ("loading_video", "loading", -1, -1, "video")]
        for name, mode, mx, my, chosen in shots:
            lau.mode, lau.chosen = mode, chosen
            lau.mx, lau.my = mx, my
            img = None
            for _ in range(36):                  # 预热: 悬停/网格动画收敛到稳态
                img = lau.render_frame(5.2 + _ * 0.03)
            out = os.path.join(args.shot, f"{name}.png")
            lau.cv2.imwrite(out, (np.clip(img, 0, 1) * 255).astype(np.uint8))
            print("[shot]", out)
        return

    if os.environ.get("DISPLAY") is None:
        print("[error] 无 DISPLAY, 板端请在本机桌面终端运行; 设计预览用 --shot", flush=True)
        sys.exit(1)
    lau.run()


if __name__ == "__main__":
    _setup_display()
    main()
