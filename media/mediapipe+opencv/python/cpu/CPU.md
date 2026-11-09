# CPU 版：mediapipe 纯 CPU 推理

> 代码在 `python/cpu/` 目录（文中代码引用的路径相对 `python/`）。
> 这是最简单的一版：**只装一个 mediapipe，剩下的它全包**。适合先理解"一次识别到底发生了什么"。

## 1. 它是什么

调用 mediapipe Tasks API 的 `HandLandmarker`，推理跑在 CPU 上（TFLite 的 XNNPACK 内核多线程加速）。
mediapipe 在 C++ 内部替你完成整套流水线，Python 侧只管：喂帧 → 拿 21 个点。

```
摄像头帧(BGR, 640x480)
  │ cvtColor → RGB
  ▼
mp.tasks HandLandmarker (CPU, C++内部完成全部三步)
  ├─ ① palm 检测: 找到手在哪 (192x192)
  ├─ ② 由 palm 关键点算出手部旋转 ROI
  └─ ③ landmark: 21 个关键点 (224x224) + 左右手/置信度
  ▼
res.hand_landmarks[0]  →  21个 (x,y,z), 全部归一化0~1
```

> 注意：虽然代码只写了一行 `detect_for_video()`，但**内部同样是"两段模型"**
> （palm 检测 + landmark），这个两段结构在 [NPU.md](NPU.md) 里会被拆开白盒讲解。

## 2. 环境搭建

### 板子（Firefly RK3588）

`mediapipe_env` 里已经装好，无需操作。如果要在别的机器复刻：

```bash
python3 -m venv mediapipe_env
source mediapipe_env/bin/activate
pip install mediapipe opencv-python numpy pyserial -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### PC 上想跑也可以

同样 `pip install mediapipe opencv-python`，把 `gpu/hand_landmarker.task` 拷到脚本同目录即可
（CPU 版不需要 GPU/NPU，普通笔记本就能跑）。

模型文件：`hand_landmarker.task`（约 7.8MB）在 `gpu/` 目录，`.task` 是 mediapipe 的模型包
（里面打好了 palm + landmark + 分类模型和图配置，具体见 [GPU.md](GPU.md) 第 4 节）。

## 3. 运行测试

```bash
# 板子上(激活环境后):
cd /home/firefly/hand_gesture/demo

python minimal_demo.py          # 极简版: 画面上手骨架 + 手势文字
python gesture_board.py         # 同类, 代码结构更适合当模板
python hand_detect.py --cpu     # 额外输出6路关节角(为控制灵巧手做准备)
python bench.py                 # 帧率基准(可对比 --gpu)
```

**预期现象**：窗口出现摄像头画面，手伸进去出现绿色骨架线 + 21 个红点；
左上角显示手势名（`OPEN_PALM` / `FIST` / `VICTORY` / `POINT`...）和 fps。
CPU 实测约 **17 fps**（`hand_detect.py` 头部注释记录的实测值），够看但控制会感觉迟钝。

按 `q` 退出。没有手时显示 `NO_HAND` 不报错。

## 4. 原理和流程（对照真实代码）

### 4.1 创建识别器（`cpu/minimal_demo.py:28-31`）

```python
Opts, Vision = mp.tasks.vision.HandLandmarkerOptions, mp.tasks.vision.RunningMode
landmarker = mp.tasks.vision.HandLandmarker.create_from_options(Opts(
    base_options=mp.tasks.BaseOptions(model_asset_path="/root/firefly_handle_demo/hand_landmarker.task"),
    running_mode=Vision.VIDEO, num_hands=1))
```

三个参数各管一件事：

| 参数 | 含义 | 为什么 |
|---|---|---|
| `model_asset_path` | `.task` 模型包路径 | 包里含全部模型权重 |
| `running_mode=VIDEO` | 视频流模式 | 内部会做跨帧跟踪优化；另一档 `IMAGE` 是单张图 |
| `num_hands=1` | 只识别 1 只手 | 检测量减半，速度快 |

**没写 `delegate=` 就默认 CPU** —— 这就是 CPU 版和 GPU 版唯一的创建参数区别。

### 4.2 主循环：喂帧拿结果（`cpu/minimal_demo.py:39-50`）

```python
while True:
    ok, img = cap.read()
    if not ok: continue
    img = cv2.rotate(img, cv2.ROTATE_180)                 # 摄像头倒装, 转正
    ts += 33                                              # VIDEO模式要递增毫秒时间戳
    res = landmarker.detect_for_video(mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), ts)
    label = "NO_HAND"
    if res.hand_landmarks:
        lm = [(p.x, p.y) for p in res.hand_landmarks[0]]  # 21个归一化点
        label = gesture(lm)
