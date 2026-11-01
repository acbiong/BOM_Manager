"""Bounded native-window verification of confirmed parent revisions."""
import argparse,json,os,sys
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--platform',choices=['windows','xcb'],required=True);args=parser.parse_args()
os.environ['QT_QPA_PLATFORM']=args.platform
sys.path[:0]=[str(root/'src'),str(root/'tests')]
from PyQt5.QtCore import Qt,QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication,QDialogButtonBox
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
from test_parent_revision_draft import ParentRevisionDraftTests
from test_role_swap_history import RoleSwapHistoryTests
from ui.parent_revision import ParentRevisionDialog
from ui.main_window import MaterialDialog
from services import history_selection as hs
os.environ['QT_QPA_PLATFORM']=args.platform
out=root/'test_reports'/('parent_draft_'+args.platform);out.mkdir(parents=True,exist_ok=True)
case=ParentRevisionDraftTests();case.setUp();errors=[]
try:
 w=case.w;w.show();assert QTest.qWaitForWindowExposed(w,3000)
 before=list(case.db.conn.iterdump());original=ParentRevisionDialog.exec_
 def confirm(dialog):
  def click():
   try:
    assert QTest.qWaitForWindowExposed(dialog,3000)
    dialog.combos[case.p].setEditText('101')
    assert dialog.grab().save(str(out/'parent_confirmation.png'))
    QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton)
   except BaseException as error:errors.append(str(error));dialog.reject()
  QTimer.singleShot(50,click)
  return original(dialog)
 values={**case.new.material_snapshot(case.c),'name':'子物料变更'}
 with patch.object(w,'choose_material_history',return_value=hs.select(case.new,case.c)),patch.object(MaterialDialog,'exec_',return_value=MaterialDialog.Accepted),patch.object(MaterialDialog,'data',return_value=values),patch.object(ParentRevisionDialog,'exec_',confirm):
  w.edit_tree_material(w.root_item.child(0).child(0))
 assert not errors,errors
 case.assert_pending();assert before==list(case.db.conn.iterdump())
 assert w.grab().save(str(out/'pending_parent.png'))
 w.history.undo();assert 'P100' in w.root_item.child(0).text(0)
 w.history.redo();case.assert_pending()
 w.refresh_external();case.assert_pending()
finally:case.tearDown()
swap=RoleSwapHistoryTests();swap.setUp()
try:swap.test_native_editor_swap_undo_save_and_reopen_without_parent_prompt()
finally:swap.tearDown()
result=dict(passed=True,platform=app.platformName(),checks=['actual_parent_dialog_confirmation','immediate_tree_info_comparison','no_database_write_before_save','undo_redo','external_refresh_preserves_draft','swap_save_reopen_without_parent_revision'])
(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
