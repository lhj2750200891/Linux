#include "gesture_recognizer.h"

#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace {

// YCrCb 肤色经验区间（室内 4000K~6000K 白光下比较稳）
constexpr int kCrMin = 133;
constexpr int kCrMax = 180;
constexpr int kCbMin = 77;
constexpr int kCbMax = 127;

}  // namespace

GestureRecognizer::GestureRecognizer(const Params& params) : params_(params) {
    kernelOpen_  = cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(5, 5));
    kernelClose_ = cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(7, 7));
}

cv::Mat GestureRecognizer::buildSkinMask(const cv::Mat& bgr) const {
    cv::Mat mask;
    if (params_.useYCrCb) {
        cv::Mat ycrcb;
        cv::cvtColor(bgr, ycrcb, cv::COLOR_BGR2YCrCb);
        cv::inRange(ycrcb,
                    cv::Scalar(0, kCrMin, kCbMin),
                    cv::Scalar(255, kCrMax, kCbMax),
                    mask);
    } else {
        cv::Mat hsv;
        cv::cvtColor(bgr, hsv, cv::COLOR_BGR2HSV);
        cv::inRange(hsv,
                    cv::Scalar(0, 40, 60),
                    cv::Scalar(25, 255, 255),
                    mask);
    }
    return mask;
}

