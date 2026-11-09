#!/usr/bin/env python3
# 石头剪刀布: 你出招(摄像头识别), 灵巧手出克制招, 永远赢你
# 规则: 你石头->它布  你剪刀->它石头  你布->它剪刀
# 防抢拍: 手势须连续稳定 STABLE_N 帧才判定出招, 变招过渡的中间形状不会触发
# 判定只看四指伸/弯(拇指不参与, 避开拇指识别误差): 全弯=石头 全伸=布 食中伸+无小弯=剪刀
# 用法:
#   python rps_game.py                # dry-run: 只识别, 屏幕显示判定, 不接灵巧手
#   python rps_game.py /dev/ttyACM0   # 对战模式
# !!! 通电时严禁用手扳动关节 !!!
import glob, os, sys, time
os.environ["DISPLAY"] = ":0"
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"             # GPU delegate 初始化EGL必需
_a = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
if _a:
    os.environ["XAUTHORITY"] = _a[-1]

import cv2, numpy as np, mediapipe as mp

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

# ================= 安全配置(与 hand_control.py 完全一致) =================
BAUD, SEND_HZ, MAX_STEP, DEADBAND = 1000000, 50, 100, 2   # 官方demo就是直接跳姿势(无插值), 限速放开到接近全速
SAFE_RANGE = {1: (300, 720), 2: (370, 750), 3: (300, 720), 4: (380, 750), 5: (520, 820), 6: (400, 850)}
PAPER = {1: 360, 2: 710, 3: 360, 4: 710, 5: 800, 6: 850}     # 官方初始姿势 = 布(准备姿势)
POSES = {                                                    # 招式姿势, 全部取官方数值表端点
    "rock":     {1: 680, 2: 410, 3: 680, 4: 420, 5: 550, 6: 600},   # 全弯+拇指压指背
    "scissors": {1: 680, 2: 410, 3: 360, 4: 710, 5: 550, 6: 600},   # 食中伸, 无名小指弯+拇指合
    "paper":    PAPER,                                               # 全伸
}
# 注意: 官方握拳(680,410,680,420,800,850)拇指是张开的——拇指与四指同时合拢会互相干涉
# (拇指挡住食指/中指下不去). 所以石头/剪刀必须分两步: 先收四指, 到位后拇指再合上压住指背
WIN = {"rock": "paper", "scissors": "rock", "paper": "scissors"}
EN = {"rock": "ROCK", "scissors": "SCISSORS", "paper": "PAPER"}

STABLE_N = 4       # 连续4帧(~0.13s)同一手势才算你出招: 再短就有抢拍风险
LOST_RESET = 1.0   # 手离开画面1秒后, 灵巧手回布, 等下一轮
FINGERS = {"index": (5, 6, 8), "middle": (9, 10, 12), "ring": (13, 14, 16), "pinky": (17, 18, 20)}

def bend255(lm, mcp, pip, tip):
    """两段骨向量夹角 -> 弯曲度0~255"""
    v1 = np.subtract(lm[pip], lm[mcp]); v2 = np.subtract(lm[tip], lm[pip])
    c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    theta = np.degrees(np.arccos(np.clip(c, -1, 1)))
    return int(np.clip(theta / 120.0, 0, 1) * 255)

def classify(lm):
    """四指伸弯 -> 石头/剪刀/布/None. 伸=bend<64(夹角<30度), 弯=bend>128(夹角>60度)"""
    b = {k: bend255(lm, m, p, t) for k, (m, p, t) in FINGERS.items()}
    if sum(v > 128 for v in b.values()) == 4: return "rock"
    if sum(v < 64 for v in b.values()) == 4: return "paper"
    if b["index"] < 64 and b["middle"] < 64 and b["ring"] > 128 and b["pinky"] > 128:
        return "scissors"
    return None

# ================= CyberHand 协议(与 hand_control.py 相同) =================
def sync_write_frame(pos):
    body = bytearray([0xFE, 3 + 3 * len(pos) + 1, 0x83, 0x2A, 0x02])
    for sid in sorted(pos):
        v = max(1, min(1024, int(pos[sid]))) - 1
        body += bytes([sid, (v >> 8) & 0xFF, v & 0xFF])
    return b"\xFF\xFF" + body + bytes([(~sum(body)) & 0xFF])

def read_position_cmd(sid):
    body = bytes([sid, 0x04, 0x02, 0x38, 0x02])
    return b"\xFF\xFF" + body + bytes([(~sum(body)) & 0xFF])

def parse_position(rx):
    if len(rx) >= 8 and rx[0:2] == b"\xFF\xFF":
        return ((rx[5] << 8) | rx[6]) + 1
    return None

