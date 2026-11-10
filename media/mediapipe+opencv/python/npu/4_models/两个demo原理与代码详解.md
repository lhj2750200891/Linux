# 两个控制 demo 原理与代码详解

> 适用文件（2026-11-10 版，md5 会随以后修改漂移）：
> - `npu/hand_control_npu.py` — **连续跟随**（原件，md5 `8e515499`）
> - `npu/4_models/gesture_pose_4_models.py` — **固定手势→姿势**（md5 `9248c696`）
>
> 识别库内部的 4 模型流水线 / 三探针融合 / 幽灵手防护详见同目录《原理.md》，本文只讲两个 demo
> 脚本本身怎么用这些结果。两者共用的代码（协议/安全/主循环骨架）几乎逐字相同，放在第 1 章讲一遍。

---

## 0. 两个 demo 是什么

| | `hand_control_npu.py` | `gesture_pose_4_models.py` |
|---|---|---|
| 模式 | **连续跟随**：机械手逐关节模仿人手 | **离散触发**：认出手势才下发整套姿势 |
| 位置 | `npu/`（用户原件） | `npu/4_models/` |
| 加载模型 | 2 个：`palm_detection.rknn` + `hand_landmark.rknn`（旧库 `hand_npu.py`） | 4 个：`4_models/` 下全部（新库 `hand_npu_4_models.py`） |
| 识别输出 | 21 个关键点坐标 | 21 点 + **8 类融合概率**（含嵌入/分类模型） |
| 点→舵机 | 每帧算关节弯曲角，线性映射到舵机位置，**手怎么动人手怎么动** | 查 `POSES` 表，**整套姿势一次性下发** |
| 发送策略 | 每帧更新目标，限速追移动目标（持续追赶） | 采纳才更新目标 + 同帧立即首发（一次性冲刺） |
| 额外机制 | — | 三探针融合概率 + 几何耶探针 + EMA/滞回防抖 |
| 速度 | MAX_STEP 64 @ 25Hz = 1600 单位/秒 | 同速，但全行程约 0.2s 走完即停 |

用法（板上，**必须用 venv 解释器**）：

```bash
# 干跑：只识别+显示，不接舵机
/home/firefly/hand_gesture/mediapipe_env/bin/python hand_control_npu.py
# 真控制：加串口设备
/home/firefly/hand_gesture/mediapipe_env/bin/python hand_control_npu.py /dev/ttyACM0
# gesture_pose_4_models.py 同理
```

⚠ **灵巧手通电时严禁用手扳动关节。**

---

## 1. 共同部分（两文件几乎逐字相同）

### 1.1 运行环境与启动

- **环境前置**（文件头）：无条件设 `DISPLAY=:0`、`XDG_RUNTIME_DIR=/run/user/1000`，
  并 glob `/run/user/1000/.mutter-Xwaylandauth*` 取 XAUTHORITY——RKNN 运行时和显示初始化必需，
  避免登录 shell 里的旧环境值捣乱。
- **摄像头**：`/dev/video11`，V4L2 + NV12 四码，640×480；每帧 `cv2.rotate(img, ROTATE_180)`
  ——摄像头是倒装的。`cap.read()` 成功后立刻记 `t_grab = time.time()`，这是所有耗时的起算点。
- **窗口**：OpenCV Qt 后端的全屏属性失灵，所以先 namedWindow+resize+显示一帧空图让窗口真正映射，
  再用 `win_fullscreen.make_fullscreen()`（EWMH 消息，与后端无关）真全屏。
  屏幕分辨率 `xrandr --current` 读取，失败兜底 1920×1080。
- **画面比例**：`bw = (H*SW − W*SH) // (2*SH)`，为正则左右补黑边到屏幕比例，画面不变形。

### 1.2 CyberHand 串口协议

串口 `/dev/ttyACM0`，1000000 8N1。舵机 ID 与位置方向（位置域 1~1024，帧内存 值−1）：

| ID | 关节 | 伸直/张开位 | 弯曲/收拢位 | 备注 |
|---|---|---|---|---|
| 1 | 小指 | 360 | 680 | |
| 2 | 无名指 | 710 | 410 | **方向反向** |
| 3 | 中指 | 360 | 680 | |
| 4 | 食指 | 710 | 420 | **方向反向** |
| 5 | 拇指弯 | 800 | 550 | **方向反向** |
| 6 | 拇指根(旋转) | 850=张开 | 600=收拢 | 跟随拇指张开度 |

- **同步写**（`sync_write_frame`，广播无应答）：
  `FF FF FE LEN 83 2A 02 (ID,位置高,位置低)×6 校验和`。
  `LEN = 3 + 3×舵机数 + 1`；校验和 = `~sum(FF后所有字节) & 0xFF`。一次帧驱动全部 6 路。