```

逐行要点：

- **`cv2.rotate(180°)`**：这颗 MIPI 摄像头物理倒装，画面上下颠倒，先转正。
- **`ts += 33`**：VIDEO 模式要求时间戳**单调递增**（毫秒），mediapipe 用它做跨帧跟踪。
  每帧 +33 相当于告诉它"按 30fps 递增"。时间戳不递增会直接报错——这是最常见的初学坑。
- **`cv2.cvtColor(BGR2RGB)`**：opencv 读进来是 BGR，mediapipe 只吃 RGB。
- **`res.hand_landmarks[0]`**：第 0 只手的 21 个点；`[1]` 是第二只（`num_hands=1` 时永远只有 [0]）。
- 每个 `p.x/p.y` 是 **0~1 归一化坐标**，画图时乘回 `w/h` 变像素（第 52 行 `int(x*w)`）。

### 4.3 手势判定：不用模型的小聪明（`cpu/minimal_demo.py:16-26`）

21 个点拿到后，手势判定根本不需要神经网络，一个几何技巧就够：

```python
def gesture(lm):                                          # lm: 21个归一化(x,y)
    wrist = np.array(lm[0])
    up = [np.hypot(*np.subtract(lm[t], wrist)) >          # 指尖比关节离手腕远 = 伸直
          np.hypot(*np.subtract(lm[p], wrist)) * 1.05 for t, p in zip(TIPS, PIPS)]
```

原理：**指尖(8/12/16/20号点)离手腕的距离 > 对应关节(6/10/14/18号点)离手腕的距离 → 这根手指伸直**。
比较距离而不是比较 y 坐标，好处是**手怎么旋转都有效**（横着手、斜着手都能判对）。
`×1.05` 是留一点裕量，避免手指伸直时临界抖动。

统计伸直的手指数就能分类：0 根=`FIST`，5 根=`OPEN_PALM`，食+中=`VICTORY`……

再配一个**防抖**（`minimal_demo.py:55-56`）：判定结果必须**连续 3 帧一致**才切换显示，
否则指尖在阈值边缘时标签会闪烁：

```python
same = same + 1 if label == prev_raw else 0           # 连续3帧一致才切换, 防抖
if label == "NO_HAND" or same >= 2: shown = label
```

### 4.4 进阶：从关键点到关节角（`cpu/hand_detect.py:29-34`）

`hand_detect.py` 多做一步：把 21 点换算成灵巧手的 6 路关节角（0=伸直，255=全弯）。
手指弯曲度 = **两段骨向量（MCP→PIP 与 PIP→TIP）的夹角**：

```python
def bend255(lm, mcp, pip, tip):
    """两段骨向量夹角 -> 弯曲度0~255. 0=伸直, 255=全弯"""
    v1 = np.subtract(lm[pip], lm[mcp]); v2 = np.subtract(lm[tip], lm[pip])
    c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    theta = np.degrees(np.arccos(np.clip(c, -1, 1)))       # 直=0度, 全弯约120度
    return int(np.clip(theta / 120.0, 0, 1) * 255)
```

向量点积除以两个模长 = 夹角余弦（`1e-6` 防止除零）；反余弦得角度；
直线时两向量同向 θ=0°，握拳约 120°，线性映射到 0~255。
这套映射在 GPU/NPU 版里原样复用——**下游逻辑与推理后端完全解耦**。

## 5. CPU 版的定位

| 优点 | 缺点 |
|---|---|
| 零配置，任何机器都能跑 | 17fps 偏慢，控制有迟滞 |
| mediapipe 全包，代码最少 | CPU 占用高（多线程吃满几个核） |
| 是理解输出格式的最佳起点 | — |

确认识别效果没问题后，下一步换 GPU 版提速（见 [GPU.md](GPU.md)）。