class CyberHand:
    """安全限位控制器: 目标clamp安全区间, 实发限速逼近, 上电先读真实位置杜绝跳变"""
    def __init__(self, port):
        import serial
        self.ser = serial.Serial(port, BAUD, timeout=0.05)
        self.cur = self._read_all()
        self.tgt = dict(self.cur)
        print(f"[hand] 已连接 {port}, 当前位置 {self.cur}", flush=True)
    def _read_all(self):
        cur = {}
        for sid in sorted(SAFE_RANGE):
            try:
                self.ser.reset_input_buffer()
                self.ser.write(read_position_cmd(sid))
                t0, pos = time.time(), None
                while time.time() - t0 < 0.1:
                    if self.ser.in_waiting >= 8:
                        pos = parse_position(self.ser.read(8))
                        break
                cur[sid] = pos if pos else PAPER[sid]
            except Exception:
                cur[sid] = PAPER[sid]
        return cur
    def set_target(self, pos):
        for sid, v in pos.items():
            lo, hi = SAFE_RANGE[sid]
            self.tgt[sid] = max(lo, min(hi, v))
    def tick(self):
        moved = False
        for sid, c in self.cur.items():
            d = self.tgt[sid] - c
            if abs(d) <= DEADBAND:
                continue
            self.cur[sid] = c + (d if abs(d) < MAX_STEP else (MAX_STEP if d > 0 else -MAX_STEP))
            moved = True
        if moved:
            self.ser.write(sync_write_frame(self.cur))
            if self.ser.in_waiting:
                self.ser.reset_input_buffer()
    def move_to_init(self, timeout=2.0):
        self.set_target(PAPER)
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.tick()
            time.sleep(1.0 / SEND_HZ)

# ================= 推理引擎: GPU优先 =================
def build(delegate):
    return mp.tasks.vision.HandLandmarker.create_from_options(
        mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL, delegate=delegate),
            running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=1))

landmarker = None
try:
    landmarker = build(mp.tasks.BaseOptions.Delegate.GPU)
    print("[infer] GPU", flush=True)
except Exception as e:
    print("[infer] GPU初始化失败, 回退CPU. 原因:", str(e)[:120], flush=True)
    landmarker = build(mp.tasks.BaseOptions.Delegate.CPU)

# ================= 主循环 =================
hand = None
if len(sys.argv) > 1:
    try:
        hand = CyberHand(sys.argv[1])
    except Exception as e:
        print(f"[error] 打开 {sys.argv[1]} 失败: {e}")
        print("[error] 确认灵巧手已上电、USB线已插, 设备节点存在: ls /dev/ttyACM*")
        sys.exit(1)
else:
    print("[dry-run] 未接灵巧手, 只判定显示. 对战模式: python rps_game.py /dev/ttyACM0", flush=True)

cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[error] 摄像头打开失败, 先查占用: pgrep -af rps\\|hand_")
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
cv2.namedWindow("rps", cv2.WINDOW_NORMAL)                    # OpenCV Qt后端全屏属性失灵, 先只设尺寸
cv2.resizeWindow("rps", SW, SH)
cv2.imshow("rps", np.zeros((480, 640, 3), np.uint8))         # 先显示一帧让窗口真正映射出来
cv2.waitKey(200)
try:
    import win_fullscreen
    win_fullscreen.make_fullscreen("rps", wait=5)            # 真全屏: EWMH消息, 与OpenCV后端无关
except Exception as e:
    print("[fullscreen] fail:", e, flush=True)

# ---- 屏上按钮: START开始 / PAUSE暂停(静止) / EXIT退出, 触摸/鼠标点击=左键 ----
STATE = "idle"          # idle=预览未开始 / running=对战 / paused=画面静止(不抓图不识别)
QUIT = False
BTN_RECTS = {}          # 按钮矩形(图像坐标), 鼠标回调判定用

def on_mouse(event, x, y, flags, param):
    global STATE, QUIT
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    for name, (x1, y1, x2, y2) in BTN_RECTS.items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            if name == "exit":
                QUIT = True
            elif name == "start" and STATE == "idle":
                STATE = "running"
            elif name == "pause":
                STATE = "paused" if STATE == "running" else "running"

