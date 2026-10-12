#!/usr/bin/env python3
"""Verify the native Deepin launch API; uses disposable files, never a business DB."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def launch(program, arguments=(), run_id='', environment=None):
    environment = environment or {}
    command = ['busctl', '--user', 'call', '--',
               'org.desktopspec.ApplicationManager1', '/org/desktopspec/ApplicationManager1',
               'org.desktopspec.ApplicationManager1', 'executeCommand', 'sasssa{ss}s',
               str(program), str(len(arguments)), *map(str, arguments), 'portablebinary',
               run_id, str(len(environment))]
    for key, value in environment.items():
        command.extend((key, value))
    return subprocess.run(command + [str(Path(program).parent)], capture_output=True, text=True, timeout=15)


def verify(image):
    results = []
    (ROOT / '.tmp').mkdir(exist_ok=True)
    (ROOT / 'test_reports').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='deepin-direct-', dir=ROOT / '.tmp') as temporary:
        base = Path(temporary)
        long_dir = base / ('共享目录 中文与空格 ' * 6).rstrip() / ('研发设计资料 ' * 6).rstrip()
        long_dir.mkdir(parents=True)
        target = long_dir / image.name
        os.link(image, target)
        report = base / 'smoke.json'
        reply = launch(target, ['--smoke-test-report', report])
        if reply.returncode:
            raise RuntimeError(reply.stderr)
        for _ in range(60):
            if report.exists():
                data = json.loads(report.read_text())
                if not data.get('passed'):
                    raise RuntimeError(data)
                results.append({'case': 'long_path_appimage', 'passed': True, 'path': str(target), 'smoke': data})
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('AppImage未产生自检报告')
        # Boundary service name lengths, UTF-8 identifiers, and short path launch.
        for index, run_id in enumerate(['short', 'a' * 212, 'a' * 213, '物料共享路径' * 80]):
            marker = base / f'marker-{index}'
            reply = launch('/usr/bin/touch', [marker], run_id)
            if reply.returncode:
                raise RuntimeError(reply.stderr)
            for _ in range(50):
                if marker.exists():
                    break
                time.sleep(0.1)
            if not marker.exists():
                raise RuntimeError(f'启动失败: {index}')
            results.append({'case': f'identifier-{index}', 'passed': True})
        reply = launch('/usr/bin/true', environment={'BAD KEY': 'invalid'})
        if reply.returncode == 0:
            raise RuntimeError('systemd错误未向调用方返回')
        results.append({'case': 'systemd_error_forwarded', 'passed': True, 'error': reply.stderr.strip()})
    output = ROOT / 'test_reports/deepin_direct_launch.json'
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(output)


if __name__ == '__main__':
    verify(Path(sys.argv[1]).resolve())
