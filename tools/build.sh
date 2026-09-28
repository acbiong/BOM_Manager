#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
tools/run_tests.sh
TMP_DIR="$PWD/.tmp"
mkdir -p "$TMP_DIR/build" "$TMP_DIR/dist" "$TMP_DIR/spec"
name="BOM管理系统_$(cat VERSION)_$(date +%Y%m%d_%H%M%S)"
python3 -m PyInstaller --noconfirm --clean --onefile --windowed \
  --workpath "$TMP_DIR/build" --distpath "$TMP_DIR/dist" --specpath "$TMP_DIR/spec" \
  --add-data "$PWD/VERSION:." --name "$name" src/main.py
printf '独立文件：%s\n' "$TMP_DIR/dist/$name"
