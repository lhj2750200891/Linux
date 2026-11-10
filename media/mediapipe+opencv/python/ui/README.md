# ui/ — Firefly 展会启动器 (RK3588 手势识别 · 灵巧手演示)

科技风全屏界面, 五区块中心对称布局: 左右各两张 demo 卡片 + 正中央公司宣传视频位。
**不改动任何 demo 原文件**; 本目录与 `npu/` `gpu/` 平级 (板端保持同样的目录布局即可直接使用)。

预览图见 `preview/` (由 `--shot` 生成, 可删):

| 预览 | 内容 |
|---|---|
| `preview/menu.png` | 主界面: 4 张 demo 卡片 + 中央宣传视频位 |
| `preview/menu_hover.png` | 视频位悬停高亮态 |
| `preview/loading.png` | demo 启动过渡页 (真实徽标 + 旋转加载环) |
| `preview/loading_video.png` | 视频启动过渡页 |
| `preview/confirm.png` | 退出确认弹窗 |

## 界面元素

- **动态背景**: 深空渐变 + 透视滚动网格 + 扫描光带 + 萤火虫粒子(琥珀/青, 呼吸明灭) + 电路走线
- **公司元素**: 左上角 `ui/logo.png` 真实徽标(透明混合+淡辉光; 无 alpha 通道的图会自动抠白底)、
  "Firefly" 字标(F 大写其余小写)、RK3588/T-CHIP 徽章、背景水印
- **五区块中心对称**:
  | 区块 | 内容 | 脚本 (按序探测, 第一个存在的生效) | 窗口 |
  |---|---|---|---|
  | 数字手势识别 | demo | `../npu/fixed_gesture_npu.py` | fixed gesture |
  | 灵巧手跟随 | demo | `../npu/hand_control_npu_roi.py` → 原版 `hand_control_npu.py` | hand control |
  | **公司宣传视频** | 中央 | `ui/promo.mp4` (或 `ui/media/*.mp4|mov`) | 播放器 |
  | 固定手势识别 | demo | `../npu/4_models/gesture_pose_4_models_roi.py` → 原版 | gesture pose |
  | 石头剪刀布 | demo | `../npu/rps_game_npu.py` → `../gpu/rps_game.py`(GPU原版备用) | rps npu / rps |

  想换回非 roi 原版: 把 `launcher.py` 顶部 `DEMOS` 里对应条目的 `scripts` 列表调换顺序即可。
- **宣传视频**: 把视频放成 `ui/promo.mp4`(或 `ui/media/` 下任意 mp4/mov)点击中央卡片即播放。
  板上有 `mpv`/`vlc`/`gst-play-1.0`/`ffplay` 之一时调外部播放器(**带音频**, 全屏, 播完或按
  ESC/q 自动回启动器); 一个都没有则用内置 OpenCV 无声播放(点击画面/任意键返回)。
- **顶栏**: 真实徽标 + Firefly 字标 · NPU READY 徽章(检测 rknnlite) · FPS · 实时时钟
- **底栏**: 左 T-CHIP · Firefly 品牌; 中间 **灵巧手串口开关**(点击或按 `s` 切换,
  自动探测 `/dev/ttyACM*|ttyUSB*`, 探测到则启动 demo 时作为第一个参数传入, 没有则干跑);
  右 **退出**(带确认弹窗, 防展会误触)
- **展会电视适配**: 界面自带过扫描安全边距(顶/底内容自动内收), 不会被电视机切掉边缘

## 运行

```bash
# 板端 / 有显示器的 PC (全屏, X11)
cd python
python3 ui/launcher.py

# 无窗口渲染预览图 (设计验证, 不需要显示器)
python3 ui/launcher.py --shot preview --size 1920x1080
```

交互: **点击/触摸卡片** 或按 `1/2/3/4` 启动对应 demo, 点击中央卡片播放宣传视频;
`s` 切换灵巧手串口; `ESC`/`q` 或点退出 → 确认弹窗。

