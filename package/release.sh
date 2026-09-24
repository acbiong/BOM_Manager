#!/bin/sh
# 初版发布自动化：修改/修复完成后执行本脚本生成最新独立文件。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
kind=${1:-patch}
python3 tools_bump_version.py "$kind"
python3 tests/audit_requirements.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q src
version=$(cat VERSION)
stamp=$(date +%Y%m%d_%H%M%S)
name="BOM管理系统_${version}_${stamp}"
rm -rf build dist
python3 -m PyInstaller --noconfirm --clean --onefile --windowed --add-data "VERSION:." --name "$name" src/main.py
bin="dist/$name"
package/audit_portability.sh "$bin"
cp "$bin" "package/$name"
sha256sum "package/$name" > "package/$name.sha256"
printf '发布完成：package/%s\n' "$name"
printf '校验文件：package/%s.sha256\n' "$name"
