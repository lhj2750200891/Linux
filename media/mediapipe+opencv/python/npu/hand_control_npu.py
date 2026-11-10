#!/usr/bin/env python3
# 手势识别 + CyberHand 灵巧手控制 (NPU版: RK3588 RKNN, 与 hand_control.py 逻辑一致)
# 推理: palm_detection.rknn + hand_landmark.rknn (hand_npu.py封装), 不用mediapipe/GPU
# 模型转换: 在x86 PC上运行 convert_rknn_pc.py, 把生成的两个.rknn拷到本脚本同目录
# 板子依赖: pip3 install rknn-toolkit-lite2 (且 /usr/lib/librknnrt.so 存在)
# 协议来源: /media/lhj/data/t-chip/7.code/handle/Python_Demo (CyberHand_Demo.py + 动作数值.txt)
#   帧格式: FF FF | FE | LEN | 83 | 2A | 02 | (ID,位置高,位置低)x6 | 校验和(~sum&0xFF, 不含FF FF)
#   串口: /dev/ttyACM0 1000000 8N1 | 舵机: 1小指 2无名 3中指 4食指 5拇指 6拇指根 | 位置1~1024
# 安全机制:
#   1. 每路舵机硬性安全区间(SAFE_RANGE), 超出强制clamp
#   2. 每帧每路限速(MAX_STEP), 杜绝暴力跳转
#   3. 启动先读舵机真实位置(不动作), 检测到手才开始跟随; 退出限速平滑复位
#   4. 丢手时停发, 保持最后姿态
# 用法:
#   python hand_control_npu.py                # 只识别, 终端每5秒打印映射位置(验证映射用)
#   python hand_control_npu.py /dev/ttyACM0   # 识别+控制
# !!! 通电时严禁用手扳动关节 !!!
import glob, os, sys, time
os.environ["DISPLAY"] = ":0"                                 # 无条件覆盖, 避免shell里的旧值捣乱
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"             # RKNN运行时/显示初始化必需
_a = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
if _a:
    os.environ["XAUTHORITY"] = _a[-1]

import cv2, numpy as np

# ================= 安全配置(上线前务必按实物核对!) =================
SERIAL_PORT_DEFAULT = "/dev/ttyACM0"
BAUD     = 1000000
SEND_HZ  = 25      # 串口下发频率
MAX_STEP = 64      # 每帧每路最大位移, 25Hz≈1600单位/秒(2026-11-10应用户要求提速, 与gesture_pose_4_models.py同速)
DEADBAND = 3       # 每路变化小于此值不发帧, 减少总线流量
# 硬性安全区间: 官方demo实际用到的范围再各留余量. 超范围值发送前被强制截断
#               1=小拇指      2=无名指      3=中指       4=食指       5=大拇指      6=拇指根部
SAFE_RANGE = {1: (300, 720), 2: (370, 750), 3: (300, 720), 4: (380, 750), 5: (520, 820), 6: (400, 850)}
POSE_INIT = {1: 360, 2: 710, 3: 360, 4: 710, 5: 800, 6: 850}   # 官方初始姿势

# ================= 识别 -> 舵机映射 =================
# 依据官方数值表标定: straight=伸直时位置, bent=握弯时位置 (注意各指方向不同!)
# 拇指根(6)跟随拇指旋转(T R), 其余跟随各指弯曲
MAP = {  # 舵机ID: (弯曲源, 伸直位, 弯曲位)
    1: ("pinky",      360, 680),
    2: ("ring",       710, 410),
    3: ("middle",     360, 680),
    4: ("index",      710, 420),
    5: ("thumb_bend", 800, 550),
    6: ("thumb_rot",  600, 850),   # 方向已核对: rot=0拇指收拢->600, rot=255张开->850
}
FINGERS = {"index": (5, 6, 8), "middle": (9, 10, 12), "ring": (13, 14, 16), "pinky": (17, 18, 20)}

def bend255(lm, mcp, pip, tip):
    """两段骨向量夹角 -> 弯曲度0~255. 0=伸直, 255=全弯"""
    v1 = np.subtract(lm[pip], lm[mcp]); v2 = np.subtract(lm[tip], lm[pip])
    c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    theta = np.degrees(np.arccos(np.clip(c, -1, 1)))
    return int(np.clip(theta / 120.0, 0, 1) * 255)

THUMB_RAW = {"fold": 0.0, "spread": 0.0}   # 原始比值, dry-run状态行显示, 用于校准

def thumb_255(lm):
    """拇指弯/张: 距离比方案(关节角对拇指失灵). 用掌长做尺度基准, 旋转/远近鲁棒
    返回 (bend255, rot255): bend 0直~255弯, rot 0合拢~255张开
    校准口诀: 直拇指时fold约1.0~1.3, 握拳拇指包拳时约0.3~0.5; 张开时spread约0.5+, 并拢约0.2"""
    palm = np.hypot(lm[9][0] - lm[0][0], lm[9][1] - lm[0][1]) + 1e-6      # 腕-中指根 = 掌长
    fold = np.hypot(lm[4][0] - lm[17][0], lm[4][1] - lm[17][1]) / palm    # 拇指尖-小指根
    spread = np.hypot(lm[4][0] - lm[5][0], lm[4][1] - lm[5][1]) / palm    # 拇指尖-食指根
    THUMB_RAW["fold"], THUMB_RAW["spread"] = round(fold, 2), round(spread, 2)
    bend = int(np.clip((1.05 - fold) / 0.65, 0, 1) * 255)   # fold 1.05->直0, 0.40->全弯255
    rot = int(np.clip((spread - 0.25) / 0.30, 0, 1) * 255)  # spread 0.25->合拢0, 0.55->张开255
    return bend, rot

