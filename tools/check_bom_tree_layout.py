"""Finite native-window checks for wrapping, dragging, save and browser restore."""
import argparse,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
parser=argparse.ArgumentParser();parser.add_argument('--platform',required=True,choices=['windows','xcb']);args=parser.parse_args()
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));sys.path.insert(0,str(root/'src'));os.environ['QT_QPA_PLATFORM']=args.platform
from PyQt5.QtCore import Qt,QSettings,QPoint,QEvent
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication,QDialogButtonBox
from PyQt5.QtTest import QTest
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow
from ui.bom_tree_layout import BomTreeColumns
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
out=root/'test_reports'/('tree_layout_'+args.platform);out.mkdir(parents=True,exist_ok=True)
def settle():
    for _ in range(8):app.processEvents()
def drag(tree,column,width):
    header=tree.header();start=QPoint(header.sectionViewportPosition(column)+header.sectionSize(column)-1,header.height()//2)
    end=start+QPoint(width-header.sectionSize(column),0)
    QTest.mousePress(header.viewport(),Qt.LeftButton,pos=start)
    app.sendEvent(header.viewport(),QMouseEvent(QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
    QTest.mouseRelease(header.viewport(),Qt.LeftButton,pos=end);settle()
with tempfile.TemporaryDirectory() as tmp:
    settings=QSettings(str(Path(tmp)/'layout.ini'),QSettings.IniFormat)
    db=Database(str(Path(tmp)/'bom.db'));svc=Services(db);windows=[]
    with patch('ui.bom_tree_layout.QSettings',return_value=settings):
        try:
            mid=svc.create_material(dict(base_code='SKU',version='100',name='BOM树换行及列宽记忆验证',unit='pcs'));sid=svc.create_sku(mid)
            child=svc.create_material(dict(base_code='CHILD',version='100',name='长中文物料名称_'+('ContinuousEnglishMaterialCode'*5),unit='pcs'))
            svc.save_bom(mid,[dict(material_id=child,quantity=1.25,unit='pcs',position='安装位置A1')])
            w=BomWindow(svc.for_sku(sid),mid);windows.append(w);w.show();assert QTest.qWaitForWindowExposed(w,3000);settle()
            tree=w.tree;item=w.root_item.child(0)
            initial={c:tree.columnWidth(c) for c in (1,2,3)}
            assert initial[1]<120 and initial[2]<120
            drag(tree,0,230);narrow=tree.visualItemRect(item).height();assert narrow>tree.fontMetrics().height()*3
            assert w.grab().save(str(out/'wrapped_editor.png'))
            drag(tree,0,400);assert tree.visualItemRect(item).height()<narrow
            drag(tree,1,110);drag(tree,2,85);drag(tree,3,170)
            manual={c:tree.columnWidth(c) for c in range(4)}
            assert manual=={0:400,1:110,2:85,3:170},manual
            assert not w.dirty
            QTest.mouseClick(tree.viewport(),Qt.LeftButton,pos=tree.visualItemRect(item).center());w.show_item_info(item)
            w.fields['quantity'].setValue(2.75);assert w.dirty
            tree._bom_columns.fit();settle();assert tree.columnWidth(1)==110
            with patch('ui.main_window.QMessageBox.information'):assert w.save()
            settle();assert tree.currentItem().data(0,Qt.UserRole)['material_id']==child
            assert {c:tree.columnWidth(c) for c in range(4)}==manual
            svc.set_sku_locked(sid,True);browser=BomWindow(svc.for_sku(sid),mid);windows.append(browser);browser.show()
            assert QTest.qWaitForWindowExposed(browser,3000);settle()
            assert browser.is_locked() and {c:browser.tree.columnWidth(c) for c in range(4)}==manual
            assert browser.grab().save(str(out/'remembered_browser.png'))
            fresh_settings=QSettings(str(Path(tmp)/'layout.ini'),QSettings.IniFormat)
            assert json.loads(fresh_settings.value(BomTreeColumns.KEY))=={str(k):v for k,v in manual.items()}
            h=browser.tree.header();point=QPoint(h.sectionViewportPosition(1)+h.sectionSize(1)-1,h.height()//2)
            QTest.mouseDClick(h.viewport(),Qt.LeftButton,pos=point);settle();assert browser.tree.columnWidth(1)<110
            result=dict(passed=True,platform=app.platformName(),checks=['content_widths','long_name_and_code_wrap','height_tracks_drag','actual_drag_persistence','draft_preserved','save_focus_and_widths','locked_browser_restore','settings_disk_roundtrip','double_click_auto_width'],widths=manual,narrow_row_height=narrow)
        finally:
            for w in windows:w.dirty=False;w.close()
            app.sendPostedEvents(None,QEvent.DeferredDelete);db.close()
(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
from tools.run_test_module import release_qt
release_qt()
