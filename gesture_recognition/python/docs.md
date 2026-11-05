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

# 使用虚拟环境
source /home/firefly/hand_gesture/mediapipe_env/bin/activate

# 下载需要的模型,传输到板子 /home/firefly/hand_gesture/demo 
https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
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

