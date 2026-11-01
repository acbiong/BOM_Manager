"""Finite native ECN double-click/save/hover/export and compare menu acceptance."""
import argparse,json,os,sys,tempfile,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--platform',required=True,choices=['windows','xcb']);args=parser.parse_args()
os.environ['QT_QPA_PLATFORM']=args.platform;sys.path.insert(0,str(root/'src'))
from PyQt5.QtCore import Qt,QTimer,QEvent,QPoint
from PyQt5.QtGui import QContextMenuEvent,QMouseEvent,QCursor
from PyQt5.QtWidgets import QApplication,QDialogButtonBox,QMenu,QToolTip
from PyQt5.QtTest import QTest
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from ui.sku_ecn import EcnDialog
from ui.bom_compare import BomCompareDialog
from openpyxl import load_workbook
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
out=root/'test_reports'/('ecn_'+args.platform);out.mkdir(parents=True,exist_ok=True)
errors=[];seen=[];target_action='复制物料名称';started=time.monotonic()
def respond():
 try:
  for d in app.topLevelWidgets():
   if not d.isVisible():continue
   if isinstance(d,EcnDialog):
    assert QTest.qWaitForWindowExposed(d,3000)
    d.number.setFocus();QTest.keyClicks(d.number,'ECN-001');d.name.setText('工程变更');d.editor.setPlainText('第一项变更\n第二项变更')
    assert d.grab().save(str(out/'ecn_form.png'));seen.append('ecn_form')
    QTest.mouseClick(d.findChild(QDialogButtonBox).button(QDialogButtonBox.Save),Qt.LeftButton)
   elif isinstance(d,QMenu):
    action=next((a for a in d.actions() if a.text()==target_action),None)
    if action:seen.append(target_action);QTest.mouseClick(d,Qt.LeftButton,pos=d.actionGeometry(action).center())
   if time.monotonic()-started>30 and isinstance(d,(EcnDialog,QMenu)):raise AssertionError('native interaction timed out')
 except Exception as error:
  errors.append(str(error))
  for d in app.topLevelWidgets():
   if isinstance(d,(EcnDialog,QMenu)):d.close()
timer=QTimer();timer.timeout.connect(respond);timer.start(50)
with tempfile.TemporaryDirectory() as tmp:
 db=Database(str(Path(tmp)/'db'));svc=Services(db)
 mid=svc.create_material(dict(base_code='NATIVE',version='100',name='真实窗口测试物料',unit='pcs'));sid=svc.create_sku(mid);sid2=svc.copy_sku_bom(sid)
 main=MainWindow(svc);compare=None;bom=None
 try:
  main.show();assert QTest.qWaitForWindowExposed(main,3000)
  bom=main.open_bom_id(sid2);bom.mark_dirty();main.activateWindow();main.raise_();app.processEvents()
  row=next(i for i in range(main.table.rowCount()) if int(main.table.item(i,6).text())==sid2)
  main.table.scrollToItem(main.table.item(row,8));app.processEvents();point=main.table.visualItemRect(main.table.item(row,8)).center()
  QTest.mouseClick(main.table.viewport(),Qt.LeftButton,pos=point);QTest.mouseDClick(main.table.viewport(),Qt.LeftButton,pos=point);app.processEvents()
  assert not errors,errors
  assert 'ecn_form' in seen and next(r for r in svc.skus() if r['id']==sid2)['ecn_number']=='ECN-001',(seen,[dict(r) for r in svc.skus()])
  assert bom.dirty and main.table.currentColumn()==8,(bom.dirty,main.table.currentColumn())
  point=main.table.visualItemRect(main.table.item(main.table.currentRow(),8)).center();QCursor.setPos(main.table.viewport().mapToGlobal(point))
  app.sendEvent(main.table.viewport(),QMouseEvent(QEvent.MouseMove,point,Qt.NoButton,Qt.NoButton,Qt.NoModifier));QTest.qWait(650)
  assert QToolTip.isVisible() and all(t in QToolTip.text() for t in ('ECN-001','工程变更','第二项变更'))
  assert main.grab().save(str(out/'ecn_column.png'));QToolTip.hideText()
  for name,export in [('sku.xlsx',svc.export_sku_list),('database.xlsx',svc.export_database)]:
   export(out/name);book=load_workbook(out/name)
   try:assert book.sheetnames[1]=='ECN' and book['ECN']['D2'].value=='【101】\n第一项变更\n第二项变更'
   finally:book.close()
  compare=BomCompareDialog(svc,main);compare.left.setCurrentIndex(compare.left.findData(sid));compare.right.setCurrentIndex(compare.right.findData(sid2));compare.compare();compare.show();compare.raise_();compare.activateWindow();assert QTest.qWaitForWindowExposed(compare,3000)
  for side,label,expected in [(0,'复制物料名称','真实窗口测试物料'),(1,'复制物料编码','NATIVE100')]:
   target_action=label;view=compare.tables[side].frozen;point=view.visualRect(view.model().index(0,0)).center()
   app.sendEvent(view.viewport(),QContextMenuEvent(QContextMenuEvent.Mouse,point,view.viewport().mapToGlobal(point)))
   assert label in seen and app.clipboard().text()==expected
  assert not errors,errors
  result=dict(passed=True,platform=app.platformName(),checks=['ecn_double_click','actual_form_save','history_specific_storage','dirty_bom_preserved','selection_retained','full_ecn_hover','sku_and_database_matrix_export','actual_compare_name_copy','actual_compare_code_copy'])
 finally:
  timer.stop()
  if compare:compare.close()
  if bom:bom.dirty=False;bom.close()
  main.close();db.close()
(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
