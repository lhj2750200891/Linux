#pragma once
// 手部21关键点推理. 全项目唯一接触 mediapipe 的模块(pimpl隔离, 其他文件不用含mediapipe头)
// 想换推理后端(如RK3588上换RKNN NPU): 只重写 hand_infer.cpp, 本接口不变
#include <string>
#include <vector>
#include <opencv2/core.hpp>

struct Landmark {
    float x, y, z;    // 归一化坐标0~1(与mediapipe一致), 画图时乘宽高
};

class HandInfer {
public:
    HandInfer() = default;
    ~HandInfer();
    HandInfer(const HandInfer&) = delete;
    HandInfer& operator=(const HandInfer&) = delete;

    // 加载模型; prefer_gpu=true先试GPU, 失败自动回CPU. 成功返回true
    bool init(const std::string& model_path, bool prefer_gpu);

    // VIDEO模式推理: ts_ms必须相对上次调用单调递增(主循环里 ts+=33 维护)
    // 检测到手返回true并填lm(21点); 无手/失败返回false
    bool detect(const cv::Mat& bgr, long ts_ms, std::vector<Landmark>& lm);

    const char* backend() const { return backend_.c_str(); }   // "GPU" / "CPU"

private:
    struct Impl;          // mediapipe对象藏在这里, 定义在hand_infer.cpp
    Impl* impl_ = nullptr;
    std::string backend_ = "-";
};
