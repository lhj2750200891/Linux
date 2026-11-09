#!/usr/bin/env python3
# 手势识别(纯识别, 无控制): 摄像头 -> mediapipe 21关键点 -> 6路关节角 -> 板子屏幕显示
# 角度含义: [拇指弯, 食指弯, 中指弯, 无名指弯, 小指弯, 拇指旋转], 0=伸直/贴掌, 255=全弯/外展
# 确认识别效果没问题后, 再在此基础上加灵巧手控制
import glob, os, sys, time
os.environ.setdefault("DISPLAY", ":0")
if "XAUTHORITY" not in os.environ:
    a = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
    os.environ["XAUTHORITY"] = a[-1] if a else ""
os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")   # GPU delegate 初始化EGL必需

import cv2, numpy as np, mediapipe as mp

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

# 用法: python hand_detect.py [--gpu] [--w 640 --h 480]
#   --gpu        推理走GPU(Mali), 失败则退回CPU
#   --w/--h      摄像头采集分辨率, 越低越快(模型内部反正缩到256, 手离得近就够用)
import argparse
ap = argparse.ArgumentParser()
ap.add_argument("--cpu", action="store_true")   # 强制CPU推理(GPU失败会自动回退,一般不用)
ap.add_argument("--w", type=int, default=640)
ap.add_argument("--h", type=int, default=480)
args = ap.parse_args()

# ---------- 关键点 -> 关节角 ----------
FINGERS = [(5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)]   # (mcp, pip, tip): 食中无小

def bend255(lm, mcp, pip, tip):
    """两段骨向量夹角 -> 弯曲度0~255. 0=伸直, 255=全弯"""
    v1 = np.subtract(lm[pip], lm[mcp]); v2 = np.subtract(lm[tip], lm[pip])
    c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    theta = np.degrees(np.arccos(np.clip(c, -1, 1)))       # 直=0度, 全弯约120度
    return int(np.clip(theta / 120.0, 0, 1) * 255)

def thumb_rot255(lm):
    """拇指旋转: 腕->拇指关节 与 腕->食指根 的张开角 -> 0~255 (0=贴掌, 255=外展)"""
    w = lm[0]
    d = np.subtract(lm[2], w); ref = np.subtract(lm[5], w)
    c = np.dot(d, ref) / (np.linalg.norm(d) * np.linalg.norm(ref) + 1e-6)
    ang = np.degrees(np.arccos(np.clip(c, -1, 1)))         # 并拢约20-40度, 张开约60-90度
    return int(np.clip((ang - 25) / 45.0, 0, 1) * 255)

def retarget(lm):
    """6路角度: [拇指弯, 食指弯, 中指弯, 无名指弯, 小指弯, 拇指旋转]"""
    bends = [bend255(lm, m, p, t) for m, p, t in FINGERS]
    return [bend255(lm, 1, 2, 4), *bends, thumb_rot255(lm)]

# ---------- 主循环 ----------
def build(delegate):
    return mp.tasks.vision.HandLandmarker.create_from_options(
        mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL, delegate=delegate),
            running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=1))

landmarker = None
if not args.cpu:
    try:
        landmarker = build(mp.tasks.BaseOptions.Delegate.GPU)   # 实测30fps
        print("[infer] GPU", flush=True)
    except Exception as e:
        print("[infer] GPU failed -> CPU:", str(e)[:80], flush=True)
if landmarker is None:
    landmarker = build(mp.tasks.BaseOptions.Delegate.CPU)       # 实测17fps
    print("[infer] CPU", flush=True)

cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.w); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.h)

CONNS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),
         (11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(17,18),(18,19),(19,20),(0,17)]
ts, fps, n, t_last = 0, 0.0, 0, time.time()
while True:
    ok, img = cap.read()
    if not ok: continue
    n += 1
    img = cv2.rotate(img, cv2.ROTATE_180)                 # 摄像头倒装, 转正
    ts += 33                                              # VIDEO模式递增毫秒时间戳
    res = landmarker.detect_for_video(mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), ts)
    if res.hand_landmarks:
        lm = [(p.x, p.y, p.z) for p in res.hand_landmarks[0]]
        ang6 = retarget(lm)                               # 识别结果, 留给后续控制用
        h, w = img.shape[:2]
        pts = [(int(p[0]*w), int(p[1]*h)) for p in lm]    # lm是3维(x,y,z), 画图只用x,y
        for a, b in CONNS: cv2.line(img, pts[a], pts[b], (0,255,0), 2)
        for p in pts: cv2.circle(img, p, 3, (0,0,255), -1)
    now = time.time()
    if now - t_last >= 1.0:
        fps = fps * 0.5 + (n / (now - t_last)) * 0.5      # 帧数/间隔, 平滑fps
        n, t_last = 0, now
    cv2.putText(img, f"{fps:.1f} fps", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
    cv2.imshow("hand detect", img)
    if cv2.waitKey(1) == ord("q"): break
