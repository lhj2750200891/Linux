# 基于 OpenCV 的手势识别（C++）：x86 开发 → RK3588 部署 全流程

目标：在 x86 Ubuntu 22.04 上写代码、调通，然后编译出 aarch64 程序在 RK3588 上跑。
识别 6 类手势：握拳 / 1 指 / 2 指 / 3 指 / 4 指 / 5 指。

```
┌──────────────────────────┐        git / rsync / scp       ┌───────────────────────────┐
│ x86 Ubuntu 22.04          │ ─────────────────────────────► │ RK3588 (aarch64)          │
│ 写代码 + USB 摄像头调试    │                               │ 板端编译 或 x86 交叉编译    │
└──────────────────────────┘                               └───────────────────────────┘
```

---

## 0. 先说技术选型（决定后面所有步骤）

| 方案 | 依赖 | 精度 | RK3588 单帧耗时 | 适用场景 |
|---|---|---|---|---|
| **A. 传统 CV**：YCrCb 肤色 + 轮廓 + 凸包缺陷 | 只要 OpenCV | 中，受光照/背景影响 | 2~5 ms（CPU 单核） | 课程作业、演示、链路验证 |
| **B. MediaPipe Hands**（palm_detection + hand_landmark，TFLite/ONNX） | OpenCV DNN + 模型文件 | 高，21 个关键点 | 20~40 ms（CPU） | 真实产品 |
| **C. 自训练分类网络 + RKNN** | rknn-toolkit2 + NPU | 高（自定义手势集） | <10 ms（NPU） | 定制手势、要上量产 |

**建议路线**：先用 A 把「相机 → 算法 → 显示/输出 → 下发到板子」整条链路跑通（本仓库代码就是 A），
之后只替换 `GestureRecognizer` 这一个类就能升级到 B / C，主程序和部署流程完全不用改。

---

## 1. x86 Ubuntu 22.04 开发环境

### 1.1 基础依赖

```bash
sudo apt update
sudo apt install -y build-essential cmake git pkg-config v4l-utils

# 直接用系统源里的 OpenCV（jammy 源通常是 4.5.4，够用）
sudo apt install -y libopencv-dev
pkg-config --modversion opencv4      # 确认版本，输出 4.5.4 或更高即可
```

验证摄像头能被识别：

```bash
ls -l /dev/video*
v4l2-ctl --list-devices                     # 看设备名
v4l2-ctl -d /dev/video0 --list-formats-ext  # 看支持的分辨率/帧率/MJPG
```

### 1.2 （可选）源码编译 OpenCV 4.8+

只有这三种情况才需要自己编：① 要用 GStreamer 接 MIPI 摄像头；② 要保证 x86 和板端版本一致；③ 要 OpenCL。

```bash
sudo apt install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
                    libavcodec-dev libavformat-dev libswscale-dev libgtk-3-dev

git clone --depth 1 -b 4.8.1 https://github.com/opencv/opencv.git
cmake -S opencv -B opencv/build -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DWITH_GSTREAMER=ON -DWITH_FFMPEG=ON \
      -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF \
      -DOPENCV_GENERATE_PKGCONFIG=ON
cmake --build opencv/build -j$(nproc)      # 约 15~30 分钟
sudo cmake --install opencv/build && sudo ldconfig
```

> 装到 `/usr/local` 后，若 CMake 仍找到旧版本，删掉 `build/` 重新 configure，或显式传
> `-DOpenCV_DIR=/usr/local/lib/cmake/opencv4`。

### 1.3 编译本工程

```bash
cd gesture_recognition
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
```

### 1.4 运行

```bash
# 实时摄像头（默认 640x480 @30，自动请求 MJPG）
./build/gesture_demo --camera 0 --debug

# 用视频文件离线调参，最省事
./build/gesture_demo --input test.mp4 --output result.mp4 --headless

# 换分辨率
./build/gesture_demo --camera 0 --width 1280 --height 720
```

按键：`q` / `ESC` 退出，`d` 切换肤色掩码窗口。
终端会同步打印每次手势变化，无显示环境也能看到结果。

---

## 2. 算法流程与调参（看懂这段才好改）

```
BGR 帧
  └─ 高斯模糊 5x5
      └─ BGR→YCrCb，inRange(Cr 133~180, Cb 77~127)  → 二值肤色掩码
          └─ 形态学开运算(去噪) + 闭运算(补洞)
              └─ findContours 取最大连通域 = 手
                  ├─ distanceTransform → 最大内切圆 = 掌心 + 手掌半径 R
                  ├─ 轮廓点到掌心最远距离 maxDist
                  │     maxDist < 1.5R  ⇒ 握拳（0 指）
                  └─ convexHull + convexityDefects → 手指之间的"谷"
                        手指数 = 谷数 + 1，上限 5
```

