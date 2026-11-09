// 固定手势识别 -> 灵巧手实时模仿 (C++版, 逻辑与 fixed_gesture.py 一致)
// 手势集: 数字1~9(中式: 6=拇指+小指 7=拇食中捏合 8=拇指+食指 9=食指弯钩) + fist拳头 + OK + 点赞
// 实时: 手势连续稳定 STABLE_N 帧才采纳(防抖), 灵巧手限速平滑跟随; 手离开1秒回准备姿势
// 交互: START开始 / PAUSE暂停(画面静止, 不抓图不识别) / EXIT退出
// 用法:
//   ./fixed_gesture                # dry-run: 只识别显示, 不接灵巧手(状态行打印阈值观测值)
//   ./fixed_gesture /dev/ttyACM0   # 识别+控制
// !!! 通电时严禁用手扳动关节 !!!
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <fstream>
#include <map>
#include <memory>
#include <string>
#include <unistd.h>
#include <vector>

#include <opencv2/opencv.hpp>

#include "cyberhand.hpp"
#include "gesture.hpp"
#include "hand_infer.hpp"
#include "timing.hpp"
#include "ui.hpp"

static const char* WIN = "fixed gesture";
// 安全配置(与 hand_control 一致)
static const int SEND_HZ = 30, MAX_STEP = 40, DEADBAND = 3;
static const int STABLE_N = 3;          // 连续3帧同一手势才采纳(~0.1s)
static const double LOST_RESET = 1.0;   // 手离开1秒回准备姿势

