cmake_minimum_required(VERSION 3.16)
project(gesture_recognition LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# 板端/交叉编译时都用同一份 CMakeLists，靠 toolchain 文件切换目标平台
find_package(OpenCV 4 REQUIRED COMPONENTS core imgproc imgcodecs videoio highgui)
message(STATUS "OpenCV ${OpenCV_VERSION} from ${OpenCV_DIR}")

add_executable(gesture_demo
  src/main.cpp
  src/gesture_recognizer.cpp
)

target_include_directories(gesture_demo PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(gesture_demo PRIVATE ${OpenCV_LIBS})

if(NOT MSVC)
  target_compile_options(gesture_demo PRIVATE -O3 -Wall -Wextra -Wno-unused-parameter)
endif()

# RK3588 的 A76 核可以加 -mtune 做调度优化（只影响调度，不改变 ISA，安全）
option(ENABLE_A76_TUNING "Tune scheduling for RK3588 Cortex-A76" OFF)
if(ENABLE_A76_TUNING AND NOT MSVC)
  target_compile_options(gesture_demo PRIVATE -mtune=cortex-a76)
endif()

install(TARGETS gesture_demo RUNTIME DESTINATION bin)