- **读位置**（`read_position_cmd`/`parse_position`）：
  发 `FF FF ID 04 02 38 02 校验`，应答 `FF FF ID 04 00 高 低 校验`，位置 = `(高<<8|低) + 1`。

### 1.3 CyberHand 类：安全控制核心

```
__init__(port)
  ├─ 打开串口
  ├─ _read_all(): 逐路读真实位置(reset输入缓冲→发读指令→等8字节→解析, 0.1s超时/异常→静默用POSE_INIT兜底)
  └─ cur = 真实位置, tgt = cur        # 上电瞬间绝不动作
set_target(pos): 目标先经 SAFE_RANGE 硬钳位再存     # 只改tgt, 不发串口
tick():      cur 朝 tgt 限速逼近一步, 有变化才发同步写帧
move_to_init(): 限速平滑回初始位(退出时调用, 2s)
```

`tick()` 的限速步进（两文件同款）：

```python
d = tgt[sid] - cur[sid]
if abs(d) <= DEADBAND:  continue        # 差3个单位以内不发帧, 减总线流量
step = d if abs(d) < MAX_STEP else (MAX_STEP if d>0 else -MAX_STEP)
cur[sid] += step                        # 每帧每路最多走 MAX_STEP
```

**安全四件套**（文件头注释同款）：
1. `SAFE_RANGE` 每路硬性安全区间，超范围强制截断；
2. `MAX_STEP` 每帧每路限速，杜绝暴力跳转（64 @ 25Hz = 1600 单位/秒，全行程约 0.2s）；
3. 启动先读真实位置再动手，退出 `move_to_init` 限速复位；
4. 丢手/无手势停发新指令，但 `tick` 会把已在途的目标走完。

`tick()` 里还有两处细节：计时武装只在**第一次实发**消费（一次性，用后 `t_src/t_det = None`，
下次 set_target 再武装——跟随模式追动不重复计时）；发完清 `ser.in_waiting` 杂散字节防缓冲膨胀。

### 1.4 延迟指标：抓图->识别 / 识别->发送

两文件的 `[status]` 输出完全同格式（用户要求兼容一致）：

```
[status] 28.5 fps | 抓图->识别 11ms | 识别->发送 6ms
```

取样机制（**同帧同源**）：

1. `t_grab`：`cap.read()` 之后（抓图完成）。
2. `detect()` 返回后记 `t_det_end`，`dec = t_det_end − t_grab` 进入 `dec_lat`（EMA 0.7旧/0.3新）。
   **这一项每帧都取样**。
3. 决策命中时（跟随=每次 set_target；姿势=每次采纳）武装 `hand.t_src = t_grab`、
   `hand.t_det = t_det_end`——把**同一帧**的两个时刻带给控制器。
4. `tick()` 首次实发写串口时：`lat = 实发 − t_src`（抓图→发送）、
   `lat_gap = 实发 − t_det`（识别结束→发送），各自 EMA 后存 `hand.lat` / `hand.lat_gap`，
   然后武装清除（一次性）。

因此恒有：

```
抓图->识别 + 识别->发送 = 抓图->发送      （同一帧相加）
识别->发送 ≥ 0                          （同一帧的先后时刻）
识别->发送 ≈ 等25Hz发送窗口(0~40ms) + 写串口；采纳帧因 next_send=0 同帧首发，所以偏小
```

> 历史教训：旧版"抓图->发送"只在采纳帧取样（多为快捷径快帧），而"抓图->识别"每帧取样
> （混着 3 探针慢帧），两个均值来自不同事件集，出现"发送 < 识别"的假数据。现版已同帧化修复。

- `--ms` = 尚无样本（首次识别前 / 首次实发前）。
- 干跑（不接串口）只有第一项 `fps | 抓图->识别`。
- `hand.lat`（抓图→发送）另外显示在屏幕左上角黄字里。

### 1.5 屏上 UI 与状态机

`STATE ∈ {idle, running, paused}`：idle 只预览不推理（省 NPU）；paused 不抓图，定格最后一帧；
底部按钮条 START/PAUSE(EXIT/RESUME)，命中区比画的宽（Qt 底部状态栏吃坐标偏移）。
pose 版点击有 0.3s 去重（`_last_click`，触摸屏一次点击偶发投递两次事件）；原件没有。
两文件都支持 `q` 键退出。

**已知差异**：pose 版装了 `_on_sigint` 信号标志（^C 落在 NPU 推理里会被 rknnlite 吞掉，
改置 QUIT 标志保证一次按就干净退出）；**原件没有**，所以原件在推理中按 ^C 常常要按第二次
（日志可见 `E Catch exception ... KeyboardInterrupt`）。修它需再改原件，待用户授权。

