# VGA

　　DP1 + DP 转 VGA 桥: dp-lane-mux 走线与 HPD 配置。参考板 itx-3588j / aio-3588q。

## 1. 硬件连接

```
VOP VP2 ====> DP1 控制器 (dp@fde60000)
              ====> usbdp_phy1 (lane2/3 给 DP, lane0/1 保持 USB3)
              ====> IT6516 DP转VGA桥芯片 (硬件直连,无需设备树节点)
              ====> VGA 连接器

  HPD      ====> GPIO1_A4 (VGA_HPDIN_L, 桥芯片 HPD 输出,高有效)
  lane 复用: usbdp_phy1 4 lane 中 DP 占 2 lane (lane2/3),
            USB3.0 继续使用 lane0/1 (2 lane DP 最高 4K@30Hz, VGA 场景足够)
```

　　注意:
- RK3588 的 DP 控制器必须依赖 usbdp_phy (无独立 DP PHY),
  VGA 输出本质是 DP1 + 外置 DP转VGA 桥芯片
- 桥芯片 (IT6516) 是硬件直连, 设备树无需桥芯片节点, 只有 HPD 引脚

## 2. 设备树配置

　　参考板: itx-3588j / aio-3588q (宏 FF_VGA)

```
/ {
	/* VGA 音频 (DP1 音频经 spdif_tx5 输出, 不需要音频可省略) */
	dp1_sound: dp1-sound {
		status = "okay";
		compatible = "rockchip,hdmi";
		rockchip,card-name = "rockchip-dp1";
		rockchip,mclk-fs = <512>;
		rockchip,cpu = <&spdif_tx5>;
		rockchip,codec = <&dp1 1>;
		rockchip,jack-det;
	};
};

/* VOP VP2 -> DP1 数据通路 */
&dp1_in_vp2 {
	status = "okay";
};

&dp1 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&dp1_hpd>;
	hpd-gpios = <&gpio1 RK_PA4 GPIO_ACTIVE_HIGH>;  // VGA_HPDIN_L
};

/* 显示路由 (aio-3588q 为 okay; itx-3588j 此处为 disabled,
 * 按实际显示链路配置) */
&route_dp1 {
	status = "okay";
	connect = <&vp2_out_dp1>;
};

/* lane2/3 给 DP1(IT6516桥), lane0/1 保持 USB3 */
&usbdp_phy1 {
	status = "okay";
	rockchip,dp-lane-mux = <2 3>;
};

/* DP1 音频 spdif (不需要音频可省略) */
&spdif_tx5 {
	status = "okay";
};

&pinctrl {
	dp {
		dp1_hpd: dp1-hpd {
			rockchip,pins = <1 RK_PA4 RK_FUNC_GPIO &pcfg_pull_none>;
		};
	};
};
```

　　注意:
- hpd-gpios 是独立口的关键属性 (Type-C altmode 场景不需要 HPD,
  由 Type-C 控制器负责热插拔检测)
- rockchip,dp-lane-mux = <2 3> 表示 phy 的 lane2/3 映射给 DP;
  若不用 USB3 想要 4 lane DP, 可不配此属性 (4 lane DP 带宽翻倍)
- itx-3588j 的 route_dp1 是 disabled 而 aio-3588q 是 okay,
  与各自 VOP 显示路由规划有关, 按板上其他显示接口 (HDMI/MIPI) 统一规划

## 3. 与 Type-C DP altmode 的区别

　　独立 DP/VGA 口不需要 Type-C 相关配置:

| 配置项 | 独立口 (本模块) | Type-C DP altmode |
|---|---|---|
| hpd-gpios | 需要 (GPIO1_A4) | 不需要 |
| orientation-switch | 不需要 | 需要 (usbdp_phy) |
| mode-switch (usbdp_phy) | 不需要 | 需要 |
| svid = <0xff01> | 不需要 | 需要 |
| sbu1/2-dc-gpios | 不需要 | 需要 |
| usbc 节点 altmodes | 不需要 | 需要 |

　　(Type-C DP altmode 的完整配置见 typec 模块)

## 4. 验证测试

```
# 查看 DRM 设备
ls /sys/class/drm/
# 应看到 card?-DP-1 (dp1) 连接器

# 接 VGA 显示器后查看状态
cat /sys/class/drm/card*-DP-1/status
# connected

# 读取 EDID
cat /sys/class/drm/card*-DP-1/edid | edid-decode
# 应解析出显示器分辨率信息

# 强制点亮测试
modetest -M rockchip -c        # 列出连接器
modetest -M rockchip -s <conn_id>:<mode_id>   # 指定模式点亮

# 常见问题:
# 1. status 一直是 disconnected: 检查 hpd-gpios 极性和引脚
# 2. 黑屏: 检查 dp-lane-mux 与硬件 lane 走线是否一致
# 3. 无音频: dp1_sound/spdif_tx5 未使能,或 alsa 中未选对声卡
```
