#!/usr/bin/env python3
# RK3588 NPU 手部追踪+8类手势识别(4模型全流程, 全部用 gesture_recognizer.task 解包出的模型):
#   hand_detector.rknn(192 palm检测) -> hand_landmarks_detector.rknn(224关键点, 取全4个输出)
#   -> gesture_embedder.rknn(整图归一化21点 -> 128维嵌入) -> canned_gesture_classifier.rknn(128 -> 8类)
#   (embedder的tflite虽声明hand/handedness/world_hand 3个输入, 但图可达性分析只有hand参与计算,
#    两个死输入在RKNN导出时被剪掉, 板上.rknn单输入, 推理只喂hand)
# 与 hand_npu.py 的区别(独立文件, 不依赖不修改hand_npu.py):
#   1) landmark 取全4输出, 多了手势段(embedder+classifier, 特征构造按官方图语义);
#      手势段做三探针集成(原始/翻面/旋正+翻面, 应对手背朝镜/手倾斜, 见_run_gesture注释)
#      并返回完整8类概率(probs), demo用EMA+滞回平滑替代逐帧计数防抖
#   2) 带ROI追踪: 有上一帧关键点时直接构ROI省掉palm推理(3次推理), 追踪失败同帧回退palm全流程(4次)
# 用法: from hand_npu_4_models import HandNPU4; res = HandNPU4().detect(bgr)
# 模型: 先在x86服务器上 convert_rknn_pc.py 转出4个.rknn放到本目录(命令见文件尾输出)
import math
import os
import cv2
import numpy as np
from rknnlite.api import RKNNLite

PALM_SIZE = 192          # palm检测模型输入
LM_SIZE = 224            # landmark模型输入
PALM_THRESH = 0.5        # palm置信度阈值(官方min_score_thresh=0.5)
NMS_IOU = 0.3            # 官方min_suppression_threshold=0.3
ROI_SCALE = 2.6          # palm框 -> 手部ROI放大系数(官方scale_x/y=2.6)
TRACK_SCALE = 2.0        # 追踪ROI放大系数(21点包围盒比palm框大, 缩小放大倍数保持同等留白)

# canned_gesture_classifier 8类输出(官方顺序), 演示层用
GESTURES = ["None", "Closed_Fist", "Open_Palm", "Pointing_Up",
            "Thumb_Down", "Thumb_Up", "Victory", "ILoveYou"]
GEST_ZH = ["无", "握拳", "手掌", "指向", "拇指向下", "点赞", "胜利", "ILoveYou"]

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

def _flip_hand(h):
    """翻面探针: (x,z)->(-x,-z). 相当于从手的另一侧看(掌背互换), 且换了一只手;
    嵌入归一化会去掉平移, 纯反射即可无需1-x"""
    g = np.asarray(h, np.float32).reshape(-1, 3).copy()
    g[:, 0] = -g[:, 0]
    g[:, 2] = -g[:, 2]
    return g.reshape(h.shape).astype(np.float32)

def _make_anchors():
    """mediapipe palm检测的SSD anchors(192输入): 共2016个, 与官方SsdAnchorsCalculator结果一致
    fixed_anchor_size=True -> 锚尺寸恒为1(归一化), 只有中心位置有意义"""
    a = []
    for fm, stride, n in ((24, 8, 2), (12, 16, 6)):
        for y in range(fm):
            for x in range(fm):
                for _ in range(n):
                    a.append(((x + 0.5) * stride / PALM_SIZE,
                              (y + 0.5) * stride / PALM_SIZE))
    return np.array(a, np.float32)          # (2016, 2)

def _rect(M, c, d, s, cx, cy):
    """统一描述一个手部ROI: M=224仿射矩阵(image->tensor), c/d=旋转, s=缩放, (cx,cy)=ROI中心"""
    return {"M": M, "c": c, "d": d, "s": s, "cx": cx, "cy": cy}

