#!/usr/bin/env python3
# 固定手势 -> 灵巧手姿势(离散触发): 认出手势才下发对应姿势指令; 无手势/丢手保持当前姿势停发
# 新文件, 不影响 hand_follow_4_models.py(连续随动) 和 gesture_tracker_4_models.py(纯识别)
# 识别: hand_npu_4_models.py 三探针融合概率 + EMA/滞回防抖(参数比识别demo略激进, 控制要快;
#       10ms推理 + EMA约2帧记忆 + 采纳即下发, 抓图->采纳实测约15~25ms, 之后限速走完动作)
# 协议/安全与 hand_follow_4_models.py 完全一致:
#   SAFE_RANGE硬钳位 + MAX_STEP限速 + 上电先读真实位置 + 退出限速平滑复位 + 丢手停发
# 用法:
#   python gesture_pose_4_models.py                # 干跑: 只识别+打印将下发的姿势(不接舵机)
#   python gesture_pose_4_models.py /dev/ttyACM0   # 识别+控制
# !!! 通电时严禁用手扳动关节 !!!
import glob, os, signal, sys, time
os.environ["DISPLAY"] = ":0"                                 # 无条件覆盖, 避免shell里的旧值捣乱
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"             # RKNN运行时/显示初始化必需
_a = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
if _a:
    os.environ["XAUTHORITY"] = _a[-1]

import cv2, numpy as np
from hand_npu_4_models import HandNPU4, GESTURES

# ================= 串口/安全配置(与 hand_follow_4_models.py 一致) =================
BAUD     = 1000000
SEND_HZ  = 25      # 串口下发频率
MAX_STEP = 64      # 每帧每路最大位移(25Hz≈1600单位/秒): 全行程0.4s->0.2s; 嫌起步猛就调回32
DEADBAND = 3       # 每路变化小于此值不发帧
# 硬性安全区间: 官方demo实际用到的范围再各留余量. 超范围值发送前被强制截断
#               1=小拇指      2=无名指      3=中指       4=食指       5=大拇指      6=拇指根部
SAFE_RANGE = {1: (300, 720), 2: (370, 750), 3: (300, 720), 4: (380, 750), 5: (520, 820), 6: (400, 850)}
POSE_INIT = {1: 360, 2: 710, 3: 360, 4: 710, 5: 800, 6: 850}   # 官方初始姿势

# ================= 手势 -> 姿势映射表 =================
# 各舵机方向(官方数值表): 1/3小指/中指 360伸直~680全弯 | 2/4无名/食指 710伸直~410/420全弯
#                        5拇指弯 800伸直~550全弯    | 6拇指根 850张开~600收拢
# ⚠ 硬件没有腕/前臂旋转舵机, Thumb_Up/Thumb_Down 只能姿势近似(无法表现朝向), 其余5个手势是标准姿势
POSES = {
    "Open_Palm":   {1: 360, 2: 710, 3: 360, 4: 710, 5: 800, 6: 850},   # 五指全伸+拇指张开
    "Closed_Fist": {1: 680, 2: 410, 3: 680, 4: 420, 5: 550, 6: 600},   # 全握拳+拇指收拢
    "Pointing_Up": {1: 680, 2: 410, 3: 680, 4: 710, 5: 700, 6: 600},   # 只伸食指
    "Victory":     {1: 680, 2: 410, 3: 360, 4: 710, 5: 700, 6: 600},   # 食指+中指(耶)
    "ILoveYou":    {1: 360, 2: 410, 3: 680, 4: 710, 5: 800, 6: 850},   # 拇指+食指+小指
    "Thumb_Up":    {1: 500, 2: 560, 3: 500, 4: 560, 5: 800, 6: 850},   # 近似: 半握+拇指伸直张开
    "Thumb_Down":  {1: 360, 2: 710, 3: 360, 4: 710, 5: 550, 6: 600},   # 近似: 四指伸直+拇指弯下收拢
}
missing = [g for g in GESTURES if g != "None" and g not in POSES]
if missing:
    print("[error] 缺姿势映射:", missing, flush=True)
    sys.exit(1)
