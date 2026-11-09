#pragma once
// 灵巧手安全限位控制器, 对应 python 版的 CyberHand 类
// 目标值clamp安全区间, 实发值限速逼近, 上电先读真实位置杜绝跳变;
// 另含"抓图->串口实发"端到端耗时统计(与python版一致)
#include <cstdlib>
#include <map>
#include <string>
#include <utility>
#include "serial_port.hpp"

// 每路舵机配置: 安全区间 + 准备姿势 + 限速参数(两个demo参数不同, 由main传入)
struct HandConfig {
    std::map<int, std::pair<int, int>> safe_range;  // ID -> (下限, 上限) 硬性安全区间
    std::map<int, int> init_pose;                   // 准备姿势/初始位
    int max_step = 32;                              // 每帧每路最大位移
    int send_hz  = 25;                              // 串口下发频率
    int deadband = 3;                               // 变化小于此值不发帧
    int baud     = 1000000;
};

class CyberHand {
public:
    // 打不开串口时抛 std::runtime_error
    CyberHand(const std::string& dev, const HandConfig& cfg);

    // 更新目标位置(自动clamp到安全区间)
    void set_target(const std::map<int, int>& pos);

    // 朝目标限速逼近一步, 有变化才发帧; 串口异常抛 std::runtime_error
    void tick();

    // 限速平滑回准备姿势(单阶段), 对应 hand_control.py 的 move_to_init
    void move_to_init(double timeout_s = 2.0);

    // 两阶段回准备姿势: 四指先伸开, 到位后拇指再张开, 对应 fixed_gesture.py 的 move_to_init
    void move_to_init_two_phase(double timeout_s = 3.5);

    std::map<int, int> cur, tgt;
    double t_src = 0.0;   // 当前目标来源帧的抓取时刻(now_s()秒), 0=无效; 由main在set_target前赋值
    double lat   = 0.0;   // 抓图->串口实发耗时(秒, 0.7/0.3平滑), 打印时*1000

private:
    std::map<int, int> read_all();
    SerialPort ser_;
    HandConfig cfg_;
};

// {1: 360, 2: 710, ...} 格式化(状态行打印用, 与python dict打印一致)
inline std::string fmt_map(const std::map<int, int>& m) {
    std::string s = "{";
    bool first = true;
    for (const auto& kv : m) {
        if (!first) s += ", ";
        s += std::to_string(kv.first) + ": " + std::to_string(kv.second);
        first = false;
    }
    return s + "}";
}
