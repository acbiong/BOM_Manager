#!/bin/sh
# 构建AppImage：自动测试、编译、生成AppDir和AppImage。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd); cd "$ROOT"
TMP_DIR="$ROOT/.tmp"
BUILD_DIR="$TMP_DIR/build"
DIST_DIR="$TMP_DIR/dist"
SPEC_DIR="$TMP_DIR/spec"
APPDIR="$TMP_DIR/AppDir"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$SPEC_DIR"
tools/run_tests.sh
rm -rf "$APPDIR"
ver=$(cat VERSION); stamp=$(date +%Y%m%d_%H%M%S); name="BOM管理系统_${ver}_${stamp}"
rm -rf "$BUILD_DIR" "$DIST_DIR" "$SPEC_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$SPEC_DIR"
python3 -m PyInstaller --noconfirm --clean --onefile --windowed \
 --workpath "$BUILD_DIR" --distpath "$DIST_DIR" --specpath "$SPEC_DIR" \
 --add-data "$ROOT/VERSION:." --name "$name" src/main.py
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications"
cp "$DIST_DIR/$name" "$APPDIR/usr/bin/BOM管理系统"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$HERE/usr/bin/BOM管理系统" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/bom管理系统.desktop" <<EOF
[Desktop Entry]
Name=BOM管理系统
Exec=BOM管理系统
TryExec=BOM管理系统
Icon=bom管理系统
Type=Application
Categories=Office;
Terminal=false
StartupNotify=true
X-AppImage-Integrate=false
EOF
if [ ! -f "$APPDIR/bom管理系统.png" ]; then
  python3 - <<PYICON
from PIL import Image,ImageDraw
im=Image.new('RGBA',(256,256),(35,104,180,255)); ImageDraw.Draw(im).text((64,100),'BOM',fill='white'); im.save('$APPDIR/bom管理系统.png')
PYICON
fi
cat > "$APPDIR/usr/share/applications/bom管理系统.desktop" <<EOF
[Desktop Entry]
Name=BOM管理系统
Exec=BOM管理系统
TryExec=BOM管理系统
Icon=bom管理系统
Type=Application
Categories=Office;
Terminal=false
StartupNotify=true
X-AppImage-Integrate=false
EOF
if command -v appimagetool >/dev/null 2>&1; then
 APPIMAGE_EXTRACT_AND_RUN=1 appimagetool --runtime-file "${APPIMAGE_RUNTIME:-$HOME/.local/bin/runtime-x86_64}" "$APPDIR" "package/${name}.AppImage"
 sha256sum "package/${name}.AppImage" > "package/${name}.AppImage.sha256"
 echo "AppImage: package/${name}.AppImage"
else
 echo "未找到 appimagetool，已生成 $APPDIR；安装 appimagetool 后重新执行本脚本。" >&2
 exit 2
fi
