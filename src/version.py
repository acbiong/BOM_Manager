"""软件版本管理：三段式版本号，发布修复时通过工具自动递增。编辑时间：2026-09-24。"""
from pathlib import Path
VERSION_FILE=Path(__file__).resolve().parents[1]/'VERSION'
def get_version():
 try:return VERSION_FILE.read_text(encoding='utf-8').strip() or '0.0.1'
 except FileNotFoundError:return '0.0.1'
def bump(kind='patch'):
 parts=[int(x) for x in get_version().split('.')]
 idx={'major':0,'minor':1,'patch':2}[kind]
 parts[idx]+=1
 for i in range(idx+1,3):parts[i]=0
 v='.'.join(map(str,parts)); VERSION_FILE.write_text(v+'\n',encoding='utf-8'); return v
