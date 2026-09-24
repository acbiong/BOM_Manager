#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m PyInstaller --noconfirm --onefile --windowed --add-data "VERSION:." --name "BOM管理系统_$(cat VERSION)_$(date +%Y%m%d_%H%M%S)" src/main.py
