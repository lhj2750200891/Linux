# NPU 版：RK3588 NPU 推理（自实现双模型流水线）

> 代码在 `python/npu/` 目录（文中代码引用的路径相对 `python/`）。核心是 `python/npu/hand_npu.py`（160 行）。
> 这是三版中原理讲得最深的一份：**mediapipe 的黑盒被拆开，每一步预处理/解码都在我们自己手里**。

## 1. 它是什么，为什么不能像 GPU 版那样一行搞定

mediapipe 的 `hand_landmarker.task` 是**私有图**，里面有自定义算子，RKNN 转换器不认识——
所以 GPU 版那种"喂帧拿点"的用法在 NPU 上不存在。

但拆开看，`.task` 图的内部本来就是两个**标准 tflite 模型**串联：

```
         ┌──────────────  mediapipe .task 私有图(C++, 转不了)  ──────────────┐
整帧 ──► │ palm_detection.tflite(192) ─► 算ROI ─► hand_landmark.tflite(224) │ ──► 21点
         └────────────────────────┬────────────────────────────────────────┘
                                  │ 两个模型本身是标准tflite → 可以分别转RKNN
NPU 版:  整帧 ──► [CPU]letterbox ─► palm_detection.rknn ─► [CPU]numpy解码+NMS ─► [CPU]算旋转ROI
                 ─► hand_landmark.rknn ─► [CPU]逆映射 ─► 21点 (与mediapipe同格式)
```

`npu/hand_npu.py` 就是用 Python 把图中"模型之间的胶水"按 mediapipe 官方源码重新实现了一遍。
所有公式都对照官方 pbtxt/计算器源码验证过，并在 PC 上用合成数据做了数值自测（精度 1e-4）。

**代价与收益**：

| 收益 | 代价 |
|---|---|
| CPU 占用显著下降（推理在 NPU） | 前后处理代码要自己写、自己验证（本版就修过 2 个 bug，见 §4.3） |
| GPU 留给显示，互不抢 | 没有跨帧跟踪，每帧都跑 palm 检测（多一次推理，但无跳变） |
| 三个 NPU 核只用一个，还有余量 | 模型转换/部署流程多几步 |

## 2. 环境搭建

### 2.1 x86 PC：装转换工具（只转一次模型）

```bash
pip3 install rknn-toolkit2 -i https://pypi.tuna.tsinghua.edu.cn/simple   # 需 Python 3.8~3.12
python3 npu/convert_rknn_pc.py        # 下载官方tflite并转出两个.rknn
```

> 下载官方模型需要访问 storage.googleapis.com，不通先 `export https_proxy=...`。

### 2.2 板子：装运行时（离线 wheel 方式）

板子 pip 默认源不通，流程是 **PC 下载 wheel → adb push → 板子离线安装**：

```bash
# PC: 下载 rknn-toolkit-lite2 + 三个依赖(psutil/ruamel.yaml/ruamel.yaml.clib)
#     wheel 文件名不能改, pip只认官方原名; 选 cp310/abi3 + aarch64 版本
adb push <4个wheel> /data/local/tmp/
adb shell '/home/firefly/hand_gesture/mediapipe_env/bin/pip install --no-deps --no-index /data/local/tmp/rknn_toolkit_lite2-2.3.2-....whl'
adb shell '/home/firefly/hand_gesture/mediapipe_env/bin/pip install --no-index /data/local/tmp/{psutil-7.2.2-....whl,ruamel_yaml-0.18.17-py3-none-any.whl,ruamel_yaml_clib-0.2.15-....whl}'
```

**版本对齐**（铁律）：板上固件自带的 `librknnrt.so` 与 pip 装的 `rknn-toolkit-lite2` **大版本必须一致**
（本项目都是 2.3.2）。不一致会加载 `.rknn` 失败。

完整命令和踩坑记录见 `npu/NPU使用说明.md`。

### 2.3 模型文件

`palm_detection.rknn`(3.2MB) + `hand_landmark.rknn`(6.0MB)，与脚本同目录
（`hand_npu.py` 用 `os.path.dirname(__file__)` 定位）。

## 3. 运行测试

```bash
# PC上: 转换并核对(见2.1), 输出里应有:
#   [sim] palm_detection.tflite 输出形状: [[1, 2016, 18], [1, 2016, 1]]
#   [sim] hand_landmark.tflite  输出形状: [[1, 63], [1, 1], [1, 1], [1, 63]]

# 板子上:
cd /home/firefly/hand_gesture/demo/npu
python fixed_gesture_npu.py                # dry-run: 只识别显示
python fixed_gesture_npu.py /dev/ttyACM0   # 识别+控制灵巧手(先读灵巧手说明!)
python hand_control_npu.py [/dev/ttyACM0]
```

**冒烟测试**（不接摄像头，验证 NPU 环境是否通）：

