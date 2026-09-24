#!/usr/bin/env python3
"""版本自动升级工具：python3 tools_bump_version.py patch|minor|major。"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'src'))
from version import bump
print(bump(sys.argv[1] if len(sys.argv)>1 else 'patch'))
