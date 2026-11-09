cmake_minimum_required(VERSION 3.10)
project(gesture_cpp CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

find_package(OpenCV REQUIRED)
find_package(X11 QUIET)
find_package(Threads REQUIRED)

# ===== MediaPipe C++ 编译产物位置(按 docs.md / 环境搭建文档 修改, 或 cmake -D 传入) =====
set(MEDIAPIPE_INCLUDE_DIR "" CACHE PATH "mediapipe源码根目录(含 mediapipe/ 头文件树)")
set(MEDIAPIPE_EXTRA_INCLUDES "" CACHE STRING "mediapipe依赖的额外头文件目录(absl/protobuf等bazel外部目录), 分号分隔")
set(MEDIAPIPE_LIBS "" CACHE STRING "mediapipe及依赖库, 空格分隔(全路径)")

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/common)
include_directories(${OpenCV_INCLUDE_DIRS})
if(X11_FOUND)
    include_directories(${X11_INCLUDE_DIR})
endif()

add_subdirectory(common)
add_subdirectory(hand_control)
add_subdirectory(fixed_gesture)
