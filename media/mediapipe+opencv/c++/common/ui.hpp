#pragma once
// 显示与交互(对应 python 的 win_fullscreen.py + 两个主循环里的按钮条/骨架绘制/环境设置)
#include <map>
#include <string>
#include <utility>
#include <vector>
#include <opencv2/core.hpp>
#include "hand_infer.hpp"

namespace ui {

// 手部骨架连线(mediapipe HAND_CONNECTIONS)
extern const std::vector<std::pair<int, int>> CONNS;

// 设置 DISPLAY / XDG_RUNTIME_DIR / XAUTHORITY(与两个python文件开头的逻辑一致)
void setup_display_env();

// 屏幕分辨率: xrandr读主屏, 失败按1920x1080兜底
std::pair<int, int> screen_size();

// 给标题含title的窗口发EWMH真全屏消息(OpenCV Qt后端的全屏属性失灵), 失败仅打印不影响运行
void make_fullscreen(const std::string& title, double wait_s = 15.0);

// 底部按钮条: idle:[START EXIT] running:[PAUSE EXIT] paused:[RESUME EXIT]
// 返回按钮名->命中矩形(比画的宽), 每帧用返回值更新给handle_click
std::map<std::string, cv::Rect> draw_buttons(cv::Mat& img, const std::string& state);

// 点击判定+状态切换(与python on_mouse一致); 点EXIT返回true(退出)
bool handle_click(const std::map<std::string, cv::Rect>& rects, int x, int y, std::string& state);

// 画骨架: 绿线连关节, 红点画关键点(坐标乘宽高)
void draw_skeleton(cv::Mat& img, const std::vector<Landmark>& lm);

}  // namespace ui
