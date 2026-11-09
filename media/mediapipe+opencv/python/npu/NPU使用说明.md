# NPU 加速使用说明(RK3588)

原两个 demo(`fixed_gesture.py` / `hand_control.py`,GPU版)**未做任何改动**。NPU 版是复制改名的新文件,推理从 mediapipe GPU 换成 RK3588 NPU(RKNN),其余逻辑(协议、安全限速、手势判定、映射、UI、延迟统计)与原版完全一致。

## 新增文件

| 文件 | 作用 | 运行位置 |
|---|---|---|
| `hand_npu.py` | NPU 推理模块:`HandNPU.detect(帧)` 返回21个关键点,与 mediapipe 同格式 | 板子 |
| `fixed_gesture_npu.py` | 固定手势 demo 的 NPU 版 | 板子 |
| `hand_control_npu.py` | 手部跟随 demo 的 NPU 版 | 板子 |
| `convert_rknn_pc.py` | 下载官方模型并转成 .rknn(含PC模拟器形状核对) | x86 PC |

## 原理(为什么是两个模型)

`hand_landmarker.task` 是 mediapipe 私有图(含自定义算子),RKNN 转不了。官方图内部本来就是两段,直接拆开各转一个:

```
整帧 ──letterbox 192──> palm_detection(FP16) ──解码+NMS──> 旋转ROI(腕→中指根对齐Y轴, 扩2.6倍)
                                                              │ 仿射裁 224×224
                                                              ▼
                                                      hand_landmark(FP16) ──> 21关键点 ──> 还原到原图
```

所有预处理/解码公式都按 mediapipe 官方源码实现(letterbox、anchors 2016 个、raw/192 线性解码、sigmoid 分数、NMS IoU 0.3、shift_y=-0.5、z×2.5/224),已在 PC 上用官方 .tflite 核对过输出形状,与 GPU 版行为对齐。

## 第1步:x86 PC 上转换模型(只需一次)

```bash
pip3 install rknn-toolkit2 -i https://pypi.tuna.tsinghua.edu.cn/simple   # Python 3.8~3.12
python3 convert_rknn_pc.py
```

脚本自动下载官方 `palm_detection_full.tflite` / `hand_landmark_full.tflite`(需要能访问 storage.googleapis.com,不通就先 `export https_proxy=...`),转出 **FP16 未量化** 的两个 .rknn,并在 PC 模拟器里跑一帧核对输出形状(palm 应含 2016,landmark 应含 [1,63])。

> 下载版模型文件名:
> `palm_detection_full.tflite` / `hand_landmark_full.tflite` 来自 mediapipe-assets 官方桶,别用别的 palm 模型,anchors 数(2016)对不上会直接报错。

## 第2步:板子上装运行时并拷文件

```bash
# 板子(Firefly RK3588, aarch64):
pip3 install rknn-toolkit-lite2 -i https://pypi.tuna.tsinghua.edu.cn/simple
ls /usr/lib/librknnrt.so        # Firefly 官方固件自带; 若没有见"常见问题"

# PC 上把 npu/ 目录整个拷到板子(目录内的脚本/模型/依赖互相引用, 需保持同目录):
scp -r npu 用户名@板子IP:~/hand_gesture/
```

> **版本对齐**:运行时 `librknnrt.so` 与 pip 包的大版本要一致(2.x 配 2.x)。若固件的 librknnrt 是 1.6,则 PC/板子都用 1.6.0:`pip install rknn-toolkit2==1.6.0`、`pip3 install rknn-toolkit-lite2==1.6.0`。

## 第3步:运行

```bash
cd npu                          # 板子上进入npu目录(脚本和模型须同目录)
python3 fixed_gesture_npu.py                # dry-run: 只识别显示
python3 fixed_gesture_npu.py /dev/ttyACM0   # 识别+控制灵巧手
python3 hand_control_npu.py                 # dry-run
python3 hand_control_npu.py /dev/ttyACM0    # 识别+控制
```

用法、屏上按钮、退出复位全部与原版一致;状态行的 `抓图->发送 xxms` 就是 NPU 版的端到端延迟,可直接与 GPU 版对比。

## 预期性能

| 阶段 | GPU版(mediapipe) | NPU版 |
|---|---|---|
| palm 检测 | (整图一起算) | ~3-5ms |
| landmark | ~13ms(整体) | ~3-5ms |
| 前后处理(CPU) | 内置 | ~2-4ms(letterbox/warpAffine/numpy解码) |
| CPU 占用 | GPU delegate 仍吃不少 CPU | 明显更低,三个NPU核还有余量 |

整帧预算约 10-15ms,受摄像头 30fps(33ms/帧)限制,`抓图->发送` 预计 **15~25ms**;收益主要在 CPU 负载下降和 GPU 被显示占用时的稳定性。

## 调参(hand_npu.py 顶部常量)

| 常量 | 默认 | 说明 |
|---|---|---|
| `PALM_THRESH` | 0.5 | 手在画面里却检不到 → 降到 0.4;误检/鬼影 → 升到 0.6 |
| `ROI_SCALE` | 2.6 | ROI 相对 palm 框的放大倍数;指尖丢 → 调大,背景干扰 → 调小 |
| `NMS_IOU` | 0.3 | 两只手挤在一起只出一只时略调大 |

## 常见问题

| 症状 | 处理 |
|---|---|
| `import rknnlite 失败` | `pip3 install rknn-toolkit-lite2 -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `librknnrt.so 不存在` | Firefly 固件一般自带;缺失则从 rknpu2 官方仓库(runtime/Linux/librknn_api/aarch64)拷一个到 `/usr/lib/`,并注意与 pip 包大版本一致 |
| 启动报 `palm模型输出N个框, 与anchors(2016)不一致` | .rknn 不是 convert_rknn_pc.py 的产物(文件拷错了),换回脚本产物 |
| `RKNN加载失败` | .rknn 与运行时大版本不匹配(见第2步版本对齐) |
| 手在画面里但一直 `无手/SHOW A GESTURE` | `PALM_THRESH` 降 0.4;手离镜头太远(占画面太小)就靠近些 |
| 关键点抖动比 GPU 版大 | 确认转换没开量化(`do_quantization=False`);检查 .rknn 是否被别的脚本用不同参数重新转过 |
| C++ 版也想要 NPU | 见 `C++/docs.md` 路线B:只重写 `common/hand_infer.cpp`(接口不变,换成 RKNN C API + 同款预处理/解码),其余模块不用动 |
