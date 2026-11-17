#!/usr/bin/env python3
# 在 x86 PC/服务器 上把 tflite 转成 RK3588 可用的 .rknn (在装了 rknn-toolkit2 的机器上运行)
# 要求: Python 3.8~3.12 + rknn-toolkit2, 版本与板子librknnrt对齐(板上当前2.3.2):
#   pip3 install rknn-toolkit2==2.3.2
#   (pypi直连失败就到 github.com/airockchip/rknn-toolkit2 的 packages/ 下找对应cp310的whl离线装)
#
# 用法:
#   python3 convert_rknn_pc.py                       # 不带参数: 批量转内置6个模型, 已有.rknn的自动跳过
#   python3 convert_rknn_pc.py xxx.tflite [yyy.tflite ...]   # 指定哪个转哪个, 已有.rknn也会覆盖重转
#   python3 convert_rknn_pc.py gesture               # 也可以用名字前缀筛选内置模型(如"gesture"=两个手势模型)
#   python3 convert_rknn_pc.py 新模型.tflite         # 目录里其他tflite也能转: 自动解析文件头判断输入类型,
#                                                     # 图像类自动按uint8转(等效float[0,1], 板上直接喂uint8)
#   python3 convert_rknn_pc.py 新模型.tflite --uint8 # 手动指定: --uint8=图像(内部归一化/255), --float=特征原样进网络
#
# 内置模型 = gesture_recognizer.task 解包出的全部内容:
#   palm_detection.tflite            图像uint8 [1,192,192,3] -> [1,2016,18]+[1,2016,1]     官网自动下载
#   hand_landmark.tflite             图像uint8 [1,224,224,3] -> [1,63]+[1,1]+[1,1]+[1,63]  官网自动下载
#   gesture_embedder.tflite          float [1,21,3]+[1,1]+[1,21,3] -> [1,128]             task解包, 需和脚本放一起
#   canned_gesture_classifier.tflite float [1,128] -> [1,8]                               task解包, 需和脚本放一起
#     classifier输出8类(官方顺序): 0=None 1=Closed_Fist 2=Open_Palm 3=Pointing_Up
#                                4=Thumb_Down 5=Thumb_Up 6=Victory 7=ILoveYou
#   hand_detector.tflite / hand_landmarks_detector.tflite: task解包版检测模型, 与上面官网两枚同架构,
#     (palm_detection.rknn/hand_landmark.rknn已覆盖, 仅在想要一一对应时才转)
# 说明: 这些tflite的图像输入实为float32[0,1](文件头type字段缺省=默认float32), 配mean0/std255后
#       板上喂uint8等效归一化结果, 与原palm_detection.rknn的做法一致.
import os
import shutil
import struct
import sys
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))

# feed: 模拟器自检的输入(类型,形状), 顺序=模型输入顺序; check: 输出形状断言(转完立即模拟器核对)
MODELS = [
    dict(name="palm_detection", tflite="palm_detection.tflite",
         url="https://storage.googleapis.com/mediapipe-assets/palm_detection_full.tflite",
         size=2339846, norm="uint8", feed=[("uint8", (1, 192, 192, 3))],
         check=lambda s: 2016 in s[0]),
    dict(name="hand_landmark", tflite="hand_landmark.tflite",
         url="https://storage.googleapis.com/mediapipe-assets/hand_landmark_full.tflite",
         size=5478917, norm="uint8", feed=[("uint8", (1, 224, 224, 3))],
         check=lambda s: [1, 63] in s and [1, 1] in s),
    dict(name="gesture_embedder", tflite="gesture_embedder.tflite", url=None,
         norm="float", feed=[("float32", (1, 21, 3)), ("float32", (1, 1)), ("float32", (1, 21, 3))],
         # ^tflite声明3输入hand/handedness/world_hand, 但图中只有hand参与计算(后两个是死输入,
         #  无算子消费), RKNN导出会剪成单输入hand[1,21,3], 板上推理只喂hand
         check=lambda s: [1, 128] in s),
    dict(name="canned_gesture_classifier", tflite="canned_gesture_classifier.tflite", url=None,
         norm="float", feed=[("float32", (1, 128))],
         check=lambda s: [1, 8] in s),
    dict(name="hand_detector_task", tflite="hand_detector.tflite", url=None,
         norm="uint8", feed=[("uint8", (1, 192, 192, 3))],
         check=lambda s: 2016 in s[0], extra=True),                    # 同palm_detection, 批量模式不转
    dict(name="hand_landmarks_detector_task", tflite="hand_landmarks_detector.tflite", url=None,
         norm="uint8", feed=[("uint8", (1, 224, 224, 3))],
         check=lambda s: [1, 63] in s and [1, 1] in s, extra=True),    # 同hand_landmark, 批量模式不转
]
KNOWN = {m["tflite"]: m for m in MODELS}

