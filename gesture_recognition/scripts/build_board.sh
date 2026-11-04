#!/usr/bin/env bash
# 在 RK3588 板子上直接编译（逻辑和 x86 上完全一致）
set -e
cd "$(dirname "$0")/.."

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"

echo "构建完成: $(pwd)/build/gesture_demo"
echo "试运行:   ./build/gesture_demo --camera 0"
