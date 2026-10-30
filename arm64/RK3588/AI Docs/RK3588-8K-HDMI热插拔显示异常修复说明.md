# RK3588 8K HDMI 热插拔显示异常修复说明

> 适用：rk3588_6.12.69_sdk / kernel 6.12（`kernel/` 与 `kernel-6.12/` 为硬链接同一份文件，改一处即可）
> 现象：HDMI0 切换到 8K（7680x4320p60）输出后，热插拔出现显示异常；拔出后立即插回黑屏；连续多次插拔后不再显示。

## 一、问题现象

1. 8K 模式下热插拔几次后显示异常 / 黑屏（Firefly 各 RK3588 板卡普遍存在）；
2. 拔出后等 1~2 秒再插正常，**立即插回则黑屏**；
3. 连续多次插拔后彻底不显示，只能重启恢复。

## 二、根因

### 根因 1：设备树把 HDMI0 绑到了两个 VP（导致热插拔后显示异常）

`rk3588-firefly-common.dtsi` 中同时打开了 `hdmi0_in_vp0` 和 `hdmi0_in_vp1`。
而 RK3588 的 8K 输出使用 VP0+VP1 **splice 模式**，由 VOP2 驱动内部完成（vp0 的
`splice_vp_id = 1`），**设备树端 HDMI0 只能绑 VP0**。vp1 端点打开后会被注册为
第二个活动 CRTC，热插拔重绑定时 8K 模式可能落到 VP1（上限 4096x2304@600MHz）
或被 `vop2_crtc_mode_valid()` 拒绝，导致显示异常。

### 根因 2：快速插回后无人重新发起 FRL 链路训练（导致立即插回黑屏）

- 8K 是 FRL（HDMI 2.1）模式，链路训练状态机 `flt_work` **只在
  `dw_hdmi_qp_bridge_atomic_enable()` 里被 queue**，即依赖桌面做完整 modeset；
- 拔出后 `flt_work` 因 HPD 低电平自行退出（LTSL），sink 断电后 FRL 链路失效；
- `dw_hdmi_qp_handle_hpd()` 对 mtmdsclock > 600MHz 直接 return（HDMI 2.1
  不支持 keep-output），内核不做任何恢复；
- **立即插回**时，桌面环境来不及消化 disconnect uevent，插回后 connector
  状态仍是 connected，桌面不做 modeset → 没有任何代码路径重跑 FRL 训练
  → 永久黑屏（HPD 稳定高电平，再无事件）。
  等 1~2 秒再插，桌面来得及处理 disconnect，插回后触发完整 modeset 所以正常。

## 三、修改内容

### 1. `arch/arm64/boot/dts/rockchip/rk3588-firefly-common.dtsi`

删除 8K 相关的 `&hdmi0_in_vp1 { status = "okay"; }` 块（8K 只绑 VP0）：

```diff
-// HDMI0 8K display
-#if defined(FF_HDMI0) && !defined(FF_HDMI1)
-&hdmi0_in_vp1 {
-	status = "okay";
-};
-#endif
```

### 2. `drivers/gpu/drm/bridge/synopsys/dw-hdmi-qp.c`

`dw_hdmi_qp_handle_hpd()` 的 HDMI 2.1（>600MHz）分支中，插入事件到来时若管线
仍在运行（`enable && !disabled && dclk_en` 且 FRL 模式），由内核直接重新 queue
`flt_work` 重训链路，不再被动等待永远不会到来的 modeset：

```c
if (hdmi->hdmi_data.video_mode.mtmdsclock > 600000000) {
	/*
	 * sink 在拔出期间断电，插回后必须重训 FRL 链路。快速插回时桌面
	 * 看到的 connector 状态一直是 connected，不会触发 modeset，无人
	 * 重训链路导致黑屏，故在此直接重新发起训练。
	 */
	if (enable && !hdmi->disabled && hdmi->dclk_en) {
		... get_link_cfg ...
		if (link_cfg && link_cfg->frl_mode)
			queue_work(hdmi->workqueue, &hdmi->flt_work);
	}
	goto out;
}
```