```python
import numpy as np
from rknnlite.api import RKNNLite
p = RKNNLite(); p.load_rknn('palm_detection.rknn'); p.init_runtime(core_mask=RKNNLite.NPU_CORE_0)
l = RKNNLite(); l.load_rknn('hand_landmark.rknn');  l.init_runtime(core_mask=RKNNLite.NPU_CORE_1)
print([o.shape for o in p.inference([np.zeros((1,192,192,3), np.uint8)])])   # [(1,2016,18),(1,2016,1)]
print([o.shape for o in l.inference([np.zeros((1,224,224,3), np.uint8)])])   # [(1,63),(1,1),(1,1),(1,63)]
```

> 注意 RKNNLite 推理输入要 **4 维**(带batch)；输出形状与 PC 模拟器一致 = 环境全通。

**板上实测**（2026-11，随机帧×30）：palm 14.3ms + landmark 11.9ms ≈ **26ms**，
在 30fps 摄像头（33ms/帧）预算内；端到端延迟看状态行 `抓图->发送`。

## 4. 原理和流程（对照 `npu/hand_npu.py` 逐段讲）

一次 `HandNPU.detect(bgr)` 内部五步。前两步是"教科书会跳过、写代码才会踩"的部分。

### 4.1 第一步：生成 2016 个 anchors（`hand_npu.py:27-37`）

palm 检测是 SSD 结构：模型不是直接输出框，而是在画面上**预先撒好 2016 个候选位置**，
每个位置预测"相对这个锚的偏移"。锚的排布是官方计算器参数的直译：

```python
def _make_anchors():
    a = []
    for fm, stride, n in ((24, 8, 2), (12, 16, 6)):       # 两层特征图
        for y in range(fm):
            for x in range(fm):
                for _ in range(n):                         # 每个格子重复n个锚
                    a.append(((x + 0.5) * stride / PALM_SIZE,   # 中心归一化坐标
                              (y + 0.5) * stride / PALM_SIZE))
    return np.array(a, np.float32)          # (2016, 2)
```

- 24×24 网格（步长 8）×2 + 12×12 网格（步长 16）×6 = 576×2 + 144×6 = **2016**
- `(x+0.5)` 是取格子中心；`/192` 归一化
- `fixed_anchor_size=True` → 锚尺寸恒为 1，只有中心有意义，所以只存 (cx, cy)

### 4.2 第二步：letterbox 预处理（`hand_npu.py:77-82`）

模型要求 192×192 正方形输入，摄像头是 640×480（4:3）。直接拉伸会变形导致检测精度掉，
所以用"等比缩放 + 居中补黑边"（像看宽屏电影）：

```python
scale = min(PALM_SIZE / W, PALM_SIZE / H)          # 取小的缩放比 → 短边贴满, 长边留空
nw = min(int(round(W * scale)), PALM_SIZE)
nh = min(int(round(H * scale)), PALM_SIZE)
pad_x, pad_y = (PALM_SIZE - nw) // 2, (PALM_SIZE - nh) // 2
canvas = np.zeros((PALM_SIZE, PALM_SIZE, 3), np.uint8)
canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = cv2.resize(rgb, (nw, nh))
outs = self._rk_palm.inference(inputs=[np.expand_dims(canvas, 0)])   # 注意4维输入
```

640×480 → scale=0.3 → 192×144，上下各补 24 像素黑边。
**为什么记录 pad**：模型输出的坐标在 192 画布里，最后要减掉 pad 才是原图坐标。

### 4.3 第三步：解码 + sigmoid + NMS（`hand_npu.py:96-123`）

模型输出 `[1,2016,18]`（每锚 18 个数：cx,cy,w,h + 7个关键点×2坐标）和 `[1,2016,1]`（分数）。
解码公式全部来自官方源码（**除以 192 的线性解码**——不是别的检测器的 /10 /5）：

```python
sel = np.nonzero(scores > PALM_THRESH)[0]          # 先按分数筛, 2016→个位数
a, r = self.anchors[sel], reg[sel]                 # 之后所有数组都是"候选子集"
cx = (a[:, 0]   + r[:, 0] / 192.0) * PALM_SIZE     # 框中心 = 锚中心 + 偏移/192
bw = (r[:, 2] / 192.0) * PALM_SIZE                 # 宽高 = raw/192
kpx = (a[:, 0:1] + r[:, 4::2] / 192.0) * PALM_SIZE # 7个关键点x: (n,1)+(n,7)
```

NMS（非极大值抑制）：同一只手会被多个邻近锚同时检出，贪心地留分数最高、
抑制与其重叠(IoU>0.3)的其余框，最后只留一只。

> **两个真实 bug 的教训**（都在这一段，都写进了自测用例）：
>
> 1. **广播 bug**：关键点解码曾写成 `a[:, 0]`（形状 `(n,)`）加 `r[:, 4::2]`（形状 `(n,7)`）。
>    numpy 广播按尾部维对齐，`(n,) vs (n,7)` 只有 n=1 或 n=7 才成立——合成数据只造了
>    1 个候选所以自测全绿，真机一帧有 2~4 个候选直接崩。修复：`a[:, 0:1]` 保住列维。
> 2. **下标空间 bug**：NMS 循环里曾用**全局锚点号**（0~2015）去索引**候选子集数组**
>    （只有 n 行），锚点号 ≥ n 时越界。修复：全程用子集内局部下标。
>
> 共同教训：**合成测试数据要覆盖"多候选""下标不对齐"这些真机常态**，
> 单候选、特殊下标的"幸运路径"会掩盖 bug。

