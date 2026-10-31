"""Bounded real-window checks for cross-project selection and live drafts."""
import time
from pathlib import Path
from PyQt5.QtCore import Qt,QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication,QDialogButtonBox,QMessageBox as NativeMessageBox
from ui.interactive_windows import QInputDialog


def select_project(dialog,side=1,capture=None):
    app=QApplication.instance();seen=[];errors=[];started=time.monotonic()
    def accept():
        for window in app.topLevelWidgets():
            if not isinstance(window,QInputDialog) or not window.isVisible():continue
            if window.windowTitle() not in ('选择对比项目','选择项目SKU BOM'):continue
            try:
                if app.platformName() not in ('offscreen','minimal'):
                    assert QTest.qWaitForWindowExposed(window,2000)
                assert window.windowModality()==Qt.NonModal
                seen.append(window.windowTitle())
                if capture:capture(window,len(seen))
                button=window.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
                QTest.mouseClick(button,Qt.LeftButton)
            except Exception as exc:errors.append(str(exc));window.reject()
        if time.monotonic()-started>8:
            errors.append('项目选择超时')
            for window in app.topLevelWidgets():
                if isinstance(window,QInputDialog) and window.isVisible():window.reject()
    timer=QTimer();timer.timeout.connect(accept);timer.start(30)
    try:
        combo=(dialog.left,dialog.right)[side];combo.showPopup()
        view=combo.view();index=combo.model().index(combo.count()-1,0)
        view.scrollTo(index);app.processEvents()
        QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=view.visualRect(index).center())
    finally:timer.stop();combo.hidePopup()
    assert not errors,errors
    assert seen==['选择对比项目','选择项目SKU BOM'],seen
    assert str(combo.currentData()).startswith('project:')


def exercise_live_project(main,compare):
    import tempfile
    from database.database import Database
    from services.services import Services
    from config.config_service import ConfigService
    from config.project_registry import ProjectRegistry
    from ui.main_window import MainWindow
    checks=[]
    with tempfile.TemporaryDirectory(prefix='bom-project-smoke-') as folder:
        path=Path(folder)/'other.db';db=Database(str(path));svc=Services(db)
        root,child=[svc.create_material(dict(base_code=code,version='1',name=code,unit='pcs')) for code in ('UI-SMOKE','UI-CHILD')]
        sid=svc.create_sku(root);svc.save_bom(root,[dict(material_id=child,quantity=2,unit='pcs')])
        svc.update_project(dict(project_code='OTHER',project_name='其他项目草稿验证'))
        registry=ProjectRegistry(main.svc.config_service)
        key=registry.remember(path,dict(svc.project()))
        other=MainWindow(Services(db,ConfigService(Path(folder)/'config')))
        try:
            other.show();bom=other.open_bom_id(sid);bom.show_item_info(bom.root_item.child(0))
            other._live_project.flush();before=path.read_bytes()
            select_project(compare);checks.append('ui_compare_other_project_selection')
            field=bom.fields['quantity'];field.setFocus();QTest.keyClick(field,Qt.Key_A,Qt.ControlModifier);QTest.keyClicks(field,'8.5')
            for _ in range(80):
                QTest.qWait(25)
                if compare._rows and compare._rows[1].right['quantity']==8.5:break
            assert bom.dirty and compare._rows[1].right['quantity']==8.5
            assert path.read_bytes()==before and svc.bom(root)[0]['quantity']==2
            assert '未保存草稿' in compare.summary.text()
            checks.append('ui_compare_other_project_live_unsaved')
            def discard():
                for window in QApplication.instance().topLevelWidgets():
                    if isinstance(window,NativeMessageBox) and window.isVisible():
                        for button in window.buttons():
                            if '不保存' in button.text() or '放弃' in button.text():button.click();return
            timer=QTimer();timer.timeout.connect(discard);timer.start(30)
            try:assert bom.close()
            finally:timer.stop()
            for _ in range(80):
                QTest.qWait(25)
                if compare._rows and compare._rows[1].right['quantity']==2:break
            assert compare._rows[1].right['quantity']==2 and path.read_bytes()==before
            checks.append('ui_compare_other_project_discard_refresh')
        finally:
            for window in list(other._bom_windows.values()):window.dirty=False
            other.close();other.deleteLater();registry.delete(key);db.close()
    return checks