def retarget_pos(lm):
    """21关键点 -> {舵机ID: 目标位置}"""
    bends = {k: bend255(lm, m, p, t) for k, (m, p, t) in FINGERS.items()}
    bends["thumb_bend"], bends["thumb_rot"] = thumb_255(lm)
    pos = {}
    for sid, (key, straight, bent) in MAP.items():
        t = bends[key] / 255.0
        pos[sid] = round(straight + (bent - straight) * t)
    return pos

# ================= CyberHand 协议 =================
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
        self.t_src, self.lat = None, 0.0     # t_src=当前目标来源帧的抓取时刻; lat=抓图->实发耗时(平滑值)
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
            if self.t_src is not None:                   # 只测决策后第一次实发(反应时间), 追动不重复计
                now_ = time.time()
                dt = now_ - self.t_src
                self.lat = dt if self.lat <= 0 else self.lat * 0.7 + dt * 0.3
                if self.t_det is not None:               # 同帧的识别结束->实发: 与lat同源, 无负值假象
                    dg = now_ - self.t_det
                    self.lat_gap = dg if self.lat_gap <= 0 else self.lat_gap * 0.7 + dg * 0.3
                self.t_src = None                        # 一次性: 用后作废, 下次set_target再武装
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
    pass                                  # dry-run: 只显示映射位置, 命令行加串口参数即控制模式

cap = cv2.VideoCapture("/dev/video11", cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"NV12"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[error] 摄像头打开失败, 先查占用: pgrep -af hand_")
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
cv2.namedWindow("hand control", cv2.WINDOW_NORMAL)           # OpenCV Qt后端全屏属性失灵, 先只设尺寸
cv2.resizeWindow("hand control", SW, SH)
cv2.imshow("hand control", np.zeros((480, 640, 3), np.uint8))  # 先显示一帧让窗口真正映射出来
cv2.waitKey(200)
try:
    import win_fullscreen
    win_fullscreen.make_fullscreen("hand control", wait=5)   # 真全屏: EWMH消息, 与OpenCV后端无关
except Exception as e:
    print("[fullscreen] fail:", e, flush=True)

# ---- 屏上按钮: START开始 / PAUSE暂停(静止) / EXIT退出, 触摸/鼠标点击=左键 ----
STATE = "idle"          # idle=预览未开始 / running=跟随控制 / paused=画面静止(不抓图不识别)
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

cv2.setMouseCallback("hand control", on_mouse)

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
ts, fps, n, t_last = 0, 0.0, 0, time.time()
next_send, t_report = 0.0, time.time()
pos = None                                                # 最近一次映射位置(状态行用)
t_grab = 0.0                                              # 本帧抓取时刻(抓图->发送耗时的起算点)
dec_lat = 0.0                                             # 抓图->识别耗时(EMA平滑, 与gesture_pose同款)
t_det_end = 0.0                                           # 本帧识别结束时刻(识别->发送耗时的同源基准)
last_img, prev_state = None, None                         # paused时定格显示的帧
try:
    while True:
        prev_state = STATE
        if STATE == "paused":                  # 暂停: 不抓图不识别, 最后一帧定格显示
            if last_img is None:
                continue
            img = last_img
        else:
            ok, img = cap.read()
            if not ok: continue
            t_grab = time.time()                          # 抓到图的时刻
            n += 1
            img = cv2.rotate(img, cv2.ROTATE_180)
            pos = None
            if STATE == "running":             # idle只预览画面, 不跑推理省NPU
                ts += 33
                lm = landmarker.detect(img, ts)   # NPU推理: 返回21点/None(与mediapipe同格式)
                t_det_end = time.time()
                dec = t_det_end - t_grab
                dec_lat = dec if dec_lat <= 0 else dec_lat * 0.7 + dec * 0.3   # 抓图->识别耗时(EMA平滑)
                if lm:
                    pos = retarget_pos(lm)
                    if hand is not None:
                        hand.t_src = t_grab    # 记录本目标来自哪次抓图
                        hand.t_det = t_det_end # 同帧识别结束时刻(发送耗时与之同源)
                        hand.set_target(pos)   # 只更新目标, 实发由下面限速tick逼近
                    h, w = img.shape[:2]
                    pts = [(int(p[0]*w), int(p[1]*h)) for p in lm]
                    for a, b in CONNS: cv2.line(img, pts[a], pts[b], (0,255,0), 2)
                    for p in pts: cv2.circle(img, p, 3, (0,0,255), -1)
        if hand is not None and STATE == "running" and time.time() >= next_send:
            try:
                hand.tick()                        # 限速逼近目标(手丢帧时也把上一目标走完)
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
        show_msg = "PAUSED" if STATE == "paused" else ("PRESS START TO PLAY" if STATE == "idle" else "FOLLOW MY HAND")
        cv2.putText(img, f"{fps:.1f} fps" + (f"  {hand.lat*1000:.0f}ms" if hand is not None else ""),
                    (bw + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        cv2.putText(img, show_msg, (bw + 10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
        cv2.imshow("hand control", img)
        last_img = img.copy()                            # paused时定格的就是这帧
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
