# GPU 版：mediapipe GPU delegate 推理

> 代码在 `python/gpu/` 目录（文中代码引用的路径相对 `python/`）。
> 和 CPU 版**同一个 mediapipe**，只是把推理内核从 CPU 换到 Mali GPU——实测从 ~17fps 提到 **~30fps**。

## 1. 它是什么

`HandLandmarker` 加一个 `delegate=GPU` 参数，mediapipe 内部会把模型的算子交给
RK3588 的 Mali-G610 GPU 执行（TFLite GPU delegate，走 OpenGL/OpenCL）。
Python 侧调用方式、输出格式与 CPU 版**完全一致**，主循环代码不用改。

```
摄像头帧(BGR) → RGB → mp.tasks HandLandmarker
                              │ delegate=GPU: 模型内核跑Mali GPU
                              │ (palm检测+ROI+landmark 仍在C++图里自动串起来)
                              ▼
                    21个归一化关键点 + 手势分类结果
```

## 2. 环境搭建

### 2.1 Python 环境（板子）

同一个 `mediapipe_env`，CPU 版装什么它就有什么。GPU 版**不需要额外装任何包**。

### 2.2 图形环境（GPU 初始化的前置条件，最容易栽的地方）

GPU delegate 初始化时要创建 EGL 上下文，**必须有可用的图形会话环境**。
这是 GPU 版最隐蔽的坑，代码开头专门处理了（`cpu/hand_detect.py:5-10`，GPU demo 同款）：

```python
os.environ.setdefault("DISPLAY", ":0")                    # adb shell 里没有X环境, 补上
if "XAUTHORITY" not in os.environ:
    auth = sorted(glob.glob("/run/user/1000/.mutter-Xwaylandauth*"))
    os.environ["XAUTHORITY"] = auth[-1] if auth else ""   # Wayland会话的X认证文件
os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/1000") # GPU delegate 初始化EGL必需
```

三行各救一种场景：

| 变量 | 缺了会怎样 | 什么时候需要 |
|---|---|---|
| `DISPLAY=:0` | 打不开显示窗口 | adb/ssh 远程登录时（板子屏幕前登录通常已有） |
| `XAUTHORITY` | X 拒绝连接 | 板子用 Wayland（mutter）时，认证文件在 `/run/user/1000/` 下 |
| `XDG_RUNTIME_DIR` | **GPU delegate 初始化直接失败** | EGL 要用它找会话 socket；经常被忽略 |

**症状对照**：如果启动时打印 `[infer] GPU初始化失败, 回退CPU`，九成是上面三个环境变量的问题。

### 2.3 模型文件

`gpu/hand_landmarker.task`（约 7.8MB），必须和脚本同目录（脚本用 `os.path.dirname(__file__)` 拼路径）。

### 2.4 摄像头

```bash
v4l2-ctl --list-devices     # 确认摄像头节点, 本项目固定用 /dev/video11
```

## 3. 运行测试

```bash
# 板子上(激活 mediapipe_env 后):
cd /home/firefly/hand_gesture/demo

python gpu/fixed_gesture.py                # 固定手势: 拳/数字/OK..., dry-run
python gpu/fixed_gesture.py /dev/ttyACM0   # + 控制灵巧手(先确认手已上电!)
python gpu/hand_control.py [/dev/ttyACM0]  # 手指跟随
python gpu/rps_game.py /dev/ttyACM0        # 石头剪刀布
# 或者直接用启动器: python demo_launcher.py (5张卡片)
```

**启动时看第一行输出**：`[infer] GPU` = 成功走 GPU；打印 `[infer] GPU初始化失败, 回退CPU...` = 落回 CPU（功能不受影响，只是慢）。

**预期现象**：全屏窗口，~30fps；状态行 `[status] 30.0 fps | SHOW A GESTURE | ...`；
接了灵巧手后状态行还有 `抓图->发送 xxms`——这是**从相机出帧到串口实发**的端到端延迟，调优就看它。

**安全提醒**：接灵巧手前务必读 `灵巧手控制说明.md`——**通电时严禁用手扳动关节**。

### 帧率快速对比（`cpu/bench.py`）

```bash
python bench.py          # GPU (默认)
python bench.py --cpu    # CPU
```

## 4. 原理和流程（对照真实代码）

### 4.1 `.task` 模型包里有什么

