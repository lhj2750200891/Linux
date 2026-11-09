# 本机(Ubuntu 22.04)C++ 项目环境搭建

> 已按本机实际状态核对过(2026-11 探测):
> Ubuntu 22.04.5 / x86_64 / 16核 / 内存15G / 根分区空闲130G / uid=1000 / DISPLAY=:0
> ✅ 已有: g++ 11.4, cmake 3.22, git 2.34, libx11-dev
> ❌ 缺失: **libopencv-dev, bazelisk, mediapipe C++**, 且**本机没有摄像头**(第6步解决测试问题)
> 注意: 本机编译出的是 **x86_64 二进制,不能直接拷到 RK3588 板子上跑**,部署见文末。

---

## 第1步: apt 基础依赖

```bash
sudo apt update
sudo apt install -y build-essential cmake git libopencv-dev unzip curl
```

验证(应输出 4.5.4):

```bash
pkg-config --modversion opencv4
```

---

## 第2步: 安装 bazelisk(bazel 的自动版本管理器)

mediapipe 仓库里有 `.bazelversion` 文件,bazelisk 会自动下载正确版本的 bazel,不用手动对版本。

```bash
mkdir -p ~/.local/bin
curl -L -o ~/.local/bin/bazelisk \
  https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64
chmod +x ~/.local/bin/bazelisk
export PATH="$HOME/.local/bin:$PATH"      # 以后登录自动生效(~/.profile 已包含该目录)
```

> 国内网络慢时,先设代理再执行 curl:
> `export https_proxy=http://<代理>:<端口> http_proxy=http://<代理>:<端口>`

验证(首次运行会下载一次 bazel,约50MB,走代理):

```bash
bazelisk --version
```

---

## 第3步: 获取 mediapipe 源码(固定 0.10.14)

```bash
mkdir -p ~/tools && cd ~/tools
git clone --depth 1 --branch v0.10.14 https://github.com/google-ai-edge/mediapipe
```

验证(目标头文件存在):

```bash
ls ~/tools/mediapipe/mediapipe/tasks/cc/vision/hand_landmarker/hand_landmarker.h
```

---

## 第4步: 两处修改 + 编译 mediapipe C++ 库

**耗时 30~60 分钟,占用磁盘约 15G(`~/.cache/bazel`),内存不够时把 `--jobs` 降到 4。**

### 4a. OpenCV 配置:整个替换 `third_party/opencv_linux.BUILD`

适配 Ubuntu 22.04 的 apt OpenCV 4.5.4(头文件在 `include/opencv4/`,库在 `/usr/lib/x86_64-linux-gnu/`):

```python
# third_party/opencv_linux.BUILD —— Ubuntu 22.04 apt OpenCV 4.x
cc_library(
    name = "opencv",
    hdrs = glob(["include/opencv4/opencv2/**/*.h*"]),
    includes = ["include/opencv4/"],
    linkopts = [
        "-L/usr/lib/x86_64-linux-gnu",
        "-lopencv_core",
        "-lopencv_imgproc",
        "-lopencv_imgcodecs",
        "-lopencv_video",
        "-lopencv_videoio",
        "-lopencv_highgui",
        "-lopencv_calib3d",
        "-lopencv_features2d",
        "-lopencv_dnn",
        "-lopencv_flann",
        "-lopencv_photo",
    ],
    visibility = ["//visibility:public"],
)
```

同时确认 `WORKSPACE`(仓库根目录)里有这段且未被注释(Ubuntu 路径正好是 `/usr`,不用改):

```python
new_local_repository(
    name = "linux_opencv",
    build_file = "//third_party:opencv_linux.BUILD",
    path = "/usr",
)
```

### 4b. 加一个"打包含依赖的动态库"目标

本项目用 `MEDIAPIPE_LIBS` 链接单个 .so,免去手列上百个 absl 静态库。在
`mediapipe/tasks/cc/vision/hand_landmarker/BUILD` **文件末尾**追加:

```python
cc_binary(
    name = "libhand_landmarker.so",
    linkshared = 1,
    deps = [":hand_landmarker"],
)
```

先核对目标名(grep 出来的 cc_library 里要有 `hand_landmarker`;若只有
`hand_landmarker_graph`,就把 deps 改成 `":hand_landmarker_graph"`):

```bash
grep -n "cc_library(" ~/tools/mediapipe/mediapipe/tasks/cc/vision/hand_landmarker/BUILD
```

### 4c. 编译(首版禁 GPU,PC 上 CPU 推理够用;代码里 kGpu 失败会自动回 CPU)

```bash
cd ~/tools/mediapipe
bazelisk build -c opt --jobs=8 --define MEDIAPIPE_DISABLE_GPU=1 \
    //mediapipe/tasks/cc/vision/hand_landmarker:libhand_landmarker.so
```

