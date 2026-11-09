#!/usr/bin/env python3
# 纯推理基准: 不弹窗不画图, 测不同分辨率下的识别帧率
# 用法: python bench.py 宽 高
import sys, time, os
import cv2, mediapipe as mp

w, h = int(sys.argv[1]), int(sys.argv[2])
gpu = len(sys.argv) > 3 and sys.argv[3] == "gpu"
os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
landmarker = mp.tasks.vision.HandLandmarker.create_from_options(
    mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task"),
            delegate=mp.tasks.BaseOptions.Delegate.GPU if gpu else mp.tasks.BaseOptions.Delegate.CPU),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=1))
cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, w); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

ts, n_warm, n = 0, 10, 100
for i in range(n_warm + n):
    ok, img = cap.read()
    if not ok: continue
    img = cv2.rotate(img, cv2.ROTATE_180)
    ts += 33
    t0 = time.time()
    landmarker.detect_for_video(mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), ts)
    if i == n_warm - 1:
        t_start = time.time()
dt = time.time() - t_start
print(f"{w}x{h} {'GPU' if gpu else 'CPU'}: {n/dt:.1f} fps  "
      f"(平均 {dt/n*1000:.1f} ms/帧, 实际取图 {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})")