`hand_landmarker.task` 不是单个模型，是一个 zip 打包的 **mediapipe 私有图**，内含：

1. palm 检测模型（192×192，找手的位置）
2. landmark 模型（224×224，出 21 点）
3. 手势分类模型 + 标签
4. 一份 pipeline 配置（把上面三者在 C++ 图里串好）

mediapipe 的 C++ 引擎按这份配置自动执行：

```
palm检测 → 由palm关键点算旋转ROI(对齐手掌) → landmark → 手势分类
     └──────────── 全部在 detect_for_video() 一次调用里完成 ────────────┘
```

这也是 [NPU.md](NPU.md) 的出发点：这个私有图里有自定义算子，**转不了 RKNN**——
但图里的两个模型本身是标准 tflite，可以拆出来单独转（NPU 版干的就是这件事）。

### 4.2 GPU 初始化与自动回退（`gpu/fixed_gesture.py:187-199`）

```python
def build(delegate):
    return mp.tasks.vision.HandLandmarker.create_from_options(
        mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL, delegate=delegate),
            running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=1))

landmarker = None
try:
    landmarker = build(mp.tasks.BaseOptions.Delegate.GPU)     # 先试GPU
    print("[infer] GPU", flush=True)
except Exception as e:
    print("[infer] GPU初始化失败, 回退CPU. 原因:", str(e)[:120], flush=True)
    landmarker = build(mp.tasks.BaseOptions.Delegate.CPU)     # 失败落回CPU
```

与 CPU 版唯一的区别就是 `delegate=GPU`。try/except 回退的意义：
演示现场环境千变万化（EGL/X 会话问题），**宁可慢也要能跑**。
注意回退是"初始化时失败"才触发——如果 GPU 跑一半崩溃，Python 里拦不住，那就要查驱动了。

### 4.3 主循环与 CPU 版逐行相同

`detect_for_video()`、`ts += 33`、归一化坐标转像素、手势判定——全部复用 CPU 版逻辑
（参考 [CPU.md](CPU.md) 第 4 节）。GPU delegate 只替换"算子在哪跑"，不改变接口和数据。

### 4.4 端到端延迟统计（`gpu/fixed_gesture.py:167-169`）

控制模式下状态行的 `抓图->发送 xxms` 是这样算的：

```python
if self.ser.write(sync_write_frame(self.cur)):
    if self.t_src is not None:                   # 抓图->串口实发的端到端耗时(轻平滑)
        dt = time.time() - self.t_src
        self.lat = dt if self.lat <= 0 else self.lat * 0.7 + dt * 0.3
```

- `t_src`：主循环 `cap.read()` 出帧那一刻打的戳，随检测结果传到串口发送处
- `dt = 现在 - t_src` = 本帧"抓图→推理→判定→映射→串口实发"的完整耗时
- 指数滑动平均（旧值 0.7 + 新值 0.3）平滑掉单帧毛刺，状态行显示的是这个均值

这是衡量控制跟手程度的核心指标：受 30fps 摄像头（33ms/帧）限制，
它不可能低于 33ms；GPU 版一般在 35~45ms。NPU 版优化方向就是压这一段。

### 4.5 灵巧手控制要点（详见 `灵巧手控制说明.md`）

串口协议一句话版：`FF FF FE LEN 83 2A 02 (ID,高,低)×N 校验和`，1M 波特率，一次写多路目标角度。
固件侧自带安全限速（SAFE_RANGE 钳位、每周期 MAX_STEP、DEADBAND 死区），所以 Python 侧发"目标角度"即可，不用自己做插值。

拇指有两阶段逻辑（`gpu/fixed_gesture.py:172-184` `move_to_init`）：**四指先动，到位后拇指再动**——
拇指先抬会扫到食/中指。这种机构约束写在代码注释里，改手势库前先读那段。

## 5. GPU 版的定位

| 优点 | 缺点 |
|---|---|
| 代码改动最小（一个参数），17→30fps | GPU 还要管显示，负载高时帧率抖动 |
| mediapipe 全包，跟踪/防抖全内置 | CPU 占用仍不低（前后处理在CPU） |
| 自动回退 CPU，鲁棒 | `.task` 私有图不可移植到 NPU |

要更低的 CPU 占用、且把 GPU 留给显示 → 换 NPU 版（见 [NPU.md](NPU.md)）。
