"""One-shot native save-preview/cancel/no-op check on a disposable database."""
import argparse,json,os,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--platform',choices=['windows','xcb'],required=True);args=parser.parse_args()
os.environ['QT_QPA_PLATFORM']=args.platform;sys.path[:0]=[str(root/'src'),str(root/'tests')]
from PyQt5.QtCore import Qt,QTimer
from PyQt5.QtWidgets import QApplication,QMessageBox,QDialogButtonBox
from PyQt5.QtTest import QTest
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
from test_pending_history_diff import PendingHistoryDiffTests
from ui.material_history import MaterialHistoryChoiceDialog
from ui.parent_revision import ParentRevisionDialog
os.environ['QT_QPA_PLATFORM']=args.platform
out=root/'test_reports'/('pending_history_'+args.platform);out.mkdir(parents=True,exist_ok=True)
case=PendingHistoryDiffTests();case.setUp();w=case.w
errors=[];seen=[];phase='cancel';started=time.monotonic()

def respond():
 try:
  for dialog in app.topLevelWidgets():
   if not dialog.isVisible() or dialog is w:continue
   if time.monotonic()-started>30:raise AssertionError('interaction timeout')
   if isinstance(dialog,ParentRevisionDialog):raise AssertionError('unexpected parent revision')
   if isinstance(dialog,MaterialHistoryChoiceDialog):
    assert phase!='noop','No-op opened a history prompt'
    assert QTest.qWaitForWindowExposed(dialog,3000)
    assert dialog.diff_table.rowCount()==1
    values=[dialog.diff_table.item(0,c).text() for c in range(5)]
    if phase=='cancel':assert values[2:] == ['数量','2','3'],values
    else:assert values[0]=='新增' and values[2]=='替代料' and 'A100' in values[4],values
    assert dialog.grab().save(str(out/(phase+'_preview.png')))
    seen.append(phase)
    button=QDialogButtonBox.Cancel if phase=='cancel' else QDialogButtonBox.Ok
    QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(button),Qt.LeftButton)
   elif isinstance(dialog,QMessageBox):
    button=dialog.button(QMessageBox.Ok)
    if button:QTest.mouseClick(button,Qt.LeftButton)
 except Exception as error:
  errors.append(str(error))
  for dialog in app.topLevelWidgets():
   if dialog is not w and dialog.isVisible() and hasattr(dialog,'reject'):dialog.reject()

timer=QTimer();timer.timeout.connect(respond);timer.start(50)
try:
 w.show();assert QTest.qWaitForWindowExposed(w,3000)
 item=w.root_item.child(0).child(0);w.tree.setCurrentItem(item)
 original=dict(item.data(0,Qt.UserRole));before=list(case.db.conn.iterdump())
 item.setData(0,Qt.UserRole,dict(original,quantity=3));item.setText(1,'3');w.dirty=True
 assert not w.save();assert not errors,errors
 assert before==list(case.db.conn.iterdump()) and item.text(1)=='3'
 assert w.dirty and w.tree.currentItem() is item
 phase='noop';item.setData(0,Qt.UserRole,original);item.setText(1,'2')
 versions=list(case.db.conn.execute('SELECT * FROM material_histories'))
 assert w.save();assert not errors,errors
 assert versions==list(case.db.conn.execute('SELECT * FROM material_histories'))
 phase='save';item=w.root_item.child(0).child(0)
 w._alternate_edits[w.alternate_key(item)]=[case.a];w.dirty=True
 old_rows=case.old.bom(case.r);old_version=case.old.material_snapshot(case.p)['history_version']
 assert w.save();assert not errors,errors
 assert seen==['cancel','save'],seen
 assert case.old.bom(case.r)==old_rows and case.old.material_snapshot(case.p)['history_version']==old_version
 assert [a['material_id'] for a in case.new.alternates(case.new.bom(case.p)[0]['id'])]==[case.a]
 assert w.tree.currentItem().data(0,Qt.UserRole)['material_id']==case.c
 assert w.grab().save(str(out/'saved.png'))
 result=dict(passed=True,platform=app.platformName(),checks=['actual_diff_window','before_after_values','actual_cancel','cancel_preserves_database','cancel_preserves_draft_focus','revert_save_without_prompt','no_op_keeps_history','actual_confirm_save','unselected_bom_unchanged','saved_selection_preserved'])
finally:
 timer.stop();case.tearDown()
(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
