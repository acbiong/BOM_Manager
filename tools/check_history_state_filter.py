"""One-shot native deletion/reminder/save check on a disposable database."""
import argparse,json,os,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--platform',choices=['windows','xcb'],required=True);args=parser.parse_args()
os.environ['QT_QPA_PLATFORM']=args.platform;sys.path[:0]=[str(root/'src'),str(root/'tests')]
from PyQt5.QtCore import Qt,QTimer
from PyQt5.QtWidgets import QApplication,QMenu,QMessageBox,QDialogButtonBox,QPushButton
from PyQt5.QtTest import QTest
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
from test_history_state_filter import HistoryStateFilterTests
from ui.material_history import MaterialHistoryChoiceDialog
from ui.parent_revision import ParentRevisionDialog
os.environ['QT_QPA_PLATFORM']=args.platform
out=root/'test_reports'/('history_filter_'+args.platform);out.mkdir(parents=True,exist_ok=True)
case=HistoryStateFilterTests();case.setUp();case.add_other();case.s.set_sku_locked(case.sid,True)
w=case.w;errors=[];seen=[];started=time.monotonic()
def respond():
 try:
  for dialog in app.topLevelWidgets():
   if not dialog.isVisible() or dialog is w:continue
   if time.monotonic()-started>25:raise AssertionError('interaction timeout')
   if isinstance(dialog,ParentRevisionDialog):raise AssertionError('unexpected parent revision')
   if isinstance(dialog,QMenu):
    action=next((a for a in dialog.actions() if a.text()=='删除替代料'),None)
    if action:seen.append('menu');QTest.mouseClick(dialog,Qt.LeftButton,pos=dialog.actionGeometry(action).center())
   elif isinstance(dialog,MaterialHistoryChoiceDialog):
    assert QTest.qWaitForWindowExposed(dialog,3000)
    assert [dialog.table.item(i,0).data(Qt.UserRole) for i in range(dialog.table.rowCount())]==[case.tid]
    assert dialog.mode().matching_sku_ids=={case.sid}
    assert dialog.grab().save(str(out/'differing_bom_only.png'))
    button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='全选可变更BOM')
    QTest.mouseClick(button,Qt.LeftButton);assert dialog.mode().sku_ids=={case.tid}
    seen.append('filtered_selection');QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton)
   elif isinstance(dialog,QMessageBox):
    button=dialog.button(QMessageBox.Yes) or dialog.button(QMessageBox.Ok)
    if button:seen.append(dialog.windowTitle());QTest.mouseClick(button,Qt.LeftButton)
 except Exception as error:
  errors.append(str(error))
  for dialog in app.topLevelWidgets():
   if dialog is not w and dialog.isVisible() and hasattr(dialog,'reject'):dialog.reject()
timer=QTimer();timer.timeout.connect(respond);timer.start(50)
try:
 w.show();assert QTest.qWaitForWindowExposed(w,3000)
 item=w.root_item.child(0).child(0);w.tree.setCurrentItem(item);w.show_item_info(item);app.processEvents()
 before=list(case.db.conn.iterdump());old_rows=case.old.bom(case.r);old_version=case.old.material_snapshot(case.p)['history_version']
 timestamp=next(s['updated_at'] for s in case.s.skus() if s['id']==case.sid)
 w.alternate_menu(w.alt_table.visualItemRect(w.alt_table.item(0,0)).center())
 assert not errors,errors
 assert not w.alternate_ids(item) and before==list(case.db.conn.iterdump())
 assert w.save();app.processEvents();assert not errors,errors
 assert not case.new.alternates(case.new.bom(case.p)[0]['id'])
 assert not case.other.alternates(case.other.bom(case.p)[0]['id'])
 assert case.old.bom(case.r)==old_rows and case.old.material_snapshot(case.p)['history_version']==old_version
 assert next(s['updated_at'] for s in case.s.skus() if s['id']==case.sid)==timestamp
 assert w.tree.currentItem().data(0,Qt.UserRole)['material_id']==case.c
 assert w.grab().save(str(out/'saved.png'))
 assert all(s in seen for s in ('menu','确认','filtered_selection','保存')),seen
 result=dict(passed=True,platform=app.platformName(),checks=['actual_delete_menu_and_confirm','only_differing_bom_visible','identical_locked_bom_hidden','actual_select_and_confirm','no_write_before_save','selected_target_synchronized','matching_bom_and_timestamp_unchanged','save_keeps_selection'])
finally:
 timer.stop();case.tearDown()
(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
