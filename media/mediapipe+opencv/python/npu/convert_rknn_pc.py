#!/usr/bin/env python3
# 在 x86 PC 上把 mediapipe 官方手部模型转成 RK3588 可用的 .rknn (只需运行一次)
# 要求: Python 3.8~3.12(本机3.10正好) + pip3 install rknn-toolkit2
#   pip3 install rknn-toolkit2 -i https://pypi.tuna.tsinghua.edu.cn/simple   # 走清华镜像, 快
# 用法: python3 convert_rknn_pc.py
# 产物: palm_detection.rknn / hand_landmark.rknn -> 拷到板子 demo 脚本同目录(scp命令见结尾输出)
import os
import sys
import urllib.request

# 模型来自 mediapipe 官方托管(仓库BUILD里 mediapipe_files 的真实下载地址):
#   palm_detection_full.tflite  = 复杂度1的palm检测(官方默认)  输出[1,2016,18]+[1,2016,1]
#   hand_landmark_full.tflite   = 复杂度1的landmark(官方默认)  输出[1,63]+[1,1]+[1,1]+[1,63]
URLS = [
    ("palm_detection.tflite", "https://storage.googleapis.com/mediapipe-assets/palm_detection_full.tflite", 2339846),
    ("hand_landmark.tflite",  "https://storage.googleapis.com/mediapipe-assets/hand_landmark_full.tflite", 5478917),
]
OUT = {"palm_detection.tflite": "palm_detection.rknn",
       "hand_landmark.tflite":  "hand_landmark.rknn"}

_DIR = os.path.dirname(os.path.abspath(__file__))


def download(name, url, size):
    path = os.path.join(_DIR, name)
    if os.path.exists(path) and os.path.getsize(path) == size:
        print(f"[dl] {name} 已存在, 跳过下载")
        return path
    print(f"[dl] 下载 {name} ({size // 1024}KB) ...")
    try:
        urllib.request.urlretrieve(url, path)      # 自动走 https_proxy 环境变量
    except Exception as e:
        print(f"[error] 下载失败: {e}")
        print("        需要能访问 storage.googleapis.com, 先设代理再运行:")
        print('        export https_proxy=http://<代理>:<端口> http_proxy=http://<代理>:<端口>')
        sys.exit(1)
    if os.path.getsize(path) != size:
        print(f"[warn] {name} 大小{os.path.getsize(path)}与预期{size}不符, 官方模型可能已更新, 继续尝试转换")
    return path


def convert(in_name, out_name):
    from rknn.api import RKNN
    in_path, out_path = os.path.join(_DIR, in_name), os.path.join(_DIR, out_name)
    rk = RKNN()
    # 输入uint8(0~255), 运行时内部做(x-0)/255归一化 -> 与tflite的float输入[0,1]一致.
    # 板上RKNNLite推理时直接喂uint8即可(与hand_npu.py的实现对应)
    if rk.config(target_platform="rk3588", mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]]) != 0:
        print(f"[error] {in_name}: config 失败")
        sys.exit(1)
    if rk.load_tflite(in_path) != 0:
        print(f"[error] {in_name}: load_tflite 失败")
        sys.exit(1)
    if rk.build(do_quantization=False) != 0:       # 不量化 -> FP16, 精度接近原始float模型
        print(f"[error] {in_name}: build 失败")
        sys.exit(1)

    # 先导出(导出必须在release之前!), 再用PC软件模拟器跑一帧核对输出形状(不依赖板子, 失败不影响产物)
    if rk.export_rknn(out_path) != 0:
        print(f"[error] {in_name}: export 失败")
        sys.exit(1)
    print(f"[ok] 已生成 {out_path} ({os.path.getsize(out_path) // 1024}KB)")
    try:
        if rk.init_runtime() == 0:
            import numpy as np
            probe = {"palm_detection.tflite": 192, "hand_landmark.tflite": 224}[in_name]
            outs = rk.inference(inputs=[np.zeros((1, probe, probe, 3), np.uint8)])
            shapes = [list(o.shape) for o in outs]
            print(f"[sim] {in_name} 输出形状: {shapes}")
            if in_name == "palm_detection.tflite":
                assert 2016 in shapes[0], "palm框数不是2016, anchors配置与模型不匹配!"
            else:
                assert [1, 63] in shapes and [1, 1] in shapes, "landmark输出形状异常!"
        rk.release()
    except Exception as e:
        print(f"[sim] 模拟器核对跳过(不影响产物): {e}")
        try:
            rk.release()
        except Exception:
            pass


def main():
    print(f"工作目录: {_DIR}")
    try:
        import rknn  # noqa: F401
    except ImportError:
        print("[error] 未安装 rknn-toolkit2, 先执行:")
        print("        pip3 install rknn-toolkit2 -i https://pypi.tuna.tsinghua.edu.cn/simple")
        print("        (要求Python 3.8~3.12, 本机3.10可用)")
        sys.exit(1)
    for name, url, size in URLS:
        download(name, url, size)
    for in_name in OUT:
        convert(in_name, OUT[in_name])
    print("\n==== 完成 ====")
    print("把两个.rknn拷到板子上demo脚本同目录, 例如:")
    print("  scp palm_detection.rknn hand_landmark.rknn 用户名@板子IP:/路径/gesture_mediapipe/")
    print("然后板子上运行: python3 fixed_gesture_npu.py  或  python3 hand_control_npu.py [/dev/ttyACM0]")


if __name__ == "__main__":
    main()
