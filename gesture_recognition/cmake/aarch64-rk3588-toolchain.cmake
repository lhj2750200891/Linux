# 用于在 x86 Ubuntu 22.04 上交叉编译到 RK3588（aarch64）
#
# 用法：
#   cmake -S . -B build-rk3588 \
#         -DCMAKE_TOOLCHAIN_FILE=$PWD/cmake/aarch64-rk3588-toolchain.cmake \
#         -DRK3588_SYSROOT=$HOME/rk3588-sysroot \
#         -DCMAKE_BUILD_TYPE=Release
#
# RK3588_SYSROOT 必须包含板端的 /usr/include、/usr/lib（其中要有 OpenCV 的 cmake 配置）

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

set(TOOLCHAIN_PREFIX aarch64-linux-gnu)

if(NOT DEFINED RK3588_SYSROOT)
  message(FATAL_ERROR "请用 -DRK3588_SYSROOT=/path/to/sysroot 指定板端根文件系统")
endif()
set(CMAKE_SYSROOT ${RK3588_SYSROOT})

set(CMAKE_C_COMPILER   ${TOOLCHAIN_PREFIX}-gcc)
set(CMAKE_CXX_COMPILER ${TOOLCHAIN_PREFIX}-g++)

set(CMAKE_FIND_ROOT_PATH ${CMAKE_SYSROOT})
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

set(CMAKE_C_FLAGS_INIT   "-O3 -pipe")
set(CMAKE_CXX_FLAGS_INIT "-O3 -pipe")