### 3. `drivers/gpu/drm/bridge/synopsys/dw-hdmi-qp.c` —— 分辨率自适应补选 8K 的刷新率修正

#### 背景：分辨率自适应补丁

8K 电视 EDID 的 preferred timing 通常是兼容性的 4K，桌面（GNOME/mutter，无用户
`monitors.xml` 时）默认按 preferred 点亮 4K，永远不会自动上 8K。为此在
`dw_hdmi_connector_get_modes()` 末尾增加 `dw_hdmi_mark_highest_mode_preferred()`：
把 `DRM_MODE_TYPE_PREFERRED` 移到**像素数最多**的模式上（像素时钟作决胜），
使"自动"分辨率即 sink 广播的最高档。仅影响默认选择；用户手动选过分辨率后
mutter 的 monitors.xml 优先，本逻辑不再起作用。

#### 问题：选最高档时 8K 停在 50Hz 而不是 60Hz

CTA-861 的 50/60Hz 同分辨率模式**像素时钟完全相同**（50Hz 是靠加宽消隐区把
刷新率拉低的，不降时钟）：

| VIC | 模式 | 像素时钟 |
|---|---|---|
| 198 | 7680x4320@50 | 2376 MHz |
| 199 | 7680x4320@60 | 2376 MHz |

原决胜条件 `clock > best->clock` 在时钟持平时不成立，`best` 保留先遍历到的
模式；`probed_modes` 按 EDID/VIC 升序排列，VIC 198（50Hz）在前，于是 50Hz 获胜。
4K50/4K60（同为 594 MHz）同理。

#### 修复

决胜层级改为：**像素数 → 像素时钟 → 刷新率**（`drm_mode_vrefresh()` 用
clock/htotal/vtotal 现算，时同时也按实际刷新率分出高下）：

```c
list_for_each_entry(mode, &connector->probed_modes, head) {
	if (!best ||
	    mode->hdisplay * mode->vdisplay > best->hdisplay * best->vdisplay ||
	    (mode->hdisplay * mode->vdisplay == best->hdisplay * best->vdisplay &&
	     (mode->clock > best->clock ||
	      (mode->clock == best->clock &&
	       drm_mode_vrefresh(mode) > drm_mode_vrefresh(best)))))
		best = mode;
}
```

验证提示：

- 桌面若已记住该显示器配置（`~/.config/monitors.xml`），手动选择会优先生效，
  需删除该文件后重启验证"自动选最高"；
- 可开 dynamic debug 查看 `mark preferred: 7680x4320@2376` 确认命中的模式。

## 四、验证结果

- 8K 模式热插拔：正常；
- 拔出后立即插回：正常显示；
- 连续多次快速插拔：正常显示（原修复后仍有小概率黑屏，后经多次插拔验证已稳定）；
- 分辨率自适应点亮 8K：通过（但有 50Hz 问题，见三-3）；
- 自适应刷新率 50Hz→60Hz 修正：待烧录验证。

## 五、相关日志速查

| 日志 | 含义 |
|---|---|
| `final tmdsclk = -1918967296` | 2376MHz 溢出 int 的显示值，无害 |
| `stop poll flt_update` | 拔出，flt_work 退出训练 |
| `Training finish, go to ltsp` + `flt success` | 训练成功，正常亮屏标志 |
| `invalid hdmi params for phy configure` | disable 时 PHY 无效参数，噪声日志，不影响功能 |
| `POST_BUF_EMPTY irq err at vp0` | disable 过程的伴生中断风暴，随本次修复一并消失/减少 |

## 六、经验总结

- RK3588 8K 输出：设备树 HDMI0 只绑 VP0，VP0/VP1 splice 由驱动内部处理；
- HDMI 2.1（FRL）模式热插拔的恢复**不能依赖桌面 modeset**，内核需在 HPD
  插入事件中主动重发链路训练；
- CTA-861 的同分辨率 50/60Hz（甚至 100/120Hz 档内）像素时钟相同，**按时钟
  挑"最高档"模式时必须再比刷新率**，否则 EDID 里排前的低刷新率（50Hz）获胜。
