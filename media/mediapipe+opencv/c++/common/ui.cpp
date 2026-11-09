#include "ui.hpp"
#include "timing.hpp"

#include <cstdio>
#include <cstdlib>                                // setenv
#include <cstring>
#include <dirent.h>
#include <regex>

#ifdef HAVE_X11
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#endif

namespace ui {

const std::vector<std::pair<int, int>> CONNS = {
    {0,1},{1,2},{2,3},{3,4},{0,5},{5,6},{6,7},{7,8},{5,9},{9,10},{10,11},
    {11,12},{9,13},{13,14},{14,15},{15,16},{13,17},{17,18},{18,19},{19,20},{0,17}};

void setup_display_env() {
    setenv("DISPLAY", ":0", 1);                       // 无条件覆盖, 避免shell旧值捣乱
    setenv("XDG_RUNTIME_DIR", "/run/user/1000", 1);   // GPU delegate 初始化EGL必需
    // 找最新的 mutter Xwayland 认证文件(python版: sorted(glob(...))[-1])
    std::string best;
    DIR* d = opendir("/run/user/1000");
    if (d) {
        dirent* e;
        while ((e = readdir(d)) != nullptr)
            if (std::strstr(e->d_name, ".mutter-Xwaylandauth") && std::string(e->d_name) > best)
                best = e->d_name;
        closedir(d);
    }
    if (!best.empty()) setenv("XAUTHORITY", ("/run/user/1000/" + best).c_str(), 1);
}

std::pair<int, int> screen_size() {
    try {
        FILE* f = popen("xrandr --current 2>/dev/null", "r");
        if (f) {
            std::string all;
            char buf[4096];
            while (fgets(buf, sizeof buf, f)) all += buf;
            pclose(f);
            std::smatch m;
            std::regex re("(\\d+)x(\\d+)\\+0\\+0");
            if (std::regex_search(all, m, re)) return {std::stoi(m[1]), std::stoi(m[2])};
        }
    } catch (...) {}
    return {1920, 1080};
}

#ifdef HAVE_X11
void make_fullscreen(const std::string& title, double wait_s) {
    Display* dpy = XOpenDisplay(nullptr);
    if (!dpy) { printf("[fullscreen] cannot open display\n"); return; }
    Window root = DefaultRootWindow(dpy);
    Atom a_state = XInternAtom(dpy, "_NET_WM_STATE", False);
    Atom a_fs    = XInternAtom(dpy, "_NET_WM_STATE_FULLSCREEN", False);
    Atom a_list  = XInternAtom(dpy, "_NET_CLIENT_LIST", False);

    Window win = 0;                                   // 从窗口管理器的客户列表按标题找窗口
    double t0 = now_s();
    while (now_s() - t0 < wait_s) {
        Atom type; int fmt; unsigned long n = 0, left = 0; unsigned char* data = nullptr;
        if (XGetWindowProperty(dpy, root, a_list, 0, 1024, False, XA_WINDOW,
                               &type, &fmt, &n, &left, &data) == Success && data && n) {
            Window* wins = (Window*)data;
            for (unsigned long i = 0; i < n && !win; i++) {
                char* nm = nullptr;
                if (XFetchName(dpy, wins[i], &nm) && nm) {
                    if (std::strstr(nm, title.c_str())) win = wins[i];
                    XFree(nm);
                }
            }
            XFree(data);
        }
        if (win) break;
        sleep_ms(500);
    }
    if (!win) {
        printf("[fullscreen] window '%s' not found\n", title.c_str());
        XCloseDisplay(dpy);
        return;
    }
    XClientMessageEvent ev{};                         // EWMH全屏消息, 发两次防WM吃掉第一条
    ev.type = ClientMessage;
    ev.window = win;
    ev.message_type = a_state;
    ev.format = 32;
    ev.data.l[0] = 1;                                 // _NET_WM_STATE_ADD
    ev.data.l[1] = (long)a_fs;
    ev.data.l[2] = 0;
    ev.data.l[3] = 1;                                 // source indication: application
    ev.data.l[4] = 0;
    for (int i = 0; i < 2; i++) {
        XSendEvent(dpy, root, False, SubstructureRedirectMask | SubstructureNotifyMask,
                   (XEvent*)&ev);
        XFlush(dpy);
        sleep_ms(300);
    }
    printf("[fullscreen] window '%s' (0x%lx) fullscreened\n", title.c_str(), (unsigned long)win);
    XCloseDisplay(dpy);
}
#else
void make_fullscreen(const std::string& title, double) {
    printf("[fullscreen] 未链接X11(HAVE_X11未定义), 跳过全屏: %s\n", title.c_str());
}
#endif

std::map<std::string, cv::Rect> draw_buttons(cv::Mat& img, const std::string& state) {
    int h = img.rows, w = img.cols;
    const int bh = 64, bw_ = 200, bh_ = 44, gap = 60;
    cv::Mat bottom = img(cv::Rect(0, h - bh, w, bh));
    bottom.convertTo(bottom, -1, 0.4);                // 按钮条背景压暗

    struct Item { std::string nm, txt; cv::Scalar col; };
    std::vector<Item> items;
    if (state == "idle")
        items = {{"start", "START", {60, 150, 60}}, {"exit", "EXIT", {60, 60, 200}}};
    else if (state == "running")
        items = {{"pause", "PAUSE", {60, 150, 60}}, {"exit", "EXIT", {60, 60, 200}}};
    else
        items = {{"pause", "RESUME", {30, 150, 220}}, {"exit", "EXIT", {60, 60, 200}}};

    int total = (int)items.size() * bw_ + ((int)items.size() - 1) * gap;
    int x0 = (w - total) / 2;
    int y0 = h - bh + (bh - bh_) / 2;
    std::map<std::string, cv::Rect> rects;
    int i = 0;
    for (const auto& it : items) {
        int rx = x0 + i * (bw_ + gap);
        cv::rectangle(img, cv::Point(rx, y0), cv::Point(rx + bw_, y0 + bh_), it.col, -1);
        cv::putText(img, it.txt, cv::Point(rx + 62, y0 + bh_ - 14),
                    cv::FONT_HERSHEY_SIMPLEX, 0.8, {255, 255, 255}, 2);
        rects[it.nm] = cv::Rect(rx - 18, y0 - 6, bw_ + 36, h - (y0 - 6));  // 命中区加宽
        i++;
    }
    return rects;
}

bool handle_click(const std::map<std::string, cv::Rect>& rects, int x, int y, std::string& state) {
    for (const auto& kv : rects) {
        if (kv.second.contains(cv::Point(x, y))) {
            if (kv.first == "exit") return true;
            if (kv.first == "start" && state == "idle") state = "running";
            else if (kv.first == "pause") state = (state == "running") ? "paused" : "running";
            return false;
        }
    }
    return false;
}

void draw_skeleton(cv::Mat& img, const std::vector<Landmark>& lm) {
    int w = img.cols, h = img.rows;
    std::vector<cv::Point> pts;
    pts.reserve(lm.size());
    for (const auto& p : lm) pts.push_back(cv::Point((int)(p.x * w), (int)(p.y * h)));
    for (const auto& ab : CONNS)
        if (ab.first < (int)pts.size() && ab.second < (int)pts.size())
            cv::line(img, pts[ab.first], pts[ab.second], {0, 255, 0}, 2);
    for (const auto& p : pts) cv::circle(img, p, 3, {0, 0, 255}, -1);
}

}  // namespace ui
