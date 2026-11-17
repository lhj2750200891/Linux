#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui_style.py — Firefly 展会UI 绘制库 (launcher.py 的底层, 也可复用到其他界面)
纯 OpenCV + numpy 实现, 零新增依赖; 中文文字经 PIL 渲染(自动探测系统中文字体,
没有 PIL/中文字体时自动降级为英文 cv2 渲染, 界面不会崩).

内容速查:
  C            科技风配色(RGB元组)
  FONT / init_fonts()   CJK字体管理(单例)
  text()       文字绘制: 锚点/字距/辉光/透明度
  T()          中英文案选择(无中文字体环境自动用英文)
  glow_sprite / blit_sprite   径向辉光精灵(萤火虫/光晕都用它)
  rrect / capsule / brackets / hexagon / vline_fade   几何图元
  neon_layer / add_layer   霓虹线稿画法: 画在黑底->高斯模糊成辉光->叠加
  Background   动态背景: 渐变+暗角+透视网格+萤火虫粒子+扫描光带+电路走线+边框装饰
  firefly_logo()   程序绘制的萤火虫logo(琥珀色发光腹部, 返回画布+腹部坐标)
  icon_digits / icon_follow / icon_pose   三个demo的动态图标
"""
import glob
import os
import subprocess

import cv2
import numpy as np

F32 = np.float32

# ============================== 配色 (RGB) ==============================
class C:
    BG_TOP   = (13, 18, 34)      # 背景顶部 深空蓝
    BG_BOT   = (3, 5, 11)        # 背景底部 近黑
    CYAN     = (0, 229, 255)     # 主色 青(科技)
    AMBER    = (255, 180, 84)    # 萤火虫琥珀(暖光)
    VIOLET   = (168, 120, 255)   # 紫(点缀)
    GREEN    = (64, 235, 170)    # 状态绿
    CORAL    = (252, 108, 92)    # 珊瑚橙(Firefly 徽标主色, 中央视频位)
    RED      = (255, 92, 106)    # 退出/告警
    TXT      = (234, 246, 255)   # 主文字
    SUB      = (128, 152, 190)   # 次文字
    MUT      = (74, 90, 118)     # 弱文字
    GRID_DIM = (16, 84, 112)     # 网格暗青

    @staticmethod
    def bgr(rgb, a=1.0):
        """RGB -> BGR float 元组(乘透明度), 供 cv2 绘制函数用"""
        return (rgb[2] / 255 * a, rgb[1] / 255 * a, rgb[0] / 255 * a)


# ============================== 字体管理 ==============================
_FONT = None          # Fonts 单例, init_fonts() 后可用
_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]


def _find_cjk_font():
    """找系统中文字体: 常见路径 -> fc-list 兜底"""
    for p in _FONT_PATHS:
        if os.path.exists(p):
            return p
    try:
        out = subprocess.check_output(["fc-list", ":lang=zh", "file"],
                                      timeout=3, stderr=subprocess.DEVNULL).decode()
        for line in out.splitlines():
            p = line.strip().rstrip(":").split(":")[0].strip()
            if p and os.path.exists(p):
                return p
    except Exception:
        pass
    for p in glob.glob(os.path.expanduser("~/.fonts/*.tt*")):   # 用户字体兜底
        return p
    return None


class Fonts:
    """中文经 PIL 渲染成 alpha 图缓存, 绘制时直接混合; 无 PIL/字体时降级 cv2 英文"""

    def __init__(self):
        self.path = None
        self.cjk = False       # 是否有可用中文字体
        self._pil = None
        self._cache = {}       # (text, px, spacing) -> float32 alpha (h,w)
        try:
            from PIL import ImageFont  # noqa: F401
            self._pil = ImageFont
        except Exception:
            self._pil = None
        if self._pil:
            self.path = _find_cjk_font()
            self.cjk = self.path is not None
        self._fonts = {}       # px -> ImageFont
        self._sc_idx = 0       # ttc 里简体中文子字体的索引

    def init(self):
        if self._pil and self.cjk:
            self._sc_idx = self._detect_sc_index()

    def _detect_sc_index(self):
        """NotoSansCJK-*.ttc 含 JP/KR/SC/TC 多个字面, 优先选 SC(简体)"""
        for i in range(6):
            try:
                f = self._pil.truetype(self.path, 16, index=i)
                name = " ".join(str(n) for n in f.getname())
                if "SC" in name or "Simplified" in name:
                    return i
            except Exception:
                break
        return 0

    def get(self, px):
        f = self._fonts.get(px)
        if f is None:
            if self._pil:
                f = self._pil.truetype(self.path, int(px), index=self._sc_idx)
            else:
                f = None
            self._fonts[px] = f
        return f

    def alpha(self, text, px, spacing=0):
        """渲染文字 -> float32 alpha 图 (h,w), 0~1. 结果缓存(含辉光版)"""
        key = (text, int(px), float(spacing))
        hit = self._cache.get(key)
        if hit is not None:
            return hit[0]
        if self._pil and self.cjk:
            a = self._render_pil(text, int(px), spacing)
        else:                                   # 降级: cv2 英文
            a = self._render_cv2(text, int(px))
        # 辉光版alpha一并缓存(每帧对同一文字不再重复高斯模糊)
        sigma = max(2.5, int(px) * 0.16)
        ag = cv2.GaussianBlur(np.clip(a * 1.3, 0, 1), (0, 0), sigma)
        if len(self._cache) > 400:              # 防极端情况内存膨胀
            self._cache.clear()
        self._cache[key] = (a, ag)
        return a

    def alpha_glow(self, text, px, spacing=0):
        """同 alpha(), 但返回 (原alpha, 辉光alpha) 二元组"""
        key = (text, int(px), float(spacing))
        self.alpha(text, px, spacing)
        return self._cache[key]

    def _render_pil(self, text, px, spacing):
        from PIL import Image, ImageDraw
        font = self.get(px)
        pad = int(px * 0.5) + 10                # 大留白: 辉光模糊在画布边缘自然衰减, 不出现硬边
        if spacing > 0 and len(text) > 1:       # 逐字符排, 实现字距
            ws = [font.getlength(ch) for ch in text]
            w = int(sum(ws) + spacing * (len(text) - 1)) + pad * 2
            asc, desc = font.getmetrics()
            h = int(asc + desc) + pad * 2
            img = Image.new("L", (max(w, 1), max(h, 1)), 0)
            d = ImageDraw.Draw(img)
            x = float(pad)
            for ch, cw in zip(text, ws):
                d.text((x, pad), ch, font=font, fill=255)
                x += cw + spacing
        else:
            bbox = font.getbbox(text)
            w = int(bbox[2] - bbox[0]) + pad * 2
            h = int(bbox[3] - bbox[1]) + pad * 2
            img = Image.new("L", (max(w, 1), max(h, 1)), 0)
            ImageDraw.Draw(img).text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=255)
        return np.asarray(img).astype(F32) / 255.0

    def _render_cv2(self, text, px):
        """无 PIL/中文字体: cv2 Hershey 字体渲染(只支持ASCII, 上层会用 T() 换英文)"""
        text = "".join(ch if ord(ch) < 128 else "" for ch in text)
        scale = max(0.4, px / 42.0)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        img = np.zeros((th + 14, tw + 12), np.uint8)
        cv2.putText(img, text, (6, th + 4), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, 255, max(1, int(px / 24)), cv2.LINE_AA)
        return img.astype(F32) / 255.0

    def size(self, text, px, spacing=0):
        a = self.alpha(text, px, spacing)
        return a.shape[1], a.shape[0]


def init_fonts():
    global _FONT
    if _FONT is None:
        _FONT = Fonts()
        _FONT.init()
    return _FONT


def T(cn, en):
    """有中文字体返回中文, 否则返回英文(界面永不出现乱码问号)"""
    init_fonts()
    return cn if _FONT.cjk else en


def text(img, xy, s, px, rgb, anchor="lt", spacing=0,
         glow=None, glow_gain=0.8, alpha=1.0):
    """把文字混合到 float 图上. anchor: [lmr][tmb] 左中右/上中下
    glow: 辉光色(RGB), glow_gain: 辉光强度. img 为 float32 BGR 0~1"""
    init_fonts()
    a, ag = _FONT.alpha_glow(s, px, spacing)
    h, w = a.shape
    ax, ay = anchor[0], anchor[1] if len(anchor) > 1 else "t"
    x = {"l": xy[0], "m": xy[0] - w / 2, "r": xy[0] - w}[ax]
    y = {"t": xy[1], "m": xy[1] - h / 2, "b": xy[1] - h}[ay]
    if glow is not None:
        _blend(img, x, y, ag, C.bgr(glow), alpha * glow_gain)
    _blend(img, x, y, a, C.bgr(rgb), alpha)
    return x, y, w, h


def text_size(s, px, spacing=0):
    init_fonts()
    return _FONT.size(s, px, spacing)


def _blend(img, x, y, a, col, alpha=1.0):
    """alpha 图混合到 img: col 可以是单色(长度3)或逐像素色图(h,w,3). 越界自动裁剪"""
    col = np.asarray(col, F32)
    H, W = img.shape[:2]
    x, y = int(round(x)), int(round(y))
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(W, x + a.shape[1]), min(H, y + a.shape[0])
    if x2 <= x1 or y2 <= y1:
        return
    sub = a[y1 - y:y2 - y, x1 - x:x2 - x, None] * alpha
    roi = img[y1:y2, x1:x2]
    if col.ndim == 3:                            # 逐像素(RGBA画布贴图)
        roi *= (1 - sub)
        roi += col[y1 - y:y2 - y, x1 - x:x2 - x] * sub
    else:                                        # 单色(文字)
        roi *= (1 - sub)
        roi += col[None, None, :] * sub


# ============================== 辉光精灵 ==============================
_SPRITES = {}


def glow_sprite(r, rgb, core=True):
    """径向辉光精灵 float32 (h,w,3) 已预乘alpha, blit_sprite 直接叠加"""
    key = (int(r), rgb, core)
    hit = _SPRITES.get(key)
    if hit is not None:
        return hit
    s = int(r * 4)
    yy, xx = np.mgrid[0:s, 0:s].astype(F32)
    d = np.hypot(xx - s / 2 + 0.5, yy - s / 2 + 0.5)
    a = np.exp(-(d / max(r, 1)) ** 2 * 1.9)
    if core:
        a += np.clip(1 - d / (r * 0.85), 0, 1) * 1.4
    a = np.clip(a, 0, 1.8)[..., None]
    spr = np.array(C.bgr(rgb))[None, None, :] * a
    if len(_SPRITES) > 120:
        _SPRITES.clear()
    _SPRITES[key] = spr
    return spr


def blit_sprite(img, spr, cx, cy, alpha=1.0):
    """把辉光精灵以加法叠到 img(中心对齐 cx,cy), 越界裁剪"""
    h, w = spr.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    H, W = img.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(W, x + w), min(H, y + h)
    if x2 <= x1 or y2 <= y1:
        return
    img[y1:y2, x1:x2] += spr[y1 - y:y2 - y, x1 - x:x2 - x] * alpha


# ============================== 几何图元 ==============================
def rrect(img, box, r, rgb, th=-1, alpha=1.0):
    """圆角矩形. th=-1填充, 否则描边. img: float 图"""
    x1, y1, x2, y2 = [int(v) for v in box]
    r = int(min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    col = C.bgr(rgb, alpha)
    if th == -1:
        cv2.rectangle(img, (x1 + r, y1), (x2 - r, y2), col, -1, cv2.LINE_AA)
        cv2.rectangle(img, (x1, y1 + r), (x2, y2 - r), col, -1, cv2.LINE_AA)
        for cx, cy, a0 in ((x1 + r, y1 + r, 180), (x2 - r, y1 + r, 270),
                           (x2 - r, y2 - r, 0), (x1 + r, y2 - r, 90)):
            cv2.ellipse(img, (cx, cy), (r, r), a0, 0, 90, col, -1, cv2.LINE_AA)
    else:
        cv2.line(img, (x1 + r, y1), (x2 - r, y1), col, th, cv2.LINE_AA)
        cv2.line(img, (x1 + r, y2), (x2 - r, y2), col, th, cv2.LINE_AA)
        cv2.line(img, (x1, y1 + r), (x1, y2 - r), col, th, cv2.LINE_AA)
        cv2.line(img, (x2, y1 + r), (x2, y2 - r), col, th, cv2.LINE_AA)
        for cx, cy, a0 in ((x1 + r, y1 + r, 180), (x2 - r, y1 + r, 270),
                           (x2 - r, y2 - r, 0), (x1 + r, y2 - r, 90)):
            cv2.ellipse(img, (cx, cy), (r, r), a0, 0, 90, col, th, cv2.LINE_AA)


def capsule(img, p1, p2, r, rgb, alpha=1.0):
    """圆头粗线(胶囊), 用于画手指/线稿"""
    col = C.bgr(rgb, alpha)
    cv2.line(img, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), col, int(r) * 2, cv2.LINE_AA)
    cv2.circle(img, (int(p1[0]), int(p1[1])), r, col, -1, cv2.LINE_AA)
    cv2.circle(img, (int(p2[0]), int(p2[1])), r, col, -1, cv2.LINE_AA)


def brackets(img, box, size, rgb, th=2, alpha=1.0):
    """四角括弧(科技风卡片角标)"""
    x1, y1, x2, y2 = [int(v) for v in box]
    s = int(size)
    col = C.bgr(rgb, alpha)
    for (cx, cy, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x2, y2, -1, -1), (x1, y2, 1, -1)):
        cv2.line(img, (cx, cy), (cx + dx * s, cy), col, th, cv2.LINE_AA)
        cv2.line(img, (cx, cy), (cx, cy + dy * s), col, th, cv2.LINE_AA)


def hexagon(cx, cy, r):
    import math
    return [(int(cx + r * math.cos(math.radians(a))),
             int(cy + r * math.sin(math.radians(a)))) for a in range(0, 360, 60)]


def vline_fade(img, x, y1, y2, rgb, alpha=0.3, w=1):
    """竖向渐隐细线(装饰), 向量化"""
    n = abs(int(y2 - y1))
    if n <= 0:
        return
    x = int(x)
    ys = int(min(y1, y2))
    t = np.linspace(0, 1, n, dtype=F32)[:, None]
    a = (alpha * (1 - t))[:, None]
    img[ys:ys + n, x] += np.array(C.bgr(rgb), F32)[None, :] * a


def hline_fade(img, y, x1, x2, rgb, alpha=0.3, flip=False):
    """横向渐隐细线: flip=False 从 x1 渐隐到 x2. 向量化"""
    n = abs(int(x2 - x1))
    if n <= 0:
        return
    y = int(y)
    xs = int(min(x1, x2))
    t = np.linspace(0, 1, n, dtype=F32)[:, None]
    a = alpha * ((1 - t) if not flip else t)
    img[y, xs:xs + n] += np.array(C.bgr(rgb), F32)[None, :] * a


# ============================== 霓虹线稿 ==============================
def neon_layer(w, h, draw_fn, glow_k=7, glow_gain=1.0, bright=1.0):
    """霓虹画法: 在黑底(float32画布)画线稿 -> 自身高斯模糊当辉光 -> 叠加返回 float 画布
    draw_fn(canvas_f32) 里用 cv2 常规函数画, 颜色用 C.bgr() 给 BGR 浮点元组"""
    cv_ = np.zeros((int(h), int(w), 3), F32)
    draw_fn(cv_)
    glow = cv2.GaussianBlur(cv_, (0, 0), glow_k) * glow_gain
    return cv_ * bright + glow


def add_layer(img, layer, x, y, gain=1.0):
    """把 neon_layer 画布按加法叠到 img, 越界裁剪"""
    h, w = layer.shape[:2]
    x, y = int(x), int(y)
    H, W = img.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(W, x + w), min(H, y + h)
    if x2 <= x1 or y2 <= y1:
        return
    img[y1:y2, x1:x2] += layer[y1 - y:y2 - y, x1 - x:x2 - x] * gain


# ============================== 动态背景 ==============================
class Background:
    """深空渐变 + 暗角 + 电路走线(静态) + 透视网格/萤火虫/扫描光带(动态)"""

    def __init__(self, W, H):
        self.W, self.H = int(W), int(H)
        self.hy = int(H * 0.72)                      # 地平线
        self.base = self._build_base()
        self.flies = _Fireflies(self.W, self.H)
        sw = np.zeros((240, self.W, 3), F32)         # 扫描光带
        yy = np.mgrid[0:240, 0:1][0].astype(F32)
        prof = np.exp(-((yy - 120) / 46.0) ** 2) * 0.10
        sw[:] = np.array(C.bgr((120, 235, 255)), F32)[None, None, :] * prof[:, :, None]
        self.sweep = sw

    # ---- 静态底图 ----
    def _build_base(self):
        W, H = self.W, self.H
        top = np.array(C.BG_TOP[::-1], F32) / 255      # 调色板是RGB, 画面缓冲是BGR
        bot = np.array(C.BG_BOT[::-1], F32) / 255
        g = np.linspace(0, 1, H, dtype=F32)[:, None, None]
        base = np.repeat(top * (1 - g) + bot * g, W, axis=1)
        yy, xx = np.mgrid[0:H, 0:W].astype(F32)      # 暗角
        d = ((xx / W - 0.5) ** 2 * 1.3 + (yy / H - 0.5) ** 2 * 1.15)
        base *= (1 - 0.32 * np.clip(d, 0, 1))[..., None]
        self._circuit(base)                          # 电路走线
        self._horizon(base)                          # 地平线辉光
        self._frame_deco(base)                       # 边框装饰
        return base

    def _circuit(self, base):
        W, H = self.W, self.H
        traces = [
            ([(0.018, 0.30), (0.135, 0.30), (0.190, 0.355), (0.190, 0.560)], C.CYAN),
            ([(0.018, 0.345), (0.105, 0.345), (0.150, 0.390)], C.AMBER),
            ([(0.982, 0.235), (0.870, 0.235), (0.815, 0.290), (0.815, 0.470)], C.CYAN),
            ([(0.982, 0.690), (0.905, 0.690), (0.862, 0.647)], C.AMBER),
            ([(0.018, 0.760), (0.090, 0.760), (0.128, 0.798)], C.CYAN),
        ]
        for pts, rgb in traces:
            pix = [(int(x * W), int(y * H)) for x, y in pts]
            cv2.polylines(base, [np.array(pix)], False, C.bgr(rgb, 0.10), 1, cv2.LINE_AA)
            for p in (pix[0], pix[-1]):
                cv2.circle(base, p, 3, C.bgr(rgb, 0.22), 1, cv2.LINE_AA)

    def _horizon(self, base):
        W, H, hy = self.W, self.H, self.hy
        for i in range(90):                          # 地平线下方辉光带
            a = 0.10 * np.exp(-(i / 24.0) ** 2)
            base[hy + i, :] += np.array(C.bgr(C.CYAN, a), F32)[None, :]
        base[hy - 1:hy + 1, :] += np.array(C.bgr(C.CYAN, 0.12), F32)[None, None, :]

    def _frame_deco(self, base):
        W, H = self.W, self.H
        cv2.rectangle(base, (12, 12), (W - 12, H - 12), C.bgr(C.CYAN, 0.07), 1, cv2.LINE_AA)
        brackets(base, (20, 20, W - 20, H - 20), 30, C.CYAN, 2, 0.34)
        step = max(120, W // 14)                     # 顶/底边刻度
        for x in range(int(step * 0.5), W - 30, step):
            cv2.line(base, (x, 13), (x, 21), C.bgr(C.CYAN, 0.15), 1, cv2.LINE_AA)
            cv2.line(base, (x, H - 13), (x, H - 21), C.bgr(C.CYAN, 0.15), 1, cv2.LINE_AA)

    # ---- 动态层 ----
    def draw(self, t):
        """返回合成好的一帧 float32 图. t: 秒"""
        W, H, hy = self.W, self.H, self.hy
        img = self.base.copy()
        # 透视网格: 纵向放射线
        for k in range(-9, 10):
            if k == 0:
                continue
            a = max(0.0, 0.20 - 0.014 * abs(k))
            x2 = W * 0.5 + k * (W / 7.0)
            cv2.line(img, (int(W * 0.5), hy), (int(x2), H),
                     C.bgr(C.GRID_DIM, a), 1, cv2.LINE_AA)
        # 透视网格: 横线由远及近滚动
        n = 9
        for i in range(n):
            p = ((i + t * 0.42) % n) / n
            y = hy + (H - hy) * (p ** 2.7)
            a = 0.05 + 0.28 * p
            col = tuple((np.array(C.bgr(C.GRID_DIM), F32) * (0.4 + 2.0 * p) * a).tolist())
            cv2.line(img, (0, int(y)), (W, int(y)), col, 1, cv2.LINE_AA)
        # 地平线呼吸
        img[hy - 1:hy + 1, :] += np.array(C.bgr(C.CYAN, 0.05 + 0.05 * np.sin(t * 1.8)), F32)[None, None, :]
        # 扫描光带
        y0 = (t * 46) % (H + 480) - 480
        blit_sprite(img, self.sweep, W / 2, y0 + 120, 1.0)
        # 萤火虫粒子
        self.flies.draw(img, t)
        return img


class _Fireflies:
    """萤火虫粒子: 正弦漂移 + 呼吸明灭, 大多琥珀色, 少量青色"""

    def __init__(self, W, H, n=36):
        rng = np.random.default_rng(7)
        self.n = n
        self.px = rng.uniform(0.02, 0.98, n)
        self.py = rng.uniform(0.06, 0.95, n)
        self.ph = rng.uniform(0, 6.28, n)
        self.sp = rng.uniform(0.45, 1.05, n)
        self.r = rng.integers(3, 9, n).astype(F32)
        self.ax = rng.uniform(16, 62, n)
        self.ay = rng.uniform(10, 40, n)
        self.rgb = [C.AMBER if rng.uniform() < 0.72 else C.CYAN for _ in range(n)]

    def draw(self, img, t):
        W, H = img.shape[1], img.shape[0]
        for i in range(self.n):
            x = (self.px[i] * W + np.sin(t * 0.28 * self.sp[i] + self.ph[i]) * self.ax[i]) % W
            y = (self.py[i] * H + np.cos(t * 0.22 * self.sp[i] + self.ph[i] * 1.7) * self.ay[i]) % H
            a = 0.16 + 0.40 * (0.5 + 0.5 * np.sin(t * 1.6 * self.sp[i] + self.ph[i] * 2.3))
            blit_sprite(img, glow_sprite(self.r[i], self.rgb[i]), x, y, a)


# ============================== Firefly 萤火虫 Logo ==============================
_LOGO_CACHE = {}


def firefly_logo(size=120):
    """程序绘制的萤火虫logo. 返回 (RGBA画布f32, 腹部相对坐标(x,y)) — 缓存"""
    size = int(size)
    hit = _LOGO_CACHE.get(size)
    if hit is not None:
        return hit
    s = size / 150.0
    cx, cy = size * 0.52, size * 0.52

    def draw(cv_):
        cyan = C.bgr(C.CYAN, 1.0)
        amber = C.bgr(C.AMBER, 1.0)
        white = (1.0, 1.0, 1.0)
        # 翅膀(两片, 斜置椭圆)
        cv2.ellipse(cv_, (int(cx - 20 * s), int(cy - 10 * s)), (int(36 * s), int(13 * s)),
                    -30, 0, 360, cyan, max(2, int(2.6 * s)), cv2.LINE_AA)
        cv2.ellipse(cv_, (int(cx + 20 * s), int(cy - 10 * s)), (int(36 * s), int(13 * s)),
                    30, 0, 360, cyan, max(2, int(2.6 * s)), cv2.LINE_AA)
        cv2.ellipse(cv_, (int(cx - 16 * s), int(cy - 8 * s)), (int(20 * s), int(7 * s)),
                    -30, 0, 360, C.bgr(C.CYAN, 0.55), max(1, int(1.6 * s)), cv2.LINE_AA)
        cv2.ellipse(cv_, (int(cx + 16 * s), int(cy - 8 * s)), (int(20 * s), int(7 * s)),
                    30, 0, 360, C.bgr(C.CYAN, 0.55), max(1, int(1.6 * s)), cv2.LINE_AA)
        # 身体(头->腹胶囊轮廓)
        cv2.line(cv_, (int(cx), int(cy - 20 * s)), (int(cx), int(cy + 24 * s)),
                 cyan, max(3, int(11 * s)), cv2.LINE_AA)
        # 头
        cv2.circle(cv_, (int(cx), int(cy - 22 * s)), int(7 * s), white, -1, cv2.LINE_AA)
        # 触角
        cv2.line(cv_, (int(cx - 3 * s), int(cy - 28 * s)), (int(cx - 12 * s), int(cy - 40 * s)),
                 cyan, max(2, int(2.4 * s)), cv2.LINE_AA)
        cv2.line(cv_, (int(cx + 3 * s), int(cy - 28 * s)), (int(cx + 12 * s), int(cy - 40 * s)),
                 cyan, max(2, int(2.4 * s)), cv2.LINE_AA)
        # 发光腹部(琥珀)
        cv2.circle(cv_, (int(cx), int(cy + 22 * s)), int(9 * s), amber, -1, cv2.LINE_AA)
        cv2.circle(cv_, (int(cx), int(cy + 22 * s)), int(4 * s), (1.0, 1.0, 1.0), -1, cv2.LINE_AA)
        # 飞行轨迹点
        for i, a in enumerate((0.5, 0.3, 0.16)):
            cv2.circle(cv_, (int(cx - 34 * s - i * 12 * s), int(cy + 38 * s + i * 9 * s)),
                       int((3 - i * 0.8) * s), C.bgr(C.AMBER, a), -1, cv2.LINE_AA)

    layer = neon_layer(size, size, draw, glow_k=6, glow_gain=1.15, bright=1.1)
    a = np.clip(layer.max(axis=2), 0, 1)[..., None]
    canvas = np.concatenate([layer, a], axis=2)      # RGBA(预乘)
    _LOGO_CACHE[size] = (canvas, (cx, cy + 22 * s))
    return canvas, (cx, cy + 22 * s)


def blit_logo(img, x, y, size=120, alpha=1.0, pulse=0.0):
    """贴logo(alpha混合) + 腹部琥珀呼吸辉光. x,y=左上角"""
    canvas, (abx, aby) = firefly_logo(size)
    blit_sprite(img, glow_sprite(size * 0.16, C.AMBER), x + abx, y + aby,
                0.35 + 0.25 * pulse)
    _blend(img, x, y, canvas[..., 3], canvas[..., :3], alpha)


# ---- 真实徽标: ui/logo.png(带alpha通道直接用; 无alpha的图自动抠白底做透明处理) ----
_PNG_LOGO = {"path": os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png"),
             "state": 0, "src": None, "cache": {}}    # state: 0未探测 1可用 -1缺失


def png_logo_canvas(h):
    """按高度缩放 ui/logo.png -> RGBA float 画布(BGR 0~1 + alpha), 结果缓存; 缺失返回 None"""
    st = _PNG_LOGO
    if st["state"] == 0:
        try:
            src = cv2.imread(st["path"], cv2.IMREAD_UNCHANGED)
            if src is None:
                st["state"] = -1
            else:
                if src.ndim == 2:
                    src = cv2.cvtColor(src, cv2.COLOR_GRAY2BGR)
                if src.shape[2] == 3:                # 无alpha: 透明处理 = 越接近白越透明
                    mn = src.min(axis=2).astype(F32)
                    a = np.clip((255.0 - mn) * 2.2, 0, 255)
                    src = np.dstack([src, a.astype(np.uint8)])
                st["src"] = src
                st["state"] = 1
        except Exception:
            st["state"] = -1
    if st["state"] != 1:
        return None
    h = max(8, int(h))
    canvas = st["cache"].get(h)
    if canvas is None:
        src = st["src"]
        w = max(1, int(round(src.shape[1] * h / src.shape[0])))
        r = cv2.resize(src, (w, h), interpolation=cv2.INTER_AREA).astype(F32)
        canvas = np.concatenate([r[..., :3] / 255.0, r[..., 3:4] / 255.0], axis=2)
        if len(st["cache"]) > 24:
            st["cache"].clear()
        st["cache"][h] = canvas
    return canvas


def png_logo_size(h):
    """真实徽标按高度 h 缩放后的 (w, h); 缺失返回 None"""
    c = png_logo_canvas(h)
    return None if c is None else (c.shape[1], c.shape[0])


def blit_png_logo(img, x, y, h, alpha=1.0, glow=0.3):
    """贴真实徽标(透明混合 + 淡白辉光), 返回宽度; 文件缺失返回 None(调用方回退程序logo)"""
    canvas = png_logo_canvas(h)
    if canvas is None:
        return None
    a = canvas[..., 3]
    if glow > 0:
        ag = cv2.GaussianBlur(a, (0, 0), max(3.0, canvas.shape[0] * 0.10)) * glow * 0.5
        ih, iw = img.shape[:2]
        x, y = int(x), int(y)
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(iw, x + ag.shape[1]), min(ih, y + ag.shape[0])
        if x2 > x1 and y2 > y1:
            img[y1:y2, x1:x2] += (ag[y1 - y:y2 - y, x1 - x:x2 - x, None]
                                  * np.array((1.0, 1.0, 1.0), F32)[None, None, :])
    _blend(img, x, y, a, canvas[..., :3], alpha)
    return canvas.shape[1]


# ============================== 三个 demo 图标 (霓虹线稿, 动态) ==============================
# 颜色约定: capsule() 等 helper 收 RGB(0~255); 直接调 cv2 的地方用 C.bgr() 转成 BGR 浮点
_WHITE = (235, 245, 255)          # 指尖/高亮白 (RGB)
_DIM = (150, 170, 195)            # 折叠手指灰蓝 (RGB)


def icon_digits(img, cx, cy, t, s=1.0, accent=C.CYAN):
    """数字手势: 手掌线稿(示3指) + 大数字3 + 扫描弧"""
    w, h = int(300 * s), int(240 * s)
    ox, oy = int(cx - w // 2), int(cy - h // 2)

    def draw(cv_):
        ac = C.bgr(accent, 1.0)
        import math
        palm = (108 * s, 168 * s)                    # 掌心(canvas坐标)
        # 五指: (相对掌心x, 长度, 角度deg, 是否竖起)
        fingers = [(-44, 22, 152, False), (-23, 66, 104, True), (0, 80, 90, True),
                   (23, 66, 76, True), (44, 24, 28, False)]
        for dx, ln, ang, up in fingers:
            r = math.radians(ang)
            x1, y1 = palm[0] + dx * s, palm[1]
            x2 = x1 + math.cos(r) * ln * s
            y2 = y1 - math.sin(r) * ln * (s if up else s * 0.5)
            if up:
                capsule(cv_, (x1, y1), (x2, y2), int(4 * s), _WHITE)
                cv2.circle(cv_, (int(x2), int(y2)), int(5 * s), ac, -1, cv2.LINE_AA)
            else:
                capsule(cv_, (x1, y1), (x2, y2), int(4 * s), _DIM)
        # 掌 + 腕
        cv2.ellipse(cv_, (int(palm[0]), int(palm[1] + 20 * s)),
                    (int(54 * s), int(38 * s)), 0, 0, 360, ac, max(2, int(2.2 * s)), cv2.LINE_AA)
        cv2.line(cv_, (int(palm[0] - 28 * s), int(palm[1] + 58 * s)),
                 (int(palm[0] + 28 * s), int(palm[1] + 58 * s)), ac, max(2, int(2.2 * s)), cv2.LINE_AA)
        # 扫描弧(绕手旋转, 双弧)
        a0 = t * 90 % 360
        cv2.ellipse(cv_, (int(palm[0]), int(palm[1] + 6 * s)), (int(96 * s), int(96 * s)),
                    0, a0, a0 + 70, ac, 2, cv2.LINE_AA)
        cv2.ellipse(cv_, (int(palm[0]), int(palm[1] + 6 * s)), (int(96 * s), int(96 * s)),
                    0, a0 + 180, a0 + 250, C.bgr(accent, 0.45), 2, cv2.LINE_AA)

    add_layer(img, neon_layer(w, h, draw, glow_k=6, glow_gain=0.9), ox, oy)
    # 大数字 3 (PIL渲染带辉光)
    text(img, (ox + 242 * s, oy + 116 * s), "3", int(84 * s), C.TXT,
         anchor="mm", glow=accent, glow_gain=0.9)


def icon_follow(img, cx, cy, t, s=1.0, accent=C.AMBER):
    """灵巧手跟随: 人手(青) -> 数据流(动画箭头) -> 机械手(琥珀)"""
    w, h = int(300 * s), int(240 * s)
    ox, oy = int(cx - w // 2), int(cy - h // 2)

    def draw(cv_):
        cyan = C.bgr(C.CYAN, 1.0)
        amber = C.bgr(accent, 1.0)
        w8 = C.bgr(_WHITE)
        import math
        # ---- 左: 人手(简化线稿, 5指) ----
        hx, hy_ = 74 * s, 138 * s
        cv2.circle(cv_, (int(hx), int(hy_ + 16 * s)), int(33 * s), cyan, max(2, int(2.2 * s)), cv2.LINE_AA)
        for dx, ln, ang in ((-30, 46, 120), (-10, 62, 98), (12, 60, 78), (32, 42, 52)):
            r = math.radians(ang)
            x1, y1 = hx + dx * s, hy_ - 4 * s
            x2, y2 = x1 + math.cos(r) * ln * s, y1 - math.sin(r) * ln * s
            capsule(cv_, (x1, y1), (x2, y2), int(3.5 * s), C.CYAN)
            cv2.circle(cv_, (int(x2), int(y2)), int(4 * s), w8, -1, cv2.LINE_AA)
        capsule(cv_, (hx + 30 * s, hy_ + 18 * s), (hx + 58 * s, hy_ - 4 * s), int(3.5 * s), C.CYAN)
        # ---- 右: 机械手(分段指节, 关节圆点) ----
        rx, ry_ = 226 * s, 128 * s
        cv2.rectangle(cv_, (int(rx - 34 * s), int(ry_ - 2 * s)),
                      (int(rx + 34 * s), int(ry_ + 42 * s)), amber, max(2, int(2.2 * s)), cv2.LINE_AA)
        for dx in (-24, -8, 8, 24):
            x1 = rx + dx * s
            for k in range(2):                    # 两段指节
                y1 = ry_ - 8 * s - k * 26 * s
                y2 = y1 - 22 * s
                cv2.line(cv_, (int(x1), int(y1)), (int(x1), int(y2)), amber, max(2, int(4 * s)), cv2.LINE_AA)
                cv2.circle(cv_, (int(x1), int(y2)), int(3 * s), w8, -1, cv2.LINE_AA)
            cv2.circle(cv_, (int(x1), int(ry_ - 4 * s)), int(3 * s), w8, -1, cv2.LINE_AA)
        cv2.line(cv_, (int(rx - 34 * s), int(ry_ + 12 * s)), (int(rx - 58 * s), int(ry_ - 14 * s)),
                 amber, max(2, int(4 * s)), cv2.LINE_AA)      # 拇指
        # ---- 中: 数据流(竖虚线 + 滚动箭头 ») ----
        for i in range(9):
            x = (118 + i * 10) * s
            a = 0.45 if i % 3 == 0 else 0.18
            cv2.line(cv_, (int(x), int(94 * s)), (int(x), int(166 * s)),
                     C.bgr(C.CYAN, a), 1, cv2.LINE_AA)
        ph = (t * 2.2) % 1.0
        for i in range(3):                        # 滚动箭头
            x = (116 + i * 20 + ph * 20) * s
            a = 1.0 - abs(i - 1) * 0.35
            cv2.line(cv_, (int(x - 8 * s), int(122 * s)), (int(x), int(130 * s)),
                     C.bgr(accent, a), max(2, int(3 * s)), cv2.LINE_AA)
            cv2.line(cv_, (int(x), int(130 * s)), (int(x - 8 * s), int(138 * s)),
                     C.bgr(accent, a), max(2, int(3 * s)), cv2.LINE_AA)

    add_layer(img, neon_layer(w, h, draw, glow_k=6, glow_gain=0.9), ox, oy)


def icon_pose(img, cx, cy, t, s=1.0, accent=C.VIOLET):
    """四模型固定手势: 中心手掌(顶视) + 四个模型节点(六边形)连线 + 手势标签"""
    w, h = int(300 * s), int(240 * s)
    ox, oy = int(cx - w // 2), int(cy - h // 2)

    def draw(cv_):
        ac = C.bgr(accent, 1.0)
        w8 = C.bgr(_WHITE)
        import math
        hx, hy_ = 150 * s, 126 * s
        # 中心手掌(顶视): 圆掌 + 五指辐射
        cv2.circle(cv_, (int(hx), int(hy_)), int(30 * s), ac, max(2, int(2.2 * s)), cv2.LINE_AA)
        for ang in (205, 247, 270, 293, 335):
            r = math.radians(ang)
            x1, y1 = hx + math.cos(r) * 26 * s, hy_ + math.sin(r) * 26 * s
            x2, y2 = hx + math.cos(r) * 60 * s, hy_ + math.sin(r) * 60 * s
            capsule(cv_, (x1, y1), (x2, y2), int(3.5 * s), accent)
            cv2.circle(cv_, (int(x2), int(y2)), int(4 * s), w8, -1, cv2.LINE_AA)
        # 四个模型节点(六边形) + 连线, 亮点轮流闪烁
        nodes = ((60, 50, "OK"), (240, 50, "9"), (60, 202, "LIKE"), (240, 202, "FIST"))
        for i, (nx, ny, lb) in enumerate(nodes):
            npx, npy = nx * s, ny * s
            on = (np.sin(t * 2.4 - i * 1.57) + 1) / 2
            cv2.polylines(cv_, [np.array(hexagon(npx, npy, 17 * s))], True,
                          C.bgr(accent, 0.35 + 0.65 * on), max(2, int(2 * s)), cv2.LINE_AA)
            cv2.circle(cv_, (int(npx), int(npy)), int(5 * s),
                       C.bgr(C.AMBER, 0.3 + 0.7 * on), -1, cv2.LINE_AA)
            cv2.line(cv_, (int(hx + (npx - hx) * 0.38), int(hy_ + (npy - hy_) * 0.38)),
                     (int(npx - (npx - hx) * 0.20), int(npy - (npy - hy_) * 0.20)),
                     C.bgr(accent, 0.30 + 0.40 * on), 1, cv2.LINE_AA)

    add_layer(img, neon_layer(w, h, draw, glow_k=6, glow_gain=0.9), ox, oy)
    # 节点标签(PIL, 小字)
    for nx, ny, lb in ((60, 50, "OK"), (240, 50, "9"), (60, 202, "LIKE"), (240, 202, "FIST")):
        text(img, (ox + nx * s, oy + ny * s + 26 * s), lb, int(12 * s), C.SUB, anchor="mm")


def icon_video(img, cx, cy, t, s=1.0, accent=C.CORAL):
    """宣传视频: 圆角屏 + 胶片孔 + 呼吸播放键 + 旋转弧"""
    w, h = int(300 * s), int(240 * s)
    ox, oy = int(cx - w // 2), int(cy - h // 2)

    def draw(cv_):
        rrect(cv_, (int(58 * s), int(56 * s), int(242 * s), int(184 * s)), int(16 * s),
              accent, th=max(2, int(2.2 * s)))
        for i in range(5):                       # 胶片孔
            fx = (76 + i * 32) * s
            cv2.rectangle(cv_, (int(fx), int(66 * s)), (int(fx + 12 * s), int(76 * s)),
                          C.bgr(accent, 0.5), -1, cv2.LINE_AA)
            cv2.rectangle(cv_, (int(fx), int(164 * s)), (int(fx + 12 * s), int(174 * s)),
                          C.bgr(accent, 0.5), -1, cv2.LINE_AA)
        pulse = 0.5 + 0.5 * np.sin(t * 2.6)      # 播放键(呼吸)
        tri = np.array([[(142 * s, 98 * s), (142 * s, 142 * s), (184 * s, 120 * s)]], np.int32)
        cv2.fillPoly(cv_, tri, C.bgr(accent, 0.30 + 0.45 * pulse), cv2.LINE_AA)
        cv2.polylines(cv_, tri, True, C.bgr(_WHITE, 0.9), max(2, int(2 * s)), cv2.LINE_AA)
        a0 = t * 80 % 360                        # 外圈旋转弧
        cv2.ellipse(cv_, (int(150 * s), int(120 * s)), (int(92 * s), int(92 * s)),
                    0, a0, a0 + 80, C.bgr(accent, 0.5), max(2, int(2 * s)), cv2.LINE_AA)

    add_layer(img, neon_layer(w, h, draw, glow_k=6, glow_gain=0.9), ox, oy)


def icon_rps(img, cx, cy, t, s=1.0, accent=C.GREEN):
    """石头剪刀布: 拳/掌/剪三徽章轮转高亮 + 顶部VS + 底部对抗箭头"""
    import math
    w, h = int(300 * s), int(240 * s)
    ox, oy = int(cx - w // 2), int(cy - h // 2)

    def draw(cv_):
        centers = ((70 * s, 132 * s), (150 * s, 132 * s), (230 * s, 132 * s))
        k = int(t * 1.4) % 3                     # 轮转高亮
        for i, (gx, gy) in enumerate(centers):
            on = 1.0 if i == k else 0.32
            cv2.circle(cv_, (int(gx), int(gy)), int(36 * s), C.bgr(accent, on),
                       max(2, int(2.4 * s)), cv2.LINE_AA)
            if i == k:                           # 高亮徽章外圈旋转刻度
                for adeg in range(0, 360, 30):
                    r = math.radians(adeg + t * 60)
                    cv2.line(cv_, (int(gx + math.cos(r) * 42 * s), int(gy + math.sin(r) * 42 * s)),
                             (int(gx + math.cos(r) * 48 * s), int(gy + math.sin(r) * 48 * s)),
                             C.bgr(accent, 0.8), max(1, int(2 * s)), cv2.LINE_AA)
        # 石头(拳): 圆拳 + 四个指节
        gx, gy = centers[0]
        cv2.circle(cv_, (int(gx), int(gy + 4 * s)), int(16 * s), C.bgr(_WHITE, 0.9),
                   max(2, int(2 * s)), cv2.LINE_AA)
        for dx in (-9, -3, 3, 9):
            cv2.circle(cv_, (int(gx + dx * s), int(gy - 10 * s)), int(4 * s),
                       C.bgr(_WHITE, 0.9), max(1, int(2 * s)), cv2.LINE_AA)
        # 布(掌): 五指辐射
        gx, gy = centers[1]
        for ang in (200, 245, 270, 295, 340):
            r = math.radians(ang)
            x1, y1 = gx + math.cos(r) * 8 * s, gy + 8 * s - math.sin(r) * 8 * s
            x2, y2 = gx + math.cos(r) * 24 * s, gy + 8 * s - math.sin(r) * 24 * s
            capsule(cv_, (x1, y1), (x2, y2), int(3 * s), _WHITE)
        # 剪刀: V 形双刃 + 铰点
        gx, gy = centers[2]
        cv2.line(cv_, (int(gx), int(gy + 12 * s)), (int(gx - 14 * s), int(gy - 16 * s)),
                 C.bgr(_WHITE, 0.9), max(2, int(3 * s)), cv2.LINE_AA)
        cv2.line(cv_, (int(gx), int(gy + 12 * s)), (int(gx + 14 * s), int(gy - 16 * s)),
                 C.bgr(_WHITE, 0.9), max(2, int(3 * s)), cv2.LINE_AA)
        cv2.circle(cv_, (int(gx), int(gy + 12 * s)), int(4 * s), C.bgr(_WHITE, 1.0), -1, cv2.LINE_AA)
        # 对抗箭头(滚动 »)
        ph = (t * 1.6) % 1.0
        for i in range(3):
            x = (108 + i * 24 + ph * 24) * s
            a = 0.9 - abs(i - 1) * 0.35
            cv2.line(cv_, (int(x), int(196 * s)), (int(x + 10 * s), int(204 * s)),
                     C.bgr(accent, a), max(2, int(3 * s)), cv2.LINE_AA)
            cv2.line(cv_, (int(x), int(212 * s)), (int(x + 10 * s), int(204 * s)),
                     C.bgr(accent, a), max(2, int(3 * s)), cv2.LINE_AA)

    add_layer(img, neon_layer(w, h, draw, glow_k=6, glow_gain=0.9), ox, oy)
    text(img, (ox + 150 * s, oy + 52 * s), "VS", int(26 * s), C.TXT,
         anchor="mm", glow=accent, glow_gain=0.8, spacing=int(4 * s))


def icon_dispatch(name, img, cx, cy, t, s=1.0, accent=C.CYAN):
    {"digits": icon_digits, "follow": icon_follow, "pose": icon_pose,
     "video": icon_video, "rps": icon_rps}[name](img, cx, cy, t, s, accent)
