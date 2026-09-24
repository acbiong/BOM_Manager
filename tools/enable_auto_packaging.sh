#!/bin/sh
set -eu
git config core.hooksPath .githooks
echo '已启用 Git 提交后自动 AppImage 打包。'
