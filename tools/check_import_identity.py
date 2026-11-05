"""Native mismatch table inspection against a disposable isolated SKU."""
import sys,os,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'src'),str(root/'tests')]
os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'xcb'
from PyQt5.QtWidgets import QApplication,QDialogButtonBox
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
app=QApplication([])
from ui.theme import apply_theme
apply_theme(False)
from test_bom_import_conflicts import BomImportConflictTests
from services.services import BomImportError
from ui.main_window import BomImportIssuesDialog
case=BomImportConflictTests();case.setUp()
out=root/'test_reports/import_identity_native';out.mkdir(parents=True,exist_ok=True)
try:
 before=list(case.db.conn.iterdump())
 case.write([('R','A',1,''),('A','B',4,'新位置'),('B','D',5,'')])
 try:case.s.import_bom(case.path,case.ids['R'],persist=False)
 except BomImportError as error:
  dialog=BomImportIssuesDialog(error);dialog.show()
  try:
   assert QTest.qWaitForWindowExposed(dialog,3000)
   assert dialog.table.rowCount()==4 and dialog.windowModality()==Qt.NonModal
   assert '系统物料库' in dialog.table.item(0,3).text()
   assert '待导入' in dialog.table.item(0,5).text()
   buttons=dialog.findChild(QDialogButtonBox)
   assert len(buttons.buttons())==1
   assert dialog.grab().save(str(out/'blocked_comparison.png'))
   QTest.mouseClick(buttons.button(QDialogButtonBox.Close),Qt.LeftButton)
   assert not dialog.isVisible()
  finally:dialog.close()
 else:raise AssertionError('Conflicting import was not rejected')
 assert before==list(case.db.conn.iterdump())
 (out/'summary.json').write_text(json.dumps(dict(passed=True,differences=4,nonmodal=True,continue_not_available=True,database_unchanged=True),indent=2))
finally:case.tearDown()
print('IMPORT_IDENTITY_NATIVE_OK')
