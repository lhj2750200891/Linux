#!/usr/bin/env python3
# RK3588 NPU 手部关键点检测(RKNN双模型): palm_detection(192x192) -> 手部ROI -> hand_landmark(224x224)
# 输出21个归一化关键点[(x,y,z)]x21, 与mediapipe同格式, 供 fixed_gesture_npu.py / hand_control_npu.py 使用
# 依赖(板子): pip3 install rknn-toolkit-lite2 且存在 /usr/lib/librknnrt.so
# 模型: 在x86 PC上运行 convert_rknn_pc.py 转出 palm_detection.rknn / hand_landmark.rknn, 放到本脚本同目录
# 预处理/解码/ROI全部按mediapipe官方图(hand_landmark_tracking_cpu.pbtxt)和计算器源码实现:
#   palm: letterbox输入, 解码=raw/192*anchor+anchor(线性), sigmoid分数, NMS(IoU 0.3)
#   anchors: (24x24,步长8,2个)+(12x12,步长16,6个)=2016, 锚尺寸恒1(fixed_anchor_size)
#   ROI: 腕(关键点0)->中指根(关键点2)对齐Y轴旋转 + 沿自身-Y上移半高(shift_y=-0.5) + max边*2.6扩方
#   landmark: 输出[1,63]局部关键点(224像素单位)/[1,1]手flag/[1,1]左右手/[1,63]world, 取前两个
# 说明: 每帧都跑palm检测(无跟踪状态), 实现简单无跳变; 若要省一次推理可缓存上一帧ROI
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

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

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

class HandNPU:
    """接口: detect(bgr, ts_ms=None) -> 21点列表/None. ts_ms为兼容旧调用保留, NPU不需要"""
    def __init__(self, palm_path, lm_path):
        self.anchors = _make_anchors()
        self._rk_palm = self._load(palm_path)
        self._rk_lm = self._load(lm_path)
        try:
            self.detect(np.zeros((480, 640, 3), np.uint8))   # 预热, 避免首帧卡顿
        except Exception:
            pass

    def _load(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到RKNN模型: {path} (先在x86 PC上运行 convert_rknn_pc.py 再拷过来)")
        rk = RKNNLite()
        if rk.load_rknn(path) != 0:
            raise RuntimeError(f"RKNN加载失败: {path}")
        if rk.init_runtime() != 0:
            raise RuntimeError(f"RKNN init_runtime失败: {path}")
        return rk

    @staticmethod
    def _split(outs, main_dim):
        """按最后一维长度识别输出张量(palm: 18=框+7关键点 / 1=分数; landmark: 63=21点 / 1=手flag),
        各取第一个匹配(官方输出顺序: palm=[18,1], landmark=[63,手flag1,左右手1,world63])"""
        if not outs:                             # 推理被中断(如Ctrl+C)时RKNN返回None, 放弃本帧
            return None, None
        main, score = None, None
        for o in outs:
            if o.shape[-1] == main_dim and main is None:
                main = o.reshape(-1, main_dim)
            elif o.shape[-1] == 1 and score is None:
                score = o.reshape(-1)
        return main, score

    def detect(self, bgr, ts_ms=None):
        H, W = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        # ---- 第一段: palm检测(整帧letterbox到192x192: 保持宽高比缩放+居中补零, 与官方一致) ----
        scale = min(PALM_SIZE / W, PALM_SIZE / H)
        nw = min(int(round(W * scale)), PALM_SIZE)
        nh = min(int(round(H * scale)), PALM_SIZE)
        pad_x, pad_y = (PALM_SIZE - nw) // 2, (PALM_SIZE - nh) // 2
        canvas = np.zeros((PALM_SIZE, PALM_SIZE, 3), np.uint8)
        canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = cv2.resize(rgb, (nw, nh))
        outs = self._rk_palm.inference(inputs=[np.expand_dims(canvas, 0)])
        reg, sco = self._split(outs, 18)
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
        # 解码(192画布像素, 官方x/y/w/h_scale=192线性解码): 中心=锚+raw/192, 宽高=raw/192
        a = self.anchors[sel]
        r = reg[sel]
        cx = (a[:, 0] + r[:, 0] / 192.0) * PALM_SIZE
        cy = (a[:, 1] + r[:, 1] / 192.0) * PALM_SIZE
        bw = r[:, 2] / 192.0 * PALM_SIZE
        bh = r[:, 3] / 192.0 * PALM_SIZE
        kpx = (a[:, 0:1] + r[:, 4::2] / 192.0) * PALM_SIZE  # 7个关键点x: (n,1)+(n,7)->(n,7)
        kpy = (a[:, 1:2] + r[:, 5::2] / 192.0) * PALM_SIZE  # (n,0)会广播失败(n!=1/7时崩)
        boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)
        # 贪心NMS(官方IoU 0.3), 只留置信度最高的一只手
        # 注意: boxes/a/r/kpx/kpy都是sel子集数组, 全程必须用sel内局部下标,
        #       若混入全局锚点下标(0~2015)会越界(真机候选少、锚点号大时必崩)
        order = np.argsort(-scores[sel])
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
        j = keep[0]                              # 置信度最高的那只手(sel内位置)
        # letterbox逆映射回原图像素
        inv = 1.0 / scale
        pcx = (cx[j] - pad_x) * inv
        pcy = (cy[j] - pad_y) * inv
        pbw = bw[j] * inv
        pbh = bh[j] * inv
        pkx = (kpx[j] - pad_x) * inv             # 原图像素坐标的关键点
        pky = (kpy[j] - pad_y) * inv

        # ---- 手部ROI(与官方PalmDetectionDetectionToRoi一致): 旋转对齐+上移半高+扩方2.6, 仿射裁224x224 ----
        theta = math.pi / 2 - math.atan2(-(pky[2] - pky[0]), pkx[2] - pkx[0])   # 腕(0)->中指根(2)对齐Y轴
        c, d = math.cos(theta), math.sin(theta)
        pcx += 0.5 * pbh * d                     # shift_y=-0.5: 沿ROI自身-Y轴(朝手指方向)平移半高
        pcy -= 0.5 * pbh * c
        side = max(pbw, pbh) * ROI_SCALE         # square_long + scale 2.6
        s = LM_SIZE / side
        # 仿射(image->tensor): 去掉旋转, ROI中心映射到(112,112)
        M = np.array([[s * c, s * d, LM_SIZE / 2 - s * (c * pcx + d * pcy)],
                      [-s * d, s * c, LM_SIZE / 2 - s * (-d * pcx + c * pcy)]], np.float32)
        crop = cv2.warpAffine(rgb, M, (LM_SIZE, LM_SIZE))

        # ---- 第二段: landmark(NPU) ----
        outs = self._rk_lm.inference(inputs=[np.expand_dims(crop, 0)])
        lm, sco2 = self._split(outs, 63)
        if lm is None or sco2 is None:
            return None
        if _sigmoid(np.clip(sco2[0], -100.0, 100.0)) < 0.5:   # 手flag: 裁出的区域不是手
            return None
        pts = lm.reshape(21, 3)                  # 模型输出为224像素单位
        dx = pts[:, 0] - LM_SIZE / 2
        dy = pts[:, 1] - LM_SIZE / 2
        px = pcx + (c * dx - d * dy) / s         # 旋转逆映射回原图像素
        py = pcy + (d * dx + c * dy) / s
        pz = pts[:, 2] * 2.5 / LM_SIZE           # 官方z: raw/224/0.4
        return [(px[k] / W, py[k] / H, pz[k]) for k in range(21)]