# 终端输出保持极简(与旧 hand_control_npu.py 风格一致): 每5秒一行 [status] fps + 两个时间

# ================= 几何耶探针: 救canned模型最弱的Victory =================
# 用户做耶的习惯(手背朝镜+倾斜+手指半弯)下融合概率只有0.3~0.5, 其他手势都0.6+;
# 但耶的几何特征(食指+中指伸, 无名+小指弯)与视角/倾斜无关, 用关节夹角判别极稳.
GEO_V_BOOST = 0.75   # 命中(连续2帧)时Victory概率抬到至少0.75, 并压Thumb_Up(耶的常见误认)

def bend255(lm, mcp, pip, tip):
    """两段骨向量夹角 -> 弯曲度0~255. 0=伸直, 255=全弯(与hand_control_4_models同款)"""
    v1 = np.subtract(lm[pip], lm[mcp]); v2 = np.subtract(lm[tip], lm[pip])
    c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    theta = np.degrees(np.arccos(np.clip(c, -1, 1)))
    return int(np.clip(theta / 120.0, 0, 1) * 255)

def geo_victory(lm):
    """几何耶: 食指+中指伸(PIP夹角<78°, 容忍半弯) 且 无名+小指弯(>87°).
    与其余6个手势几何上互斥(手掌/爱你的无名小指是伸的, 指向/拇上/握拳的食指或中指是弯的)"""
    try:
        b_i = bend255(lm, 5, 6, 8)
        b_m = bend255(lm, 9, 10, 12)
        b_r = bend255(lm, 13, 14, 16)
        b_p = bend255(lm, 17, 18, 20)
    except Exception:
        return False
    return b_i < 165 and b_m < 165 and b_r > 185 and b_p > 185

# ================= 防抖参数(EMA+滞回) =================
# ⚠ 必须=识别demo的板上验证配置(cb00a30e/8c812e22那轮, 用户实测全部手势可识别):
#   曾为控制速度改成0.45/0.45, 临界手势(融合概率悬在0.4~0.5)采纳率明显掉 —— 调参勿离开验证区
EMA_A   = 0.35    # 新帧权重: 约5帧记忆, 单帧毛刺打不垮; 响应约0.2s
ADOPT   = 0.40    # 采纳阈值
RELEASE = 0.18    # 释放滞回: 跌破只撤标签, 姿势保持不动
ADOPT_V = 0.30    # Victory专属(用户手背朝镜+倾斜, 融合概率天然0.3~0.5)

# ================= CyberHand 协议(与 hand_follow_4_models.py 一致) =================
def sync_write_frame(pos):
    """多舵机同步位置指令帧. pos: {ID: 位置1~1024}"""
    body = bytearray([0xFE, 3 + 3 * len(pos) + 1, 0x83, 0x2A, 0x02])
    for sid in sorted(pos):
        v = max(1, min(1024, int(pos[sid]))) - 1
        body += bytes([sid, (v >> 8) & 0xFF, v & 0xFF])
    return b"\xFF\xFF" + body + bytes([(~sum(body)) & 0xFF])

def read_position_cmd(sid):
    """读取舵机当前位置指令: FF FF ID 04 02 38 02 校验(官方Read.py同款)"""
    body = bytes([sid, 0x04, 0x02, 0x38, 0x02])
    return b"\xFF\xFF" + body + bytes([(~sum(body)) & 0xFF])

def parse_position(rx):
    """应答: FF FF ID 04 00 位置高 位置低 校验, 位置=(高<<8|低)+1"""
    if len(rx) >= 8 and rx[0:2] == b"\xFF\xFF":
        return ((rx[5] << 8) | rx[6]) + 1
    return None

