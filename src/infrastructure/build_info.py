"""软件构建信息：源码读取Git，冻结包读取随包JSON。编辑时间：2026-10-10。"""
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_URL = 'https://github.com/acbiong/BOM_Manager'
COPYRIGHT = 'Copyright © 2026 Biong & BrainCo Inc.\n第三方组件的版权归各自权利人所有。'


def collect_build_info(root):
    def git(*args):
        try:
            return subprocess.check_output(['git', '-C', str(root), *args],
                stderr=subprocess.DEVNULL, text=True, timeout=3).strip()
        except (OSError, subprocess.SubprocessError):
            return ''
    remote = git('remote', 'get-url', 'origin')
    if remote.startswith('git@github.com:'):
        remote = 'https://github.com/' + remote.split(':', 1)[1]
    url = remote.removesuffix('.git') if remote.startswith('https://') else REPOSITORY_URL
    return dict(repository=url, commit=git('rev-parse', 'HEAD'),
                author=git('show', '-s', '--format=%an', 'HEAD'),
                date=git('show', '-s', '--format=%cI', 'HEAD'),
                message=git('show', '-s', '--format=%B', 'HEAD'))


def load_build_info():
    if getattr(sys, 'frozen', False):
        try:
            data = json.loads((Path(sys._MEIPASS) / 'build_info.json').read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError, AttributeError):
            pass
        return {'repository': REPOSITORY_URL}
    return collect_build_info(Path(__file__).resolve().parents[2])
