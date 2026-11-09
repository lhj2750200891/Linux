# 手势识别项目学习文档（CPU / GPU / NPU）

同一套功能（摄像头 → 手部 21 关键点 → 手势/控制灵巧手）在 RK3588 上有三种推理后端的实现。
本目录 3 份文档分别讲一种：**环境搭建、运行测试、原理和流程**，讲解全部引用仓库里的真实代码。

| 文档 | 代码目录 | 推理硬件 | 谁干活 | 实测帧率 |
|---|---|---|---|---|
| [CPU.md](CPU.md) | `python/cpu/` | CPU 多线程 (XNNPACK) | mediapipe 全包 | ~17 fps |
| [GPU.md](GPU.md) | `python/gpu/` | Mali-G610 GPU | mediapipe 全包，TFLite 内核跑 GPU | ~30 fps |
| [NPU.md](NPU.md) | `python/npu/` | RK3588 NPU | **自己拼流水线**，只把两个模型跑在 NPU | ~30 fps (推理≈26ms) |

## 三者关系一句话

- **CPU 版**：什么都不用配，mediapipe 一个库解决，慢但一定能跑。
- **GPU 版**：还是 mediapipe 全包，只是加一个 `delegate=GPU`，把模型内核交给 Mali GPU，快一倍，CPU 占用降低。
- **NPU 版**：mediapipe 的 `.task` 模型转不了 RKNN，所以把官方图里的两个模型拆出来分别转 `.rknn`，
  **预处理、解码、ROI、后处理全部自己用 Python/numpy 实现**（`npu/hand_npu.py`）——这是三份文档里原理讲得最深的一份。

## 仓库结构

```
gesture_mediapipe/
├── python/          ← 本目录: 学习文档 + 三个自包含的代码目录
│   ├── cpu/         ← CPU 版: minimal_demo.py / hand_detect.py / gesture_board.py / bench.py ...
│   ├── gpu/         ← GPU 版: fixed_gesture.py / hand_control.py / rps_game.py + hand_landmarker.task
│   ├── npu/         ← NPU 版: hand_npu.py / fixed_gesture_npu.py / hand_control_npu.py / convert_rknn_pc.py
│   └── CPU.md / GPU.md / NPU.md / README.md
├── demo_launcher.py ← 板端启动器(5 张卡片: GPU×3 + NPU×2)
├── 灵巧手控制说明.md  ← CyberHand 串口协议/安全事项(控制类 demo 都引用它)
└── 手势识别调试笔记.md
```

> **三个代码目录相互隔离**：各自带齐所需的模型/辅助模块，删掉任意一个目录，
> 其余两个目录的 demo 都能照常运行（模型路径都按脚本所在目录解析）。

## 公共背景（三份文档都会用到，先看这里）

**硬件**：Firefly RK3588 板子 + MIPI 摄像头（`/dev/video11`，NV12，640×480，倒装需 `cv2.rotate` 180°）。

**板端 Python 环境**：`/home/firefly/hand_gesture/mediapipe_env`（Python 3.10，已装 mediapipe / opencv / numpy / pyserial；NPU 版另装了 rknn-toolkit-lite2）。

**一次识别的输出格式（三种后端完全一致）**：
21 个关键点，每个 `(x, y, z)` 都是**归一化坐标**（0~1，相对画面宽高）。手腕是 0 号点，指尖是 4/8/12/16/20 号。
所以后面的手势判定、画骨架、映射灵巧手角度，三版代码是同一套逻辑，**只有"怎么得到 21 个点"不同**。

**学习路线建议**：先读 [CPU.md](CPU.md)（理解 mediapipe 的调用方式和输出格式），
再读 [GPU.md](GPU.md)（理解 delegate 和板端环境），最后读 [NPU.md](NPU.md)（拆开黑盒，看懂两段模型流水线的每一步数学）。