### 4.4 第四步：旋转 ROI（`hand_npu.py:136-145`，最精华的一段）

landmark 模型要的输入不是"框"，而是**摆正的手掌区域**：手掌竖直、居中、占合适比例。
三步变换，公式来自官方 `PalmDetectionDetectionToRoi` 计算器：

```python
# ① 旋转: 把"腕(点0)→中指根(点2)"的方向转到竖直(Y轴), 手掌就摆正了
theta = math.pi / 2 - math.atan2(-(pky[2] - pky[0]), pkx[2] - pkx[0])
# ② 平移: 沿手掌自身方向上移半高(shift_y=-0.5), 让整只手(含指尖)进入ROI
pcx += 0.5 * pbh * d      # d=sin(theta)
pcy -= 0.5 * pbh * c      # c=cos(theta)
# ③ 扩方: 取长边×2.6做正方形, 保证手腕到指尖全覆盖
side = max(pbw, pbh) * ROI_SCALE
s = LM_SIZE / side
# 仿射矩阵: ROI中心映射到224画布正中(112,112), 同时旋回正
M = np.array([[s * c, s * d, LM_SIZE / 2 - s * (c * pcx + d * pcy)],
              [-s * d, s * c, LM_SIZE / 2 - s * (-d * pcx + c * pcy)]], np.float32)
crop = cv2.warpAffine(rgb, M, (LM_SIZE, LM_SIZE))    # 一次warp完成缩放+旋转+平移
```

直觉理解：atan2 算出手掌"朝向"，theta 把它补成竖直；上移半高是因为 palm 框偏重掌心，
不移动的话指尖会被切掉；2.6 倍是官方调好的"手完整且背景最少"的平衡值（`ROI_SCALE` 可调）。

### 4.5 第五步：landmark 解码与逆映射（`hand_npu.py:148-159`）

NPU 跑第二段模型，输出 `[1,63]`（21 点×x,y,z，224 像素单位）和 `[1,1]`（"这真是一只手吗"的 flag）：

```python
if _sigmoid(np.clip(sco2[0], -100.0, 100.0)) < 0.5:   # flag<0.5: 裁出的不是手
    return None
pts = lm.reshape(21, 3)
dx, dy = pts[:, 0] - LM_SIZE / 2, pts[:, 1] - LM_SIZE / 2   # 相对ROI中心的偏移
px = pcx + (c * dx - d * dy) / s     # 旋转+缩放的逆变换, 映射回原图像素
py = pcy + (d * dx + c * dy) / s
pz = pts[:, 2] * 2.5 / LM_SIZE       # 官方z: raw/224/0.4 (0.4=normalize_z)
```

输出 `(px, py, pz)` 与 mediapipe 的 21 点同格式（归一化坐标），
所以 `fixed_gesture_npu.py` / `hand_control_npu.py` 的下游判定、映射、控制代码
**与 GPU 版逐行相同**——只换了"引擎"那一小段。

### 4.6 模型转换脚本怎么写（`npu/convert_rknn_pc.py:48-59`）

```python
rk.config(target_platform="rk3588", mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]])
rk.load_tflite(in_path)
rk.build(do_quantization=False)            # 不量化 → FP16, 精度接近float原模型
rk.export_rknn(out_path)                   # 先导出!
# 然后才 init_runtime + 模拟器推理核对形状, 最后 release
```

- `mean 0 / std 255`：输入 uint8(0~255)，运行时内部自动做 `(x-0)/255` 归一化，
  与 tflite 的 float[0,1] 输入等价——板上就能直接喂 uint8，省一次预处理
- `do_quantization=False`：FP16 不量化。量化可再提速但会掉精度（关键点抖动变大），
  手部关键点对精度敏感，不量化
- **顺序教训**：`export_rknn` 必须在 `release()` 之前（曾因先 release 导致 export 崩溃）；
  PC 模拟器核对形状是最后一道保险（palm 必须含 2016，对不上=锚配置错了）

## 5. 调参与常见问题

`hand_npu.py` 顶部三个常量，对照现象调：

| 常量 | 默认 | 现象 → 调整 |
|---|---|---|
| `PALM_THRESH` | 0.5 | 手在画面里却检不到 → 降 0.4；误检/鬼影 → 升 0.6 |
| `ROI_SCALE` | 2.6 | 指尖丢（ROI 裁太小）→ 调大；背景干扰 → 调小 |
| `NMS_IOU` | 0.3 | 两只手挤在一起只出一只 → 略调大 |

| 症状 | 原因 |
|---|---|
| `No module named 'rknnlite'` | 板子没装 toolkit-lite2（见 §2.2） |
| RKNN 加载失败 | librknnrt 与 pip 包版本不齐 |
| 框数与 2016 不一致报错 | `.rknn` 不是 convert_rknn_pc.py 的产物 |
| 关键点抖动比 GPU 版大 | 转换误开了量化 |
