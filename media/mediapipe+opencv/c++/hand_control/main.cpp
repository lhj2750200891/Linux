// 手势识别 + CyberHand 灵巧手控制 (C++版, 逻辑与 hand_control.py 一致)
// 用法:
//   ./hand_control                # 只识别, 终端每5秒打印映射位置(验证映射用)
//   ./hand_control /dev/ttyACM0   # 识别+控制
// !!! 通电时严禁用手扳动关节 !!!
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <memory>
#include <string>
#include <unistd.h>
#include <vector>

#include <opencv2/opencv.hpp>

#include "cyberhand.hpp"
#include "hand_infer.hpp"
#include "retarget.hpp"
#include "timing.hpp"
#include "ui.hpp"

static const char* WIN = "hand control";
// 安全配置(上线前务必按实物核对, 与 python 版一致)
static const int SEND_HZ = 25;      // 串口下发频率
static const int MAX_STEP = 32;     // 每帧每路最大位移, 25Hz≈800单位/秒, 防撞击
static const int DEADBAND = 3;      // 每路变化小于此值不发帧

static HandConfig make_cfg() {
    HandConfig c;
    // 硬性安全区间: 官方demo实际用到的范围再各留余量. 超范围值发送前被强制截断
    //               1=小拇指      2=无名指      3=中指       4=食指       5=大拇指      6=拇指根部
    c.safe_range = {{1, {300, 720}}, {2, {370, 750}}, {3, {300, 720}},
                    {4, {380, 750}}, {5, {520, 820}}, {6, {400, 850}}};
    c.init_pose = {{1, 360}, {2, 710}, {3, 360}, {4, 710}, {5, 800}, {6, 850}};  // 官方初始姿势
    c.max_step = MAX_STEP;
    c.send_hz = SEND_HZ;
    c.deadband = DEADBAND;
    return c;
}

static std::string exe_dir() {
    char buf[4096];
    ssize_t r = readlink("/proc/self/exe", buf, sizeof buf - 1);
    if (r <= 0) return ".";
    buf[r] = 0;
    std::string p = buf;
    size_t s = p.find_last_of('/');
    return s == std::string::npos ? "." : p.substr(0, s);
}

static std::string find_model() {
    const char* env = getenv("HAND_MODEL");
    if (env && env[0]) return env;
    std::string d = exe_dir();
    for (const std::string& c : {d + "/hand_landmarker.task", d + "/../hand_landmarker.task",
                                 d + "/../../hand_landmarker.task", std::string("hand_landmarker.task")}) {
        std::ifstream f(c, std::ios::binary);
        if (f.good()) return c;
    }
    return "";
}

// ---- 屏上按钮: START开始 / PAUSE暂停(静止) / EXIT退出, 触摸/鼠标点击=左键 ----
struct MouseCtx {
    const std::map<std::string, cv::Rect>* rects;
    std::string* state;
    bool* quit;
};
static void on_mouse(int event, int x, int y, int, void* ud) {
    if (event != cv::EVENT_LBUTTONDOWN) return;
    auto* c = (MouseCtx*)ud;
    if (ui::handle_click(*c->rects, x, y, *c->state)) *c->quit = true;
}

