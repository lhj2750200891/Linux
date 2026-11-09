#!/usr/bin/env python3
"""手势识别 (mediapipe HandLandmarker) — 板端。
用法: python gesture_board.py <PC_IP> [PC_PORT]
 - 摄像头 /dev/video11, 640x480@30
 - 识别结果: 稳定手势变化时打印到 stdout
 - 画面(含关键点/手势标签): JPEG 经 TCP 发到 PC 端 viewer
 - 每 5 秒在本地存一张 snapshot.jpg 供离线检查
 - 加 --local 参数则直接 cv2.imshow 本地显示(需 X 环境变量)
"""
import sys, time, socket, struct, argparse, os
from collections import deque, Counter

import cv2
import numpy as np
import mediapipe as mp

# 模型跟脚本同目录(目录自包含); 找不到再退回板子旧部署的固定路径
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
if not os.path.exists(MODEL):
    MODEL = "/root/firefly_handle_demo/hand_landmarker.task"

MP_HANDS_CONNECTIONS = mp.tasks.vision.HandLandmarker.HAND_CONNECTIONS \
    if hasattr(mp.tasks.vision.HandLandmarker, "HAND_CONNECTIONS") else None

# 21 个关键点索引
WRIST = 0
THUMB_TIP, THUMB_IP, THUMB_MCP = 4, 3, 2
FINGERS = {  # name: (mcp, pip, dip, tip)
    "index":  (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring":   (13, 14, 15, 16),
    "pinky":  (17, 18, 19, 20),
}

def dist(a, b):
    return np.hypot(a[0] - b[0], a[1] - b[1])

def finger_extended(lm, mcp, pip, tip):
    """旋转不敏感: 指尖离手腕比中段关节更远 => 伸直"""
    return dist(lm[tip], lm[WRIST]) > dist(lm[pip], lm[WRIST]) * 1.05

def thumb_extended(lm):
    return dist(lm[THUMB_TIP], lm[WRIST]) > dist(lm[THUMB_IP], lm[WRIST]) * 1.05

def classify(lm):
    ext = {name: finger_extended(lm, m, p, t) for name, (m, p, d, t) in FINGERS.items()}
    thumb = thumb_extended(lm)
    n = sum(ext.values()) + (1 if thumb else 0)

    # OK: 拇指指尖与食指指尖捏合, 其余手指有伸直
    pinch = dist(lm[THUMB_TIP], lm[8]) < dist(lm[WRIST], lm[9]) * 0.45
    if pinch and (ext["middle"] or ext["ring"] or ext["pinky"]):
        return "OK", ext, thumb
    if thumb and n == 1:  # 只有拇指伸直
        return "THUMBS_UP" if lm[THUMB_TIP][1] < lm[5][1] else "THUMB_SIDE", ext, thumb
    if ext["index"] and ext["middle"] and not ext["ring"] and not ext["pinky"]:
        return "VICTORY", ext, thumb
    if ext["index"] and ext["pinky"] and not ext["middle"] and not ext["ring"]:
        return "ROCK", ext, thumb
    if thumb and ext["pinky"] and not ext["index"] and not ext["middle"] and not ext["ring"]:
        return "CALL_ME", ext, thumb
    if ext["index"] and ext["middle"] and ext["ring"] and not ext["pinky"]:
        return "THREE", ext, thumb
    if n == 5:
        return "OPEN_PALM", ext, thumb
    if n == 4 and not thumb:
        return "FOUR", ext, thumb
    if n == 0:
        return "FIST", ext, thumb
    if ext["index"] and n == 1:
        return "POINT", ext, thumb
    return f"{n}_FINGERS", ext, thumb

def draw(img, lm_px, label, fps):
    if MP_HANDS_CONNECTIONS is not None:
        conns = list(MP_HANDS_CONNECTIONS)
    else:
        conns = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),
                 (11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(17,18),(18,19),(19,20),(0,17)]
    for a, b in conns:
        cv2.line(img, lm_px[a], lm_px[b], (0, 255, 0), 2)
    for p in lm_px:
        cv2.circle(img, p, 3, (0, 0, 255), -1)
    cv2.putText(img, f"{label}  {fps:.1f}fps", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pc_ip", nargs="?", default=None)
    ap.add_argument("pc_port", nargs="?", type=int, default=9000)
    ap.add_argument("--local", action="store_true", help="imshow 本地显示而不是推流")
    ap.add_argument("--rot180", action="store_true", help="画面旋转180度(摄像头倒装时使用)")
    args = ap.parse_args()

    BaseOptions = mp.tasks.BaseOptions
    HandLandmarker = mp.tasks.vision.HandLandmarker
    HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL),
        running_mode=VisionRunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    sock = None
    if not args.local and args.pc_ip:
        try:
            sock = socket.create_connection((args.pc_ip, args.pc_port), timeout=4)
            print(f"[net] connected to {args.pc_ip}:{args.pc_port}", flush=True)
        except OSError as e:
            print(f"[net] connect failed: {e}, fall back to headless", flush=True)

    landmarker = HandLandmarker.create_from_options(options)
    cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    if not cap.isOpened():
        print("camera open failed"); return 1

    history = deque(maxlen=6)     # 平滑: 最近 6 帧的分类投票
    stable = None                 # 当前稳定手势
    ts = 0
    t_fps = time.time(); n_fps = 0; fps = 0.0
    t_snap = time.time()
    print("[run] started, ctrl+c to stop", flush=True)
    try:
        while True:
            ok, img = cap.read()
            if not ok:
                time.sleep(0.01); continue
            if args.rot180:
                img = cv2.rotate(img, cv2.ROTATE_180)
            ts += 33  # VIDEO 模式需要递增毫秒时间戳
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(mp_img, ts)

            label = "NO_HAND"
            if result.hand_landmarks:
                # 画面上只画/标第一只手, 分类取每只手投票
                for i, lms in enumerate(result.hand_landmarks):
                    lm = [(p.x, p.y) for p in lms]
                    g, _, _ = classify(lm)
                    history.append(g)
                common, cnt = Counter(history).most_common(1)[0]
                if cnt >= 4:  # 6 帧里 >=4 帧一致才算稳定
                    label = common
                    if label != stable:
                        print(f"[gesture] {label}", flush=True)
                        stable = label
            else:
                history.clear()
                stable = None

            n_fps += 1
            now = time.time()
            if now - t_fps >= 1.0:
                fps = n_fps / (now - t_fps); n_fps = 0; t_fps = now

            disp = img
            if result.hand_landmarks:
                h, w = img.shape[:2]
                lm_px = [(int(p.x * w), int(p.y * h)) for p in result.hand_landmarks[0]]
                disp = img.copy()
                draw(disp, lm_px, label, fps)
            else:
                disp = img.copy()
                cv2.putText(disp, f"{label}  {fps:.1f}fps", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

            if now - t_snap >= 5.0:
                cv2.imwrite("/root/firefly_handle_demo/snapshot.jpg", disp)
                t_snap = now

            if args.local:
                cv2.imshow("gesture", disp)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            elif sock is not None:
                okc, buf = cv2.imencode(".jpg", disp, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if okc:
                    data = buf.tobytes()
                    sock.sendall(struct.pack("<I", len(data)) + data)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        landmarker.close()
        if sock: sock.close()
        cv2.destroyAllWindows()
        print("[run] stopped", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