验证:

```bash
ls -lh bazel-bin/mediapipe/tasks/cc/vision/hand_landmarker/libhand_landmarker.so
# 预期: 20~40MB 的动态库
```

---

## 第5步: 编译本项目

```bash
cd /media/lhj/data/t-chip/7.code/gesture_mediapipe/C++
mkdir -p build && cd build

MP=~/tools/mediapipe
# absl/protobuf 的头文件在 bazel 的 external 目录里(名字不对就 ls $MP/bazel-mediapipe/external/ 核对)
cmake \
  -DMEDIAPIPE_INCLUDE_DIR=$MP \
  -DMEDIAPIPE_EXTRA_INCLUDES="$MP/bazel-mediapipe/external/com_google_absl;$MP/bazel-mediapipe/external/com_google_protobuf/src" \
  -DMEDIAPIPE_LIBS=$MP/bazel-bin/mediapipe/tasks/cc/vision/hand_landmarker/libhand_landmarker.so \
  ..
make -j8
```

验证(两个可执行文件都生成):

```bash
ls hand_control/hand_control fixed_gesture/fixed_gesture
```

运行时需要找到 mediapipe 的 .so(二选一):

```bash
# 方式一: 每次运行前
export LD_LIBRARY_PATH=$MP/bazel-bin/mediapipe/tasks/cc/vision/hand_landmarker:$LD_LIBRARY_PATH
# 方式二(一劳永逸): 拷进系统库目录
sudo cp $MP/bazel-bin/mediapipe/tasks/cc/vision/hand_landmarker/libhand_landmarker.so /usr/local/lib/
sudo ldconfig
```

---

## 第6步: 冒烟测试(本机没摄像头 → 虚拟摄像头)

本机没有 `/dev/video*`,用 v4l2loopback 把一段**手势视频**伪装成摄像头:

```bash
sudo apt install -y v4l2loopback-dkms ffmpeg
sudo modprobe v4l2loopback devices=1 video_nr=11     # 直接造出 /dev/video11, 代码默认路径都不用改
ls /dev/video11                                       # 验证
# 用任意一段有手势的测试视频循环喂给虚拟摄像头:
ffmpeg -stream_loop -1 -re -i /path/to/手势测试视频.mp4 -pix_fmt yuv420p -f v4l2 /dev/video11
```

另开一个终端运行(模型就用仓库根目录那份,环境变量指定):

```bash
cd /media/lhj/data/t-chip/7.code/gesture_mediapipe/C++/build
export HAND_MODEL=/media/lhj/data/t-chip/7.code/gesture_mediapipe/hand_landmarker.task
./fixed_gesture          # dry-run: 点START, 看骨架跟踪和状态行打印
./hand_control           # dry-run: 状态行打印映射位置
```

> 本机 DISPLAY=:0 与代码默认值一致,X11 全屏/按钮可直接用。
> 串口控制模式(`./hand_control /dev/ttyACM0`)只能在**板子**上测,PC 上没有舵机。

---

## 常见问题

| 症状 | 处理 |
|---|---|
| bazel 拉外部仓库卡住/超时 | 全程带代理: `export https_proxy=... http_proxy=...` |
| 磁盘/缓存占满 | `cd ~/tools/mediapipe && bazelisk clean --expunge` 清掉 `~/.cache/bazel` |
| 链接阶段 OOM | 编译改 `--jobs=4`;make 改 `make -j2` |
| 编译报找不到 absl/protobuf 头文件 | `ls $MP/bazel-mediapipe/external/` 找到实际目录名,追加进 `MEDIAPIPE_EXTRA_INCLUDES`(分号分隔) |
| 报 mediapipe 字段名不存在(`hand_infer.cpp` 末尾) | mediapipe 版本差异,按编译器提示微调 `common/hand_infer.cpp` 尾部几十行 |
| 虚拟摄像头帧率异常 | ffmpeg 命令里 `-re` 保持实时速率;视频分辨率最好 640x480 |

## 下一步: 部署到 RK3588 板子

本机产物是 x86_64,**不能**直接上板。两条路:

1. **RKNN(推荐)**: 在本机 `pip install rknn-toolkit2`(Python 3.10 正好匹配)完成
   tflite→rknn 模型转换;板子只需装 `librknnrt.so` 运行时,然后重写
   `common/hand_infer.cpp`(接口不变,详见 `docs.md` 路线B);其余模块只依赖
   OpenCV/X11,在板子上 `apt install libopencv-dev libx11-dev` 后同样两行 cmake 即可。
2. Bazel 交叉编译 mediapipe 到 aarch64 —— 可行但极折腾,不推荐。
