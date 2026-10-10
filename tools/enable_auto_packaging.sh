#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
git config core.hooksPath .githooks
echo '已启用 Git 提交后按平台打包（Windows EXE / Linux AppImage），无常驻监控。'
echo 'AI 编程完成后请执行：tools/finish_ai_change.sh --message-file .tmp/change_message.txt'
