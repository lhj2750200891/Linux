#!/usr/bin/env python3
# 极简手势识别: /dev/video11 -> mediapipe手部关键点 -> 手势 -> 板子主屏显示
import glob, os
os.environ.setdefault("DISPLAY", ":0")                    # adb shell 里没有X环境, 补上
if "XAUTHORITY" not in os.environ:
    auth = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
    os.environ["XAUTHORITY"] = auth[-1] if auth else ""   # Wayland会话的X认证文件

# 模型跟脚本同目录(目录自包含); 找不到再退回板子旧部署的固定路径
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
if not os.path.exists(MODEL):
    MODEL = "/root/firefly_handle_demo/hand_landmarker.task"

import cv2, mediapipe as mp
import numpy as np

CONNS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),  # 手骨架连线
         (11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(17,18),(18,19),(19,20),(0,17)]
TIPS, PIPS = [4,8,12,16,20], [3,6,10,14,18]               # 五指指尖 / 对应关节

def gesture(lm):                                          # lm: 21个归一化(x,y)
    wrist = np.array(lm[0])
    up = [np.hypot(*np.subtract(lm[t], wrist)) >          # 指尖比关节离手腕远 = 伸直(不怕手旋转)
          np.hypot(*np.subtract(lm[p], wrist)) * 1.05 for t, p in zip(TIPS, PIPS)]
    n = sum(up)
    if n == 0:            return "FIST"
    if n == 5:            return "OPEN_PALM"
    if up[1] and up[2] and n == 2: return "VICTORY"
    if up[0] and n == 1:  return "THUMBS_UP" if lm[4][1] < lm[5][1] else "THUMB"
    if up[1] and n == 1:  return "POINT"
    return f"{n}_FINGERS"

Opts, Vision = mp.tasks.vision.HandLandmarkerOptions, mp.tasks.vision.RunningMode
landmarker = mp.tasks.vision.HandLandmarker.create_from_options(Opts(
    base_options=mp.tasks.BaseOptions(model_asset_path=MODEL),
    running_mode=Vision.VIDEO, num_hands=1))

cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

ts = same = 0
prev_raw = shown = prev_shown = "NO_HAND"
while True:
    ok, img = cap.read()
    if not ok: continue
    img = cv2.rotate(img, cv2.ROTATE_180)                 # 摄像头倒装, 转正
    ts += 33                                              # VIDEO模式要递增毫秒时间戳
    res = landmarker.detect_for_video(mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), ts)
    label = "NO_HAND"
    if res.hand_landmarks:
        lm = [(p.x, p.y) for p in res.hand_landmarks[0]]
        label = gesture(lm)
        h, w = img.shape[:2]
        pts = [(int(x*w), int(y*h)) for x, y in lm]
        for a, b in CONNS: cv2.line(img, pts[a], pts[b], (0,255,0), 2)
        for p in pts: cv2.circle(img, p, 3, (0,0,255), -1)
    same = same + 1 if label == prev_raw else 0           # 连续3帧一致才切换, 防抖
    if label == "NO_HAND" or same >= 2: shown = label
    if shown != prev_shown: print("[gesture]", shown, flush=True)
    prev_raw, prev_shown = label, shown
    cv2.putText(img, shown, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
    cv2.imshow("gesture", img)
    if cv2.waitKey(1) == ord("q"): break
