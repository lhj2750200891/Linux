#include "gesture.hpp"

#include <algorithm>
#include <cmath>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace gesture {
Dbg dbg{};   // 定义

namespace {

// ---- 官方数值表(与python版一致) ----
const std::map<int, int> EXT4 = {{1, 360}, {2, 710}, {3, 360}, {4, 710}};   // 四指伸
const std::map<int, int> FLD4 = {{1, 680}, {2, 410}, {3, 680}, {4, 420}};   // 四指握
const std::map<int, int> TH_OPN = {{5, 800}, {6, 850}};                     // 拇指张开
const std::map<int, int> TH_FLD = {{5, 550}, {6, 600}};                     // 拇指收拢

std::map<int, int> merge(std::map<int, int> a, std::map<int, int> b) {
    for (const auto& kv : b) a[kv.first] = kv.second;
    return a;
}

const std::map<std::string, std::map<int, int>>& poses() {
    static const std::map<std::string, std::map<int, int>> POSES = {
        {"1",    merge(merge(FLD4, {{4, 710}}), TH_FLD)},                       // 食指
        {"2",    merge({{1, 680}, {2, 410}, {3, 360}, {4, 710}}, TH_FLD)},      // 食中(V)
        {"3",    merge({{1, 680}, {2, 710}, {3, 360}, {4, 710}}, TH_FLD)},      // 食中无名
        {"4",    merge(EXT4, TH_FLD)},                                          // 四指, 拇指收
        {"5",    merge(EXT4, TH_OPN)},                                          // 手掌
        {"6",    merge({{1, 360}, {2, 410}, {3, 680}, {4, 420}}, TH_OPN)},      // 拇指+小指
        {"7",    {{1, 680}, {2, 410}, {3, 520}, {4, 560}, {5, 660}, {6, 720}}}, // 拇食中捏合(近似)
        {"8",    merge({{1, 680}, {2, 410}, {3, 680}, {4, 710}}, TH_OPN)},      // 拇指+食指
        {"9",    merge({{1, 680}, {2, 410}, {3, 680}, {4, 560}}, TH_FLD)},      // 食指弯钩
        {"fist", merge(FLD4, TH_FLD)},                                          // 拳头
        {"ok",   {{1, 360}, {2, 710}, {3, 360}, {4, 500}, {5, 640}, {6, 700}}}, // 中无小伸, 拇食成圈
        {"like", merge(FLD4, TH_OPN)},                                          // 点赞
    };
    return POSES;
}

const std::map<std::string, std::string> EN = {
    {"1", "1"}, {"2", "2"}, {"3", "3"}, {"4", "4"}, {"5", "5"}, {"6", "6"},
    {"7", "7"}, {"8", "8"}, {"9", "9"}, {"fist", "10"}, {"ok", "OK"}, {"like", "LIKE"}};
const std::map<std::string, std::string> ZH = {
    {"1", "数字1"}, {"2", "数字2"}, {"3", "数字3"}, {"4", "数字4"}, {"5", "数字5"},
    {"6", "数字6"}, {"7", "数字7"}, {"8", "数字8"}, {"9", "数字9"},
    {"fist", "拳头"}, {"ok", "OK手势"}, {"like", "点赞"}};

// 两段骨向量夹角 -> 弯曲度0~255. 0=伸直, 255=全弯 (3D, 与python一致)
int bend255(const std::vector<Landmark>& lm, int mcp, int pip, int tip) {
    double v1x = lm[pip].x - lm[mcp].x, v1y = lm[pip].y - lm[mcp].y, v1z = lm[pip].z - lm[mcp].z;
    double v2x = lm[tip].x - lm[pip].x, v2y = lm[tip].y - lm[pip].y, v2z = lm[tip].z - lm[pip].z;
    double c = (v1x * v2x + v1y * v2y + v1z * v2z) /
               (std::sqrt(v1x * v1x + v1y * v1y + v1z * v1z) *
                std::sqrt(v2x * v2x + v2y * v2y + v2z * v2z) + 1e-6);
    double theta = std::acos(std::max(-1.0, std::min(1.0, c))) * 180.0 / M_PI;
    return (int)(std::max(0.0, std::min(1.0, theta / 120.0)) * 255);
}

}  // namespace