class CyberHand:
    """带安全限位的控制器: 目标值clamp安全区间, 实发值每帧限速逼近, 上电先读真实位置杜绝跳变"""
    def __init__(self, port):
        import serial
        self.ser = serial.Serial(port, BAUD, timeout=0.05)
        self.cur = self._read_all()          # 从真实位置出发
        self.tgt = dict(self.cur)
        self.t_src, self.lat = None, 0.0     # t_src=当前目标来源帧的抓取时刻; lat=抓图->实发耗时
        self.t_det, self.lat_gap = None, 0.0 # t_det=同帧识别结束时刻; lat_gap=识别结束->实发(同源恒>=0)
    def _read_all(self):
        cur = {}
        for sid in sorted(SAFE_RANGE):       # 逐个读真实位置, 失败用初始位兜底
            try:
                self.ser.reset_input_buffer()
                self.ser.write(read_position_cmd(sid))
                t0 = time.time()
                pos = None
                while time.time() - t0 < 0.1:
                    if self.ser.in_waiting >= 8:
                        pos = parse_position(self.ser.read(8))
                        break
                cur[sid] = pos if pos else POSE_INIT[sid]   # 读位超时静默用初始位兜底
            except Exception:
                cur[sid] = POSE_INIT[sid]
        return cur
    def set_target(self, pos):
        for sid, v in pos.items():
            lo, hi = SAFE_RANGE[sid]        # 安全区间硬限制
            self.tgt[sid] = max(lo, min(hi, v))
    def tick(self):
        """朝目标限速逼近一步, 有变化才发帧"""
        moved = False
        for sid, c in self.cur.items():
            d = self.tgt[sid] - c
            if abs(d) <= DEADBAND:
                continue
            step = d if abs(d) < MAX_STEP else (MAX_STEP if d > 0 else -MAX_STEP)
            self.cur[sid] = c + step
            moved = True
        if moved:
            self.ser.write(sync_write_frame(self.cur))   # 同步写广播无应答
            if self.t_src is not None:                   # 只测采纳后第一次实发(反应时间)
                now_ = time.time()
                dt = now_ - self.t_src
                self.lat = dt if self.lat <= 0 else self.lat * 0.7 + dt * 0.3
                if self.t_det is not None:               # 同帧的识别结束->实发: 与lat同源, 无负值假象
                    dg = now_ - self.t_det
                    self.lat_gap = dg if self.lat_gap <= 0 else self.lat_gap * 0.7 + dg * 0.3
                self.t_src = None
                self.t_det = None
            if self.ser.in_waiting:
                self.ser.reset_input_buffer()            # 清理杂散字节防缓冲膨胀
    def move_to_init(self, timeout=2.0):
        """限速平滑回到初始位, 不跳变"""
        self.set_target(POSE_INIT)
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.tick()
            time.sleep(1.0 / SEND_HZ)

# ================= 推理引擎: RK3588 NPU(RKNN) 4模型流水线 =================
_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    landmarker = HandNPU4(_DIR)
except Exception as e:
    print("[infer] NPU初始化失败:", str(e)[:200], flush=True)
    print("检查: 1)板子已 pip3 install rknn-toolkit-lite2  2)/usr/lib/librknnrt.so 存在  "
          "3)4个.rknn模型在本脚本同目录", flush=True)
    sys.exit(1)

hand = None
if len(sys.argv) > 1:
    try:
        hand = CyberHand(sys.argv[1])
    except Exception as e:
        print(f"[error] 打开 {sys.argv[1]} 失败: {e}")
        print("[error] 确认灵巧手已上电、USB线已插, 设备节点存在: ls /dev/ttyACM*")
        sys.exit(1)

cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[error] 摄像头打开失败, 先查占用: pgrep -af gesture_pose\\|hand_")
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
cv2.namedWindow("gesture pose", cv2.WINDOW_NORMAL)
cv2.resizeWindow("gesture pose", SW, SH)
cv2.imshow("gesture pose", np.zeros((480, 640, 3), np.uint8))   # 先显示一帧让窗口真正映射出来
cv2.waitKey(200)
try:
    import win_fullscreen
    win_fullscreen.make_fullscreen("gesture pose", wait=5)
