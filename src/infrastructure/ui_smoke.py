"""Exercise actual save prompts and every dialog family in an isolated smoke DB."""
import sys,traceback
from pathlib import Path
from PyQt5 import sip
from PyQt5.QtCore import QTimer,QEventLoop,QEvent,Qt,QPointF
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication,QMessageBox as NativeMessageBox


def exercise_windows(service,main,library):
    from ui.main_window import (MaterialDialog,CreateMaterialDialog,NewSkuDialog,ProjectDialog,
        MaterialHeaderMappingDialog,MaterialConflictDialog,MaterialImportResultDialog,
        BomImportIssuesDialog,BomImportConflictDialog,MaterialVersionDialog,MaterialUsageDialog,
        MaterialColumnFilterDialog,MaterialSelectionDialog)
    from ui.material_search import MaterialSearchDialog,BomSearchDialog
    from ui.bom_compare import BomCompareDialog
    from ui.bom_sync_confirmation import BomSyncConfirmationDialog
    from ui.parent_revision import ParentRevisionDialog
    from ui.replacement_selection import ReplacementSelectionDialog
    from ui.shared_bom_migration import SharedBomMigrationDialog
    from ui.sku_change_description import ChangeDescriptionDialog
    from ui.about_dialog import AboutDialog
    from ui.interactive_windows import QFileDialog,QInputDialog,QColorDialog,QMessageBox
    from ui.window_geometry import WindowGeometryMemory
    from ui.save_shortcut import install_save_shortcuts
    from services.services import BomImportError
    from version import get_version
    app=QApplication.instance();checks=[];errors=[];opened=[]
    previous=sys.excepthook
    sys.excepthook=lambda *args:errors.append(''.join(traceback.format_exception(*args)))
    geometry=WindowGeometryMemory(app,service.config_service)
    had_shortcuts=hasattr(app,'_bom_save_shortcuts');shortcuts=install_save_shortcuts(app)
    def drain(ms=90):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec_()
        app.sendPostedEvents(None,QEvent.DeferredDelete)
        if errors:raise RuntimeError('\n'.join(errors))
    def dismiss_messages():
        for window in app.topLevelWidgets():
            if isinstance(window,NativeMessageBox) and window.isVisible():
                button=window.button(NativeMessageBox.Ok)
                if button is not None:button.click()
    messages=QTimer();messages.timeout.connect(dismiss_messages);messages.start(30)
    try:
        # Closed-project startup must expose saved config entries on first hover.
        import tempfile
        from config.config_service import ConfigService
        from config.project_registry import ProjectRegistry
        from services.services import Services
        from ui.main_window import MainWindow
        from PyQt5.QtTest import QTest
        with tempfile.TemporaryDirectory() as directory:
            from database.database import Database
            from ui.startup_project import restore_project
            history_db=Database(str(Path(directory)/'history.db'));history_service=Services(history_db)
            history_service.update_project(dict(project_code='OLD',project_name='历史项目'))
            history_service.create_sku(history_service.create_material(dict(base_code='OLD-SKU',version='100',name='恢复SKU',unit='pcs')))
            history_db.close()
            config=ConfigService(directory);registry=ProjectRegistry(config)
            registry.remember(Path(directory)/'history.db',dict(project_code='OLD',project_name='历史项目'))
            history_window=MainWindow(Services(None,config));opened.append(history_window)
            history_window.show();history_window.raise_();history_window.activateWindow();drain()
            if app.platformName() not in ('offscreen','minimal'):
                assert QTest.qWaitForWindowActive(history_window,3000),'历史项目测试窗口未获得焦点'
            assert history_window.history_menu.actions()[0].text()=='OLD 历史项目'
            bar=history_window.menuBar()
            project_action=next(a for a in bar.actions() if a.text()=='项目');menu=project_action.menu()
            # Open through the actual menu bar so native popup focus and mouse
            # tracking are established before the first submenu hover.
            QTest.mouseClick(bar,Qt.LeftButton,pos=bar.actionGeometry(project_action).center());drain()
            assert menu.isVisible(),'项目菜单无法打开'
            def hover(action):
                point=menu.actionGeometry(action).center()
                # Deliver the pointer event to the real menu. On Windows,
                # QTest.mouseMove only relocates the shared desktop cursor and
                # its OS event may be lost when popup focus is being assigned.
                app.sendEvent(menu,QMouseEvent(QEvent.MouseMove,QPointF(point),QPointF(menu.mapToGlobal(point)),Qt.NoButton,Qt.NoButton,Qt.NoModifier))
            hover(menu.actions()[0]);drain()
            hover(history_window.history_menu.menuAction())
            for _ in range(40):
                if history_window.history_menu.isVisible():break
                drain(50)
            assert history_window.history_menu.isVisible(),'历史项目子菜单无法首次展开'
            history_window.history_menu.close();menu.close();history_window.close()
            history_window.deleteLater();opened.remove(history_window);drain()
            checks.append('ui_closed_project_history_first_hover')
            def select_startup_project():
                for window in app.topLevelWidgets():
                    if isinstance(window,QInputDialog) and window.isVisible() and window.windowTitle()=='选择启动项目':window.accept()
            selector=QTimer();selector.timeout.connect(select_startup_project);selector.start(30)
            restored=None;restored_window=None
            try:
                restored=restore_project(config,config.load())
                restored_window=MainWindow(Services(restored,config));restored_window.show();drain()
                assert restored_window.table.rowCount()==1 and restored_window.table.item(0,1).text()=='OLD-SKU100'
                assert config.load()['database']['path']=='history.db'
                checks.append('ui_legacy_config_select_project_load_skus')
            finally:
                selector.stop()
                if restored_window is not None:restored_window.close();restored_window.deleteLater();drain()
                if restored is not None:restored.close()
        root=service.create_material(dict(base_code='UI-SMOKE',version='1',name='界面保存验证',unit='pcs'))
        child=service.create_material(dict(base_code='UI-CHILD',version='1',name='界面子料',unit='pcs'))
        sid=service.create_sku(root);scoped=service.for_sku(sid)
        scoped.save_bom(root,[dict(material_id=child,quantity=1,unit='pcs')])
        bom=main.open_bom_id(sid);opened.append(bom)
        main.compare_boms();compare=main._compare_dialog
        compare.left.setCurrentIndex(compare.left.findData(sid));compare.right.setCurrentIndex(compare.right.findData(sid));compare.compare()
        for quantity in ('2.125','3','4.25'):
            bom.show_item_info(bom.root_item.child(0));bom.fields['quantity'].setText(quantity)
            bom.save_action.trigger();drain(180)
            assert not bom.dirty and scoped.bom(root)[0]['quantity']==float(quantity),'BOM真实保存失败'
        checks.extend(['ui_save_three_times_with_real_prompt','ui_compare_live_after_save'])
        output=Path(service.db.path).parent/'ui_saved.xlsx';service.export_sku(sid,output);assert output.exists()
        checks.append('ui_export_after_save')
        material=service.material_snapshot(child)
        incoming={'物料基础编码':material['base_code'],'物料版本号':material['version'],'物料名称':material['name']}
        factories=[
            lambda:MaterialDialog(main,data=material),lambda:CreateMaterialDialog(main),lambda:NewSkuDialog(service,main),
            lambda:ProjectDialog(main),lambda:ChangeDescriptionDialog('测试描述',main),
            lambda:MaterialHeaderMappingDialog('smoke.xlsx',['物料基础编码'],[],main,required=['物料基础编码']),
            lambda:MaterialConflictDialog(incoming,material,main),lambda:MaterialImportResultDialog([],[(2,'A1','测试','必填项缺失')],main),
            lambda:BomImportIssuesDialog(BomImportError(['第2行缺少物料编码']),main),lambda:BomImportConflictDialog([],main),
            lambda:MaterialVersionDialog(material,[],main),lambda:MaterialUsageDialog(material,[],main),
            lambda:MaterialColumnFilterDialog('筛选',['A','B'],parent=main),lambda:MaterialSelectionDialog(main),
            lambda:MaterialSearchDialog(library),lambda:BomSearchDialog(bom),lambda:BomSyncConfirmationDialog([],bom),
            lambda:ParentRevisionDialog(service,[],bom),lambda:ReplacementSelectionDialog([],bom),
            lambda:SharedBomMigrationDialog(service.db,{},main),lambda:AboutDialog(get_version(),main),
            lambda:QFileDialog(main),lambda:QInputDialog(main),lambda:QColorDialog(main)]
        for factory in factories:
            dialog=factory();opened.append(dialog)
            QTimer.singleShot(60,dialog.reject);dialog.exec_()
            assert dialog.windowModality()==Qt.NonModal,type(dialog).__name__+'意外变成模态'
            checks.append('dialog_'+type(dialog).__name__)
            dialog.deleteLater();opened.remove(dialog);drain()
        # Real pure notification windows are not mocked: exercise Qt native lifetimes.
        for name in ('information','warning','critical'):
            getattr(QMessageBox,name)(main,'冒烟测试','自动关闭的'+name+'提示')
            drain();checks.append('message_'+name)
        bom.dirty=False;bom.close();drain();opened.remove(bom)
        compare.close();drain()
        reopened=main.open_bom_id(sid);opened.append(reopened);drain()
        assert reopened.root_item.child(0).text(1)=='4.25'
        reopened.close();drain();opened.remove(reopened);checks.append('ui_close_reopen_saved_bom')
        from ui.help_dialog import HelpDialog
        from PyQt5.QtWidgets import QLabel
        visible={window for window in app.topLevelWidgets() if window.isVisible()}
        help_window=HelpDialog(main);opened.append(help_window);help_window.show();drain()
        assert {window for window in app.topLevelWidgets() if window.isVisible()}-visible=={help_window}
        images=[label for label in help_window.findChildren(QLabel) if label.pixmap() is not None and not label.pixmap().isNull()]
        from ui.help_guides import GUIDES
        assert len(images)==len(GUIDES[0]['steps'])+10,'帮助静态截图未完整打包'
        for index in range(help_window.guide_selector.count()):
            help_window.guide_selector.setCurrentRow(index);drain(10)
            assert help_window._guide_index==index
            labels=help_window.guide_view.widget().findChildren(QLabel)
            images=[label for label in labels if label.pixmap() is not None and not label.pixmap().isNull()]
            assert len(images)==len(GUIDES[index]['steps']),'教程截图未完整加载'
        checks.extend(['ui_help_annotated_action_resources','ui_help_no_extra_windows'])
        help_window.close();help_window.deleteLater();opened.remove(help_window);drain()
        return checks
    finally:
        messages.stop()
        for window in reversed(opened):
            if not sip.isdeleted(window):
                if hasattr(window,'dirty'):window.dirty=False
                window.close();window.deleteLater()
        app.sendPostedEvents(None,QEvent.DeferredDelete)
        if not had_shortcuts:shortcuts.shutdown();del app._bom_save_shortcuts
        geometry.timer.stop();app.removeEventFilter(geometry);app.aboutToQuit.disconnect(geometry.save_visible);geometry.deleteLater()
        app.sendPostedEvents(None,QEvent.DeferredDelete);sys.excepthook=previous
