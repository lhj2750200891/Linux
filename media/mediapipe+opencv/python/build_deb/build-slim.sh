#!/bin/bash
# build-slim.sh — 生成 oem 分区(128M)能装下的瘦身版 deb
#
# 背景: oem 分区 128MiB,里面已有 rk1828-policy 的驱动/温控 deb(~33MiB),
# hand-gesture-demo 原包 96MiB 放不下。本脚本不修改 pkgbuild/ 原目录,
# 在临时副本上做三层瘦身后用 xz -9 打包:
#   1. strip 便携版 CPython 的调试段(libpython3.10.so.1.0 40M -> ~5M)
#   2. 删应用不用的运行库: tcl/tk 全家、tkinter、idlelib、_test* 扩展
#   3. wheel 重打包为 zip store 模式(deflate 的成员 xz 压不动,store 后
#      xz 直接压裸 ELF: opencv 49M wheel -> ~15M、numpy 14M -> ~5M;
#      成员字节与 RECORD 哈希不变,pip 照常安装)
#
# 用法: ./build-slim.sh   (依赖 aarch64-linux-gnu-strip / unzip / python3)
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v aarch64-linux-gnu-strip >/dev/null; then
    echo "E: 需要 aarch64-linux-gnu-strip (binutils-aarch64-linux-gnu)" >&2
    exit 1
fi

STAGE=$(mktemp -d /tmp/hand-gesture-slim.XXXXXX)
trap 'rm -rf "$STAGE"' EXIT
cp -a pkgbuild "$STAGE/pkgbuild"
CP="$STAGE/pkgbuild/opt/hand-gesture-demo/cpython"
WHEELS="$CP/../wheels"

echo ">>> [1/4] strip cpython 调试段"
aarch64-linux-gnu-strip --strip-unneeded \
    "$CP/lib/libpython3.10.so.1.0" "$CP/bin/python3.10"

echo ">>> [2/4] 删除应用未使用的 tcl/tk、tkinter、idlelib、_test* 扩展"
rm -rf "$CP"/lib/{tcl8.6,tk8.6,Tix8.4.3,itcl4.2.2,tcl8,thread2.8.7,pkgconfig}
rm -rf "$CP"/lib/python3.10/{tkinter,idlelib}
rm -f  "$CP"/lib/python3.10/lib-dynload/_test*.so \
       "$CP"/lib/python3.10/lib-dynload/_tkinter*.so

echo ">>> [3/4] wheel 重打包为 store 模式 (zip 内容/RECORD 不变)"
python3 - "$WHEELS" <<'PYEOF'
import sys, zipfile
from pathlib import Path
for whl in sorted(Path(sys.argv[1]).glob("*.whl")):
    with zipfile.ZipFile(whl) as zin:
        names = zin.namelist()
        payload = {n: zin.read(n) for n in names}
    with zipfile.ZipFile(whl, "w", compression=zipfile.ZIP_STORED) as zout:
        for n in names:
            zout.writestr(zipfile.ZipInfo(n, date_time=(2025, 1, 1, 0, 0, 0)),
                          payload[n])
    print(f"    {whl.name}: stored")
PYEOF

echo ">>> [4/4] 按 staging 实际大小刷新 Installed-Size, xz -9 打包"
IS=$(du -sk "$STAGE/pkgbuild" | cut -f1)
sed -i "s/^Installed-Size: .*/Installed-Size: $IS/" "$STAGE/pkgbuild/DEBIAN/control"
NAME=$(awk '/^Package:/{print $2; exit}'  pkgbuild/DEBIAN/control)
VER=$(awk '/^Version:/{print $2; exit}'  pkgbuild/DEBIAN/control)
ARCH=$(awk '/^Architecture:/{print $2; exit}' pkgbuild/DEBIAN/control)
OUT="${NAME}_${VER}_${ARCH}.deb"
dpkg-deb --build -Zxz -z9 --root-owner-group "$STAGE/pkgbuild" "$OUT"

echo "---"
echo "完成: $OUT ($(du -h "$OUT" | cut -f1)) | 原始包 $(du -h "${NAME}_${VER}_${ARCH}.deb" 2>/dev/null | cut -f1) 不可比时以本输出为准"
echo "oem 装载校验: 33MiB(策略包) + 本包 应 < ~109MiB (128MiB - journal/元数据)"
