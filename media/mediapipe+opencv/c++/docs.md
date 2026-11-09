# 手势灵巧手 C++ 版

`hand_control.py` / `fixed_gesture.py` 的 C++ 移植, 主循环逻辑逐行对应(含"抓图->串口实发"耗时统计)。
环境自己搭, 本文档给步骤。

## 目录结构

```
C++/
├── CMakeLists.txt            # 顶层: OpenCV/X11 探测 + MEDIAPIPE 路径变量
├── docs.md                   # 本文件
├── common/                   # 公共模块(每个功能一对 hpp/cpp, 独立可改)
│   ├── timing.hpp            #   统一时钟(python的time.time()全对应now_s())
│   ├── serial_port.*         #   串口收发(termios raw 8N1)   <- python: serial.Serial
│   ├── protocol.*            #   舵机协议帧构造/解析(纯函数) <- python: sync_write_frame等
│   ├── cyberhand.*           #   安全限位控制器(clamp/限速/读位/耗时统计) <- python: CyberHand
│   ├── hand_infer.*          #   21关键点推理(GPU优先) <- python: build()/detect_for_video
│   ├── gesture.*             #   固定手势分类+姿势表 <- python fixed_gesture: classify/POSES
│   ├── retarget.*            #   连续跟随映射 <- python hand_control: retarget_pos/thumb_255
│   └── ui.*                  #   全屏(EWMH)/按钮条/骨架绘制/环境变量 <- python: win_fullscreen.py
├── hand_control/             # 项目1: 连续跟随
│   ├── main.cpp              #   主循环(防抖/按钮状态机/两阶段拇指/耗时打印)
│   └── CMakeLists.txt
└── fixed_gesture/            # 项目2: 固定手势
    ├── main.cpp
    └── CMakeLists.txt
```

## 改哪去哪

| 想改的东西 | 改这个文件 |
|---|---|
| 推理后端(换RKNN NPU/NCNN) | `common/hand_infer.cpp`(全项目唯一碰mediapipe的文件, 接口不变) |
| 串口/波特率 | `common/serial_port.cpp`, `HandConfig.baud` |
| 协议帧格式 | `common/protocol.cpp` |
| 限速/死区/安全区间/初始姿势 | 各 `main.cpp` 顶部常量 + `make_cfg()` |
| 手势分类阈值/各手势目标位置 | `common/gesture.cpp` |
| 跟随映射比例/拇指标定 | `common/retarget.cpp` |
| 按钮/全屏/骨架显示 | `common/ui.cpp` |
| 主流程(状态机/两阶段拇指) | `hand_control/main.cpp`, `fixed_gesture/main.cpp` |

## 环境搭建

### 1. 基础依赖(板子上)

```bash
sudo apt install build-essential cmake libopencv-dev libx11-dev
# 要求: OpenCV >= 4.x, GCC >= 9 (C++17)
```

### 2. MediaPipe C++ 推理库(三选一)

`hand_infer.cpp` 按 MediaPipe Tasks 官方 C++ API(0.10.x)编写。CMake 需要
两个变量: `MEDIAPIPE_INCLUDE_DIR`(mediapipe 源码根) 和 `MEDIAPIPE_LIBS`(要链接的库)。

**路线A: 源码编译 MediaPipe(通用但最费劲)**

```bash
# x86 电脑上(板子上编全量mediapipe非常慢, 不建议)
git clone https://github.com/google-ai-edge/mediapipe
cd mediapipe && sudo ./setup_android_sdk_and_ndk.sh   # 仅安卓需要, 可跳
bazel build -c opt --cxxopt='--std=c++17' \
    //mediapipe/tasks/cc/vision/hand_landmarker:hand_landmarker_graph
```
编出的静态库在 `bazel-bin/`, 把 `libhand_landmarker*.a` 及依赖(absl/protobuf/tflite 等)
一起传给 `MEDIAPIPE_LIBS`。具体目标名随版本变, 以仓库 `mediapipe/tasks/cc/vision/hand_landmarker/BUILD` 为准。
注意: 需要能提供 `hand_landmarker.task` 同款任务的链接; 如果只想要"能跑"的链接组合,
更省事的做法是把自己写的 demo 加进 mediapipe 仓库里用它的 BUILD 编译。

**路线B(RK3588 推荐): RKNN NPU**

1. PC 装 [rknn-toolkit2](https://github.com/airockchip/rknn-toolkit2)
2. 取 google 官方 `hand_landmarker.tflite`(float16), 转成 rknn
3. 只重写 `common/hand_infer.cpp`: `init`→`rknn_init`, `detect`→`rknn_run` + 输出解码
   - 注意 landmarker 模型输出是热图+offset, 需要自己写21点解码,
     参考 rknn_model_zoo 的手部关键点示例
4. CMake 里给 `hand_infer` 目标链接 `librknnrt.so`, 其余文件零改动

**路线C: 先编通推理以外的部分**

`MEDIAPIPE_INCLUDE_DIR`/`MEDIAPIPE_LIBS` 留空, 串口/协议/控制/手势/UI 全部能编,
只有 `hand_infer.cpp` 会编不过 —— 适合先调UI和舵机。

### 3. 模型文件

```bash
cp ../hand_landmarker.task C++/build/hand_control/   # 放到可执行文件同级
# 或: export HAND_MODEL=/path/to/hand_landmarker.task
```
查找顺序: `$HAND_MODEL` → 可执行文件同级 → 上两级 → 当前目录。

### 4. 编译

```bash
cd C++
mkdir build && cd build
cmake -DMEDIAPIPE_INCLUDE_DIR=/path/to/mediapipe \
      -DMEDIAPIPE_LIBS="/path/libhand_landmarker.a /path/libmediapipe.a ..." ..
make -j
# 产物: build/hand_control/hand_control, build/fixed_gesture/fixed_gesture
```

### 5. 运行

```bash
sudo usermod -aG dialout $USER    # 串口权限(重新登录生效)
./hand_control                    # dry-run: 只识别, 每5秒打印映射位置
./hand_control /dev/ttyACM0       # 识别+控制
./fixed_gesture /dev/ttyACM0
```
DISPLAY / XDG_RUNTIME_DIR / XAUTHORITY 代码里自动设置(与 python 版一致)。
!!! 通电时严禁用手扳动关节 !!!

## 与 python 版的一致性说明

- 参数全部相同: SEND_HZ/MAX_STEP/DEADBAND/SAFE_RANGE/POSES/MAP 标定值, 在两个
  `main.cpp` 顶部和 `gesture.cpp`/`retarget.cpp` 里
- 含新加的"抓图->发送"耗时统计: 状态行 + 画面 fps 旁实时 ms
- `fixed_gesture` 两阶段拇指(四指到位或1.2s兜底再压拇指)、丢手1秒回准备、
  防抖 STABLE_N=3、START/PAUSE/EXIT 按钮均一致
- 已知差异(有意为之):
  - 时间戳用 monotonic 时钟(`now_s()`), 不受系统时间跳变影响
  - `hand_control` 开局不做复位动作(python 版相同, 只有 fixed_gesture 开局回准备姿势)
  - mediapipe Tasks C++ 的结果字段名随版本略有差异, 编译报字段错时微调 `hand_infer.cpp` 末尾
