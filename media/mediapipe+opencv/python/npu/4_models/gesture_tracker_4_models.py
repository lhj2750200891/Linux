#!/usr/bin/env python3
# 手部追踪 + 8类手势识别(NPU 4模型全流程), 视觉demo不接灵巧手
# 手势集(官方canned分类器): Closed_Fist握拳 / Open_Palm手掌 / Pointing_Up指向 / Thumb_Down拇下
#                          / Thumb_Up点赞 / Victory胜利 / ILoveYou / None无
# 追踪+识别由 hand_npu_4_models.py 的 HandNPU4 实现(带ROI追踪, 丢失自动回退palm检测;
# 手势段为三探针集成, detect返回完整8类概率probs)
# 实时: 8类概率做EMA平滑, 超过采纳阈值才显示、跌破释放阈值才撤下(滞回防边界闪烁)
# 交互与其他demo同一套: START开始 / PAUSE暂停(画面静止, 不抓图不识别) / EXIT退出
# 状态行每5秒打印: fps 和 抓图->识别 耗时
import glob, os, signal, sys, time
os.environ["DISPLAY"] = ":0"
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"
_a = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
if _a:
    os.environ["XAUTHORITY"] = _a[-1]

import cv2, numpy as np
from hand_npu_4_models import HandNPU4, GESTURES

EMA_A = 0.35       # EMA系数(新帧权重): 约5帧记忆, 单帧毛刺打不垮; 响应约0.2s
ADOPT = 0.40       # 采纳阈值: 平滑概率的EMA超过它才显示新手势
RELEASE = 0.18     # 释放阈值(滞回): 已显示手势的EMA跌破它才撤下, 边界抖动不再反复闪/清

eng = HandNPU4()   # 本目录4个.rknn: hand_detector / hand_landmarks_detector / gesture_embedder / canned_gesture_classifier

cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[error] 摄像头打开失败, 先查占用: pgrep -af gesture_tracker\\|hand_")
    sys.exit(1)

