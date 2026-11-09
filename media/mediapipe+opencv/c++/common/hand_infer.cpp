// mediapipe Tasks C++ API 的封装(对应 python 版 build()/landmarker.detect_for_video)
// 注意: 不同 mediapipe 版本的字段/枚举名可能略有差异, 编译报错时按你的版本微调本文件末尾即可
#include "hand_infer.hpp"

#include <cstdio>

#include <mediapipe/framework/formats/image_frame.h>
#include <mediapipe/tasks/cc/core/base_options.h>
#include <mediapipe/tasks/cc/vision/hand_landmarker/hand_landmarker.h>

#include <opencv2/imgproc.hpp>

struct HandInfer::Impl {
    std::unique_ptr<mediapipe::tasks::vision::hand_landmarker::HandLandmarker> landmarker;
};

HandInfer::~HandInfer() { delete impl_; }

bool HandInfer::init(const std::string& model_path, bool prefer_gpu) {
    delete impl_;
    impl_ = new Impl();

    auto create = [&](mediapipe::tasks::core::BaseOptions::Delegate del) -> bool {
        mediapipe::tasks::vision::hand_landmarker::HandLandmarkerOptions opt;
        opt.base_options.model_asset_path = model_path;
        opt.base_options.delegate         = del;
        opt.running_mode                  = mediapipe::tasks::core::RunningMode::VIDEO;
        opt.num_hands                     = 1;
        auto r = mediapipe::tasks::vision::hand_landmarker::HandLandmarker::CreateFromOptions(opt);
        if (r.ok()) {
            impl_->landmarker = std::move(*r);
            return true;
        }
        fprintf(stderr, "[infer] init fail: %s\n", r.status().ToString().c_str());
        return false;
    };

    backend_ = "GPU";
    if (prefer_gpu && create(mediapipe::tasks::core::BaseOptions::Delegate::kGpu)) return true;
    backend_ = "CPU";
    return create(mediapipe::tasks::core::BaseOptions::Delegate::kCpu);
}

bool HandInfer::detect(const cv::Mat& bgr, long ts_ms, std::vector<Landmark>& lm) {
    lm.clear();
    if (!impl_ || !impl_->landmarker) return false;

    cv::Mat rgb;                                          // BGR->RGB(与python一致)
    cv::cvtColor(bgr, rgb, cv::COLOR_BGR2RGB);
    auto frame = std::make_shared<mediapipe::ImageFrame>(
        mediapipe::ImageFormat::SRGB, rgb.cols, rgb.rows, rgb.step[0], rgb.data,
        [](uint8_t*) {});                                 // rgb在detect返回前一直存活, 空deleter安全
    mediapipe::Image image(frame);

    auto res = impl_->landmarker->DetectForVideo(image, (int64_t)ts_ms);
    if (!res.ok() || res->hand_landmarks.empty()) return false;

    const auto& lms = res->hand_landmarks[0].landmarks;
    lm.reserve(lms.size());
    for (const auto& p : lms) lm.push_back({p.x, p.y, p.z});
    return true;
}
