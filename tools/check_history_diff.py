"""Bounded native-window checks and optional help captures on disposable data."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--platform', required=True, choices=['windows', 'xcb'])
parser.add_argument('--update-help', action='store_true')
args = parser.parse_args()
os.environ['QT_QPA_PLATFORM'] = args.platform
sys.path[:0] = [str(root / 'src'), str(root / 'tests')]
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QColor, QPainter, QPen, QPalette
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication
from test_material_history_diff import example
from ui.material_history import MaterialHistoryDialog
from ui.theme import apply_theme

out = root / 'test_reports' / ('history_diff_' + args.platform)
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
apply_theme(False)
checks = []
with tempfile.TemporaryDirectory(prefix='bom-history-diff-') as folder:
    db, svc, ids = example(folder)
    before = '\n'.join(db.conn.iterdump())
    w = None
    try:
        w = MaterialHistoryDialog(svc, ids['R'], 101)
        w.show(); w.raise_(); w.activateWindow()
        assert QTest.qWaitForWindowExposed(w, 3000)
        w.tree.expandAll(); app.processEvents()
        changed = w.tree.topLevelItem(0).child(1)
        QTest.mouseClick(w.tree.viewport(), Qt.LeftButton, pos=w.tree.visualItemRect(changed).center())
        assert w.tree.currentItem() is changed and w.attribute_values['name'].text() == '主控板改版'
        assert w.attribute_values['name'].font().bold()
        w.tree.clearSelection(); app.processEvents()
        assert w.grab().save(str(out / 'changes_light.png'))
        checks.append('native_row_selection_and_changed_properties')
        if args.update_help:
            directory = root / 'resources/help_screenshots'
            manifest = json.loads((directory / 'actions.json').read_text(encoding='utf-8'))
            for key, target in [('action_material_history_view', w.tree),
                                ('action_material_history_switch', w.version_combo),
                                ('action_material_history_references', w.references_group)]:
                rect = QRect(target.mapTo(w, QPoint(0, 0)), target.size()).adjusted(-2, -2, 2, 2).intersected(w.rect())
                pix = w.grab(); ratio = pix.devicePixelRatio(); pix.setDevicePixelRatio(1)
                painter = QPainter(pix); painter.setPen(QPen(QColor('#ed1826'), 3)); painter.setBrush(Qt.NoBrush)
                painter.drawRect(QRect(round(rect.x()*ratio), round(rect.y()*ratio), round(rect.width()*ratio), round(rect.height()*ratio))); painter.end()
                assert pix.save(str(directory / (key + '.png')))
                manifest[key] = dict(window=w.windowTitle(), target=[rect.x(), rect.y(), rect.width(), rect.height()], size=[pix.width(), pix.height()])
            (directory / 'actions.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        apply_theme(True); app.processEvents()
        assert w.attribute_values['name'].font().bold()
        assert w.attribute_values['name'].palette().color(QPalette.WindowText) == QColor('#9a6700')
        assert w.grab().save(str(out / 'changes_dark.png'))
        checks.append('native_light_and_dark_render')
        apply_theme(False); app.processEvents()
        w.version_combo.setFocus(); QTest.keyClick(w.version_combo, Qt.Key_Down); app.processEvents()
        assert w.version_combo.currentData() == 100 and w.previous_version is None
        assert w.tree.topLevelItem(0).childCount() == 3
        assert not w.attribute_values['name'].font().bold()
        assert w.grab().save(str(out / 'first_version.png'))
        QTest.keyClick(w.version_combo, Qt.Key_Up); app.processEvents()
        assert w.previous_version == 100 and w.tree.topLevelItem(0).childCount() == 4
        checks.append('native_version_keyboard_switch_and_marker_reset')
        removed = w.tree.topLevelItem(0).child(3)
        w.tree.scrollToItem(removed); app.processEvents()
        QTest.mouseClick(w.tree.viewport(), Qt.LeftButton, pos=w.tree.visualItemRect(removed).center())
        assert '已删除的对照节点' in w.reference_label.text()
        checks.append('native_deleted_node_reference_context')
        assert '\n'.join(db.conn.iterdump()) == before
        checks.append('database_unchanged')
    finally:
        if w is not None: w.close()
        db.close()
result = dict(passed=True, platform=app.platformName(), checks=checks)
(out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
