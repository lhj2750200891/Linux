#pragma once
// 连续跟随映射(对应 python hand_control.py 的 retarget_pos / thumb_255)
// 官方数值表标定: straight=伸直位置, bent=握弯位置 (各指方向不同!)
// 拇指根(6)跟随拇指旋转, 其余跟随各指弯曲
#include <map>
#include <vector>
#include "hand_infer.hpp"

namespace retarget {

struct Raw {              // 拇指原始比值, dry-run状态行显示供校准
    float fold = 0, spread = 0;
};
extern Raw raw;

// 21关键点 -> {舵机ID: 目标位置}
std::map<int, int> retarget_pos(const std::vector<Landmark>& lm);

}  // namespace retarget