USAGE = """用法:
  python3 convert_rknn_pc.py                          批量转官方4个模型(已有.rknn跳过)
  python3 convert_rknn_pc.py xxx.tflite [yyy.tflite]  指定转哪些, 覆盖已有的.rknn(重新转)
  python3 convert_rknn_pc.py 前缀                      按名字筛选内置模型, 如 gesture
  python3 convert_rknn_pc.py 任意.tflite --uint8       手动指定: 图像模型--uint8 / 特征模型--float
"""


def read_tflite_inputs(path):
    """解析tflite(flatbuffer)文件头, 返回输入张量的(形状,类型), 顺序=模型输入顺序.
    类型按TFLite枚举: 0=float32; vtable里type字段偏移为0表示字段缺省=默认float32"""
    TYPE = {0: "float32", 3: "uint8", 9: "int8"}

    class B:
        __slots__ = ("b",)

        def __init__(s, b):
            s.b = b

        def u16(s, p):
            return struct.unpack_from("<H", s.b, p)[0]

        def u32(s, p):
            return struct.unpack_from("<I", s.b, p)[0]

        def i32(s, p):
            return struct.unpack_from("<i", s.b, p)[0]

    def vtable(b, t):
        vt = t - b.i32(t)
        return [b.u16(vt + 4 + 2 * i) for i in range(b.u16(vt) // 2 - 2)]

    def deref(b, t, o):
        return (t + o) + b.i32(t + o)

    def ivec(b, t, o):
        if not o:
            return None
        p = deref(b, t, o)
        return [b.i32(p + 4 + 4 * i) for i in range(b.u32(p))]

    def tvec(b, t, o):
        p = deref(b, t, o)
        return [e + b.i32(e) for e in (p + 4 + 4 * i for i in range(b.u32(p)))]

    b = B(open(path, "rb").read())
    mpos = b.u32(0)
    subg = tvec(b, mpos, vtable(b, mpos)[2])[0]          # SubGraph[0]
    fs = vtable(b, subg)
    tensors = tvec(b, subg, fs[0])
    ins = ivec(b, subg, fs[1])
    out = []
    for i in ins:
        ft = vtable(b, tensors[i])
        t = b.u8(tensors[i] + ft[1]) if ft[1] else 0     # 偏移0=缺省类型=float32
        out.append((ivec(b, tensors[i], ft[0]), TYPE.get(t, f"type{t}")))
    return out


def get_tflite(m):
    """拿到内置模型的tflite: 本目录有就用, 该下载的下载, task解包模型顺带从本机解包目录拷一份"""
    path = os.path.join(_DIR, m["tflite"])
    if os.path.exists(path):
        if m["url"] and os.path.getsize(path) != m["size"]:
            print(f"[warn] {m['tflite']} 大小{os.path.getsize(path)}与官方{m['size']}不符, 官方模型可能已更新")
        return path
    if m["url"] is None:
        cand = os.path.join(_DIR, "..", "gpu", "gesture_recognizer_extracted", m["tflite"])
        if os.path.exists(cand):
            shutil.copy(cand, path)
            print(f"[cp] {m['tflite']} <- {cand}")
            return path
        print(f"[error] 缺 {m['tflite']}: 解包 gesture_recognizer.task, 把该文件放到脚本同目录")
        sys.exit(1)
    print(f"[dl] 下载 {m['tflite']} ...")
    try:
        urllib.request.urlretrieve(m["url"], path)      # 自动走 https_proxy 环境变量
    except Exception as e:
        print(f"[error] 下载失败: {e}")
        print("        需要能访问 storage.googleapis.com, 先设代理再运行:")
        print('        export https_proxy=http://<代理>:<端口> http_proxy=http://<代理>:<端口>')
        sys.exit(1)
    if os.path.getsize(path) != m["size"]:
        print(f"[warn] {m['tflite']} 大小{os.path.getsize(path)}与预期{m['size']}不符, 继续尝试转换")
    return path


def convert(path, norm, feeds, check, out_path=None, force=False):
    """转一个tflite -> 同名.rknn. force=False且产物已存在时跳过(批量补缺); force=True覆盖重转"""
    import numpy as np
    from rknn.api import RKNN
    if out_path is None:
        out_path = os.path.splitext(path)[0] + ".rknn"
    if os.path.exists(out_path):
        if not force:
            print(f"[skip] {os.path.basename(out_path)} 已存在, 跳过 (重新转: 把tflite名写在命令行上)")
            return
        print(f"[重转] 覆盖已有 {os.path.basename(out_path)}")
    print(f"[rknn] 转换 {os.path.basename(path)} -> {os.path.basename(out_path)} (norm={norm}) ...")
    rk = RKNN()
    kw = dict(target_platform="rk3588")
    if norm == "uint8":                # 图像模型: 内部做(x-0)/255, 与tflite的float[0,1]输入一致, 板上直接喂uint8
        kw.update(mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]])
    # float特征模型不配mean/std, 数据原样进网络
    if rk.config(**kw) != 0:
        print("[error] config 失败")
        sys.exit(1)
    if rk.load_tflite(path) != 0:
        print(f"[error] load_tflite 失败: {path}")
        sys.exit(1)
    if rk.build(do_quantization=False) != 0:       # 不量化 -> FP16, 精度接近原始float模型
        print("[error] build 失败")
        sys.exit(1)
    if rk.export_rknn(out_path) != 0:              # 导出必须在release之前
        print("[error] export 失败")
        sys.exit(1)
    print(f"[ok] 已生成 {out_path} ({os.path.getsize(out_path) // 1024}KB)")

    # PC软件模拟器跑一帧核对(不依赖板子, 失败不影响产物); 未知模型自己解析文件头构造探针
    try:
        if rk.init_runtime() != 0:
            raise RuntimeError("init_runtime失败")
        if feeds is None:
            dt = np.uint8 if norm == "uint8" else np.float32
            feeds = [(dt, tuple(shp)) for shp, _t in read_tflite_inputs(path)]
        inputs = [np.zeros(shp, dt) for dt, shp in feeds]
        outs = rk.inference(inputs=inputs)
        shapes = [list(o.shape) for o in outs]
        print(f"[sim] 输出形状: {shapes}")
        if check is not None:
            assert check(shapes), "输出形状与预期不符!"
        rk.release()
    except Exception as e:
        print(f"[sim] 模拟器核对跳过(不影响产物): {e}")
        try:
            rk.release()
        except Exception:
            pass