关键参数（`include/gesture_recognizer.h` 的 `Params`）：

| 参数 | 默认值 | 什么时候改 |
|---|---|---|
| `minContourArea` | 3000 | 背景里出现大片肤色误检 → 调大；手离镜头很远 → 调小 |
| `defectDepthRatio` | 0.10 | 手指没分开时误判成一根 → 调大 |
| `minDefectDepthPx` | 12 | 掩码边缘抖动导致手指乱跳 → 调大 |
| `fistRatio` | 1.50 | 握拳被识别成 1 指 → 调大；伸 1 指识别成握拳 → 调小 |
| `useYCrCb` | true | 暖色/黄光环境误检多 → 改 `false` 试 HSV |

**调参顺序**：先开 `--debug` 只看肤色掩码。掩码干净（手是实心白块、背景是黑）之后，
再调 `fistRatio` 和 `defectDepthRatio`，否则调后面的参数没有意义。

**这套方法的已知短板**（提前知道，别浪费时间）：肤色法对光照、背景、肤色差异敏感，
快速运动有拖影，手套/袖子会干扰。要稳定上产品就必须换方案 B/C。

---

## 3. RK3588 部署

### 3.1 先摸清板子环境

```bash
uname -m                       # 必须 aarch64
cat /etc/os-release            # 记下 VERSION_ID，决定用哪条路线
ldd --version | head -1        # glibc 版本，交叉编译时非常重要
nproc                          # RK3588 是 8 核（4×A76 + 4×A55）
pkg-config --modversion opencv4 || dpkg -l | grep -i opencv
ls /dev/video*
```

### 3.2 路线 A：板端直接编译（**推荐先走这条**）

优点：零交叉编译配置、不会踩 glibc 版本坑，出问题好排查。缺点：板子编译慢一点（本工程约 1~2 分钟）。

```bash
sudo apt update
sudo apt install -y build-essential cmake libopencv-dev v4l-utils

# 把源码传上去（在 x86 上执行）
rsync -avz --exclude build --exclude build-rk3588 \
      gesture_recognition/ root@<板子IP>:/home/root/

# 板端编译运行
cd /home/root/gesture_recognition
bash scripts/build_board.sh
./build/gesture_demo --camera 0
```

如果 `apt install libopencv-dev` 报找不到包，或版本低于 4.2：
在板子上源码编译 OpenCV（同 1.2 那套命令，`-j4`，A76 上大概 40~90 分钟），
或者改走路线 B、把 x86 上编好的 OpenCV 交叉编译过去。
（只在板端跑本工程时也可以只装运行时库 `libopencv-core4.5d` 之类，但编译需要 `-dev` 包。）

### 3.3 路线 B：x86 交叉编译

**前置条件**：x86 和板端的 glibc 要匹配（工具链的 glibc 版本 ≤ 板端）。
Ubuntu 22.04 的 `gcc-aarch64-linux-gnu` 是 glibc 2.35，板端是 Ubuntu 22.04 正好匹配；
如果板端是 20.04（glibc 2.31），会报 `GLIBC_2.34 not found`，此时用 Ubuntu 20.04 的 Docker 做交叉编译，或改走路线 A。

#### (1) 装交叉工具链

```bash
sudo apt install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu
aarch64-linux-gnu-g++ --version
```

#### (2) 准备 sysroot（关键一步，90% 的失败都在这）

sysroot 就是板端的根文件系统视图，里面要有 `/usr/include` 和 `/usr/lib`（含 OpenCV 的 cmake 配置）。

方式一：sshfs 直接挂载（最快，适合调通阶段）

```bash
sudo apt install -y sshfs
mkdir -p ~/rk3588-root
sshfs root@<板子IP>:/ ~/rk3588-root
# 之后用 -DRK3588_SYSROOT=$HOME/rk3588-root
```

方式二：rsync 拷一份到本地（稳定、离线可用）

```bash
mkdir -p ~/rk3588-sysroot
rsync -avz --rsync-path="sudo rsync" root@<板子IP>:/usr/include ~/rk3588-sysroot/usr/
rsync -avz --rsync-path="sudo rsync" root@<板子IP>:/usr/lib     ~/rk3588-sysroot/usr/
rsync -avz --rsync-path="sudo rsync" root@<板子IP>:/lib         ~/rk3588-sysroot/
```