except Exception as e:
    print("[fullscreen] fail:", e, flush=True)

# ---- 屏上按钮: START开始 / PAUSE暂停(静止) / EXIT退出, 触摸/鼠标点击=左键 ----
STATE = "idle"          # idle=预览未开始 / running=识别控制 / paused=画面静止(不抓图不识别)
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
    if time.time() - _last_click[0] < 0.3:      # 触摸/Qt偶发一次点击投递两次事件, toggle会互相抵消
        return
    _last_click[0] = time.time()
    for name, (x1, y1, x2, y2) in BTN_RECTS.items():
        if x1 <= x <= x2 and y1 <= y <= y2:
            if name == "exit":
                QUIT = True
            elif name == "start" and STATE == "idle":
                STATE = "running"
            elif name == "pause":
                STATE = "paused" if STATE == "running" else "running"

cv2.setMouseCallback("gesture pose", on_mouse)

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
        BTN_RECTS[nm] = (r[0] - 18, y0 - 6, r[2] + 18, h)   # 命中区比画的宽(避开Qt状态栏坐标偏移)
        cv2.rectangle(img, (r[0], r[1]), (r[2], r[3]), col, -1)
        cv2.putText(img, txt, (r[0] + 62, r[3] - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

CONNS = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),
         (11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(17,18),(18,19),(19,20),(0,17)]
fps, n, t_last = 0.0, 0, time.time()
next_send, t_report = 0.0, time.time()
dec_lat = 0.0                             # 抓图->识别耗时(EMA平滑, dry-run和控制都显示)
t_det_end = 0.0                           # 本帧识别结束时刻(识别->发送耗时的同源基准)
ema = np.zeros(8, np.float32)             # 8类融合概率的EMA平滑(顺序同GESTURES)
geo_streak = 0                            # 几何耶连续命中帧数(>=2才补强, 防手势切换路过帧误触发)
last_g = None                             # 当前已采纳手势(姿势已下发)
t_grab = 0.0                              # 本帧抓取时刻(抓图->采纳/实发耗时的起算点)
last_img, prev_state = None, None
try:
    while True:
        if STATE == "running" and prev_state != "running":   # (重新)开局: 清防抖状态, 姿势保持
            ema[:] = 0
            geo_streak = 0
            last_g = None
        prev_state = STATE
        if STATE == "paused":                  # 暂停: 不抓图不识别, 最后一帧定格显示
            if last_img is None:
                continue
            img = last_img
        else:
            ok, img = cap.read()
            if not ok: continue
            t_grab = time.time()
            n += 1
            img = cv2.rotate(img, cv2.ROTATE_180)
            if STATE == "running":             # idle只预览画面, 不跑推理省NPU
                res = landmarker.detect(img)
                t_det_end = time.time()
                dec = t_det_end - t_grab
                dec_lat = dec if dec_lat <= 0 else dec_lat * 0.7 + dec * 0.3   # 抓图->识别耗时(EMA平滑)
                lm = res["pts"] if res else None
                if lm:
                    h, w = img.shape[:2]
                    pts = [(int(p[0]*w), int(p[1]*h)) for p in lm]
                    for a, b in CONNS: cv2.line(img, pts[a], pts[b], (0,255,0), 2)
                    for p in pts: cv2.circle(img, p, 3, (0,0,255), -1)
                    if res["probs"] is not None:
                        pb = np.asarray(res["probs"], np.float32).copy()
                        geo_streak = geo_streak + 1 if geo_victory(lm) else 0
                        if geo_streak >= 2:                    # 几何耶补强: 3探针对用户的耶天然偏弱
                            pb[6] = max(pb[6], GEO_V_BOOST)
                            pb[5] = min(pb[5], 0.20)           # 压Thumb_Up(模型视角误认的主要去向)
                        ema = (1.0 - EMA_A) * ema + EMA_A * pb
                        j = int(np.argmax(ema[1:])) + 1        # 只在7个固定手势里选(None类不参与)
                        g = GESTURES[j]
                        if last_g != g and ema[j] >= (ADOPT_V if j == 6 else ADOPT):
                            last_g = g
                            if hand is not None:
                                hand.t_src = t_grab    # 记录本姿势来自哪次抓图
                                hand.t_det = t_det_end # 同帧识别结束时刻(发送耗时与之同源)
                                hand.set_target(POSES[g])   # 只更新目标, 实发由限速tick逼近
                                next_send = 0.0        # 采纳后同帧立即发第一帧, 省掉等25Hz窗口的平均20ms
                        elif last_g is not None and ema[GESTURES.index(last_g)] < RELEASE:
                            last_g = None              # 撤标签; 姿势保持不动
                else:                                  # 丢手: 清防抖, 停发新指令, 姿势保持
                    if last_g is not None:
                        last_g = None
                    ema[:] = 0
                    geo_streak = 0
        if hand is not None and STATE == "running" and time.time() >= next_send:
            try:
                hand.tick()                        # 限速逼近目标; 刚采纳的姿势会走完(丢手不打断在途动作)
            except Exception as e:
                print("[hand] 串口异常, 停止控制:", e, flush=True)
                break
            next_send = time.time() + 1.0 / SEND_HZ
        now = time.time()
        if now - t_last >= 1.0:
            fps = fps * 0.5 + (n / (now - t_last)) * 0.5
            n, t_last = 0, now
        if now - t_report >= 5.0:
            dec = f"{dec_lat*1000:.0f}ms" if dec_lat > 0 else "--ms"   # 首次识别前没有样本
            if hand is None:                   # dry-run: 没有串口实发
                print(f"[status] {fps:.1f} fps | 抓图->识别 {dec}", flush=True)
            else:
                gap = f"{hand.lat_gap*1000:.0f}ms" if hand.lat_gap > 0 else "--ms"   # 首次实发前没有样本
                print(f"[status] {fps:.1f} fps | 抓图->识别 {dec} | 识别->发送 {gap}", flush=True)
            t_report = now
        bw = (img.shape[0] * SW - img.shape[1] * SH) // (2 * SH)   # 补黑边到屏幕比例, 画面不变形
        if bw > 0:
            img = cv2.copyMakeBorder(img, 0, 0, bw, bw, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        draw_buttons(img)                                # 屏上按钮条
        show_msg = "PAUSED" if STATE == "paused" else ("PRESS START TO PLAY" if STATE == "idle"
                   else (last_g if last_g else "SHOW A GESTURE"))   # 屏上英文(cv2画不了中文)
        cv2.putText(img, f"{fps:.1f} fps" + (f"  {hand.lat*1000:.0f}ms" if hand is not None and hand.lat > 0 else ""),
                    (bw + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        cv2.putText(img, show_msg, (bw + 10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
        if STATE == "running" and last_g is not None:              # 当前手势大字居中显示
            big = last_g
            (tw_, _b), _ = cv2.getTextSize(big, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 3)
            cv2.putText(img, big, ((img.shape[1] - tw_) // 2, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 200, 255), 3)
        cv2.imshow("gesture pose", img)
        last_img = img.copy()                  # paused时定格的就是这帧
        if cv2.waitKey(1) == ord("q"): break
        if QUIT: break
except KeyboardInterrupt:
    pass
finally:
    if hand is not None:
        try:
            hand.move_to_init()                   # 退出限速平滑复位, 防止停在奇怪姿势
        except Exception as e:
            print("[exit] 复位失败(串口已断?):", e, flush=True)
    cap.release(); cv2.destroyAllWindows()
