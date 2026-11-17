#!/usr/bin/env python3
# 固定手势识别 -> 灵巧手实时模仿 (NPU版: RK3588 RKNN, 与 fixed_gesture.py 逻辑一致)
# 推理: palm_detection.rknn + hand_landmark.rknn (hand_npu.py封装), 不用mediapipe/GPU
# 模型转换: 在x86 PC上运行 convert_rknn_pc.py, 把生成的两个.rknn拷到本脚本同目录
# 板子依赖: pip3 install rknn-toolkit-lite2 (且 /usr/lib/librknnrt.so 存在)
# 手势集: 数字1~9(中式: 6=拇指+小指 7=拇食中捏合 8=拇指+食指 9=食指弯钩) + 拳头 + OK + 点赞
# 实时: 手势连续稳定 STABLE_N 帧才采纳(防抖), 灵巧手限速平滑跟随; 手离开1秒回准备姿势
# 交互与其他demo同一套: START开始 / PAUSE暂停(画面静止, 不抓图不识别) / EXIT退出
# 用法:
#   python fixed_gesture_npu.py                # dry-run: 只识别显示, 不接灵巧手
#   python fixed_gesture_npu.py /dev/ttyACM0   # 识别+控制
# !!! 通电时严禁用手扳动关节 !!!
import glob, os, sys, time
os.environ["DISPLAY"] = ":0"
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"             # NPU/EGL初始化必需
_a = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
if _a:
    os.environ["XAUTHORITY"] = _a[-1]

import cv2, numpy as np

# ================= 安全配置(与 hand_control.py 一致) =================
BAUD, SEND_HZ, MAX_STEP, DEADBAND = 1000000, 30, 40, 3
SAFE_RANGE = {1: (300, 720), 2: (370, 750), 3: (300, 720), 4: (380, 750), 5: (520, 820), 6: (400, 850)}
PAPER = {1: 360, 2: 710, 3: 360, 4: 710, 5: 800, 6: 850}     # 准备姿势=手掌

EXT4 = {1: 360, 2: 710, 3: 360, 4: 710}                      # 四指伸(官方数值)
FLD4 = {1: 680, 2: 410, 3: 680, 4: 420}                      # 四指握(官方数值)
TH_OPN = {5: 800, 6: 850}                                    # 拇指张开
TH_FLD = {5: 550, 6: 600}                                    # 拇指收拢

POSES = {    # 手势 -> 六路目标(全部落在SAFE_RANGE内)
    "1":    {**FLD4, 4: 710, **TH_FLD},                      # 食指
    "2":    {1: 680, 2: 410, 3: 360, 4: 710, **TH_FLD},      # 食中(V)
    "3":    {1: 680, 2: 710, 3: 360, 4: 710, **TH_FLD},      # 食中无名
    "4":    {**EXT4, **TH_FLD},                              # 四指, 拇指收
    "5":    {**EXT4, **TH_OPN},                              # 手掌
    "6":    {1: 360, 2: 410, 3: 680, 4: 420, **TH_OPN},      # 拇指+小指
    "7":    {1: 680, 2: 410, 3: 520, 4: 560, 5: 660, 6: 720},  # 拇食中捏合(近似)
    "8":    {1: 680, 2: 410, 3: 680, 4: 710, **TH_OPN},      # 拇指+食指
    "9":    {1: 680, 2: 410, 3: 680, 4: 560, **TH_FLD},      # 食指弯钩
    "fist": {**FLD4, **TH_FLD},                              # 拳头(四指先握, 拇指后压)
    "ok":   {1: 360, 2: 710, 3: 360, 4: 500, 5: 640, 6: 700},  # 中无小伸, 拇食成圈
    "like": {**FLD4, **TH_OPN},                              # 点赞: 四指握+拇指翘
}
EN = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
      "6": "6", "7": "7", "8": "8", "9": "9",
      "fist": "10", "ok": "OK", "like": "LIKE"}   # 数字手势直接显示数字, 拳头=10
ZH = {"1": "数字1", "2": "数字2", "3": "数字3", "4": "数字4", "5": "数字5",
      "6": "数字6", "7": "数字7", "8": "数字8", "9": "数字9",
      "fist": "拳头", "ok": "OK手势", "like": "点赞"}