### 1.6 主循环骨架（伪代码，两文件同构）

```
while True:
    [pose特有] (重新)开局: 清 ema/geo_streak/last_g（判断在前、prev_state 赋值在后）
    paused? → 用 last_img 定格显示, 不抓图
    cap.read → t_grab → rotate180
    running?
        detect(img) → t_det_end, dec_lat
        跟随: 有手 → 每帧 retarget → hand.set_target
        姿势: 有手 → probs → 防抖 → 采纳才 set_target
        画骨架(CONNS 21条线+21个点)
    到达25Hz节拍(time.time() ≥ next_send)? → hand.tick(); next_send = now + 1/25
    fps统计(EMA) ; 每5s打一行 [status]
    衬黑边 → 画按钮/文字 → imshow → last_img 存副本
    q键 或 QUIT → break
finally:
    hand.move_to_init() ; 释放摄像头/窗口
```

（原件里 `prev_state = STATE` 是遗留变量——跟随不需要重启清零，赋值后没有条件用它。）

---

## 2. `hand_control_npu.py` —— 连续跟随

### 2.1 原理：关节弯曲角 → 舵机位置

**四根手指**（食/中/无名/小）：取 MCP→PIP→TIP 两段骨的夹角 θ：

```python
def bend255(lm, mcp, pip, tip):          # FINGERS = index(5,6,8) middle(9,10,12) ring(13,14,16) pinky(17,18,20)
    v1 = lm[pip] - lm[mcp];  v2 = lm[tip] - lm[pip]
    theta = arccos( dot(v1,v2)/(|v1||v2|) )      # 手指伸直θ≈0°, 全弯θ→180°
    return clip(theta/120, 0, 1) * 255           # 0=伸直, 255=弯过120°
```

**拇指**：关节角方案对拇指失灵（拇指弯曲以掌根旋转为主，角度不敏感），改用**距离比**，
用掌长（腕0→中指根9）做尺度基准，对手的旋转/远近鲁棒：

```python
fold   = |拇指尖4 − 小指根17| / 掌长      # 直拇指≈1.0~1.3, 包拳≈0.3~0.5
spread = |拇指尖4 − 食指根5|  / 掌长      # 张开≈0.5+, 并拢≈0.2
thumb_bend = clip((1.05 − fold)/0.65)  *255    # fold 1.05→直0, 0.40→全弯255
thumb_rot  = clip((spread − 0.25)/0.30)*255    # spread 0.25→合拢0, 0.55→张开255(舵机6)
```

**映射**：`pos = straight + (bent − straight) × (bend/255)`，straight/bent 来自 `MAP` 表
（就是第 1.2 节那张方向表的数值；注意 2/4/5/6 方向相反已在表里消化）。
`retarget_pos()` 每帧把 6 路全部算一遍，返回 `{舵机ID: 目标位置}`。

### 2.2 控制节奏与速度感

- 每帧（约 28fps）都 `set_target(新目标)`——目标一直在动。
- `tick` 以 25Hz、每路每帧最多 64 单位追赶 → **永远在追移动目标**，动作平滑但持续滞后
  （这与"姿势模式感觉更快"不矛盾：姿势是一次性冲刺走完全程，跟随是无限追赶）。
- 速度只由 `MAX_STEP × SEND_HZ` 决定：64×25 = 1600 单位/秒（2026-11-10 用户要求提速到与姿势模式同速）。

### 2.3 推理与输出

- 旧库 `HandNPU(palm_detection.rknn, hand_landmark.rknn)`：每帧 palm 检测 + 关键点两级串联
  （旧库无 ROI 追踪优化、也不跑手势段），`detect(img, ts)` 返回 21 点或 None，实测抓图→识别 16~18ms。
- `ts += 33` 只是兼容旧签名，NPU 不需要时间戳。
- 终端：每 5 秒一行 `[status]`（干跑无第二项）；屏上：fps/毫秒黄字 + `FOLLOW MY HAND`。

---

## 3. `gesture_pose_4_models.py` —— 固定手势→姿势

### 3.1 原理：识别→触发的完整链条

每帧（running 态）：

1. **4 模型推理** `HandNPU4.detect(img)` → `res["probs"]`（8 类融合概率：三探针逐类 max，
   原始探针 top1≥0.8 走捷径）＋21 点。详见《原理.md》。
2. **几何耶探针**（本脚本内，不动库）：`geo_victory(lm)` 用 `bend255` 判
   `食指<165 且 中指<165（伸/半弯容忍） 且 无名>185 且 小指>185（弯）`——
   与其余 6 手势几何互斥、视角无关。连续 2 帧命中（`geo_streak≥2`，防切换路过帧）才生效：
   `pb[6](Victory) = max(pb[6], 0.75)`，同时 `pb[5](Thumb_Up) ≤ 0.20`（耶的常见误认去向）。
   背景：用户的耶习惯性手背朝镜+倾斜+手指半弯，融合概率天然只有 0.3~0.5。
