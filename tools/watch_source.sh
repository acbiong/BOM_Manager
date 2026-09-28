#!/bin/sh
# 监视源代码：检测到 src 变更后自动递增版本、提交 Git；post-commit 负责生成 AppImage。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd); cd "$ROOT"
interval=${1:-3}
PID_FILE="$ROOT/.tmp/auto_watch.pid"
LOG_FILE="$ROOT/.tmp/auto_watch.log"
mkdir -p "$ROOT/.tmp"
hash_sources() {
 find src -type f -name '*.py' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1
}
if [ -f "$PID_FILE" ]; then
 old_pid=$(cat "$PID_FILE" 2>/dev/null || true)
 if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null && ps -p "$old_pid" -o args= | grep -q 'tools/watch_source.sh'; then
  echo "[auto-watch] 已有监视进程运行：$old_pid"; exit 0
 fi
fi
printf '%s\n' "$$" >"$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT INT TERM
last=$(hash_sources)
echo "[auto-watch] 已启动，轮询间隔 ${interval}s，PID=$$" | tee -a "$LOG_FILE"
while :; do
 current=$(hash_sources)
 if [ "$current" != "$last" ]; then
  echo "[auto-watch] 检测到源代码变化：$(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
  if ! git diff --cached --quiet; then
   echo '[auto-watch] 检测到已有暂存变更，为避免误提交，本次跳过自动提交' | tee -a "$LOG_FILE"
  elif tools/run_tests.sh >>"$LOG_FILE" 2>&1 && \
     python3 tools_bump_version.py patch >>"$LOG_FILE" 2>&1 && \
     git add src VERSION && \
     ! git diff --cached --quiet; then
   git commit -m '自动更新源代码并打包' >>"$LOG_FILE" 2>&1 || echo '[auto-watch] Git提交失败，等待下次检查' | tee -a "$LOG_FILE"
  else
   echo '[auto-watch] 测试、版本升级或暂存失败，暂不提交，等待下次检查' | tee -a "$LOG_FILE"
  fi
  last=$(hash_sources)
 fi
 sleep "$interval"
done