确认 OpenCV 的 cmake 配置进去了：

```bash
ls ~/rk3588-sysroot/usr/lib/aarch64-linux-gnu/cmake/opencv4/
```

#### (3) 交叉编译

```bash
cd gesture_recognition
cmake -S . -B build-rk3588 \
      -DCMAKE_TOOLCHAIN_FILE=$PWD/cmake/aarch64-rk3588-toolchain.cmake \
      -DRK3588_SYSROOT=$HOME/rk3588-sysroot \
      -DCMAKE_BUILD_TYPE=Release \
      -DENABLE_A76_TUNING=ON
cmake --build build-rk3588 -j$(nproc)
```

#### (4) 验证产物确实是 aarch64

```bash
file build-rk3588/gesture_demo
# 期望: ELF 64-bit LSB pie executable, ARM aarch64, ...

# 看依赖的库，确认板端都有
aarch64-linux-gnu-readelf -d build-rk3588/gesture_demo | grep NEEDED

# 检查 glibc 符号版本要求，不能高于板端 ldd 的版本
aarch64-linux-gnu-objdump -T build-rk3588/gesture_demo | grep -o 'GLIBC_[0-9.]*' | sort -u
```

#### (5) 部署运行

```bash
scp build-rk3588/gesture_demo root@<板子IP>:/home/root/
ssh root@<板子IP>
chmod +x /home/root/gesture_demo
./gesture_demo --camera 0
```

### 3.4 摄像头接入（RK3588 最容易卡住的地方）

**USB UVC 摄像头**：插上就能用，`/dev/video0`，直接 `--camera 0`。
建议先用 `v4l2-ctl -d /dev/video0 --list-formats-ext` 确认支持 MJPG，程序默认会请求 MJPG。

**MIPI / CSI 摄像头**（板载排线那种）：不能当普通 V4L2 用，必须走 GStreamer，
而且 OpenCV 必须编译时开了 `WITH_GSTREAMER=ON`（`apt` 装的版本一般已开启，用
`./gesture_demo` 启动时打印的 `cv::getBuildInformation` 或源码里 `HAVE_GSTREAMER` 确认）。

```bash
v4l2-ctl --list-devices        # 找 rkisp 对应的节点，rk3588 上常见 /dev/video11 是主通路
```

```bash
./gesture_demo --pipeline \
 "v4l2src device=/dev/video11 ! video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 ! videoconvert ! video/x-raw,format=BGR ! appsink max-buffers=1 drop=true"
```

> 一定要带 `videoconvert` 和 `appsink`；`max-buffers=1 drop=true` 用于降低延迟。
> 具体节点号和 format 以 `v4l2-ctl` 的实际输出为准，别照抄。

### 3.5 无显示环境（SSH 登录 / 没接 HDMI）

`cv::imshow` 在无 X server 时会直接抛异常，用 `--headless`：

```bash
# 只打印识别结果
./gesture_demo --camera 0 --headless

# 存成视频，拉回 x86 看
./gesture_demo --camera 0 --headless --output out.mp4

# 板子接了 HDMI 且在桌面里跑，但你是 SSH 登录的：把显示指过去
export DISPLAY=:0
./gesture_demo --camera 0
```

---

## 4. 性能优化清单（在板子上按顺序试）

1. **降处理分辨率**：识别在 320x240 上做，显示仍用 640x480（肤色分割对分辨率不敏感，耗时直接降 4 倍）。
2. **MJPG 优先**：YUYV 在 USB2.0 上跑 720p 只有 5fps，且 OpenCV 解码 YUYV 更慢。
3. **锁大核**：`taskset -c 4-7 ./build/gesture_demo --camera 0`（A76 四个核）。
4. **限制 OpenCV 线程数**：`cv::setNumThreads(4)`，线程开满反而在 8 核上抢 CPU。
5. **关掉 debug 窗口**：`--debug` 会多两次全图拷贝 + `imshow`，实测能吃掉 1~2ms。
6. **编译选项**：`-O3` 已开；`ENABLE_A76_TUNING=ON` 加 `-mtune=cortex-a76`；
   aarch64 的 NEON 是基线指令集，OpenCV 默认就会用，不用额外开。
7. **OpenCL**（可选）：RK3588 是 Mali-G610，`cv::ocl::setUseOpenCL(true)` 对 `cvtColor`/`inRange`
   这类逐像素操作有收益，但需要 OpenCV 编译时 `WITH_OPENCL=ON`，且首次调用有初始化开销。
