#pragma once
// 统一时钟: 全项目一律用"程序启动起的秒数"(monotonic), 避免系统时间跳变
// python版里的 time.time() 在这里全部对应 now_s()
#include <chrono>
#include <thread>

inline double now_s() {
    using namespace std::chrono;
    static const steady_clock::time_point t0 = steady_clock::now();
    return duration_cast<duration<double>>(steady_clock::now() - t0).count();
}

inline void sleep_ms(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }
