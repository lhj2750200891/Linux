#include "retarget.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace retarget {
Raw raw{};   // 定义

namespace {

// 舵机ID: (弯曲源, 伸直位, 弯曲位)
// 弯曲源: 0=index 1=middle 2=ring 3=pinky 4=thumb_bend 5=thumb_rot
struct MapEntry { int sid, key, straight, bent; };
const MapEntry MAP[] = {
    {1, 3, 360, 680},    // 1=小指     ("pinky", 360, 680)
    {2, 2, 710, 410},    // 2=无名指   ("ring", 710, 410)
    {3, 1, 360, 680},    // 3=中指     ("middle", 360, 680)
    {4, 0, 710, 420},    // 4=食指     ("index", 710, 420)
    {5, 4, 800, 550},    // 5=大拇指   ("thumb_bend", 800, 550)
    {6, 5, 600, 850},    // 6=拇指根   ("thumb_rot", 600, 850) 方向已核对
};

// 两段骨向量夹角 -> 弯曲度0~255 (3D)
int bend255(const std::vector<Landmark>& lm, int mcp, int pip, int tip) {
    double v1x = lm[pip].x - lm[mcp].x, v1y = lm[pip].y - lm[mcp].y, v1z = lm[pip].z - lm[mcp].z;
    double v2x = lm[tip].x - lm[pip].x, v2y = lm[tip].y - lm[pip].y, v2z = lm[tip].z - lm[pip].z;
    double c = (v1x * v2x + v1y * v2y + v1z * v2z) /
               (std::sqrt(v1x * v1x + v1y * v1y + v1z * v1z) *
                std::sqrt(v2x * v2x + v2y * v2y + v2z * v2z) + 1e-6);
    double theta = std::acos(std::max(-1.0, std::min(1.0, c))) * 180.0 / M_PI;
    return (int)(std::max(0.0, std::min(1.0, theta / 120.0)) * 255);
}

// 拇指弯/张: 距离比方案(关节角对拇指失灵), 用掌长做尺度基准
// 校准口诀: 直拇指fold约1.0~1.3, 握拳包拳约0.3~0.5; 张开spread约0.5+, 并拢约0.2
// 返回 (bend255, rot255): bend 0直~255弯, rot 0合拢~255张开
std::pair<int, int> thumb_255(const std::vector<Landmark>& lm) {
    double palm = std::hypot(lm[9].x - lm[0].x, lm[9].y - lm[0].y) + 1e-6;
    double fold = std::hypot(lm[4].x - lm[17].x, lm[4].y - lm[17].y) / palm;    // 拇尖-小指根
    double spread = std::hypot(lm[4].x - lm[5].x, lm[4].y - lm[5].y) / palm;    // 拇尖-食指根
    raw.fold = (float)fold;
    raw.spread = (float)spread;
    int bend = (int)(std::max(0.0, std::min(1.0, (1.05 - fold) / 0.65)) * 255);  // 1.05->直, 0.40->全弯
    int rot = (int)(std::max(0.0, std::min(1.0, (spread - 0.25) / 0.30)) * 255); // 0.25->合, 0.55->张
    return {bend, rot};
}

}  // namespace

std::map<int, int> retarget_pos(const std::vector<Landmark>& lm) {
    int bends[4] = {bend255(lm, 5, 6, 8), bend255(lm, 9, 10, 12),
                    bend255(lm, 13, 14, 16), bend255(lm, 17, 18, 20)};
    auto tb = thumb_255(lm);
    std::map<int, int> pos;
    for (const auto& e : MAP) {
        int t = (e.key == 4 ? tb.first : e.key == 5 ? tb.second : bends[e.key]) ;
        pos[e.sid] = (int)std::lround(e.straight + (e.bent - e.straight) * (t / 255.0));
    }
    return pos;
}

}  // namespace retarget
