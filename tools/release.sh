#!/bin/sh
# 初版发布自动化：修改/修复完成后执行本脚本生成最新独立文件。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
kind=${1:-patch}
python3 tools_bump_version.py "$kind"
tools/run_tests.sh
TMP_DIR="$ROOT/.tmp"
version=$(cat VERSION)
stamp=$(date +%Y%m%d_%H%M%S)
name="BOM管理系统_${version}_${stamp}"
BUILD_DIR="$TMP_DIR/build"; DIST_DIR="$TMP_DIR/dist"; SPEC_DIR="$TMP_DIR/spec"
rm -rf "$BUILD_DIR" "$DIST_DIR" "$SPEC_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$SPEC_DIR"
python3 -m PyInstaller --noconfirm --clean --onefile --windowed \
  --workpath "$BUILD_DIR" --distpath "$DIST_DIR" --specpath "$SPEC_DIR" \
  --add-data "$ROOT/VERSION:." --name "$name" src/main.py
bin="$DIST_DIR/$name"
tools/audit_portability.sh "$bin"
cp "$bin" "package/$name"
sha256sum "package/$name" > "package/$name.sha256"
printf '发布完成：package/%s\n' "$name"
printf '校验文件：package/%s.sha256\n' "$name"