cv2.setMouseCallback("rps", on_mouse)

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
        BTN_RECTS[nm] = (r[0] - 18, y0 - 6, r[2] + 18, h)   # 命中区比画的宽: Qt底部状态栏吃掉~25px, 贴边点击坐标会偏
        cv2.rectangle(img, (r[0], r[1]), (r[2], r[3]), col, -1)
        cv2.putText(img, txt, (r[0] + 62, r[3] - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

CONNS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),
         (11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(17,18),(18,19),(19,20),(0,17)]
if hand is not None:
    print("[hand] 开局回准备姿势(布)...", flush=True)
    hand.move_to_init()

ts, fps, n, t_last = 0, 0.0, 0, time.time()
next_send, t_report = 0.0, time.time()
seen, same, last_played = None, 0, None   # seen/same: 手势稳定计数; last_played: 上一轮你出的
msg = "SHOW YOUR HAND"
lose_t = None
thumb_pending, t_thumb = None, 0.0        # 待合拇指目标(四指到位后才发)
last_img, prev_state = None, None         # paused时定格显示的帧; 上轮状态(用于按钮切换检测)
try:
    while True:
        if STATE == "running" and prev_state != "running":   # (重新)开局: 清空对局状态
            seen, same, last_played = None, 0, None
            lose_t, thumb_pending = None, None
            msg = "SHOW YOUR HAND"
        prev_state = STATE
        if STATE == "paused":                  # 暂停: 不抓图不识别, 最后一帧定格显示
            if last_img is None:
                continue
            img = last_img
        else:
            ok, img = cap.read()
            if not ok: continue
            n += 1
            img = cv2.rotate(img, cv2.ROTATE_180)
            g = None
            if STATE == "running":             # idle只预览画面, 不跑推理省GPU
                ts += 33
                res = landmarker.detect_for_video(mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), ts)
                if res.hand_landmarks:
                    lm = [(p.x, p.y, p.z) for p in res.hand_landmarks[0]]
                    g = classify(lm)
                    h, w = img.shape[:2]
                    pts = [(int(p[0]*w), int(p[1]*h)) for p in lm]
                    for a, b in CONNS: cv2.line(img, pts[a], pts[b], (0,255,0), 2)
                    for p in pts: cv2.circle(img, p, 3, (0,0,255), -1)
        if g:                                  # 出招判定(只有running会拿到g)
            lose_t = None
            same = same + 1 if g == seen else 1
            seen = g
            if same >= STABLE_N and g != last_played:
                play = WIN[g]
                last_played = g
                same = 0
                if hand is not None:
                    pose = POSES[play]
                    if play == "paper":
                        hand.set_target(pose)           # 布: 全程无干涉, 六路同步
                    else:
                        # 石头/剪刀: 先收四指, 四指到位后再合拇指(拇指压在指背上)
                        hand.set_target({k: pose[k] for k in (1, 2, 3, 4)})
                        thumb_pending = {k: pose[k] for k in (5, 6)}
                        t_thumb = time.time()
                msg = f"YOU:{EN[g]}  ME:{EN[play]}  >> YOU LOSE"
                print(f"[round] 你:{EN[g]} 我:{EN[play]} 你输了", flush=True)
        else:                                   # 丢手: 计数清零, 手离开1秒后回准备姿势
            seen, same = None, 0
            if last_played is not None:
                if lose_t is None:
                    lose_t = time.time()
                elif time.time() - lose_t > LOST_RESET:
                    if hand is not None:
                        hand.set_target(PAPER)
                    thumb_pending = None
                    last_played, msg = None, "READY - SHOW YOUR HAND"
                    print("[round] 手离开, 复位准备下一轮", flush=True)
        if hand is not None and STATE == "running" and time.time() >= next_send:
            if thumb_pending is not None:
                fingers_done = all(abs(hand.tgt[s] - hand.cur[s]) <= DEADBAND for s in (1, 2, 3, 4))
                if fingers_done or time.time() - t_thumb > 1.2:   # 四指压到位(或1.2s兜底)再合拇指
                    hand.set_target(thumb_pending)
                    thumb_pending = None
            try:
                hand.tick()
            except Exception as e:
                print("[hand] 串口异常, 停止控制:", e, flush=True)
                break
            next_send = time.time() + 1.0 / SEND_HZ
        now = time.time()
        if now - t_last >= 1.0:
            fps = fps * 0.5 + (n / (now - t_last)) * 0.5
            n, t_last = 0, now
        if now - t_report >= 5.0:
            if hand is not None:
                print(f"[status] {fps:.1f} fps | 实发 {hand.cur}", flush=True)
            t_report = now
        bw = (img.shape[0] * SW - img.shape[1] * SH) // (2 * SH)   # 补黑边到屏幕比例, 画面不变形
        if bw > 0:
            img = cv2.copyMakeBorder(img, 0, 0, bw, bw, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        draw_buttons(img)                                # 屏上按钮条
        show_msg = "PAUSED" if STATE == "paused" else ("PRESS START TO PLAY" if STATE == "idle" else msg)
        cv2.putText(img, f"{fps:.1f} fps", (bw + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        cv2.putText(img, show_msg, (bw + 10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
        cv2.imshow("rps", img)
        last_img = img.copy()                            # paused时定格的就是这帧
        if cv2.waitKey(1) == ord("q"): break
        if QUIT: break
except KeyboardInterrupt:
    pass
finally:
    if hand is not None:
        try:
            hand.move_to_init()               # 退出限速平滑复位
        except Exception as e:
            print("[exit] 复位失败(串口已断?):", e, flush=True)
    cap.release(); cv2.destroyAllWindows()
    print("[exit] done", flush=True)
