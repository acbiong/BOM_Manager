#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
git config core.hooksPath .githooks
echo '已启用 Git 提交后自动 AppImage 打包。'
echo 'AI 编程完成后请执行：tools/finish_ai_change.sh'