int main(int argc, char** argv) {
    ui::setup_display_env();

    // ---- 推理引擎: GPU优先, 失败回CPU ----
    HandInfer infer;
    {
        std::string model = find_model();
        if (model.empty()) {
            printf("[error] 找不到 hand_landmarker.task (可用环境变量 HAND_MODEL 指定路径)\n");
            return 1;
        }
        if (!infer.init(model, true)) {
            printf("[error] 推理引擎初始化失败\n");
            return 1;
        }
        printf("[infer] %s\n", infer.backend());
    }

    // ---- 灵巧手(可选) ----
    std::unique_ptr<CyberHand> hand;
    if (argc > 1) {
        try {
            hand = std::make_unique<CyberHand>(argv[1], make_cfg());
        } catch (const std::exception& e) {
            printf("[error] 打开 %s 失败: %s\n", argv[1], e.what());
            printf("[error] 确认灵巧手已上电、USB线已插, 设备节点存在: ls /dev/ttyACM*\n");
            return 1;
        }
    } else {
        printf("[dry-run] 未接灵巧手, 只显示映射位置. 控制模式: ./hand_control /dev/ttyACM0\n");
    }

    // ---- 摄像头(默认板子ISP; PC上可用 HAND_CAM=/dev/video0 或虚拟摄像头覆盖) ----
    const char* cam_dev = getenv("HAND_CAM");
    cv::VideoCapture cap(cam_dev && cam_dev[0] ? cam_dev : "/dev/video11", cv::CAP_V4L2);
    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('N', 'V', '1', '2'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, 640);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, 480);
    if (!cap.isOpened()) {
        printf("[error] 摄像头打开失败, 先查占用: pgrep -af hand_\n");
        return 1;
    }

    // ---- 窗口 + 真全屏 + 按钮 ----
    auto [SW, SH] = ui::screen_size();
    cv::namedWindow(WIN, cv::WINDOW_NORMAL);                 // OpenCV Qt后端全屏属性失灵, 先只设尺寸
    cv::resizeWindow(WIN, SW, SH);
    cv::imshow(WIN, cv::Mat(480, 640, CV_8UC3, cv::Scalar::all(0)));  // 先显示一帧让窗口真正映射出来
    cv::waitKey(200);
    try {
        ui::make_fullscreen(WIN, 5);
    } catch (const std::exception& e) {
        printf("[fullscreen] fail: %s\n", e.what());
    }
    std::string state = "idle";      // idle=预览未开始 / running=跟随控制 / paused=画面静止
    bool quit = false;
    std::map<std::string, cv::Rect> btn_rects;
    MouseCtx mctx{&btn_rects, &state, &quit};
    cv::setMouseCallback(WIN, on_mouse, &mctx);

    // ---- 主循环 ----
    long ts = 0;
    int n = 0;
    double fps = 0.0, t_last = now_s();
    double next_send = 0.0, t_report = now_s();
    double t_grab = 0.0;             // 本帧抓取时刻(抓图->发送耗时的起算点)
    std::map<int, int> pos;          // 本帧映射位置(状态行用), 空=无手
    cv::Mat last_img, img;           // paused时定格显示的帧
    std::string prev_state;
    while (true) {
        prev_state = state;
        std::map<int, int> pos_now;
        cv::Mat frame;
        if (state == "paused") {                 // 暂停: 不抓图不识别, 最后一帧定格显示
            if (last_img.empty()) continue;
            img = last_img;
        } else {
            if (!cap.read(frame)) continue;
            t_grab = now_s();                    // 抓到图的时刻
            n++;
            cv::rotate(frame, frame, cv::ROTATE_180);
            if (state == "running") {            // idle只预览画面, 不跑推理省GPU
                ts += 33;
                std::vector<Landmark> lm;
                if (infer.detect(frame, ts, lm)) {
                    pos_now = retarget::retarget_pos(lm);
                    if (hand) {
                        hand->t_src = t_grab;    // 记录本目标来自哪次抓图
                        hand->set_target(pos_now);  // 只更新目标, 实发由限速tick逼近
                    }
                    ui::draw_skeleton(frame, lm);
                }
            }
        }
        pos = pos_now;                           // 状态行显示本帧映射位置(无手时为空)
        if (hand && state == "running" && now_s() >= next_send) {
            try {
                hand->tick();                    // 限速逼近目标(手丢帧时也把上一目标走完)
            } catch (const std::exception& e) {
                printf("[hand] 串口异常, 停止控制: %s\n", e.what());
                break;
            }
            next_send = now_s() + 1.0 / SEND_HZ;
        }
        double now = now_s();
        if (now - t_last >= 1.0) {
            fps = fps * 0.5 + (n / (now - t_last)) * 0.5;
            n = 0;
            t_last = now;
        }
        if (now - t_report >= 5.0) {
            if (!hand) {
                printf("[status] %.1f fps | fold=%.2f spread=%.2f | 映射位置 %s\n",
                       fps, retarget::raw.fold, retarget::raw.spread,
                       pos.empty() ? "无手" : fmt_map(pos).c_str());
            } else {
                printf("[status] %.1f fps | 抓图->发送 %.0fms | 实发 %s\n",
                       fps, hand->lat * 1000, fmt_map(hand->cur).c_str());
            }
            t_report = now;
        }
        img = frame;                             // 后续只在副本上画, 保持last_img干净
        int bw = ((long long)img.rows * SW - (long long)img.cols * SH) / (2 * SH);  // 补黑边不变形
        if (bw > 0) {
            cv::Mat padded;
            cv::copyMakeBorder(img, padded, 0, 0, bw, bw, cv::BORDER_CONSTANT, {0, 0, 0});
            img = padded;
        }
        btn_rects = ui::draw_buttons(img, state);
        char lat_s[32] = "";
        if (hand) snprintf(lat_s, sizeof lat_s, "  %.0fms", hand->lat * 1000);
        char fps_s[96];
        snprintf(fps_s, sizeof fps_s, "%.1f fps%s", fps, lat_s);
        cv::putText(img, fps_s, cv::Point(bw + 10, 30), cv::FONT_HERSHEY_SIMPLEX, 1, {0, 255, 255}, 2);
        std::string show_msg = state == "paused" ? "PAUSED"
                             : (state == "idle" ? "PRESS START TO PLAY" : "FOLLOW MY HAND");
        cv::putText(img, show_msg, cv::Point(bw + 10, 70), cv::FONT_HERSHEY_SIMPLEX, 0.9, {0, 255, 0}, 2);
        cv::imshow(WIN, img);
        last_img = img.clone();                  // paused时定格的就是这帧
        if (cv::waitKey(1) == 'q') break;
        if (quit) break;
    }

    // ---- 收尾 ----
    if (hand) {
        try {
            hand->move_to_init(2.0);             // 退出限速平滑复位, 防止停在奇怪姿势
        } catch (const std::exception& e) {
            printf("[exit] 复位失败(串口已断?): %s\n", e.what());
        }
    }
    cap.release();
    cv::destroyAllWindows();
    printf("[exit] done\n");
    return 0;
}