STABLE_N = 3       # 连续3帧同一手势才采纳(~0.1s)
LOST_RESET = 1.0   # 手离开1秒回准备姿势

FINGERS = {"index": (5, 6, 8), "middle": (9, 10, 12), "ring": (13, 14, 16), "pinky": (17, 18, 20)}

def _ang(a, b, c):
    """顶点在b, 射线b->a与b->c的夹角(度)"""
    v1 = np.subtract(a, b); v2 = np.subtract(c, b)
    cs = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cs, -1, 1))))

def bend255(lm, mcp, pip, tip):
    """两段骨向量夹角 -> 弯曲度0~255. 0=伸直, 255=全弯"""
    v1 = np.subtract(lm[pip], lm[mcp]); v2 = np.subtract(lm[tip], lm[pip])
    c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    return int(np.clip(np.degrees(np.arccos(np.clip(c, -1, 1))) / 120.0, 0, 1) * 255)

GES_DBG = {"fold": 0.0, "spread": 0.0, "pin_i": 0.0, "pin_m": 0.0, "pin3": 0.0,
           "m_r": 0.0, "h_ir": 0.0, "tb": 0}   # 观测值, 状态行打印供调阈值

def classify(lm):
    """固定手势 -> 标签/None. 伸=bend<90(微弯也算伸, 4/5常伸不直), 弯=bend>128; 特形(7捏/OK/9钩/点赞)先判"""
    b = {k: bend255(lm, m, p, t) for k, (m, p, t) in FINGERS.items()}
    ext = {k: v < 90 for k, v in b.items()}
    bnt = {k: v > 128 for k, v in b.items()}
    palm = np.hypot(lm[9][0] - lm[0][0], lm[9][1] - lm[0][1]) + 1e-6   # 腕-中指根=掌长(尺度基准)
    def d(i, j):
        return float(np.hypot(lm[i][0] - lm[j][0], lm[i][1] - lm[j][1]) / palm)
    fold, spread = d(4, 17), d(4, 5)       # 拇指尖-小指根 / 拇指尖-食指根
    pin_i, pin_m = d(4, 8), d(8, 12)       # 拇食指尖 / 食中指尖
    tb = bend255(lm, 2, 3, 4)              # 拇指自身弯度: 收拢=弯(tb大), 张开=直(tb小) -> 4/5的关键
    h_ir = d(8, 16)                        # 食指尖-无名指尖(9钩: 食指尖单独伸出, 此值大; 拳/赞指尖聚拢, 此值小)
    m_r = d(12, 16)                        # 中指尖-无名指尖(7: 中指随捏抬起, 与收下的无名指散开; 拳头所有点聚拢, 此值小)
    pin3 = max(pin_i, pin_m, d(4, 12))     # 拇/食/中三指尖(4,8,12)最大间距
    GES_DBG.update(fold=round(fold, 2), spread=round(spread, 2), pin_i=round(pin_i, 2),
                   pin_m=round(pin_m, 2), pin3=round(pin3, 2), m_r=round(m_r, 2),
                   h_ir=round(h_ir, 2), tb=tb)
    if pin3 < 0.4 and m_r > 0.45:
        return "7"                          # 拇食中三指聚合 且 中/无名指尖明显散开(拳头所有点都聚在一起)
    if ext["middle"] and ext["ring"] and ext["pinky"] and bnt["index"] and pin_i < 0.45:
        return "ok"                         # 中无小伸直, 拇食成圈
    if bnt["index"] and bnt["middle"] and bnt["ring"] and bnt["pinky"]:
        if pin_m > 0.55 and h_ir > 0.5:
            return "9"                      # 食指尖单独伸出, 离中/无名指尖都远(拳/赞指尖聚拢不会误判)
        if spread > 0.5 and fold > 0.7:
            return "like"                   # 四指握+拇指翘起
        return "fist"
    n = sum(ext.values())
    if n == 4:
        return "5" if tb < 64 else "4"      # 四指全伸: 拇指直=5, 拇指收(弯)=4
    if ext["index"] and ext["middle"] and ext["ring"] and bnt["pinky"]:
        return "3"
    if ext["index"] and ext["middle"] and bnt["ring"] and bnt["pinky"]:
        return "2"
    if ext["index"] and bnt["middle"] and bnt["ring"] and bnt["pinky"]:
        return "8" if (spread > 0.45 and fold > 0.7) else "1"
    if ext["pinky"] and bnt["index"] and bnt["middle"] and bnt["ring"] and spread > 0.45:
        return "6"
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
        self.t_src, self.lat = None, 0.0     # t_src=当前目标来源帧的抓取时刻; lat=抓图->实发耗时(平滑值)
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
            if self.t_src is not None:                   # 只测决策后第一次实发(反应时间), 追动不重复计
                dt = time.time() - self.t_src
                self.lat = dt if self.lat <= 0 else self.lat * 0.7 + dt * 0.3
                self.t_src = None                        # 一次性: 用后作废, 下次set_target再武装
            if self.ser.in_waiting:
                self.ser.reset_input_buffer()
    def move_to_init(self, timeout=3.5):
        """两阶段回准备姿势: 四指先伸开, 到位后拇指再张开(拇指先动会扫到食/中指)"""
        self.set_target({k: PAPER[k] for k in (1, 2, 3, 4)})
        t0 = time.time()
        while time.time() - t0 < timeout and \
                any(abs(self.tgt[s] - self.cur[s]) > DEADBAND for s in (1, 2, 3, 4)):
            self.tick()
            time.sleep(1.0 / SEND_HZ)
        self.set_target({k: PAPER[k] for k in (5, 6)})
        t0 = time.time()
        while time.time() - t0 < 1.0:
            self.tick()
            time.sleep(1.0 / SEND_HZ)

