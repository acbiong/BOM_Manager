#!/bin/sh
# 运行需求审计、自动化测试和源码编译校验，并保存完整报告。
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
mkdir -p test_reports .tmp/compile
stamp=$(date +%Y%m%d_%H%M%S)
report="test_reports/test_${stamp}.txt"
status=0

run_check() {
  label=$1
  shift
  {
    printf '\n[%s]\n' "$label"
    printf '$'
    printf ' %s' "$@"
    printf '\n'
    "$@"
    rc=$?
    printf '[exit=%s]\n' "$rc"
    [ "$rc" -eq 0 ] || status=1
  } >>"$report" 2>&1
}

printf 'BOM管理系统测试报告\n时间：%s\n项目：%s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$ROOT" >"$report"
run_check '需求追踪审计' env PYTHONDONTWRITEBYTECODE=1 python3 tests/audit_requirements.py
run_check '自动化测试' env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q

{
  printf '\n[源码编译校验]\n'
  python3 - "$ROOT/.tmp/compile" <<'PYCOMPILE'
import pathlib, py_compile, sys
out = pathlib.Path(sys.argv[1])
for source in pathlib.Path('src').rglob('*.py'):
    target = (out / source.relative_to('src')).with_suffix('.pyc')
    target.parent.mkdir(parents=True, exist_ok=True)
    py_compile.compile(str(source), cfile=str(target), doraise=True)
print('COMPILE_OK')
PYCOMPILE
  rc=$?
  printf '[exit=%s]\n' "$rc"
  [ "$rc" -eq 0 ] || status=1
} >>"$report" 2>&1

printf '\n报告文件：%s\n' "$report"
cat "$report"
exit "$status"
