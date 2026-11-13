# Android 开发

## 1. SDK 获取与编译

```
# 我这里是firefly的android 14,在百度网盘下载的
cd /media/lhj/windows/code/arm64/rockchip/rockchip_android_sdk
ls # 输出如下:
android_sdk_delivery.tar.gz.part00  android_sdk_delivery.tar.gz.part05
android_sdk_delivery.tar.gz.part01  android_sdk_delivery.tar.gz.part06
android_sdk_delivery.tar.gz.part02  android_sdk_delivery.tar.gz.part07
android_sdk_delivery.tar.gz.part03  android_sdk_delivery.tar.gz.part08
android_sdk_delivery.tar.gz.part04

# 先合并压缩包并检验
cat android_sdk_delivery.tar.gz.part* &gt; android_sdk_delivery.tar.gz
md5sum SourceCode/android/android_sdk_delivery.tar.gz

# 解压
tar xzf android_sdk_delivery.tar.gz  

# 编译
cd android_sdk
source build/envsetup.sh && lunch rk3588_aic-userdebug
env ALLOW_MISSING_DEPENDENCIES=true ./build_aic.sh -K   # ① 先编内核（必须，生成 kernel Image）
env ALLOW_MISSING_DEPENDENCIES=true ./build_aic.sh -A   # ② 再编 android 容器固件
# 产物：IMAGE/RK3588_AIC_ANDROID14_USERDEBUG_&lt;时间戳&gt;/IMAGES/container/


```
