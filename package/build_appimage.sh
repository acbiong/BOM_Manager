#!/bin/sh
# 构建AppImage：自动测试、编译、生成AppDir和AppImage。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd); cd "$ROOT"
python3 tests/audit_requirements.py
python3 -m unittest discover -s tests -q
python3 -m compileall -q src
ver=$(cat VERSION); stamp=$(date +%Y%m%d_%H%M%S); name="BOM管理系统_${ver}_${stamp}"
rm -rf build dist AppDir
python3 -m PyInstaller --noconfirm --clean --onefile --windowed --add-data "VERSION:." --name "$name" src/main.py
mkdir -p AppDir/usr/bin AppDir/usr/share/applications
cp "dist/$name" AppDir/usr/bin/BOM管理系统
cat > AppDir/AppRun <<'EOF'
#!/bin/sh
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$HERE/usr/bin/BOM管理系统" "$@"
EOF
chmod +x AppDir/AppRun
cat > AppDir/bom管理系统.desktop <<EOF
[Desktop Entry]
Name=BOM管理系统
Exec=BOM管理系统
Icon=bom管理系统
Type=Application
Categories=Office;
EOF
cat > AppDir/usr/share/applications/bom管理系统.desktop <<EOF
[Desktop Entry]
Name=BOM管理系统
Exec=BOM管理系统
Icon=bom管理系统
Type=Application
Categories=Office;
EOF
if command -v appimagetool >/dev/null 2>&1; then
 appimagetool AppDir "package/${name}.AppImage"
 sha256sum "package/${name}.AppImage" > "package/${name}.AppImage.sha256"
 echo "AppImage: package/${name}.AppImage"
else
 echo "未找到 appimagetool，已生成 AppDir；安装 appimagetool 后重新执行本脚本。" >&2
 exit 2
fi
