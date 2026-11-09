#pragma once
// 固定手势识别(对应 python fixed_gesture.py 的 classify 及全部姿势表)
// 手势集: 数字1~9(中式) + fist拳头 + ok + like点赞
#include <map>
#include <string>
#include <vector>
#include "hand_infer.hpp"

namespace gesture {

struct Dbg {              // 分类观测值, 状态行打印供调阈值
    float fold = 0, spread = 0, pin_i = 0, pin_m = 0, pin3 = 0, m_r = 0, h_ir = 0;
    int tb = 0;
};
extern Dbg dbg;

// 固定手势 -> 标签; 无匹配返回"" (伸=bend<90, 弯=bend>128; 特形手势7捏/OK/9钩/点赞先判)
std::string classify(const std::vector<Landmark>& lm);

// 各手势的六路目标位置(全部落在SAFE_RANGE内)
const std::map<int, int>& pose_of(const std::string& g);

// 准备姿势(手掌)
const std::map<int, int>& paper_pose();

// 显示名: 数字手势直接显示数字, 拳头=10
std::string en_name(const std::string& g);   // "1".."9","10","OK","LIKE"
std::string zh_name(const std::string& g);   // "数字1".."拳头","OK手势","点赞"

}  // namespace gesture
