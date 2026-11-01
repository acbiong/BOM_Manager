"""One-shot native interaction: swap, delete new alternate, save and retain focus."""
import argparse,json,os,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--platform',choices=['windows','xcb'],required=True);args=parser.parse_args()
os.environ['QT_QPA_PLATFORM']=args.platform;sys.path[:0]=[str(root/'src'),str(root/'tests')]
from PyQt5.QtCore import Qt,QTimer
from PyQt5.QtWidgets import QApplication,QMenu,QMessageBox,QDialogButtonBox
from PyQt5.QtTest import QTest
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
from test_role_swap_history import RoleSwapHistoryTests
from ui.main_window import BomWindow
from ui.parent_revision import ParentRevisionDialog
from ui.material_history import MaterialHistoryChoiceDialog
os.environ['QT_QPA_PLATFORM']=args.platform
out=root/'test_reports'/('swap_save_view_'+args.platform);out.mkdir(parents=True,exist_ok=True)
case=RoleSwapHistoryTests();case.setUp();w=BomWindow(case.new,case.r);errors=[];seen=[];started=time.monotonic()
def respond():
 try:
  for dialog in app.topLevelWidgets():
   if not dialog.isVisible() or dialog is w:continue
   if isinstance(dialog,ParentRevisionDialog):errors.append('unexpected parent revision');dialog.reject()
   elif isinstance(dialog,QMenu):
    action=next((a for a in dialog.actions() if a.text()=='删除替代料'),None)
    if action:seen.append('delete_menu');QTest.mouseClick(dialog,Qt.LeftButton,pos=dialog.actionGeometry(action).center())
   elif isinstance(dialog,QMessageBox):
    button=dialog.button(QMessageBox.Yes) or dialog.button(QMessageBox.Ok)
    if button:seen.append(dialog.windowTitle());QTest.mouseClick(button,Qt.LeftButton)
   elif isinstance(dialog,MaterialHistoryChoiceDialog):
    dialog.select_all(False);QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton)
   if time.monotonic()-started>25 and hasattr(dialog,'reject'):errors.append('interaction timeout');dialog.reject()
 except Exception as error:errors.append(str(error))
timer=QTimer();timer.timeout.connect(respond);timer.start(50)
try:
 w.show();assert QTest.qWaitForWindowExposed(w,3000)
 before=list(case.db.conn.iterdump());node=w.promote_alternate(w.root_item.child(0).child(0),case.a)
 w.show_item_info(node);app.processEvents()
 w.alternate_menu(w.alt_table.visualItemRect(w.alt_table.item(0,0)).center())
 assert not errors,errors
 assert not w.alternate_ids(node) and before==list(case.db.conn.iterdump())
 assert w.grab().save(str(out/'unsaved_swap_delete.png'))
 w.tree.setCurrentItem(node);assert w.save();app.processEvents()
 assert not errors,errors
 assert w.tree.currentItem().data(0,Qt.UserRole)['material_id']==case.a
 assert w.current_item is w.tree.currentItem()
 assert case.new.material_snapshot(case.p)['version']=='100'
 assert not case.new.alternates(case.new.bom(case.p)[0]['id'])
 assert case.old.bom(case.p)[0]['material_id']==case.c
 assert w.grab().save(str(out/'saved_same_selection.png'))
 assert 'delete_menu' in seen and '确认' in seen and '保存' in seen,seen
 result=dict(passed=True,platform=app.platformName(),checks=['actual_delete_menu_and_confirmation','unsaved_swap_delete_no_parent_revision','database_untouched_before_save','actual_save_dialog','selection_and_details_retained','parent_code_unchanged','other_bom_preserved'])
finally:
 timer.stop();w.dirty=False;w.close();case.tearDown()
(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
