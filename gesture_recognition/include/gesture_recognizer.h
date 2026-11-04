#pragma once

#include <opencv2/core.hpp>

#include <vector>

// 手势类别：握拳 + 1~5 根手指
enum class Gesture {
    None = -1,   // 未检测到手
    Fist = 0,    // 0 根手指
    One,
    Two,
    Three,
    Four,
    Five,
    Unknown
};

struct GestureResult {
    bool      handFound   = false;
    Gesture   gesture     = Gesture::None;
    int       fingerCount = 0;
    cv::Rect  bbox;                      // 手部外接框
    cv::Point palmCenter{0, 0};          // 掌心（最大内切圆圆心）
    double    palmRadius  = 0.0;         // 手掌等效半径（像素）
    std::vector<cv::Point> fingertipHints;  // 凸包上远离掌心的点（可视化用）
    std::vector<cv::Point> valleyPoints;    // 手指间的凹陷点
};

// 传统 CV 手势识别器：YCrCb 肤色分割 + 轮廓 + 凸包缺陷
class GestureRecognizer {
public:
    struct Params {
        int   minContourArea   = 3000;   // 640x480 下最小手部面积，误检多就调大
        int   maxContourArea   = 400000; // 防止把整块背景当手
        float defectDepthRatio = 0.10f;  // 缺陷深度 / 手掌半径 的阈值
        int   minDefectDepthPx = 12;     // 缺陷深度像素下限，抗噪
        float fistRatio        = 1.50f;  // 最远点/手掌半径 < 该值判定为握拳
        bool  useYCrCb         = true;   // false 则改用 HSV 肤色范围
    };

    explicit GestureRecognizer(const Params& params = Params());

    // 输入 BGR 图像；debugMask 非空时输出二值肤色掩码，便于调参
    GestureResult process(const cv::Mat& bgr, cv::Mat* debugMask = nullptr);

private:
    cv::Mat buildSkinMask(const cv::Mat& bgr) const;

    Params  params_;
    cv::Mat kernelOpen_;
    cv::Mat kernelClose_;
};

const char* gestureName(Gesture g);

// 把识别结果画到画面上（原地修改）
void drawOverlay(cv::Mat& canvas, const GestureResult& result);
