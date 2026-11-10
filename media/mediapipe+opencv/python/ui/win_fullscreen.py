#!/usr/bin/env python3
"""给X11窗口发EWMH全屏消息(绕过OpenCV Qt后端失灵的全屏属性)
用法: import win_fullscreen; win_fullscreen.make_fullscreen("rps")
依赖: libX11 + xprop(板子都有), 环境需 DISPLAY/XAUTHORITY(demo里已设好)
"""
import ctypes, ctypes.util, re, subprocess, time


def _find_win_by_title(title):
    """从 _NET_CLIENT_LIST(窗口管理器维护的客户窗口列表)里按标题找窗口id"""
    ids = subprocess.check_output(["xprop", "-root", "_NET_CLIENT_LIST"], timeout=3).decode()
    for w in re.findall(r"0x[0-9a-f]+", ids):
        try:
            nm = subprocess.check_output(["xprop", "-id", w, "WM_NAME"], timeout=2).decode()
            m = re.search(r'"(.*)"', nm)
            if m and title in m.group(1):
                return int(w, 16)
        except Exception:
            continue
    return None


def make_fullscreen(title, wait=15.0):
    """把标题含title的窗口全屏化. 等窗口出现最多wait秒"""
    lib = ctypes.util.find_library("X11")
    if not lib:
        print("[fullscreen] libX11 not found", flush=True)
        return False
    x11 = ctypes.CDLL(lib)
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    dpy = x11.XOpenDisplay(None)
    if not dpy:
        print("[fullscreen] cannot open display", flush=True)
        return False
    try:
        root = x11.XDefaultRootWindow(dpy)
        atom_state = x11.XInternAtom(dpy, b"_NET_WM_STATE", False)
        atom_fs = x11.XInternAtom(dpy, b"_NET_WM_STATE_FULLSCREEN", False)
        win = None
        t0 = time.time()
        while time.time() - t0 < wait:
            win = _find_win_by_title(title)
            if win:
                break
            time.sleep(0.5)
        if not win:
            print(f"[fullscreen] window '{title}' not found", flush=True)
            return False

        class XEvent(ctypes.Structure):
            _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong),
                        ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                        ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
                        ("format", ctypes.c_int), ("data", ctypes.c_ulong * 5)]

        for _ in range(2):                    # 发两次, 防窗口管理器吃掉第一条
            ev = XEvent()
            ev.type = 33                      # ClientMessage
            ev.window = win
            ev.message_type = atom_state
            ev.format = 32
            ev.data[0] = 1                    # _NET_WM_STATE_ADD
            ev.data[1] = atom_fs
            ev.data[2] = 0
            ev.data[3] = 1                    # source indication: application
            x11.XSendEvent(dpy, root, 0, (1 << 20) | (1 << 19), ctypes.byref(ev))
            x11.XFlush(dpy)
            time.sleep(0.3)
        print(f"[fullscreen] window '{title}' (0x{win:x}) fullscreened", flush=True)
        return True
    finally:
        x11.XCloseDisplay(dpy)


if __name__ == "__main__":
    import sys
    make_fullscreen(sys.argv[1] if len(sys.argv) > 1 else "rps")
