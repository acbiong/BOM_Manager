#!/usr/bin/env python3
"""安装短名称桌面入口，绕过Deepin长路径可执行文件转systemd单元名失败。"""
import argparse
import os
from pathlib import Path
import subprocess


def desktop_exec(path):
    # Desktop Entry Exec双引号内的反斜杠需同时经过桌面文件与Exec两层解析。
    value=str(path).replace('\\','\\\\\\\\')
    for char in ('"','`','$'):
        value=value.replace(char,'\\\\'+char)
    return '"'+value.replace('%','%%')+'"'


def install(image,desktop=None):
    image=Path(image).expanduser().resolve()
    if not image.is_file():raise ValueError('AppImage不存在：'+str(image))
    if not os.access(image,os.X_OK):raise ValueError('AppImage没有执行权限，请先设置可执行权限')
    applications=Path.home()/'.local/share/applications';applications.mkdir(parents=True,exist_ok=True)
    if desktop is None:
        try:desktop=Path(subprocess.check_output(['xdg-user-dir','DESKTOP'],text=True).strip())
        except (OSError,subprocess.SubprocessError):desktop=Path.home()/'Desktop'
    desktop=Path(desktop);desktop.mkdir(parents=True,exist_ok=True)
    body='\n'.join(['[Desktop Entry]','Type=Application','Name=BOM管理系统','Comment=启动BOM管理系统（支持长路径和网络共享）','Exec='+desktop_exec(image),'Icon=applications-office','Terminal=false','Categories=Office;','StartupNotify=false',''])
    paths=[applications/'bom-manager.desktop',desktop/'bom-manager.desktop']
    for target in paths:
        target.write_text(body,encoding='utf-8');target.chmod(0o755)
    return paths

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('appimage');args=parser.parse_args()
    for target in install(args.appimage):print(target)
