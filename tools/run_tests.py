#!/usr/bin/env python3
"""Windows/Linux通用测试入口，完整报告写入test_reports。"""
import datetime
import os
import platform
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
os.chdir(root)
(root/'test_reports').mkdir(exist_ok=True)
report=root/'test_reports'/('test_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.txt')
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
# Windows runners may expose an 8.3 TEMP alias; use one canonical path in
# subprocess fixtures and application path comparisons.
if os.name == 'nt':
    canonical_temp = str(Path(tempfile.gettempdir()).resolve())
    env.update(TEMP=canonical_temp, TMP=canonical_temp, TMPDIR=canonical_temp)
failed=False
with report.open('w',encoding='utf-8') as output:
    output.write(f'BOM管理系统测试报告\n时间：{datetime.datetime.now().astimezone().isoformat()}\n项目：{root}\nPython：{sys.executable}\n平台：{platform.platform()}\n')
    for args in ([sys.executable,'tests/audit_requirements.py'],[sys.executable,'-m','unittest','discover','-s','tests','-q']):
        output.write('\n$ '+subprocess.list2cmdline(args)+'\n');output.flush()
        result=subprocess.run(args,env=env,stdout=output,stderr=subprocess.STDOUT)
        output.write(f'[exit={result.returncode}]\n')
        failed=failed or result.returncode!=0
    try:
        for source in (root/'src').rglob('*.py'):
            dest=root/'.tmp'/'compile'/source.relative_to(root/'src').with_suffix('.pyc')
            dest.parent.mkdir(parents=True,exist_ok=True)
            py_compile.compile(str(source),cfile=str(dest),doraise=True)
        output.write('\nCOMPILE_OK\n')
    except Exception as exc:
        output.write(str(exc));failed=True
print(report.read_text(encoding='utf-8'))
print('报告：',report)
raise SystemExit(1 if failed else 0)
