#!/bin/bash
# build.sh — hand-gesture-demo 打包脚本
# 原则: pkgbuild/ 里有什么就打什么, 不做任何剔除/过滤。
#   - 增删文件直接在 pkgbuild/home/firefly/hand_gesture/ 里手动操作
#   - 从板子拉新代码进来(自己挑, 同样不剔除):
#       rsync -a firefly@板子IP:/home/firefly/hand_gesture/某目录 pkgbuild/home/firefly/hand_gesture/
#   - ./build.sh sync: 用本地 hand_gesture/ 整目录镜像覆盖 payload(--delete,
#     以 hand_gesture/ 为准, 里面有什么同步什么——含 mediapipe_env 等大文件,
#     不要的内容先在 hand_gesture/ 里删掉再 sync)
set -e
cd "$(dirname "$0")"

if [ "$1" = "sync" ]; then
    rsync -a --delete hand_gesture/ pkgbuild/home/firefly/hand_gesture/
    echo ">>> 已按 hand_gesture/ 镜像 payload (未做任何剔除)"
fi

# 维护脚本权限 + 语法检查 (没执行权限会直接装不上)
chmod 755 pkgbuild/DEBIAN/postinst pkgbuild/DEBIAN/prerm pkgbuild/DEBIAN/postrm 2>/dev/null || true
for s in postinst prerm postrm; do
    [ -f "pkgbuild/DEBIAN/$s" ] && sh -n "pkgbuild/DEBIAN/$s"
done

# Installed-Size 按 payload 实际大小刷新
IS=$(du -sk pkgbuild | cut -f1)
sed -i "s/^Installed-Size: .*/Installed-Size: $IS/" pkgbuild/DEBIAN/control

# 输出文件名自动取自 control: <包名>_<版本>_<架构>.deb (改版本号就改 control)
NAME=$(awk '/^Package:/{print $2; exit}'      pkgbuild/DEBIAN/control)
VER=$(awk '/^Version:/{print $2; exit}'       pkgbuild/DEBIAN/control)
ARCH=$(awk '/^Architecture:/{print $2; exit}' pkgbuild/DEBIAN/control)
OUT="${NAME}_${VER}_${ARCH}.deb"

dpkg-deb --build --root-owner-group pkgbuild "$OUT"
echo "---"
echo "完成: $OUT ($(du -h "$OUT" | cut -f1)) | payload $(du -sh pkgbuild | cut -f1) | 文件数 $(find pkgbuild -type f | wc -l)"
