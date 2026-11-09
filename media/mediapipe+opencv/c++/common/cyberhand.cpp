#include "cyberhand.hpp"
#include "protocol.hpp"
#include "timing.hpp"

#include <cmath>
#include <cstdio>
#include <stdexcept>

CyberHand::CyberHand(const std::string& dev, const HandConfig& cfg) : cfg_(cfg) {
    if (!ser_.open(dev, cfg_.baud)) {
        throw std::runtime_error("打开串口失败: " + dev);
    }
    cur = read_all();                    // 从真实位置出发
    tgt = cur;
    printf("[hand] 已连接 %s, 当前位置 %s\n", dev.c_str(), fmt_map(cur).c_str());
}

std::map<int, int> CyberHand::read_all() {
    std::map<int, int> out;
    for (const auto& kv : cfg_.safe_range) {         // 逐个读真实位置, 失败用初始位兜底
        int sid = kv.first;
        int pos = -1;
        try {
            ser_.drain_input();
            ser_.write_all(cyber::read_position_cmd(sid));
            std::vector<uint8_t> rx;
            if (ser_.wait_bytes(8, 100, rx)) pos = cyber::parse_position(rx.data(), rx.size());
        } catch (...) {
            pos = -1;
        }
        if (pos <= 0) {
            printf("[hand] 舵机%d读位超时, 用初始位兜底\n", sid);
            pos = cfg_.init_pose[sid];
        }
        out[sid] = pos;
    }
    return out;
}

void CyberHand::set_target(const std::map<int, int>& pos) {
    for (const auto& kv : pos) {
        const auto& range = cfg_.safe_range.at(kv.first);   // 安全区间硬限制
        int v = kv.second;
        if (v < range.first) v = range.first;
        if (v > range.second) v = range.second;
        tgt[kv.first] = v;
    }
}

void CyberHand::tick() {
    bool moved = false;
    for (auto& kv : cur) {
        int d = tgt[kv.first] - kv.second;
        if (std::abs(d) <= cfg_.deadband) continue;
        kv.second += (std::abs(d) < cfg_.max_step) ? d : (d > 0 ? cfg_.max_step : -cfg_.max_step);
        moved = true;
    }
    if (moved) {
        if (!ser_.write_all(cyber::sync_write_frame(cur)))   // 同步写广播无应答
            throw std::runtime_error("串口写入失败");
        if (t_src > 0) {                                     // 抓图->串口实发的端到端耗时(轻平滑)
            double dt = now_s() - t_src;
            lat = (lat <= 0) ? dt : lat * 0.7 + dt * 0.3;
        }
        ser_.drain_input();                                  // 清理杂散字节防缓冲膨胀
    }
}

void CyberHand::move_to_init(double timeout_s) {
    set_target(cfg_.init_pose);
    double t0 = now_s();
    while (now_s() - t0 < timeout_s) {
        tick();
        sleep_ms((int)(1000.0 / cfg_.send_hz));
    }
}

void CyberHand::move_to_init_two_phase(double timeout_s) {
    // 阶段一: 四指先伸开(拇指先动会扫到食/中指)
    std::map<int, int> fingers;
    for (int sid : {1, 2, 3, 4}) fingers[sid] = cfg_.init_pose.at(sid);
    set_target(fingers);
    double t0 = now_s();
    while (now_s() - t0 < timeout_s) {
        bool done = true;
        for (int sid : {1, 2, 3, 4})
            if (std::abs(tgt[sid] - cur[sid]) > cfg_.deadband) { done = false; break; }
        if (done) break;
        tick();
        sleep_ms((int)(1000.0 / cfg_.send_hz));
    }
    // 阶段二: 拇指再张开
    std::map<int, int> thumb;
    for (int sid : {5, 6}) thumb[sid] = cfg_.init_pose.at(sid);
    set_target(thumb);
    t0 = now_s();
    while (now_s() - t0 < 1.0) {
        tick();
        sleep_ms((int)(1000.0 / cfg_.send_hz));
    }
}
