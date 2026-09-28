#!/bin/sh
# AI 编程收尾流程：测试、审计、编译、版本升级、提交；提交钩子随后自动打包 AppImage。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
requested_message=${1:-}

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
if [ -n "$requested_message" ]; then
 commit_message="$requested_message"
else
 changed=$(git diff --cached --name-only)
 details=''; kind='变更'
 add_detail() {
  case ",$details," in *,"$1",*) ;; *) details="${details}${details:+、}$1" ;; esac
 }
 while IFS= read -r path; do
  case "$path" in
   src/ui/*) add_detail '界面与交互'; [ "$kind" = '变更' ] && kind='优化' ;;
   src/database/*) add_detail '数据库结构与访问逻辑' ;;
   src/services/*) add_detail '业务逻辑与BOM处理' ;;
   tests/*|test_reports/*) add_detail '测试与验证' ;;
   docs/*) add_detail '开发文档与审计记录' ;;
   tools/*|.githooks/*) add_detail '自动化测试、提交与打包流程'; [ "$kind" = '变更' ] && kind='构建' ;;
   VERSION) add_detail '软件版本' ;;
  esac
 done <<EOF
$changed
EOF
 [ -n "$details" ] || details='项目源代码'
 commit_message="${kind}：更新${details}"
fi
git commit -m "$commit_message"
echo '[ai-finish] 已完成测试、版本升级和Git提交；post-commit将继续生成AppImage。'
