# unitree_sdk3 学习笔记

## 1. 源码拉取与编译

```
# 拉取源码
git clone https://githubproxy.cc/https://github.com/unitreerobotics/unitree_sdk2.git

# 依赖安装
sudo apt-get update
sudo apt-get install -y libboost-dev libboost-program-options-dev libboost-system-dev libboost-thread-dev
sudo apt-get install -y libeigen3-dev   # 不安装会有 #include <eigen3/Eigen/Dense> 错误
sudo apt-get install -y libfmt-dev      # 不安装找不到 -lfmt,报错

# cmakelist.txt修改
vim /media/lhj/data/t-chip/7.code/unitree_sdk2/example/h2/CMakeLists.txt
if(yaml-cpp_FOUND AND ${yaml-cpp_VERSION} VERSION_GREATER_EQUAL "0.6") 改为:
if(yaml-cpp_FOUND AND yaml-cpp_VERSION VERSION_GREATER_EQUAL "0.6")

# 编译
cd unitree_sdk2
mkdir build
cd build
cmake ..           # 如果错误需要重新编译的时候,需要先删除产物
make
sudo make install

# 验证安装
ls -l /usr/local/lib/libunitree_sdk2.a /usr/local/lib/libddsc*.so*
ls /usr/local/lib/cmake/unitree_sdk2/

# 编译完成,在bin下面会生成二进制文件
ls /media/lhj/data/t-chip/7.code/unitree_sdk2/build/bin
```

![image-20261104162151988](/home/lhj/.config/Typora/typora-user-images/image-20261104162151988.png)



## 2. 配置网络环境

​        目的是让目标设备,与自己的电脑处于同一局域网,机器狗的ip地址是192.168.123.161,设置好电脑的ip地址以后,用ping命令测试是否连通



在电脑上使用ifocnfig,查看与机器狗连接的网卡的名称:

![image-20261104164313531](/home/lhj/.config/Typora/typora-user-images/image-20261104164313531.png)

## 3. 例程运行

运行例程前,先关闭主控程序,然后再运行

```
cd /media/lhj/data/t-chip/7.code/unitree_sdk2/build/bin
./go2_low_level 网卡序号     # 就是ifconfig查出来的
```