GestureResult GestureRecognizer::process(const cv::Mat& bgr, cv::Mat* debugMask) {
    GestureResult result;
    if (bgr.empty()) return result;

    // 1) 预处理：轻微高斯模糊，压掉肤色掩码里的椒盐噪点
    cv::Mat blurred;
    cv::GaussianBlur(bgr, blurred, cv::Size(5, 5), 0);

    // 2) 肤色分割 + 形态学去噪
    cv::Mat mask = buildSkinMask(blurred);
    cv::morphologyEx(mask, mask, cv::MORPH_OPEN, kernelOpen_);
    cv::morphologyEx(mask, mask, cv::MORPH_CLOSE, kernelClose_, cv::Point(-1, -1), 2);

    if (debugMask) mask.copyTo(*debugMask);

    // 3) 取最大连通域当作手
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(mask, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
    if (contours.empty()) return result;

    const auto largest = std::max_element(
        contours.begin(), contours.end(),
        [](const std::vector<cv::Point>& a, const std::vector<cv::Point>& b) {
            return cv::contourArea(a) < cv::contourArea(b);
        });

    std::vector<cv::Point> contour = *largest;
    const double area = cv::contourArea(contour);
    if (area < params_.minContourArea || area > params_.maxContourArea) return result;

    result.handFound = true;
    result.bbox      = cv::boundingRect(contour);

    // 4) 掌心与手掌半径：在填充后的手部区域上做距离变换取最大值（最大内切圆）
    cv::Mat filled = cv::Mat::zeros(mask.size(), CV_8UC1);
    std::vector<std::vector<cv::Point>> one{contour};
    cv::drawContours(filled, one, 0, cv::Scalar(255), cv::FILLED);

    cv::Mat dist;
    cv::distanceTransform(filled, dist, cv::DIST_L2, 5);
    double palmRadius = 0.0;
    cv::Point palm;
    cv::minMaxLoc(dist, nullptr, &palmRadius, nullptr, &palm);
    if (palmRadius < 1e-3) return result;

    result.palmCenter = palm;
    result.palmRadius = palmRadius;

    // 5) 轮廓点到掌心的最远距离：手指伸开时远大于手掌半径，握拳时接近 1.2 倍
    double maxDist = 0.0;
    for (const cv::Point& p : contour) {
        maxDist = std::max(maxDist, cv::norm(p - palm));
    }

    // 6) 凸包 + 凸包缺陷：每两个相邻手指之间会形成一个"山谷"
    std::vector<int> hullIdx;
    cv::convexHull(contour, hullIdx, false, false);

    std::vector<cv::Point> hullPts;
    cv::convexHull(contour, hullPts);
    for (const cv::Point& p : hullPts) {
        if (cv::norm(p - palm) > params_.fistRatio * palmRadius) {
            result.fingertipHints.push_back(p);
        }
    }

    const bool fingersExtended = (maxDist > params_.fistRatio * palmRadius);
    if (fingersExtended && hullIdx.size() >= 4) {
        std::vector<cv::Vec4i> defects;
        cv::convexityDefects(contour, hullIdx, defects);

        // OpenCV 的 depth 是 8.8 定点数（放大 256 倍存储），先换算成像素
        const double minDepth = std::max<double>(params_.minDefectDepthPx,
                                                 params_.defectDepthRatio * palmRadius);
        for (const cv::Vec4i& d : defects) {
            const double depthPx = d[3] / 256.0;
            if (depthPx < minDepth) continue;

            const cv::Point far = contour[static_cast<size_t>(d[2])];
            // 落在手掌内部（<0.8R）的凹陷在几何上不可能是指缝，直接丢掉
            if (cv::norm(far - palm) < 0.8 * palmRadius) continue;
            result.valleyPoints.push_back(far);
        }
    }

    // 7) 手指数 = 山谷数 + 1（伸开时有 n 根手指就有 n-1 个谷），握拳单独判定
    int fingerCount = 0;
    if (fingersExtended) {
        fingerCount = std::min<int>(5, static_cast<int>(result.valleyPoints.size()) + 1);
    }
    result.fingerCount = fingerCount;

    switch (fingerCount) {
        case 0:  result.gesture = Gesture::Fist; break;
        case 1:  result.gesture = Gesture::One; break;
        case 2:  result.gesture = Gesture::Two; break;
        case 3:  result.gesture = Gesture::Three; break;
        case 4:  result.gesture = Gesture::Four; break;
        case 5:  result.gesture = Gesture::Five; break;
        default: result.gesture = Gesture::Unknown; break;
    }
    return result;
}

const char* gestureName(Gesture g) {
    switch (g) {
        case Gesture::Fist: return "FIST";
        case Gesture::One:  return "ONE";
        case Gesture::Two:  return "TWO";
        case Gesture::Three:return "THREE";
        case Gesture::Four: return "FOUR";
        case Gesture::Five: return "FIVE";
        case Gesture::Unknown: return "UNKNOWN";
        case Gesture::None:
        default: return "NO HAND";
    }
}

void drawOverlay(cv::Mat& canvas, const GestureResult& result) {
    if (!result.handFound) {
        cv::putText(canvas, "NO HAND", cv::Point(16, 40),
                    cv::FONT_HERSHEY_SIMPLEX, 1.0, cv::Scalar(0, 0, 255), 2, cv::LINE_AA);
        return;
    }

    cv::rectangle(canvas, result.bbox, cv::Scalar(0, 255, 0), 2);
    cv::circle(canvas, result.palmCenter,
               static_cast<int>(result.palmRadius), cv::Scalar(255, 160, 0), 1, cv::LINE_AA);

    for (const cv::Point& p : result.valleyPoints) {
        cv::circle(canvas, p, 6, cv::Scalar(0, 0, 255), cv::FILLED, cv::LINE_AA);
    }
    for (const cv::Point& p : result.fingertipHints) {
        cv::circle(canvas, p, 5, cv::Scalar(0, 255, 255), cv::FILLED, cv::LINE_AA);
    }

    const std::string label = std::string(gestureName(result.gesture)) +
                              "  fingers=" + std::to_string(result.fingerCount);
    int baseline = 0;
    const cv::Size sz = cv::getTextSize(label, cv::FONT_HERSHEY_SIMPLEX, 0.8, 2, &baseline);
    const cv::Rect box(10, 10, sz.width + 20, sz.height + 20);
    cv::rectangle(canvas, box, cv::Scalar(0, 0, 0), cv::FILLED);
    cv::putText(canvas, label, cv::Point(20, 10 + sz.height + 6),
                cv::FONT_HERSHEY_SIMPLEX, 0.8, cv::Scalar(0, 255, 0), 2, cv::LINE_AA);
}
