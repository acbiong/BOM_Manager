#!/usr/bin/env python3
"""检查Linux发布目录ELF架构、缺失动态库及glibc基线（deepin25为2.38）。"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();errors=[];highest=(0,0);files=0
# PyInstaller bootloader将内部库目录加入LD_LIBRARY_PATH；审计使用相同解析规则。
env=dict(os.environ,LD_LIBRARY_PATH=str(root/'_internal'),LC_ALL='C')
for path in root.rglob('*'):
    if not path.is_file() or path.read_bytes()[:4]!=b'\x7fELF':continue
    files+=1
    header=subprocess.run(['readelf','-h',str(path)],capture_output=True,text=True,check=True).stdout
    if 'X86-64' not in header:errors.append(str(path)+': 非x86_64')
    symbols=subprocess.run(['objdump','-T',str(path)],capture_output=True,text=True).stdout
    for line in symbols.splitlines():
        if '*UND*' not in line:continue
        for major,minor in re.findall(r'GLIBC_(\d+)\.(\d+)',line):
            version=(int(major),int(minor));highest=max(highest,version)
            if version>(2,38):errors.append(str(path)+': GLIBC_'+major+'.'+minor)
    deps=subprocess.run(['ldd',str(path)],capture_output=True,text=True,env=env).stdout
    if 'not found' in deps:errors.append(str(path)+': '+deps)
report={'elf_files':files,'maximum_required_glibc':'.'.join(map(str,highest)),'errors':errors}
Path('test_reports/linux_bundle_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
raise SystemExit(1 if errors or not files else 0)
