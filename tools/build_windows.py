#!/usr/bin/env python3
"""Windows x64原生构建单文件EXE，包含测试、元数据、图标、自检和SHA256。"""
import datetime
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.windows_signing import signing_config, sign_and_verify, write_version_resource


def finalize_artifact(exe, report, signing, env):
    checksum=exe.with_suffix('.exe.sha256')
    signing_report=report.with_name(exe.stem+'_signing.json')
    for stale in (checksum,report,signing_report):stale.unlink(missing_ok=True)
    signature = sign_and_verify(exe, signing, env)
    result=subprocess.run([str(exe),'--smoke-test-report',str(report)],env=env,timeout=120)
    if result.returncode or not report.is_file() or not json.loads(report.read_text(encoding='utf-8')).get('passed'):
        raise RuntimeError('EXE自检未通过，请检查'+str(report))
    digest=hashlib.sha256(exe.read_bytes()).hexdigest()
    signature.update(file=exe.name,sha256=digest)
    signing_report.write_text(json.dumps(signature,ensure_ascii=False,indent=2),encoding='utf-8')
    checksum.write_text(digest+'  '+exe.name+'\n',encoding='utf-8')


def main():
    if sys.platform!='win32' or platform.machine().lower() not in ('amd64','x86_64'):
        raise SystemExit('请在Windows 10/11 x64环境使用64位Python 3.12构建；PyInstaller不支持从Linux直接交叉编译Windows EXE。')
    root=Path(__file__).resolve().parents[1];os.chdir(root)
    env=dict(os.environ,PYTHONUTF8='1')
    signing=signing_config(env)
    def run(args):subprocess.run(args,check=True,env=env)
    run([sys.executable,'tools/run_tests.py'])
    run([sys.executable,'tools/write_build_info.py'])
    from PIL import Image,ImageDraw
    tmp=root/'.tmp'/'windows';tmp.mkdir(parents=True,exist_ok=True)
    icon=tmp/'bom.ico';image=Image.new('RGB',(256,256),'#2368b4');draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((16,16,240,240),radius=28,outline='white',width=6)
    draw.text((30,95),'BOM',fill='white',font_size=64)
    image.save(icon,sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    version=(root/'VERSION').read_text().strip();name=f'BOM_Manager_{version}_{datetime.datetime.now():%Y%m%d_%H%M%S}_windows_x64'
    version_resource=tmp/'version_info.txt';write_version_resource(version_resource,version)
    package=root/'package';package.mkdir(exist_ok=True)
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
         '--workpath',str(tmp/'build'),'--distpath',str(package),'--specpath',str(tmp/'spec'),
         '--icon',str(icon),'--version-file',str(version_resource),'--add-data',str(root/'VERSION')+os.pathsep+'.',
         '--add-data',str(root/'.tmp'/'build_info.json')+os.pathsep+'.','--name',name,'src/main.py'])
    exe=package/(name+'.exe');report=root/'test_reports'/(name+'_smoke.json')
    finalize_artifact(exe,report,signing,env)
    print('EXE:',exe)
if __name__=='__main__':main()