8. **上 NPU**：只有换深度学习模型（方案 B/C）时才谈得上，走 RKNN 的 `librknnrt.so`。
   传统 CV 算法没有 NPU 加速路径，别指望。
9. **看温度别降频**：`watch -n1 cat /sys/class/thermal/thermal_zone*/temp`，超过 80℃ 要考虑散热。

---

## 5. 升级到深度学习（`GestureRecognizer` 的替换方法）

主程序只依赖 `GestureRecognizer::process()` 返回的 `GestureResult`，所以升级时**不用动 main.cpp**：

```cpp
class MediaPipeHandRecognizer {          // 新写一个类，接口对齐
public:
    GestureResult process(const cv::Mat& bgr, cv::Mat* debugMask = nullptr);
};
```

三条可选路径，按投入从低到高：

1. **OpenCV DNN + ONNX**：把训练好的手势分类/关键点模型用 `cv::dnn::readNetFromONNX` 加载，
   预处理成 blob 后 `net.forward()`。零额外依赖，板端 CPU 可跑，适合固定背景的 6~10 类手势。
2. **MediaPipe Hands（TFLite）**：`cv::dnn::readNetFromTFLite` 可以直接读
   `palm_detection_full.tflite` 和 `hand_landmark_full.tflite`，但要自己实现 SSD anchor 解码和
   ROI 裁剪，代码量约 300~500 行；好处是拿到 21 个关键点后，手势判定规则会非常稳。
3. **RKNN（要性能就走这条）**：x86 上用 rknn-toolkit2（Docker 镜像）把 ONNX 转成 `.rknn`，
   板端链接 `librknnrt.so` 做推理，单帧可做到 10ms 以内。
   Rockchip 的 `rknn_model_zoo` 里有现成的推理 demo 可以照着改。

---

## 6. 排错表

| 现象 | 原因 | 处理 |
|---|---|---|
| `无法打开视频源` | 设备号错 / 无权限 / 被占用 | `ls /dev/video*`、`sudo usermod -aG video $USER` 后重新登录 |
| 画面极慢（<5fps） | 走了 YUYV 没走 MJPG | `v4l2-ctl` 确认格式；程序已请求 MJPG，确认摄像头支持 |
| 掩码几乎全白/全黑 | 光照偏色、曝光过高 | 关掉摄像头自动曝光，换白光；或 `useYCrCb=false` 试 HSV |
| 手指数量一直跳 | 掩码边缘抖动 | 调大 `minDefectDepthPx`、`defectDepthRatio`；加大闭运算核 |
| 握拳识别成 1 指 | `fistRatio` 偏小 | 调大到 1.6~1.8 |
| 交叉编译 `GLIBC_2.34 not found` | 工具链 glibc 高于板端 | 用低版本容器编译，或改板端编译 |
| `error while loading shared libraries: libopencv_core.so.4.5` | 板端缺运行库 | 板端 `sudo apt install libopencv-core4.5d libopencv-imgproc4.5d`，或 `LD_LIBRARY_PATH` 指过去 |
| `cv::imshow` 报 `no display` | 无 X server | 用 `--headless`，或 `export DISPLAY=:0` |
| `GStreamer: pipeline have not been created` | OpenCV 未编译 GStreamer | 重编 OpenCV 加 `-DWITH_GSTREAMER=ON` |
| CMake 找到旧 OpenCV | 多个安装路径冲突 | 删 `build/`，显式传 `-DOpenCV_DIR=...` |

---

## 7. 验收清单

- [ ] x86 上用 `--input test.mp4` 跑通，6 类手势都能稳定识别（`--debug` 看掩码干净）
- [ ] `file build-rk3588/gesture_demo` 显示 `ARM aarch64`（走交叉编译时）
- [ ] 板端 `--headless` 连续跑 10 分钟不崩、不掉帧
- [ ] 板端 640x480 下整机 ≥25 fps，算法单帧 ≤8ms（画面左下角有实时数据）
- [ ] 断电重启后能一条命令启动（写成 `/etc/rc.local` 或 systemd service）

---

## 8. 工程结构

```
gesture_recognition/
├── CMakeLists.txt                                                 # 一套 CMake 同时支持本机/板端/交叉编译
├── cmake/aarch64-rk3588-toolchain.cmake  # 交叉编译工具链
├── include/gesture_recognizer.h                     # 识别器接口（换方案 B/C 只改这里和 .cpp）
├── src/gesture_recognizer.cpp                       # 肤色分割 + 凸包缺陷
├── src/main.cpp                                                 # 采集/显示/参数解析/性能统计
├── scripts/build_board.sh                               # 板端一键编译
└── README.md
```