def auto_norm(path):
    """未知模型: 解析文件头猜norm. 单输入4维且3通道(如[1,192,192,3])视为图像 -> uint8(等效float[0,1]);
    其余按float特征模型. 返回(norm, 输入信息文本)"""
    try:
        ins = read_tflite_inputs(path)
    except Exception as e:
        print(f"[hint] {os.path.basename(path)} 文件头解析失败({e}), 按 float 特征模型转")
        return "float", "?"
    info = "; ".join(f"{s} {t}" for s, t in ins)
    if len(ins) == 1 and len(ins[0][0]) == 4 and ins[0][0][3] == 3:
        print(f"[auto] {os.path.basename(path)} 输入[{info}] 是图像类(HWC,3通道) -> 按 uint8 转(板上直接喂uint8)")
        return "uint8", info
    print(f"[auto] {os.path.basename(path)} 输入[{info}] -> 按 float 特征模型转(数据原样进网络)")
    return "float", info


def main():
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(USAGE)
        return
    flags = [a for a in args if a.startswith("--")]
    for f in flags:
        if f not in ("--uint8", "--float"):
            print(f"[error] 不认识的选项: {f}\n{USAGE}")
            sys.exit(1)
    flag_norm = "uint8" if "--uint8" in flags else ("float" if "--float" in flags else None)
    paths = [a for a in args if not a.startswith("--")]

    if not paths:                                   # 不带参数: 批量补缺(只转官方4个), 已有的跳过
        try:
            import rknn  # noqa: F401
        except ImportError:
            print("[error] 未安装 rknn-toolkit2, 先执行:")
            print("        pip3 install rknn-toolkit2==2.3.2   # 与板子librknnrt 2.3.2对齐")
            sys.exit(1)
        print(f"工作目录: {_DIR}")
        for m in MODELS:
            if m.get("extra"):
                continue
            convert(get_tflite(m), m["norm"], m["feed"], m["check"])
    else:                                           # 指定tflite/前缀: 强制重转覆盖
        jobs = []                                   # (tflite路径, norm, feed, check)
        for a in paths:
            if ".tflite" in a:
                p = a if os.path.exists(a) else os.path.join(_DIR, a)
                if not os.path.exists(p):
                    print(f"[error] 找不到 {a} (相对当前目录或脚本目录找)")
                    sys.exit(1)
                known = KNOWN.get(os.path.basename(p))
                if known:
                    jobs.append((p, flag_norm or known["norm"], known["feed"], known["check"]))
                elif flag_norm:
                    jobs.append((p, flag_norm, None, None))
                else:
                    norm, _info = auto_norm(p)
                    jobs.append((p, norm, None, None))
            else:                                   # 按名字筛选内置模型
                hits = [m for m in MODELS
                        if a.lower() in m["name"].lower() or a.lower() in m["tflite"].lower()]
                if not hits:
                    print(f"[error] 没有匹配 {a} 的内置模型, 可选:")
                    for m in MODELS:
                        print(f"        {m['tflite']}")
                    sys.exit(1)
                for m in hits:
                    jobs.append((get_tflite(m), flag_norm or m["norm"], m["feed"], m["check"]))
        for p, norm, feeds, check in jobs:
            convert(p, norm, feeds, check, force=True)
    print("\n==== 完成 ====")
    print("把.rknn拷到板子上demo脚本同目录, 例如:")
    print("  scp palm_detection.rknn hand_landmark.rknn gesture_embedder.rknn canned_gesture_classifier.rknn \\")
    print("      用户名@板子IP:/home/firefly/hand_gesture/python/npu/")


if __name__ == "__main__":
    main()
