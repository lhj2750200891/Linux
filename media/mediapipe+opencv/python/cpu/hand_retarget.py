#!/usr/bin/env python3
# 手势重定向: 摄像头 -> mediapipe 21关键点 -> 6路关节角(0~255) -> 因时Inspire类串口灵巧手
# 用法:
#   python hand_retarget.py                # dry-run: 板子屏幕显示+只打印角度, 不碰串口
#   python hand_retarget.py /dev/ttyUSB0   # 实际下发到灵巧手 (115200, 8N1)
import glob, os, sys, time
os.environ.setdefault("DISPLAY", ":0")
if "XAUTHORITY" not in os.environ:
    a = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
    os.environ["XAUTHORITY"] = a[-1] if a else ""

import cv2, numpy as np, mediapipe as mp

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

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
    """返回6路角度: [拇指弯, 食指, 中指, 无名, 小指, 拇指旋转]  -- 顺序以你的协议手册为准"""
    bends = [bend255(lm, m, p, t) for m, p, t in FINGERS]
    return [bend255(lm, 1, 2, 4), *bends, thumb_rot255(lm)]

# ---------- 串口下发: 因时Inspire RH56类帧格式 EB 00 LEN CMD DATA SUM ----------
# !!! 帧格式/角度顺序/波特率务必对照你手上灵巧手的协议手册核对 !!!
def send_angles(ser, ang6):
    if ser is None:
        print("[angles]", ang6, flush=True); return
    payload = bytes([0x01, *ang6])                         # CMD 0x01=角度控制, 6字节各0~255
    frame = bytearray([0xEB, 0x00, len(payload), *payload])
    frame.append(sum(frame[2:]) & 0xFF)                    # 校验和: 从LEN起累加取低8位
    ser.write(bytes(frame))

# ---------- 主循环 ----------
landmarker = mp.tasks.vision.HandLandmarker.create_from_options(
    mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=MODEL),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=1))

ser = None
if len(sys.argv) > 1:
    import serial
    ser = serial.Serial(sys.argv[1], 115200, timeout=0.1)  # 波特率按手册改
    print("[serial]", sys.argv[1], "115200 8N1", flush=True)
else:
    print("[dry-run] 不接串口, 只打印角度. 用法: python hand_retarget.py /dev/ttyUSB0", flush=True)

cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

CONNS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),
         (11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(17,18),(18,19),(19,20),(0,17)]
ts, cnt = 0, 0
per = 1.0 / 25                                            # 目标25Hz下发
next_t = time.time()
while True:
    ok, img = cap.read()
    if not ok: continue
    img = cv2.rotate(img, cv2.ROTATE_180)                 # 摄像头倒装, 转正
    ts += 33
    res = landmarker.detect_for_video(mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), ts)
    ang6, txt = None, "NO_HAND"
    if res.hand_landmarks:
        lm = [(p.x, p.y, p.z) for p in res.hand_landmarks[0]]
        ang6 = retarget(lm)
        txt = f"{ang6[0]},{ang6[1]},{ang6[2]},{ang6[3]},{ang6[4]}|R{ang6[5]}"
        cnt += 1
        if cnt % 5 == 0: print("[angles]", ang6, flush=True)
        h, w = img.shape[:2]
        pts = [(int(p[0]*w), int(p[1]*h)) for p in lm]   # lm是3维(x,y,z), 画图只用x,y
        for a, b in CONNS: cv2.line(img, pts[a], pts[b], (0,255,0), 2)
        for p in pts: cv2.circle(img, p, 3, (0,0,255), -1)
    cv2.putText(img, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,255), 2)
    cv2.imshow("hand retarget", img)
    if cv2.waitKey(1) == ord("q"): break
    if ang6 is not None:
        send_angles(ser, ang6)
        dt = next_t - time.time()
        if dt > 0: time.sleep(dt)                          # 限速25Hz, 串口别灌爆
    next_t = time.time() + per
