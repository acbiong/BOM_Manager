#!/bin/sh
# AI 编程收尾流程：测试、审计、编译、版本升级、提交；提交钩子随后自动打包 AppImage。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
requested_message=${1:-}
if [ "$requested_message" = '--message-file' ]; then
 [ -n "${2:-}" ] && [ -s "$2" ] || { echo '请提供包含变更标题、具体变更和验证结果的提交说明文件。' >&2; exit 2; }
 requested_message=$(cat "$2")
fi
if [ -z "$requested_message" ]; then
 echo '请根据实际改动填写详细提交说明：tools/finish_ai_change.sh --message-file <说明文件>（也支持直接传入多行说明）。' >&2
 exit 2
fi

if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
 echo '[ai-finish] 没有检测到代码变更，仍执行测试校验。'
 tools/run_tests.sh
 exit 0
fi

tools/run_tests.sh
python3 tools_bump_version.py patch
git add -A
if git diff --cached --quiet; then
 echo '[ai-finish] 暂存区没有可提交内容。'
 exit 0
fi
mkdir -p .tmp
printf '%s\n' "$requested_message" > .tmp/ai_commit_message.txt
git commit --file .tmp/ai_commit_message.txt
echo '[ai-finish] 已完成测试、版本升级和Git提交；post-commit将继续生成AppImage。'