std::string classify(const std::vector<Landmark>& lm) {
    const int IDX = 0, MID = 1, RING = 2, PNK = 3;
    int b[4] = {bend255(lm, 5, 6, 8), bend255(lm, 9, 10, 12), bend255(lm, 13, 14, 16),
                bend255(lm, 17, 18, 20)};
    bool ext[4], bnt[4];
    for (int i = 0; i < 4; i++) { ext[i] = b[i] < 90; bnt[i] = b[i] > 128; }

    double palm = std::hypot(lm[9].x - lm[0].x, lm[9].y - lm[0].y) + 1e-6;   // 腕-中指根=掌长
    auto d = [&](int i, int j) {
        return std::hypot(lm[i].x - lm[j].x, lm[i].y - lm[j].y) / palm;
    };
    double fold = d(4, 17), spread = d(4, 5);       // 拇指尖-小指根 / 拇指尖-食指根
    double pin_i = d(4, 8), pin_m = d(8, 12);       // 拇食指尖 / 食中指尖
    int tb = bend255(lm, 2, 3, 4);                  // 拇指自身弯度: 收拢=弯(tb大), 张开=直
    double h_ir = d(8, 16);                         // 食尖-无名尖(9钩: 单独伸出时大)
    double m_r = d(12, 16);                         // 中尖-无名尖(7: 中指随捏抬起散开)
    double pin3 = std::max(pin_i, std::max(pin_m, d(4, 12)));   // 拇/食/中三指尖最大间距

    dbg.fold = (float)fold; dbg.spread = (float)spread; dbg.pin_i = (float)pin_i;
    dbg.pin_m = (float)pin_m; dbg.pin3 = (float)pin3; dbg.m_r = (float)m_r;
    dbg.h_ir = (float)h_ir; dbg.tb = tb;

    if (pin3 < 0.4 && m_r > 0.45) return "7";        // 三指聚合 且 中/无名尖明显散开
    if (ext[MID] && ext[RING] && ext[PNK] && bnt[IDX] && pin_i < 0.45) return "ok";  // 拇食成圈
    if (bnt[IDX] && bnt[MID] && bnt[RING] && bnt[PNK]) {
        if (pin_m > 0.55 && h_ir > 0.5) return "9";  // 食尖单独伸出
        if (spread > 0.5 && fold > 0.7) return "like";  // 四指握+拇指翘
        return "fist";
    }
    int n = ext[0] + ext[1] + ext[2] + ext[3];
    if (n == 4) return tb < 64 ? "5" : "4";          // 四指全伸: 拇指直=5, 拇指收=4
    if (ext[IDX] && ext[MID] && ext[RING] && bnt[PNK]) return "3";
    if (ext[IDX] && ext[MID] && bnt[RING] && bnt[PNK]) return "2";
    if (ext[IDX] && bnt[MID] && bnt[RING] && bnt[PNK])
        return (spread > 0.45 && fold > 0.7) ? "8" : "1";
    if (ext[PNK] && bnt[IDX] && bnt[MID] && bnt[RING] && spread > 0.45) return "6";
    return "";
}

const std::map<int, int>& pose_of(const std::string& g) {
    static const std::map<int, int> empty;
    const auto& P = poses();
    auto it = P.find(g);
    return it != P.end() ? it->second : empty;
}

const std::map<int, int>& paper_pose() {
    static const std::map<int, int> PAPER = {{1, 360}, {2, 710}, {3, 360}, {4, 710}, {5, 800}, {6, 850}};
    return PAPER;
}

std::string en_name(const std::string& g) {
    auto it = EN.find(g);
    return it != EN.end() ? it->second : g;
}

std::string zh_name(const std::string& g) {
    auto it = ZH.find(g);
    return it != ZH.end() ? it->second : g;
}

}  // namespace gesture