static HandConfig make_cfg() {
    HandConfig c;
    c.safe_range = {{1, {300, 720}}, {2, {370, 750}}, {3, {300, 720}},
                    {4, {380, 750}}, {5, {520, 820}}, {6, {400, 850}}};
    c.init_pose = {{1, 360}, {2, 710}, {3, 360}, {4, 710}, {5, 800}, {6, 850}};  // 准备姿势=手掌
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

// 取姿势表里的一部分舵机(两阶段用: {1,2,3,4}四指 / {5,6}拇指)
static std::map<int, int> pick(const std::map<int, int>& pose, std::initializer_list<int> ids) {
    std::map<int, int> out;
    for (int id : ids) {
        auto it = pose.find(id);
        if (it != pose.end()) out[id] = it->second;
    }
    return out;
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
        printf("[dry-run] 未接灵巧手, 只识别显示. 控制模式: ./fixed_gesture /dev/ttyACM0\n");
    }

    // ---- 摄像头(默认板子ISP; PC上可用 HAND_CAM=/dev/video0 或虚拟摄像头覆盖) ----
    const char* cam_dev = getenv("HAND_CAM");
    cv::VideoCapture cap(cam_dev && cam_dev[0] ? cam_dev : "/dev/video11", cv::CAP_V4L2);
    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('N', 'V', '1', '2'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, 640);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, 480);
    if (!cap.isOpened()) {
        printf("[error] 摄像头打开失败, 先查占用: pgrep -af fixed_gesture\\|hand_\n");
        return 1;
    }

    // ---- 窗口 + 真全屏 + 按钮 ----
    auto [SW, SH] = ui::screen_size();
    cv::namedWindow(WIN, cv::WINDOW_NORMAL);
    cv::resizeWindow(WIN, SW, SH);
    cv::imshow(WIN, cv::Mat(480, 640, CV_8UC3, cv::Scalar::all(0)));  // 先显示一帧让窗口真正映射出来
    cv::waitKey(200);
    try {
        ui::make_fullscreen(WIN, 5);
    } catch (const std::exception& e) {
        printf("[fullscreen] fail: %s\n", e.what());
    }
    std::string state = "idle";      // idle=预览未开始 / running=识别跟随 / paused=画面静止
    bool quit = false;
    std::map<std::string, cv::Rect> btn_rects;
    MouseCtx mctx{&btn_rects, &state, &quit};
    cv::setMouseCallback(WIN, on_mouse, &mctx);

    if (hand) {                      // 开局回准备姿势(手掌)
        printf("[hand] 开局回准备姿势(手掌)...\n");
        try {
            hand->move_to_init_two_phase(3.5);
        } catch (const std::exception& e) {
            printf("[hand] 复位失败: %s\n", e.what());
        }
    }

    // ---- 主循环 ----
    long ts = 0;
    int n = 0;
    double fps = 0.0, t_last = now_s();
    double next_send = 0.0, t_report = now_s();
    double t_grab = 0.0;             // 本帧抓取时刻(抓图->发送耗时的起算点)
    std::string seen, last_g;        // seen/same: 手势稳定计数; last_g: 当前已采纳手势
    int same = 0;
    std::string label = "SHOW A GESTURE";
    double lose_t = -1.0;            // 丢手时刻, -1=未丢
    std::map<int, int> thumb_pending;   // 拳头等两阶段: 四指到位后才压拇指(空=无待发)
    double t_thumb = 0.0;
    cv::Mat last_img, img;
    std::string prev_state;
    while (true) {
        if (state == "running" && prev_state != "running") {   // (重新)开局: 清空状态
            seen.clear();
            same = 0;
            last_g.clear();
            lose_t = -1.0;
            thumb_pending.clear();
            label = "SHOW A GESTURE";
        }
        prev_state = state;
        std::string g;                   // 本帧识别结果, 空=无手势
        if (state == "paused") {         // 暂停: 不抓图不识别, 最后一帧定格显示
            if (last_img.empty()) continue;
            img = last_img;
        } else {
            if (!cap.read(img)) continue;
            t_grab = now_s();            // 抓到图的时刻
            n++;
            cv::rotate(img, img, cv::ROTATE_180);
            if (state == "running") {    // idle只预览画面, 不跑推理省GPU
                ts += 33;
                std::vector<Landmark> lm;
                if (infer.detect(img, ts, lm)) {
                    g = gesture::classify(lm);
                    ui::draw_skeleton(img, lm);
                }
            }
        }
        if (!g.empty()) {                // 稳定N帧才采纳, 采纳即改灵巧手目标
            lose_t = -1.0;
            same = (g == seen) ? same + 1 : 1;
            seen = g;
            if (same >= STABLE_N && g != last_g) {
                last_g = g;
                same = 0;
                const std::map<int, int>& pose = gesture::pose_of(g);
                if (hand) {              // 所有手势两阶段: 四指先走, 到位后拇指再动
                    hand->t_src = t_grab;             // 记录本目标来自哪次抓图
                    hand->set_target(pick(pose, {1, 2, 3, 4}));
                    thumb_pending = pick(pose, {5, 6});
                    t_thumb = now_s();
                }
                label = gesture::en_name(g);
                const gesture::Dbg& d = gesture::dbg;
                printf("[ges] %s (%s) pin3=%.2f m_r=%.2f h_ir=%.2f fold=%.2f spread=%.2f tb=%d\n",
                       gesture::zh_name(g).c_str(), label.c_str(),
                       d.pin3, d.m_r, d.h_ir, d.fold, d.spread, d.tb);
            }
        } else {                         // 丢手: 计数清零, 离开1秒回准备姿势
            seen.clear();
            same = 0;
            if (!last_g.empty()) {
                if (lose_t < 0) {
                    lose_t = now_s();
                } else if (now_s() - lose_t > LOST_RESET) {
                    if (hand) {          // 回准备姿势也两阶段: 四指先伸, 拇指后张
                        hand->t_src = t_grab;
                        hand->set_target(pick(gesture::paper_pose(), {1, 2, 3, 4}));
                        thumb_pending = pick(gesture::paper_pose(), {5, 6});
                        t_thumb = now_s();
                    } else {
                        thumb_pending.clear();
                    }
                    last_g.clear();
                    label = "SHOW A GESTURE";
                    printf("[ges] 手离开, 回准备姿势\n");
                }
            }
        }
        if (hand && state == "running" && now_s() >= next_send) {
            if (!thumb_pending.empty()) {
                bool fingers_ok = true;
                for (int s : {1, 2, 3, 4})
                    if (std::abs(hand->tgt[s] - hand->cur[s]) > DEADBAND) { fingers_ok = false; break; }
                if (fingers_ok || now_s() - t_thumb > 1.2) {   // 四指到位(或1.2s兜底)再压拇指
                    hand->set_target(thumb_pending);
                    thumb_pending.clear();
                }
            }
            try {
                hand->tick();
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
            const gesture::Dbg& d = gesture::dbg;
            if (!hand) {                 // dry-run: 打印观测值供调分类阈值
                printf("[status] %.1f fps | %s | fold=%.2f spread=%.2f pin3=%.2f m_r=%.2f "
                       "h_ir=%.2f tb=%d\n",
                       fps, label.c_str(), d.fold, d.spread, d.pin3, d.m_r, d.h_ir, d.tb);
            } else {
                printf("[status] %.1f fps | %s | 抓图->发送 %.0fms | 实发 %s\n",
                       fps, label.c_str(), hand->lat * 1000, fmt_map(hand->cur).c_str());
            }
            t_report = now;
        }
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
        std::string show = state == "paused" ? "PAUSED"
                         : (state == "idle" ? "PRESS START TO PLAY" : label);
        cv::putText(img, show, cv::Point(bw + 10, 70), cv::FONT_HERSHEY_SIMPLEX, 0.9, {0, 255, 0}, 2);
        if (state == "running" && !last_g.empty()) {           // 当前手势大字居中显示
            auto sz = cv::getTextSize(label, cv::FONT_HERSHEY_SIMPLEX, 1.8, 3, nullptr);
            cv::putText(img, label, cv::Point((img.cols - sz.width) / 2, 160),
                        cv::FONT_HERSHEY_SIMPLEX, 1.8, {0, 200, 255}, 3);
        }
        cv::imshow(WIN, img);
        last_img = img.clone();          // paused时定格的就是这帧
        if (cv::waitKey(1) == 'q') break;
        if (quit) break;
    }

    // ---- 收尾 ----
    if (hand) {
        try {
            hand->move_to_init_two_phase(3.5);   // 退出限速平滑复位
        } catch (const std::exception& e) {
            printf("[exit] 复位失败(串口已断?): %s\n", e.what());
        }
    }
    cap.release();
    cv::destroyAllWindows();
    printf("[exit] done\n");
    return 0;
}