# ================= 推理引擎: RK3588 NPU(RKNN) =================
# 模型由PC上 convert_rknn_pc.py 转出, 与本脚本同目录; ts参数仅为兼容旧调用, NPU不需要
_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    from hand_npu import HandNPU
    landmarker = HandNPU(os.path.join(_DIR, "palm_detection.rknn"),
                         os.path.join(_DIR, "hand_landmark.rknn"))
except Exception as e:
    print("[infer] NPU初始化失败:", str(e)[:200], flush=True)
    print("检查: 1)板子已 pip3 install rknn-toolkit-lite2  2)/usr/lib/librknnrt.so 存在  "
          "3)两个.rknn模型在本脚本同目录", flush=True)
    sys.exit(1)

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
    pass                                  # dry-run: 只识别显示, 命令行加串口参数即控制模式

cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[error] 摄像头打开失败, 先查占用: pgrep -af fixed_gesture\\|hand_")
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
cv2.namedWindow("fixed gesture", cv2.WINDOW_NORMAL)
cv2.resizeWindow("fixed gesture", SW, SH)
cv2.imshow("fixed gesture", np.zeros((480, 640, 3), np.uint8))   # 先显示一帧让窗口真正映射出来
cv2.waitKey(200)
try:
    import win_fullscreen
    win_fullscreen.make_fullscreen("fixed gesture", wait=5)
except Exception as e:
    print("[fullscreen] fail:", e, flush=True)

# ---- 屏上按钮: START开始 / PAUSE暂停(静止) / EXIT退出, 触摸/鼠标点击=左键 ----
STATE = "idle"          # idle=预览未开始 / running=识别跟随 / paused=画面静止(不抓图不识别)
QUIT = False
BTN_RECTS = {}

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

cv2.setMouseCallback("fixed gesture", on_mouse)

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
if hand is not None:
    hand.move_to_init()