class HandNPU4:
    """接口: detect(bgr) -> dict(pts, world, handed, hand_score, gesture, gesture_zh, gesture_score, probs, tracked) / None
    pts=21个归一化关键点[(x,y,z)], world=(21,3)世界坐标, handed='Left'/'Right', tracked=本帧是否走的追踪路径,
    probs=融合后8类概率(顺序同GESTURES, 手势段异常时为None; 逐类取最大后不再是严格概率分布, 但不影响比大小)"""
    def __init__(self, model_dir=None):
        d = model_dir or os.path.dirname(os.path.abspath(__file__))
        self.anchors = _make_anchors()
        self._rk_palm = self._load(os.path.join(d, "hand_detector.rknn"))
        self._rk_lm = self._load(os.path.join(d, "hand_landmarks_detector.rknn"))
        self._rk_emb = self._load(os.path.join(d, "gesture_embedder.rknn"))
        self._rk_cls = self._load(os.path.join(d, "canned_gesture_classifier.rknn"))
        self._track_pts = None                 # 上一帧21个关键点的原图像素坐标(21,2), 追踪用
        self._track_shape = None               # 上次追踪时的帧尺寸, 变了就重置
        try:
            self.detect(np.zeros((480, 640, 3), np.uint8))   # 预热, 避免首帧卡顿
        except Exception:
            pass

    def _load(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"找不到RKNN模型: {path}\n"
                f"先在x86服务器上运行 convert_rknn_pc.py gesture_embedder.tflite canned_gesture_classifier.tflite "
                f"(hand_detector/hand_landmarks_detector 同理), 再把4个.rknn scp到板子本目录")
        rk = RKNNLite()
        if rk.load_rknn(path) != 0:
            raise RuntimeError(f"RKNN加载失败: {path}")
        if rk.init_runtime() != 0:
            raise RuntimeError(f"RKNN init_runtime失败: {path}")
        return rk

    @staticmethod
    def _split_palm(outs):
        """palm输出按最后一维识别: [1,2016,18]=框+7关键点, [1,2016,1]=分数"""
        if not outs:                           # 推理被中断(如Ctrl+C)时RKNN返回None, 放弃本帧
            return None, None
        reg = sco = None
        for o in outs:
            if o.shape[-1] == 18 and reg is None:
                reg = o.reshape(-1, 18)
            elif o.shape[-1] == 1 and sco is None:
                sco = o.reshape(-1)
        return reg, sco

    @staticmethod
    def _split_lm(outs):
        """landmark全4输出(官方顺序): [1,63]局部21点 / [1,1]手flag / [1,1]左右手logit / [1,63]world"""
        if not outs:
            return None, None, None, None
        lm = world = flag = hand = None
        for o in outs:
            n = o.shape[-1]
            if n == 63:
                if lm is None:
                    lm = o.reshape(-1, 63)
                else:
                    world = o.reshape(21, 3)
            elif n == 1:
                if flag is None:
                    flag = o.reshape(-1)[0]
                else:
                    hand = o.reshape(-1)[0]
        return lm, flag, hand, world

    # ---- ROI来源1: palm检测(letterbox192 -> 解码NMS -> 仿射224), 与hand_npu.py同一套实现 ----
    def _palm_rect(self, rgb):
        H, W = rgb.shape[:2]
        scale = min(PALM_SIZE / W, PALM_SIZE / H)
        nw = min(int(round(W * scale)), PALM_SIZE)
        nh = min(int(round(H * scale)), PALM_SIZE)
        pad_x, pad_y = (PALM_SIZE - nw) // 2, (PALM_SIZE - nh) // 2
        canvas = np.zeros((PALM_SIZE, PALM_SIZE, 3), np.uint8)
        canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = cv2.resize(rgb, (nw, nh))
        outs = self._rk_palm.inference(inputs=[np.expand_dims(canvas, 0)])
        reg, sco = self._split_palm(outs)
        if reg is None or sco is None:
            return None
        if reg.shape[0] != self.anchors.shape[0]:
            raise RuntimeError(
                f"palm模型输出{reg.shape[0]}个框, 与anchors({self.anchors.shape[0]})不一致, "
                f"请核对 _make_anchors 配置")
        scores = _sigmoid(np.clip(sco, -100.0, 100.0))    # 官方score_clipping_thresh=100
        sel = np.nonzero(scores > PALM_THRESH)[0]
        if len(sel) == 0:
            return None
        # 解码(192画布像素): 中心=锚+raw/192, 宽高=raw/192; 全程用sel内局部下标(NMS混全局下标会越界)
        a = self.anchors[sel]
        r = reg[sel]
        cx = (a[:, 0] + r[:, 0] / 192.0) * PALM_SIZE
        cy = (a[:, 1] + r[:, 1] / 192.0) * PALM_SIZE
        bw = r[:, 2] / 192.0 * PALM_SIZE
        bh = r[:, 3] / 192.0 * PALM_SIZE
        kpx = (a[:, 0:1] + r[:, 4::2] / 192.0) * PALM_SIZE  # (n,1)+(n,7)->(n,7)
        kpy = (a[:, 1:2] + r[:, 5::2] / 192.0) * PALM_SIZE
        boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)
        order = np.argsort(-scores[sel])                    # 贪心NMS, 只留置信度最高的一只手
        keep = []
        while len(order):
            i = order[0]
            keep.append(i)
            if len(order) == 1:
                break
            rest = order[1:]
            xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
            yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
            xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
            yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
            area_r = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
            iou = inter / (area_i + area_r - inter + 1e-6)
            order = rest[iou <= NMS_IOU]
        j = keep[0]
        inv = 1.0 / scale                                   # letterbox逆映射回原图像素
        pcx = (cx[j] - pad_x) * inv
        pcy = (cy[j] - pad_y) * inv
        pbw = bw[j] * inv
        pbh = bh[j] * inv
        pkx = (kpx[j] - pad_x) * inv
        pky = (kpy[j] - pad_y) * inv
        # ROI: 腕(0)->中指根(2)对齐Y轴旋转 + 沿自身-Y上移半高 + max边*2.6扩方
        theta = math.pi / 2 - math.atan2(-(pky[2] - pky[0]), pkx[2] - pkx[0])
        c, d = math.cos(theta), math.sin(theta)
        pcx += 0.5 * pbh * d                                # shift_y=-0.5: 朝手指方向平移半高
        pcy -= 0.5 * pbh * c
        side = max(pbw, pbh) * ROI_SCALE
        s = LM_SIZE / side
        M = np.array([[s * c, s * d, LM_SIZE / 2 - s * (c * pcx + d * pcy)],
                      [-s * d, s * c, LM_SIZE / 2 - s * (-d * pcx + c * pcy)]], np.float32)
        return _rect(M, c, d, s, pcx, pcy)

    # ---- ROI来源2: 追踪(上一帧21点直接构ROI, 省掉palm推理) ----
    def _roi_from_landmarks(self, pts):
        """pts=上一帧原图像素坐标(21,2). 腕(0)->中指根(9)对齐Y轴, 21点旋转包围盒*TRACK_SCALE扩方,
        中心取包围盒中心. 注意不做palm路径的"上移半高"补偿: 那是补偿palm框不含手指;
        21点包围盒已含全手, 再上移(=整个包围盒高)会把全手推到裁剪下缘, 关键点质量崩坏+幻影手"""
        x0, y0 = pts[0]                                     # 腕
        theta = math.pi / 2 - math.atan2(-(pts[9, 1] - pts[0, 1]), pts[9, 0] - pts[0, 0])
        c, d = math.cos(theta), math.sin(theta)
        u = c * pts[:, 0] + d * pts[:, 1]                   # 旋转坐标(u,v), 与仿射矩阵线性部分一致
        v = -d * pts[:, 0] + c * pts[:, 1]
        side = max(u.max() - u.min(), v.max() - v.min()) * TRACK_SCALE
        side = max(side, 56.0)                              # 防退化(手贴到镜头时包围盒过小)
        side = min(side, 1.2 * max(self._track_shape))      # 上限: 手贴近镜头时21点包围盒可能比画面还大,
                                                            # ROI超帧 -> 裁剪大半是黑边 -> landmark输出垃圾(幽灵手根源)
        um, vm = (u.max() + u.min()) / 2, (v.max() + v.min()) / 2
        # u,v是绕图像原点旋转的绝对坐标, 逆变换原点自动抵消: (x,y)=(c·u-d·v, d·u+c·v)
        # (不能加回(x0,y0): 那会把ROI中心位移整个腕向量, 裁剪跑出手外, 幻影坐标逐帧复合翻倍)
        cx = c * um - d * vm
        cy = d * um + c * vm
        s = LM_SIZE / side
        M = np.array([[s * c, s * d, LM_SIZE / 2 - s * (c * cx + d * cy)],
                      [-s * d, s * c, LM_SIZE / 2 - s * (-d * cx + c * cy)]], np.float32)
        return _rect(M, c, d, s, cx, cy)

    def _run_landmark(self, rgb, rect):
        """按ROI裁224推理landmark, 手flag达标才解码; 成功则更新追踪缓存并返回解码中间量"""
        crop = cv2.warpAffine(rgb, rect["M"], (LM_SIZE, LM_SIZE))
        outs = self._rk_lm.inference(inputs=[np.expand_dims(crop, 0)])
        lm, flag, hand_logit, world = self._split_lm(outs)
        if lm is None or flag is None or hand_logit is None or world is None:
            return None
        if _sigmoid(np.clip(flag, -100.0, 100.0)) < 0.5:    # 裁出的区域不是手
            return None
        pts = lm.reshape(21, 3)                             # 224像素单位
        c, d, s = rect["c"], rect["d"], rect["s"]
        dx = pts[:, 0] - LM_SIZE / 2
        dy = pts[:, 1] - LM_SIZE / 2
        px = rect["cx"] + (c * dx - d * dy) / s             # 旋转逆映射回原图像素
        py = rect["cy"] + (d * dx + c * dy) / s
        # 合理性守卫: 坏裁剪时模型可能输出天文数字坐标(有限值, 但x帧宽超int32会炸cv2绘制)或nan/inf;
        # 非有限或超帧尺寸4倍一律视为坏解码 -> 返回None(detect里清追踪缓存/同帧回退palm)
        Hh, Ww = rgb.shape[:2]
        if not (np.isfinite(px).all() and np.isfinite(py).all() and np.isfinite(pts[:, 2]).all()) \
                or float(np.abs(px).max()) > 4 * Ww or float(np.abs(py).max()) > 4 * Hh:
            return None
        self._track_pts = np.stack([px, py], 1)             # 追踪缓存: 原图像素坐标
        pz = pts[:, 2] / LM_SIZE                            # 官方z约定: raw z/224(腕锚定, 朝相机为负),
        # 与官方landmark输出的z同尺度; 不能再乘系数(实测x2.5会让embedder乱出标签, z占63维输入的21维)
        return {"px": px, "py": py, "pz": pz, "world": world,
                "hand_logit": float(hand_logit), "rect": rect}

    @staticmethod
    def _canon_up(h):
        """旋正探针: 绕腕(0号点)旋转xy, 使腕->中指根(9)竖直朝上(canned训练数据是竖直手);
        只旋转xy(z不变), 在归一化坐标上做, 公式与_roi_from_landmarks同一套"""
        g = np.asarray(h, np.float32).reshape(21, 3)
        w = g[0, :2].astype(np.float64)
        v = g[9, :2].astype(np.float64) - w
        ang = math.atan2(v[0], -v[1])            # 相对"竖直向上"(图像y向下)的偏角
        c, s = math.cos(ang), math.sin(ang)
        x, y = g[:, 0] - w[0], g[:, 1] - w[1]
        out = g.astype(np.float64).copy()
        out[:, 0] = w[0] + c * x + s * y
        out[:, 1] = w[1] - s * x + c * y
        return out.reshape(h.shape).astype(np.float32)

    @staticmethod
    def _fuse_probs(ps):
        """多探针概率融合(逐类取最大):
        Thumb_Up/Thumb_Down 的上下语义会被翻面破坏 -> 这两类只用 原始/翻面 两探针;
        None类同样不许 旋正+翻面 探针参与: 该探针对拇指类等姿态语义错误时会输出None~1.0,
        若许它投None会把本已识别的手势压掉(实测f_0028 Thumb_Up被压成None 1.00)。
        即旋正+翻面探针只许"提名"固定手势(类1,2,3,6,7), 不许投反对票;
        实测38帧: 手掌0.48->0.65 握拳0.67->0.84, 且不在ILoveYou帧上制造假Victory"""
        fused = np.maximum(ps[0], ps[1])
        if len(ps) > 2:
            for i in (1, 2, 3, 6, 7):             # 排除0=None 4=Thumb_Down 5=Thumb_Up
                fused[i] = max(fused[i], ps[2][i])
        return fused

    def _run_gesture(self, hand_f):
        """手势段(多探针集成): 对 原始/翻面/旋正+翻面 三种特征各跑一遍embedder+classifier.
        原始探针已很自信(非None且>=0.8)时跳过其余探针省4次小推理.
        返回(手势名或None, 分数, 融合后8类概率); 异常由调用方兜底"""
        ps = []
        for i, h in enumerate((hand_f, _flip_hand(hand_f),
                               _flip_hand(self._canon_up(hand_f)))):
            emb = self._rk_emb.inference(inputs=[np.ascontiguousarray(h, np.float32)])
            if not emb:
                continue
            e = np.asarray(emb[0], np.float32).reshape(1, 128)
            logits = self._rk_cls.inference(inputs=[e])
            if not logits:
                continue
            p = np.asarray(logits[0], np.float32).reshape(-1)
            if abs(float(p.sum()) - 1.0) > 1e-3:  # 输出不是概率分布就补softmax
                e2 = np.exp(p - p.max())
                p = e2 / e2.sum()
            ps.append(p)
            if i == 0 and float(p[int(p.argmax())]) >= 0.8 and int(p.argmax()) > 0:
                break                             # 原始探针已足够自信, 不再跑其余探针
        if not ps:
            return None, None, None
        fused = self._fuse_probs(ps) if len(ps) > 1 else ps[0]
        idx = int(fused.argmax())
        return (GESTURES[idx] if idx > 0 else None), float(fused[idx]), fused

    def _track_plausible(self, res, prev, W, H):
        """追踪路径解码结果合理性守卫(幽灵手防线): 旧守卫只拦>4倍帧尺寸/非有限值,
        实测追踪ROI坏裁剪会输出"腕(1.51,1.90)出画但不夸张"的垃圾且flag照样>=0.5,
        垃圾进缓存后下一帧ROI更歪 -> 幽灵手骨架持续. 三条硬规则(实测palm路径24帧全干净,
        所以拒绝后同帧回退palm就能消掉幽灵):
          1) 腕必须落在画面内;
          2) 21点至少18个在画面±5%范围内(允许少量指尖出画, 手贴近镜头时常见);
          3) 与上一帧的中位点位移 < 0.25×min(W,H) (30fps下手每帧移动有限,
             静止手瞬间跳到画面外必然是垃圾). prev=上一帧缓存像素坐标(21,2),
             注意必须在_run_landmark更新缓存之前取"""
        px, py = res["px"], res["py"]
        if not (0.0 <= float(px[0]) <= W and 0.0 <= float(py[0]) <= H):
            return False
        inside = ((px > -0.05 * W) & (px < 1.05 * W) & (py > -0.05 * H) & (py < 1.05 * H))
        if int(inside.sum()) < 18:
            return False
        d = np.hypot(px - prev[:, 0], py - prev[:, 1])
        if float(np.median(d)) > 0.25 * min(W, H):
            return False
        return True

    def detect(self, bgr):
        H, W = bgr.shape[:2]
        if self._track_shape != (H, W):                     # 帧尺寸变了, 追踪缓存作废
            self._track_pts = None
            self._track_shape = (H, W)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        res, tracked = None, False
        if self._track_pts is not None:                     # 追踪优先: 3次推理(landmark+embedder+classifier)
            prev = self._track_pts                          # 上一帧缓存(_run_landmark会更新它, 先存)
            res = self._run_landmark(rgb, self._roi_from_landmarks(prev))
            if res is not None and not self._track_plausible(res, prev, W, H):
                res = None                                  # 解码"合法"但出画/跳变 -> 幽灵手, 判为追踪失败
            tracked = res is not None
            if res is None:
                self._track_pts = None                      # 追踪失败, 同帧回退palm全流程
        if res is None:                                     # palm全流程: 4次推理
            rect = self._palm_rect(rgb)
            if rect is None:
                return None
            res = self._run_landmark(rgb, rect)
            if res is None:
                return None
        # ---- 手势段: 官方embedder只有hand输入参与计算(整图归一化21点), 单输入直接喂 ----
        # canned分类器对视角敏感: 手背朝镜/手倾斜时官方模型也输出None(实测官方与我们同样失败),
        # 因此做多探针集成(原始/翻面/旋正+翻面, 见_run_gesture), 融合概率给demo做EMA平滑
        hand_f = np.stack([res["px"] / W, res["py"] / H, res["pz"]], 1)[None].astype(np.float32)  # (1,21,3)
        hs = float(_sigmoid(np.clip(res["hand_logit"], -100.0, 100.0)))
        gesture = g_score = probs = None
        try:
            gesture, g_score, probs = self._run_gesture(hand_f)
        except Exception:
            pass                                            # 手势段失败不影响追踪输出
        # 左右手: 模型输出按镜像自拍视角约定(s>=0.5为Right), 摄像头画面未镜像 -> 显示时对调
        handed = "Left" if hs >= 0.5 else "Right"
        return {"pts": [(res["px"][k] / W, res["py"][k] / H, res["pz"][k]) for k in range(21)],
                "world": res["world"], "handed": handed, "hand_score": hs,
                "gesture": gesture, "gesture_score": g_score, "probs": probs, "tracked": tracked}