def screen_size():
    """屏幕分辨率: xrandr读, 失败按1920x1080兜底"""
    try:
        import re, subprocess
        out = subprocess.check_output(["xrandr", "--current"], timeout=2).decode()
        m = re.search(r"(\d+)x(\d+)\+0\+0", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 1920, 1080

SW, SH = screen_size()
cv2.namedWindow("gesture tracker", cv2.WINDOW_NORMAL)
cv2.resizeWindow("gesture tracker", SW, SH)
cv2.imshow("gesture tracker", np.zeros((480, 640, 3), np.uint8))   # 先显示一帧让窗口真正映射出来
cv2.waitKey(200)
try:
    import win_fullscreen
    win_fullscreen.make_fullscreen("gesture tracker", wait=5)
except Exception as e:
    print("[fullscreen] fail:", e, flush=True)

# ---- 屏上按钮: START开始 / PAUSE暂停(静止) / EXIT退出, 触摸/鼠标点击=左键 ----
STATE = "idle"          # idle=预览未开始 / running=识别 / paused=画面静止(不抓图不识别)
QUIT = False
BTN_RECTS = {}

def _on_sigint(sig, frame):
    global QUIT
    QUIT = True            # ^C落在NPU推理里会被rknnlite吞掉, 改用信号标志保证一定能干净退出
signal.signal(signal.SIGINT, _on_sigint)

_last_click = [0.0]

def on_mouse(event, x, y, flags, param):
    global STATE, QUIT
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    if time.time() - _last_click[0] < 0.3:      # 触摸/Qt偶发一次点击投递两次事件;
        return                                  # PAUSE/RESUME是toggle, 双投递会互相抵消, 300ms内去重
    _last_click[0] = time.time()
    for name, (x1, y1, x2, y2) in BTN_RECTS.items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            if name == "exit":
                QUIT = True
            elif name == "start" and STATE == "idle":
                STATE = "running"
            elif name == "pause":
                STATE = "paused" if STATE == "running" else "running"

cv2.setMouseCallback("gesture tracker", on_mouse)

def draw_buttons(img):
    """底部按钮条, 随状态变化: idle:[START EXIT] running:[PAUSE EXIT] paused:[RESUME EXIT]"""
    h, w = img.shape[:2]
    bh = 64
    img[h - bh:, :] = (img[h - bh:, :] * 0.4).astype(np.uint8)
    bw_, bh_, gap = 200, 44, 60
    items = {
        "idle":    [("start", "START", (60, 150, 60)), ("exit", "EXIT", (60, 60, 200))],
        "running": [("pause", "PAUSE", (60, 150, 60)), ("exit", "EXIT", (60, 60, 200))],
        "paused":  [("pause", "RESUME", (30, 150, 220)), ("exit", "EXIT", (60, 60, 200))],
    }[STATE]
    total = len(items) * bw_ + (len(items) - 1) * gap
    x0 = (w - total) // 2
    y0 = h - bh + (bh - bh_) // 2
    BTN_RECTS.clear()
    for i, (nm, txt, col) in enumerate(items):
        r = (x0 + i * (bw_ + gap), y0, x0 + i * (bw_ + gap) + bw_, y0 + bh_)
        BTN_RECTS[nm] = (r[0] - 18, y0 - 6, r[2] + 18, h)   # 命中区比画的宽(避开Qt状态栏的坐标偏移)
        cv2.rectangle(img, (r[0], r[1]), (r[2], r[3]), col, -1)
        cv2.putText(img, txt, (r[0] + 62, r[3] - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

CONNS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),
         (11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(17,18),(18,19),(19,20),(0,17)]

n, fps, t_last = 0, 0.0, time.time()
lat, t_report = 0.0, time.time()          # 抓图->识别耗时(EMA平滑)
ema = np.zeros(8, np.float32)             # 8类融合概率的EMA平滑(顺序同GESTURES)
last_g = None                             # 当前已采纳手势
label = "SHOW A GESTURE"
last_img, prev_state = None, None
try:
    while True:
        if STATE == "running" and prev_state != "running":   # (重新)开局: 清空状态
            ema[:] = 0
            last_g = None
            label = "SHOW A GESTURE"
        prev_state = STATE
        pts = None
        if STATE == "paused":                  # 暂停: 不抓图不识别, 最后一帧定格显示
            if last_img is None:
                continue
            img = last_img
        else:
            ok, img = cap.read()
            if not ok: continue
            n += 1
            img = cv2.rotate(img, cv2.ROTATE_180)
            t_grab = time.time()
            if STATE == "running":             # idle只预览画面, 不跑推理省NPU
                res = eng.detect(img)
                lat = (time.time() - t_grab) if lat <= 0 else lat * 0.7 + (time.time() - t_grab) * 0.3
                if res:
                    pts = res["pts"]
                    if res["probs"] is not None:   # 多探针融合概率 -> EMA平滑(单帧毛刺打不垮)
                        ema = (1.0 - EMA_A) * ema + EMA_A * res["probs"]
                        j = int(np.argmax(ema[1:])) + 1        # 只在7个固定手势里选(None类不参与)
                        if last_g != GESTURES[j] and ema[j] >= ADOPT:
                            last_g, label = GESTURES[j], GESTURES[j].upper()
                        elif last_g is not None and ema[GESTURES.index(last_g)] < RELEASE:
                            last_g, label = None, "SHOW A GESTURE"   # 低于释放阈值才撤下
        if pts is None and STATE == "running":                 # 丢手: 立即清EMA和标签
            if last_g is not None:
                last_g, label = None, "SHOW A GESTURE"
            ema[:] = 0
        now = time.time()
        if now - t_last >= 1.0:
            fps = fps * 0.5 + (n / (now - t_last)) * 0.5
            n, t_last = 0, now
        if now - t_report >= 5.0:
            lat_s = f"{lat*1000:.0f}ms" if lat > 0 else "--ms"  # 首帧识别前没有样本
            print(f"[status] {fps:.1f} fps | 抓图->识别 {lat_s}", flush=True)
            t_report = now
        # 骨架只在固定手势成立时画(last_g=None=无手势: 不画, 免得满屏线条杂乱);
        # 用已采纳的稳定手势而不是单帧结果, 避免骨架闪烁
        if pts and last_g is not None:
            h, w = img.shape[:2]
            # 坐标clip到±2^20(int32安全): cv2 5.0只收int且超int32范围的int也会解析失败
            p2 = [(min(1 << 20, max(-(1 << 20), int(p[0] * w))),
                   min(1 << 20, max(-(1 << 20), int(p[1] * h)))) for p in pts]
            for a, b in CONNS: cv2.line(img, p2[a], p2[b], (0,255,0), 2)
            for p in p2: cv2.circle(img, p, 3, (0,0,255), -1)
        bw = (img.shape[0] * SW - img.shape[1] * SH) // (2 * SH)   # 补黑边到屏幕比例, 画面不变形
        if bw > 0:
            img = cv2.copyMakeBorder(img, 0, 0, bw, bw, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        draw_buttons(img)
        cv2.putText(img, f"{fps:.1f} fps  {lat*1000:.0f}ms" if lat > 0 else f"{fps:.1f} fps",
                    (bw + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        show = "PAUSED" if STATE == "paused" else ("PRESS START TO PLAY" if STATE == "idle" else label)
        cv2.putText(img, show, (bw + 10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
        if STATE == "running" and last_g is not None:              # 当前手势大字居中显示
            (tw_, _b), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 3)
            cv2.putText(img, label, ((img.shape[1] - tw_) // 2, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 200, 255), 3)
        cv2.imshow("gesture tracker", img)
        last_img = img.copy()                  # paused时定格的就是这帧
        if cv2.waitKey(1) == ord("q"): break
        if QUIT: break
except KeyboardInterrupt:
    pass
finally:
    cap.release(); cv2.destroyAllWindows()
