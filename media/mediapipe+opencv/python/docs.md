# 灵巧手

## 1. MediaPipe + OpenCV

### 1.1 环境搭建

```
# 安装OPENCV
sudo apt update
sudo apt install python3-opencv

# 终端中测试OPENCV
python3
import cv2   # 不报错即可
exit()

# 安装python的mediapipe,python需要3.9及以上版本
sudo apt install python3-pip   # 先安装pip
python3 -m pip install mediapipe -i https://pypi.org/simple    # 在安装mediapipe

# 如果python3.12会导致mediapipe安装失败,采用下面的方式,使用3.10+虚拟环境的方式
# ppa 方式安装python3.10
sudo apt update
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.10 python3.10-venv
python3.10 --version
# 使用3.10 创建虚拟环境
mkdir -p /home/firefly/hand_gesture/
mkdir -p /home/firefly/hand_gesture/demo   # 用来放代码
python3.10 -m venv /home/firefly/hand_gesture/mediapipe_env   # 根目录下创建mediapipe_env的独立环境
source /home/firefly/hand_gesture/mediapipe_env/bin/activate   # 激活虚拟环境,退出使用: deactivate
pip install --upgrade pip    # 安装pip
pip install mediapipe opencv-python pyserial    # 安装opencv和mediapipe和串口
# 使用 npu 还需要下面的环境
# 安装 rknn-toolkit-lite2
cd /media/lhj/data/t-chip/7.code/arm64/rockchip/airockchip/rknn-toolkit2/rknn-toolkit-lite2/packages    # pc
scp rknn_toolkit_lite2-2.3.2-cp310-cp310-manylinux_2_17_aarch64.manylinux2014_aarch64.whl firefly@172.16.10.96:/home/firefly              # pc
cd /home/firefly/hand_gesture/demo/npu
source /home/firefly/hand_gesture/mediapipe_env/bin/activate   # 激活虚拟环境
mv/home/fireflyrknn_toolkit_lite2-2.3.2-cp310-cp310-manylinux_2_17_aarch64.manylinux2014_aarch64.whl ./
pip install --no-deps --no-index rknn_toolkit_lite2-2.3.2-cp310-cp310-manylinux_2_17_aarch64.manylinux2014_aarch64.whl

# 安装依赖
# pc
wget https://mirrors.aliyun.com/pypi/packages/af/fe/b6045c782f1fd1ae317d2a6ca1884857ce5c20f59befe6ab25a8603c43a7/ruamel_yaml-0.18.17-py3-none-any.whl
scp ruamel_yaml-0.18.17-py3-none-any.whl firefly@172.16.10.96:/home/firefly 

wget https://mirrors.aliyun.com/pypi/packages/63/65/37648c0c158dc222aba51c089eb3bdfa238e621674dc42d48706e639204f/psutil-7.2.2-cp36-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl
scp psutil-7.2.2-cp36-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl firefly@172.16.10.96:/home/firefly 

wget https://mirrors.aliyun.com/pypi/packages/90/16/e708059c4c429ad2e33be65507fc1730641e5f239fb2964efc1ba6edea94/ruamel_yaml_clib-0.2.15-cp310-cp310-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl
scp ruamel_yaml_clib-0.2.15-cp310-cp310-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl firefly@172.16.10.96:/home/firefly 

# rk3588
pip install --no-index psutil-7.2.2-cp36-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl ruamel_yaml-0.18.17-py3-none-any.whl ruamel_yaml_clib-0.2.15-cp310-cp310-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl

# 验证
python -c "from rknnlite.api import RKNNLite; print(\"rknnlite OK\")"

# 使用虚拟环境
source /home/firefly/hand_gesture/mediapipe_env/bin/activate

# 下载需要的模型,传输到板子 /home/firefly/hand_gesture/demo 
https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
wget https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task

# 因为npu使用的模型是rknn,所以不能直接使用 hand_landmarker.task,使用下面的方式转换
# 本机
# 解压 task
unzip hand_landmarker.task -d hand_landmarker_extracted/
# 转 rknn,我现在的环境是在服务器中,本机没有安装
cd /home/lhj/Linux/media/mediapipe+opencv/python/gpu/gesture_recognizer_extracted
scp gesture_embedder.tflite canned_gesture_classifier.tflite hand_detector.tflite hand_landmarks_detector.tflite lhj@172.16.0.21:/home4/lhj
cd /home/lhj/Linux/media/mediapipe+opencv/python/npu
scp convert_rknn_pc.py lhj@172.16.0.21:/home4/lhj

# 服务器
cd /home4/lhj/arm64/rockchip/airockchip/rknn-toolkit2
mv /home4/lhj/*.tflite ./
mv /home4/lhj/convert_rknn_pc.py ./
python3 convert_rknn_pc.py gesture_embedder.tflite
python3 convert_rknn_pc.py canned_gesture_classifier.tflite
python3 convert_rknn_pc.py hand_detector.tflite
python3 convert_rknn_pc.py hand_landmarks_detector.tflite
# 转换后的rknn模型,传输到板端,然后在python文件中调用即可

# 测试
source /home/firefly/hand_gesture/mediapipe_env/bin/activate
cd /home/firefly/hand_gesture/python/npu/
python hand_control_npu.py       # 手势跟踪
python fixed_gesture_npu.py      # 手势数字识别
python 4_models/gesture_pose_4_models.py   # 固定手势识别,gesture 的手势分类(7种:耶,握拳,张掌,食指向上,拇指向上,拇指向下,iloveyou)
```

### 1.2 python代码框架

首先先编写python代码,先实现摄像头的取图和显示

python 代码

```
import cv2
import time

cap = cv2.VideoCapture(11)   # 11 代表mipi 摄像头的编号是/dev/video11
last_time = time.time()

while True:
        success,img = cap.read()
        if not success:
        	break
        img = cv2.rotate(img, cv2.ROTATE_180)    # 转正摄像头
        current_time = time.time()
        fps = 1.0 / (current_time - last_time)
        last_time = current_time
        cv2.putText(img, f"FPS: {fps:.1f}", (10, 30),cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        cv2.imshow("Image",img)
        cv2.waitKey(1)
```

```
# 运行测试
source /home/firefly/hand_gesture/mediapipe_env/bin/activate
cd /home/firefly/hand_gesture/demo
export DISPLAY=:0
export XAUTHORITY=$(ls -t /run/user/1000/.mutter-Xwaylandauth* | head -1)
python single_demo.py
```



### 1.3 手势识别

代码:

```

```



## 2. FFMedia

### 2.1 源码拉取与demo编译

```
# 拉取源码
mkdir media
cd media
git clone --depth=1 https://github.com/Firefly-rk-linux-utils/ffmedia_release.git

# 编译
cd /media/lhj/data/t-chip/7.code/media/ffmedia_release
cmake -S . -B build

```

