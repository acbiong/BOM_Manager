#!/usr/bin/env python3
"""Capture real desktop pixels during export on an isolated read-only DB backup."""
import argparse, hashlib, json, sqlite3, sys, tempfile, traceback, time
from unittest.mock import patch
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PyQt5.QtCore import QTimer, QPoint, QEvent
from PyQt5.QtWidgets import QApplication
from database.database import Database
from config.config_service import ConfigService
from services.services import Services
from ui.main_window import MainWindow
from ui.operation_progress import OperationProgress, operation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--legacy-paint', action='store_true')
    parser.add_argument('--bulk-count', type=int, default=0)
    args = parser.parse_args()
    report = Path(args.report).resolve()
    source = Path(args.source).resolve()
    digest = lambda: hashlib.sha256(source.read_bytes()).hexdigest()
    before = digest()
    app = QApplication([])
    assert app.platformName() not in ('offscreen', 'minimal'), 'Requires real desktop'
    result = {'platform': app.platformName(), 'captures': []}
    with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as tmp:
        target = Path(tmp) / 'copy.db'
        a = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
        b = sqlite3.connect(target)
        try:a.backup(b)
        finally:a.close();b.close()
        db = Database(str(target))
        service = Services(db, ConfigService(tmp))
        window = MainWindow(service)
        window.show()
        if args.bulk_count:window.show_materials()
        bulk_controllers = set(); bulk_dialogs = set(); bulk_geometry = set()
        update = OperationProgress.update
        def observe(controller, message=None, current=None, total=None):
            if args.legacy_paint:
                with patch.object(QApplication, 'processEvents', return_value=None):
                    update(controller, message, current, total)
            else:update(controller, message, current, total)
            dialog = controller.dialog
            if controller.title == '批量导入物料':
                bulk_controllers.add(id(controller))
                if dialog is not None:
                    bulk_dialogs.add(id(dialog));bulk_geometry.add((dialog.x(),dialog.y(),dialog.width(),dialog.height()))
            if dialog is None or not dialog.isVisible():return
            if not args.legacy_paint and not dialog.windowHandle().isExposed():return
            if controller.title == '导出资料库' and (not total or current < total / 2):return
            previous = next((c for c in result['captures'] if c['operation'] == controller.title), None)
            if previous and time.monotonic() - previous['captured_at'] < .060:return
            if previous:result['captures'].remove(previous)
            point = dialog.mapToGlobal(QPoint(0, 0))
            image = dialog.screen().grabWindow(0, point.x(), point.y(), dialog.width(), dialog.height())
            image_path = report.with_name(report.stem + '_' + controller.title + '.png')
            image.save(str(image_path))
            result['captures'].append(dict(operation=controller.title, captured_at=time.monotonic(), exposed=dialog.windowHandle().isExposed(),
                label=dialog.labelText(), value=dialog.value(), maximum=dialog.maximum(),
                image=str(image_path)))
        OperationProgress.update = observe
        def run():
            try:
                if args.bulk_count:
                    from openpyxl import Workbook
                    from services.services import MATERIAL_IMPORT_HEADERS
                    from ui.operation_progress import RECENT_OPERATIONS
                    book=Workbook();book.active.append(MATERIAL_IMPORT_HEADERS)
                    for i in range(args.bulk_count):
                        book.active.append([f'PROGRESS-TEST-{i}', '100', f'进度验证物料{i}', '自动换行规格'*8, 'pcs', '', 'M', '测试厂商', ''])
                    path=Path(tmp)/'bulk.xlsx';book.save(path);book.close()
                    RECENT_OPERATIONS.clear()
                    ok,failed=operation('批量导入物料')(lambda:service.import_materials(path))()
                    result['bulk']={'imported':len(ok),'failed':len(failed),'controllers':len(bulk_controllers),
                                    'dialogs':len(bulk_dialogs),'geometry_count':len(bulk_geometry),
                                    'operations':[r['operation'] for r in RECENT_OPERATIONS]}
                    assert len(ok)==args.bulk_count and not failed
                    assert len(bulk_controllers)==1 and len(bulk_dialogs)==1
                    assert len(bulk_geometry)==1, bulk_geometry
                    assert result['bulk']['operations']==['批量导入物料']
                operation('导出资料库')(lambda:service.export_database(str(Path(tmp)/'export.xlsx')))()
                if not args.legacy_paint:
                    for title, function in [('导出物料库', service.export_materials), ('导出SKU清单', service.export_sku_list)]:
                        operation(title)(lambda:function(str(Path(tmp)/(title+'.xlsx'))))()
                    operation('物料导入')(lambda:service.import_materials(str(Path(tmp)/'导出物料库.xlsx'),lambda *args:'skip',sheet_name='物料库'))()
                    # Deterministic slow-path coverage for every shared UI label;
                    # these are component scenarios, not writes to the source DB.
                    from infrastructure.operation_progress import checkpoint, file_work
                    for title in ('物料导入', 'BOM导入', '保存BOM', '刷新BOM', '导出采购BOM'):
                        def slow_path():
                            checkpoint('正在处理测试副本…', 1, 2)
                            file_work(time.sleep, .300)
                            checkpoint('处理完成', 2, 2)
                        operation(title)(slow_path)()
                result['ok'] = bool(result['captures']) and all(c['exposed'] for c in result['captures'])
            except Exception:
                result['error'] = traceback.format_exc();result['ok'] = False
            finally:QTimer.singleShot(100, app.quit)
        QTimer.singleShot(500, run)
        app.exec_()
        OperationProgress.update = update
        for widget in app.topLevelWidgets():widget.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        db.close()
    result['source_unchanged'] = before == digest()
    result['source_sha256'] = before
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok') and result['source_unchanged'] else 1

if __name__ == '__main__':sys.exit(main())
