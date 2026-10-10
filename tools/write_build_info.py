#!/usr/bin/env python3
"""将当前提交信息写入打包临时目录，随AppImage携带。"""
import json
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from infrastructure.build_info import collect_build_info
if __name__ == '__main__':
    target = root / '.tmp' / 'build_info.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(collect_build_info(root), ensure_ascii=False, indent=2), encoding='utf-8')
