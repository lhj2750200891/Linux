#include <opencv2/opencv.hpp>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>

#include "gesture_recognizer.h"

namespace {

struct Options {
    int         camera   = 0;
    std::string input;      // 视频文件
    std::string pipeline;   // 自定义 GStreamer 管道
    std::string output;     // 结果视频
    int         width    = 640;
    int         height   = 480;
    int         fps      = 30;
    bool        mirror   = true;
    bool        headless = false;
    bool        debug    = false;
};

void printUsage(const char* prog) {
    std::cout
        << "用法: " << prog << " [选项]\n"
        << "  --camera <id>        USB 摄像头编号，默认 0（/dev/video<id>）\n"
        << "  --input <file>       读视频文件（x86 上离线调试用）\n"
        << "  --pipeline <str>     自定义 GStreamer 管道（MIPI/CSI 摄像头、RTSP）\n"
        << "  --width  <w>         采集宽度，默认 640\n"
        << "  --height <h>         采集高度，默认 480\n"
        << "  --fps    <n>         采集帧率，默认 30\n"
        << "  --output <file>      写出带标注的结果视频，如 out.mp4\n"
        << "  --no-mirror          关闭左右镜像（默认开启）\n"
        << "  --headless           无显示模式（SSH 登录 / 没接 HDMI 时用）\n"
        << "  --debug              额外显示肤色掩码窗口，方便调参\n"
        << "  -h, --help           显示帮助\n"
        << "\n运行时按键: q/ESC 退出, d 切换掩码窗口\n";
}

bool parseArgs(int argc, char** argv, Options& opt) {
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto take = [&](const char* name) -> std::string {
            if (i + 1 >= argc) {
                std::cerr << "参数 " << name << " 缺少取值\n";
                std::exit(EXIT_FAILURE);
            }
            return std::string(argv[++i]);
        };
        if (a == "--camera")         opt.camera = std::stoi(take("--camera"));
        else if (a == "--input")     opt.input = take("--input");
        else if (a == "--pipeline")  opt.pipeline = take("--pipeline");
        else if (a == "--output")    opt.output = take("--output");
        else if (a == "--width")     opt.width = std::stoi(take("--width"));
        else if (a == "--height")    opt.height = std::stoi(take("--height"));
        else if (a == "--fps")       opt.fps = std::stoi(take("--fps"));
        else if (a == "--no-mirror") opt.mirror = false;
        else if (a == "--headless")  opt.headless = true;
        else if (a == "--debug")     opt.debug = true;
        else if (a == "-h" || a == "--help") { printUsage(argv[0]); return false; }
        else {
            std::cerr << "未知参数: " << a << "\n";
            printUsage(argv[0]);
            return false;
        }
    }
    return true;
}

bool openCapture(const Options& opt, cv::VideoCapture& cap) {
    if (!opt.pipeline.empty()) {
        return cap.open(opt.pipeline, cv::CAP_GSTREAMER);
    }
    if (!opt.input.empty()) {
        if (opt.input.find('!') != std::string::npos) {
            return cap.open(opt.input, cv::CAP_GSTREAMER);  // 直接传了 gst 管道
        }
        return cap.open(opt.input);                          // 视频文件
    }

    if (!cap.open(opt.camera, cv::CAP_V4L2)) return false;

    // MJPG 能大幅降低 USB2.0 带宽压力：720p/1080p 必须用它，否则会被迫降到 5fps
    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, opt.width);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, opt.height);
    cap.set(cv::CAP_PROP_FPS, opt.fps);
    cap.set(cv::CAP_PROP_BUFFERSIZE, 1);  // 只留最新帧，降低延迟
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    Options opt;
    if (!parseArgs(argc, argv, opt)) return 0;

    cv::VideoCapture cap;
    if (!openCapture(opt, cap)) {
        std::cerr << "无法打开视频源，逐项检查：\n"
                  << "  1) 设备存在? ls -l /dev/video*\n"
                  << "  2) 权限?    sudo usermod -aG video $USER  （要重新登录）\n"
                  << "  3) 被占用?  关掉 mjpg-streamer / cheese 等\n"
                  << "  4) MIPI 摄像头需要 --pipeline 传 GStreamer 管道\n";
        return -1;
    }

    std::cout << "采集: " << cap.get(cv::CAP_PROP_FRAME_WIDTH) << "x"
              << cap.get(cv::CAP_PROP_FRAME_HEIGHT) << " @ "
              << cap.get(cv::CAP_PROP_FPS) << " fps" << std::endl;
    std::cout << "OpenCV " << CV_VERSION << std::endl;

    GestureRecognizer recognizer;
    cv::VideoWriter   writer;
    bool              writerReady = false;

    double fpsEma   = 0.0;
    int    lastFingers = -999;
    bool   lastFound   = false;
    int    failCount   = 0;
    const bool needCanvas = (!opt.headless || !opt.output.empty());

    while (true) {
        cv::Mat frame;
        if (!cap.read(frame) || frame.empty()) {
            if (opt.input.empty()) {
                if (++failCount > 30) {
                    std::cerr << "连续读帧失败，摄像头可能已断开\n";
                    break;
                }
                continue;
            }
            std::cout << "视频播放结束\n";
            break;
        }
        failCount = 0;

        if (opt.mirror) cv::flip(frame, frame, 1);

        const auto t0 = std::chrono::steady_clock::now();
        cv::Mat mask;
        GestureResult result = recognizer.process(frame, opt.debug ? &mask : nullptr);
        const auto t1 = std::chrono::steady_clock::now();

        const double costMs  = std::chrono::duration<double, std::milli>(t1 - t0).count();
        const double instFps = 1000.0 / std::max(1e-3, costMs);
        fpsEma = (fpsEma <= 0.0) ? instFps : 0.9 * fpsEma + 0.1 * instFps;

        if (needCanvas) {
            drawOverlay(frame, result);
            char buf[128];
            std::snprintf(buf, sizeof(buf), "%.1f fps | algo %.1f ms", fpsEma, costMs);
            cv::putText(frame, buf, cv::Point(16, frame.rows - 16),
                        cv::FONT_HERSHEY_SIMPLEX, 0.6, cv::Scalar(0, 255, 255), 1, cv::LINE_AA);
        }

        if (!opt.output.empty()) {
            if (!writerReady) {
                writer.open(opt.output, cv::VideoWriter::fourcc('m', 'p', '4', 'v'),
                            opt.fps, frame.size());
                writerReady = true;
                if (!writer.isOpened()) {
                    std::cerr << "无法创建输出视频: " << opt.output << "\n";
                }
            }
            if (writer.isOpened()) writer.write(frame);
        }

        if (result.handFound != lastFound || result.fingerCount != lastFingers) {
            std::cout << (result.handFound ? gestureName(result.gesture) : "NO HAND")
                      << "  fingers=" << result.fingerCount << std::endl;
            lastFound   = result.handFound;
            lastFingers = result.fingerCount;
        }

        if (!opt.headless) {
            cv::imshow("gesture recognition", frame);
            if (opt.debug && !mask.empty()) cv::imshow("skin mask", mask);

            const int key = cv::waitKey(1) & 0xFF;
            if (key == 27 || key == 'q') break;
            if (key == 'd') opt.debug = !opt.debug;
        }
    }

    if (writer.isOpened()) writer.release();
    return 0;
}