demo 启动后: 启动器等 demo 的全屏窗口出现, 随即隐藏自己的窗口把屏幕完全让给 demo,
**demo 内的 START/PAUSE/EXIT 按钮用法不变**; demo 退出后启动器窗口自动恢复, 回到主界面。
demo 的日志直接打印在启动器的终端里 (排查启动失败看这里)。

## 石头剪刀布 (必胜规则)

第 4 个 demo 默认跑 **NPU 版 `npu/rps_game_npu.py`**(RKNN 双模型识别 21 关键点, 与其他 demo
共用 `npu/hand_npu.py` + 两个 `.rknn`): 识别你的出招(连续 4 帧稳定才算, 防抢拍),
灵巧手随后出克制招 —— 你石头→它布, 你剪刀→它石头, 你布→它剪刀, **机器后手, 每次都是机器赢**。
屏上带 YOU/AI 出招面板与比分(AI 恒胜)。接上灵巧手串口即可对战, 不接则干跑。
`gpu/rps_game.py`(MediaPipe GPU 版)保留在探测列表第二位, 原 demo 未改动。

## 板端部署

```bash
# 目录布局与仓库一致 (ui/ 与 npu/ gpu/ 平级), 整个 python/ 拷过去即可
scp -r python/ firefly@<板子IP>:/home/firefly/hand_gesture/demo/
ssh firefly@<板子IP>
source /home/firefly/hand_gesture/mediapipe_env/bin/activate
cd /home/firefly/hand_gesture/demo
python3 ui/launcher.py
```

依赖: `opencv-python`、`numpy` (demo 本来就要装, **零新增依赖**)。
中文渲染走 PIL + 系统中文字体 (Firefly 出厂镜像一般自带 Noto CJK);
若板子没有 PIL 或中文字体, 界面自动降级为全英文, 不会报错——想要中文就:

```bash
sudo apt install python3-pil fonts-noto-cjk
```

### 展会开机自启 (可选)

创建 `~/.config/autostart/firefly-ui.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Firefly Demo UI
Exec=/home/firefly/hand_gesture/mediapipe_env/bin/python /home/firefly/hand_gesture/demo/ui/launcher.py
X-GNOME-Autostart-enabled=true
```

## 文件结构

```
ui/
├── launcher.py        # 入口: 全屏启动器 (五区块/视频播放/串口开关/退出确认/启动交接)
├── ui_style.py        # 绘制库: 配色/CJK文字/辉光/几何图元/动态背景/真实徽标加载/五个图标
├── logo.png           # Firefly 真实徽标(透明PNG; 缺失则回退程序绘制萤火虫logo)
├── promo.mp4          # 公司宣传视频 (自备, 放进来即被识别; 也可放 media/*.mp4)
├── win_fullscreen.py  # EWMH 全屏工具 (与 npu/ 内的同款, 保持目录自包含)
├── preview/           # --shot 生成的预览图 (可删)
└── README.md
```

石头剪刀布 NPU 版本体在 `npu/rps_game_npu.py`(与 `npu/` 的两个 `.rknn` 同目录使用)。

## 常见问题

- **点击卡片提示"模块缺失"**: `ui/` 和 `npu/` `gpu/` 不在同一父目录下, 或 demo 脚本被改名 —— 保持仓库布局即可。
- **视频位显示"视频未就绪"**: 没找到 `ui/promo.mp4`, 放入即可(文件名也可为 `promo.*` 或放 `media/` 下)。
- **视频没声音**: 板上没有任何外部播放器, 回退成了内置无声播放 —— `sudo apt install mpv` 即可有声。
- **启动失败 · 见终端**: 多为摄像头被占用 (`pgrep -af fixed_gesture\|hand_\|rps`) 或 `.rknn` 模型缺失。
- **画面没有全屏**: 启动器与 demo 一样靠 `win_fullscreen.py` 发 EWMH 消息, 需要 X11 + xprop。
- **分辨率适配**: 与 demo 同一套 `xrandr` 探测, 布局按 1920×1080 设计等比缩放。
