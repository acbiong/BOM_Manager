#!/bin/sh
# 无需Git提交的源码目录轮询打包器：./tools/watch_source.sh [秒数]
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd); cd "$ROOT"
interval=${1:-3}; last=''
while :; do
 hash=$(find src -type f -name '*.py' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
 if [ "$hash" != "$last" ]; then
  if [ -n "$last" ]; then
   echo '[watch-package] 检测到源代码变化，开始生成AppImage'
   APPIMAGE_EXTRACT_AND_RUN=1 APPIMAGE_RUNTIME="${APPIMAGE_RUNTIME:-$HOME/.local/bin/runtime-x86_64}" PATH="$HOME/.local/bin:$PATH" tools/build_appimage.sh || echo '[watch-package] 打包失败，等待下次变化'
  fi
  last=$hash
 fi
 sleep "$interval"
done