3. **EMA+滞回防抖**（⚠ 参数=识别 demo 板上验证值，**调参勿离开此区**——
   曾改 0.45/0.45 提控制速度，临界手势采纳率明显回归）：
   - `ema = 0.65*ema + 0.35*pb`（约 5 帧记忆，单帧毛刺打不垮，响应约 0.2s）
   - **采纳**：`j = argmax(ema[1:]) + 1`（None 类不参与）；`last_g ≠ g` 且
     `ema[j] ≥ ADOPT(0.40)`（Victory 用专属 `ADOPT_V=0.30`）→ 换目标
   - **释放**：`ema[当前] < RELEASE(0.18)` → 只撤标签，**姿势保持不动**
   - **丢手/None**：清 ema/geo_streak/last_g，停发新指令，在途动作走完
4. **下发**：采纳时 `hand.set_target(POSES[g])` + `next_send = 0`——**采纳帧立即首发**，
   省掉平均 ~20ms 的 25Hz 窗口等待；之后限速冲刺，全行程约 0.2s。
   手势不变就不再重发（DEADBAND 到位后 `tick` 不再发帧）。
5. 开局/START 重启时清全部防抖状态（判断在前、`prev_state` 赋值在后的顺序是修过的 bug，
   写反条件就永假）。

### 3.2 POSES 姿势表

7 个手势（None 无姿势），数值方向见 1.2 节表：

| 手势 | 1 | 2 | 3 | 4 | 5 | 6 | 含义 |
|---|---|---|---|---|---|---|---|
| Open_Palm | 360 | 710 | 360 | 710 | 800 | 850 | 五指全伸+拇指张开（=POSE_INIT） |
| Closed_Fist | 680 | 410 | 680 | 420 | 550 | 600 | 全握拳+拇指收拢 |
| Pointing_Up | 680 | 410 | 680 | 710 | 700 | 600 | 只伸食指 |
| Victory | 680 | 410 | 360 | 710 | 700 | 600 | 食指+中指 |
| ILoveYou | 360 | 410 | 680 | 710 | 800 | 850 | 拇指+食指+小指 |
| Thumb_Up | 500 | 560 | 500 | 560 | 800 | 850 | **近似**：半握+拇指伸直张开 |
| Thumb_Down | 360 | 710 | 360 | 710 | 550 | 600 | **近似**：四指伸直+拇指弯下收拢 |

⚠ 硬件没有腕/前臂旋转舵机，Thumb_Up/Down 只能姿势近似（无法表现朝向），其余 5 个是标准姿势。
启动时有 `missing` 守卫：`GESTURES` 里的手势缺了映射直接报错退出。

### 3.3 推理与输出

- 新库 `HandNPU4`：追踪帧 3 次推理（跳过 palm），捷径帧抓图→识别 10~11ms，
  3 探针全跑 27~28ms（EMA 显示的是混合均值）。
- 终端：每 5 秒一行 `[status]`，格式与原件完全一致。
- 屏上：当前手势大字居中显示；idle 提示 `PRESS START TO PLAY`，running 无手势时 `SHOW A GESTURE`。

---

## 4. 两文件输出对照（速查）

| 场景 | 输出 |
|---|---|
| 两文件 × 控制模式 | `[status] {fps} fps \| 抓图->识别 {X}ms \| 识别->发送 {Y}ms`（每 5s 一行） |
| 两文件 × 干跑 | `[status] {fps} fps \| 抓图->识别 {X}ms` |
| 读数 | X≈推理耗时（跟随 16~18ms；姿势 10~11 快帧 / 27~28 慢帧）；Y=等发送窗口+写串口，X+Y=抓图→实发 |
| `--ms` | 尚无样本（首次识别/实发前），不是 0 |

## 5. 使用注意事项

1. **板上必须用 venv**：`/home/firefly/hand_gesture/mediapipe_env/bin/python`
   （系统 python3/python 没有 cv2；`python` 不存在）。
2. 先干跑验证识别，再接 `/dev/ttyACM0` 真控制；控制异常会打印串口错误并停。
3. **通电时严禁手扳关节**；退出程序会自动限速回初始位（`move_to_init`）。
4. 调速度改 `MAX_STEP`（32=800单位/s 温柔，64=1600单位/s 现值）；调灵敏度**不要动**
   `EMA_A/ADOPT/RELEASE/ADOPT_V`（已离开验证区一次并回归）。
5. 原件 ^C 需按两次（无信号处理）；pose 版按一次即退。
6. 摄像头倒装已由 `rotate(180)` 消化；换摄像头装向要同步改这行。
