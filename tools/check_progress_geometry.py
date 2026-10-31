#!/usr/bin/env python3
"""Bounded native-window placement regression; no business database or settings."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget
from config.config_service import ConfigService
from ui.operation_progress import OperationProgress
from ui.window_geometry import WindowGeometryMemory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    path = Path(args.report).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    report = dict(passed=False, platform=app.platformName(),
                  wsl_distribution=os.environ.get('WSL_DISTRO_NAME'), cases=[])
    owner = QWidget()
    owner.setWindowTitle('进度窗口定位验证（临时）')
    owner.resize(800, 500)
    controller = memory = None
    try:
        assert app.platformName() not in ('offscreen', 'minimal'), 'Requires a native display'
        owner.show();owner.activateWindow()
        assert QTest.qWaitForWindowExposed(owner, 3000)
        with tempfile.TemporaryDirectory(prefix='bom-progress-geometry-') as temp:
            for remember in (False, True):
                if remember:
                    memory = WindowGeometryMemory(app, ConfigService(temp))
                for attempt in range(3):
                    controller = OperationProgress(owner, '进度位置稳定性验证')
                    controller.threshold = controller.paint_interval = 0
                    for phase in ('initial', 'resume'):
                        if phase == 'resume':
                            controller.pause()
                            assert not controller.dialog.isVisible()
                            QTest.qWait(80)
                            controller.resume()
                        positions = []
                        for step in range(20):
                            controller.update('正在处理测试数据…' if step < 10 else '阶段变化与很长的处理说明' * 15,
                                              step + 1, 20)
                            dialog = controller.dialog
                            assert dialog.isVisible() and dialog.windowHandle().isExposed()
                            assert dialog.windowModality() == Qt.NonModal
                            assert dialog.value() == step + 1
                            positions.append(dialog.geometry().getRect())
                            QTest.qWait(25)
                        unique = sorted(set(positions))
                        case = dict(window_memory=remember, attempt=attempt, phase=phase,
                                    samples=len(positions), positions=unique)
                        report['cases'].append(case)
                        assert len(unique) == 1, case
                        distance = (dialog.frameGeometry().center() - owner.screen().availableGeometry().center()).manhattanLength()
                        assert distance <= 30, (case, distance)
                        if not remember and attempt == 0 and phase == 'initial':
                            assert dialog.grab().save(str(path.with_suffix('.png')))
                    controller.close();controller = None
                    app.sendPostedEvents(None, QEvent.DeferredDelete)
                if memory is not None:
                    memory.timer.stop();memory.placement_timer.stop()
                    app.removeEventFilter(memory);app.aboutToQuit.disconnect(memory.save_visible)
                    memory.deleteLater();memory = None
                    app.sendPostedEvents(None, QEvent.DeferredDelete)
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if controller is not None:controller.close()
        if memory is not None:
            memory.timer.stop();memory.placement_timer.stop()
            app.removeEventFilter(memory);app.aboutToQuit.disconnect(memory.save_visible)
            memory.deleteLater()
        owner.close();owner.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
