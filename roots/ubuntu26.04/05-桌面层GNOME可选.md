# 05 桌面层: GNOME (可选)

> 04 完成后系统已可用; 本章叠加图形栈。体积 +2~3G, 时间主要耗在 apt 下载。

## 1. 选型

| 方案 | 命令 | 得到什么 |
| --- | --- | --- |
| ubuntu-desktop-minimal (推荐) | `apt install -y ubuntu-desktop-minimal` | gdm + gnome-shell + wayland 全栈 + 常用应用 |
| 精简手工组 (教学向) | 见 §2 第二块代码 | 只装登录管理器+shell+终端, 看清桌面由哪几层组成 |

## 2. 安装

方案一 (一步到位):

```
apt install -y ubuntu-desktop-minimal
```

方案二 (教学向, 看清层次):

```
apt install -y gdm3 gnome-shell gnome-terminal \
               nautilus gnome-control-center
```

- 三层结构: gdm3 (登录管理器) → gnome-shell (合成器/桌面) → wayland (显示协议);
- xwayland 兼容层会自动带上, X11 应用照跑;
- 音频栈 (pipewire + wireplumber) 作为依赖自动进来 —— 生产镜像里 wpctl 那套就是它;
- `--no-install-recommends` 可砍近一半体积, 但会缺字体/驱动胶水, 调试期不建议。

## 3. 自动登录 (对齐生产镜像)

```
cat >> /etc/gdm3/custom.conf <<'EOF'

[daemon]
AutomaticLoginEnable=true
AutomaticLogin=firefly
EOF
```

生产镜像首启直接进桌面就是这一段配置; 无屏板子可以不开, 纯串口/ssh 使用。
装完 gdm 后 systemctl get-default 应已是 graphical.target (装包时自动切换)。

## 4. 与生产镜像的差异提醒

- 屏幕键盘 onboard: 26.04 官方源已无此包, 用你们板编 deb 继续
  (生产镜像 gnome-wayland 组第 6 步同款方案);
- GNOME 较 24.04 (GNOME 46) 新两代: dconf 路径/扩展白名单机制需重新核对,
  别照抄 24.04 的 gsettings 设置;
- 默认 wayland; 若屏异常, 先查 /dev/dri 与 libmali 是否装好 (04 §5),
  再查 dtb 与内核参数 —— 顺序别反。

## 5. 阶段验收 (烧板后回看)

```
echo $XDG_SESSION_TYPE          # -> wayland
systemctl status gdm3           # -> active
sudo systemctl get-default      # -> graphical.target
```
