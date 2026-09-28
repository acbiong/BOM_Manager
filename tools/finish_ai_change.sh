#!/bin/sh
# AI 编程收尾流程：测试、审计、编译、版本升级、提交；提交钩子随后自动打包 AppImage。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

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
git commit -m "AI自动完成代码更新、测试和打包"
echo '[ai-finish] 已完成测试、版本升级和Git提交；post-commit将继续生成AppImage。'
