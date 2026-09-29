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
ver=$(cat VERSION); stamp=$(date +%Y%m%d_%H%M%S); name="BOM_Manager_${ver}_${stamp}"
rm -rf "$BUILD_DIR" "$DIST_DIR" "$SPEC_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$SPEC_DIR"
python3 -m PyInstaller --noconfirm --clean --onefile --windowed \
 --workpath "$BUILD_DIR" --distpath "$DIST_DIR" --specpath "$SPEC_DIR" \
 --add-data "$ROOT/VERSION:." --name "$name" src/main.py
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp "$DIST_DIR/$name" "$APPDIR/usr/bin/BOM管理系统"
python3 - "$APPDIR" <<'PYICON'
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import sys
root=Path(sys.argv[1])
im=Image.new('RGB',(256,256),(29,91,160))
draw=ImageDraw.Draw(im)
draw.rounded_rectangle((16,16,240,240),radius=28,fill=(35,104,180),outline=(180,220,255),width=5)
try: font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',54)
except OSError: font=ImageFont.load_default()
text='BOM'; box=draw.textbbox((0,0),text,font=font); x=(256-(box[2]-box[0]))//2; y=(256-(box[3]-box[1]))//2-8
draw.text((x,y),text,font=font,fill=(255,255,255))
# RGB PNG and ASCII basename are accepted by Deepin and AppImage icon lookup.
for target in (root/'bom_manager.png',root/'bom管理系统.png',root/'usr/share/icons/hicolor/256x256/apps/bom_manager.png'):
 target.parent.mkdir(parents=True,exist_ok=True); im.save(target,format='PNG',optimize=True)
PYICON
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Deepin文件管理器可能向子进程传递dxcb等宿主专用Qt平台值；冻结包只携带xcb插件。
# 有显示服务时明确选择兼容的xcb，避免双击启动后Qt平台插件初始化失败。
if [ -n "${DISPLAY:-}" ]; then export QT_QPA_PLATFORM=xcb; fi
exec "$HERE/usr/bin/BOM管理系统" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/bom管理系统.desktop" <<EOF
[Desktop Entry]
Name=BOM管理系统
Exec=BOM管理系统
TryExec=BOM管理系统
Icon=bom_manager
Type=Application
Categories=Office;
Terminal=false
StartupNotify=true
X-AppImage-Integrate=false
EOF
cat > "$APPDIR/usr/share/applications/bom管理系统.desktop" <<EOF
[Desktop Entry]
Name=BOM管理系统
Exec=BOM管理系统
TryExec=BOM管理系统
Icon=bom_manager
Type=Application
Categories=Office;
Terminal=false
StartupNotify=true
X-AppImage-Integrate=false
EOF
if command -v appimagetool >/dev/null 2>&1; then
 # Deepin文件管理器启动时不会注入 APPIMAGE_EXTRACT_AND_RUN；在没有FUSE的机器上，
 # 原生runtime会直接退出。复制runtime并将该分支设为默认，保证双击也能自动解压运行。
 runtime_src="${APPIMAGE_RUNTIME:-$HOME/.local/bin/runtime-x86_64}"
 runtime_default="$TMP_DIR/runtime-extract-x86_64"
 cp "$runtime_src" "$runtime_default"
 python3 - "$runtime_default" <<'PYRUNTIME'
from pathlib import Path
import sys
p=Path(sys.argv[1]); b=bytearray(p.read_bytes())
# type2-runtime: test getenv("APPIMAGE_EXTRACT_AND_RUN") then JNE extract.
needle=bytes.fromhex('0f 85 53 04 00 00')
pos=b.find(needle)
if pos < 0:
    raise SystemExit('无法定位 AppImage runtime 的提取分支，拒绝生成可能无法双击运行的包')
b[pos+1]=0x84  # 缺少环境变量时也跳转到 extract-and-run
p.write_bytes(b)
PYRUNTIME
 chmod +x "$runtime_default"
 # appimagetool自身需要原始runtime解析参数；先正常生成，再在同尺寸runtime中替换分支。
 APPIMAGE_EXTRACT_AND_RUN=1 appimagetool --runtime-file "$runtime_src" "$APPDIR" "package/${name}.AppImage"
 python3 - "package/${name}.AppImage" "$runtime_default" <<'PYAPPIMAGE'
from pathlib import Path
import sys
out=Path(sys.argv[1]); runtime=Path(sys.argv[2]); image=bytearray(out.read_bytes()); patched=runtime.read_bytes()
needle=bytes.fromhex('0f 85 53 04 00 00'); pos=image.find(needle)
if pos < 0: raise SystemExit('生成的AppImage中未找到runtime提取分支')
image[pos+1]=0x84
out.write_bytes(image)
PYAPPIMAGE
 chmod +x "package/${name}.AppImage"
 sha256sum "package/${name}.AppImage" > "package/${name}.AppImage.sha256"
 echo "AppImage: package/${name}.AppImage"
else
 echo "未找到 appimagetool，已生成 $APPDIR；安装 appimagetool 后重新执行本脚本。" >&2
 exit 2
fi