ts, fps, n, t_last = 0, 0.0, 0, time.time()
next_send, t_report = 0.0, time.time()
t_grab = 0.0                              # 本帧抓取时刻(抓图->发送耗时的起算点)
seen, same, last_g = None, 0, None        # seen/same: 手势稳定计数; last_g: 当前已采纳手势
label = "SHOW A GESTURE"
lose_t = None
thumb_pending, t_thumb = None, 0.0        # 拳头两阶段: 四指到位后才压拇指
last_img, prev_state = None, None
try:
    while True:
        if STATE == "running" and prev_state != "running":   # (重新)开局: 清空状态
            seen, same, last_g = None, 0, None
            lose_t, thumb_pending = None, None
            label = "SHOW A GESTURE"
        prev_state = STATE
        if STATE == "paused":                  # 暂停: 不抓图不识别, 最后一帧定格显示
            if last_img is None:
                continue
            img = last_img
        else:
            ok, img = cap.read()
            if not ok: continue
            t_grab = time.time()                      # 抓到图的时刻
            n += 1
            img = cv2.rotate(img, cv2.ROTATE_180)
            g = None
            if STATE == "running":             # idle只预览画面, 不跑推理省NPU
                ts += 33
                lm = landmarker.detect(img, ts)
                if lm:
                    g = classify(lm)
                    h, w = img.shape[:2]
                    pts = [(int(p[0]*w), int(p[1]*h)) for p in lm]
                    for a, b in CONNS: cv2.line(img, pts[a], pts[b], (0,255,0), 2)
                    for p in pts: cv2.circle(img, p, 3, (0,0,255), -1)
        if g:                                  # 稳定N帧才采纳, 采纳即改灵巧手目标
            lose_t = None
            same = same + 1 if g == seen else 1
            seen = g
            if same >= STABLE_N and g != last_g:
                last_g, same = g, 0
                pose = POSES[g]
                if hand is not None:           # 所有手势两阶段: 四指先走, 到位后拇指再动
                    hand.t_src = t_grab        # 记录本目标来自哪次抓图
                    hand.set_target({k: pose[k] for k in (1, 2, 3, 4)})
                    thumb_pending = {k: pose[k] for k in (5, 6)}
                    t_thumb = time.time()
                label = EN[g]
        else:                                  # 丢手: 计数清零, 离开1秒回准备姿势
            seen, same = None, 0
            if last_g is not None:
                if lose_t is None:
                    lose_t = time.time()
                elif time.time() - lose_t > LOST_RESET:
                    if hand is not None:       # 回准备姿势也两阶段: 四指先伸, 拇指后张
                        hand.t_src = t_grab    # 回准备目标同样记抓图时刻
                        hand.set_target({k: PAPER[k] for k in (1, 2, 3, 4)})
                        thumb_pending = {k: PAPER[k] for k in (5, 6)}
                        t_thumb = time.time()
                    else:
                        thumb_pending = None
                    last_g = None
                    label = "SHOW A GESTURE"
        if hand is not None and STATE == "running" and time.time() >= next_send:
            if thumb_pending is not None:
                if all(abs(hand.tgt[s] - hand.cur[s]) <= DEADBAND for s in (1, 2, 3, 4)) \
                        or time.time() - t_thumb > 1.2:       # 四指到位(或1.2s兜底)再压拇指
                    hand.set_target(thumb_pending)   # 拇指是收尾动作, 不参与延迟统计(首发已消费t_src)
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
            if hand is None:                   # dry-run: 没有串口实发, 只报fps
                print(f"[status] {fps:.1f} fps", flush=True)
            else:
                lat = f"{hand.lat*1000:.0f}ms" if hand.lat > 0 else "--ms"   # 首次实发前没有样本
                print(f"[status] {fps:.1f} fps | 抓图->发送 {lat}", flush=True)
            t_report = now
        bw = (img.shape[0] * SW - img.shape[1] * SH) // (2 * SH)   # 补黑边到屏幕比例, 画面不变形
        if bw > 0:
            img = cv2.copyMakeBorder(img, 0, 0, bw, bw, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        draw_buttons(img)
        cv2.putText(img, f"{fps:.1f} fps" + (f"  {hand.lat*1000:.0f}ms" if hand is not None else ""),
                    (bw + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        show = "PAUSED" if STATE == "paused" else ("PRESS START TO PLAY" if STATE == "idle" else label)
        cv2.putText(img, show, (bw + 10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
        if STATE == "running" and last_g is not None:              # 当前手势大字居中显示
            (tw_, _), _b = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 3)
            cv2.putText(img, label, ((img.shape[1] - tw_) // 2, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 200, 255), 3)
        cv2.imshow("fixed gesture", img)
        last_img = img.copy()                  # paused时定格的就是这帧
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
