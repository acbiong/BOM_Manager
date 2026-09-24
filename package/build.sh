#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m PyInstaller --noconfirm --onefile --windowed --name "BOM管理系统_0.0.1_$(date +%Y%m%d_%H%M%S)" src/main.py
