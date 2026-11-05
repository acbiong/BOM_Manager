import os,sys,unittest
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QEvent
from PyQt5.QtWidgets import QApplication,QAbstractItemView,QTabWidget
from services.services import BomImportError
from ui.main_window import BomImportIssuesDialog

class ImportComparisonTableTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_side_by_side_values_paths_and_scrollable_all_errors(self):
  comparison=dict(parent='P100 父物料',material='C100 子物料',field='位置',left_path='SKU / A / P',right_path='SKU / B / P',left_line=212,right_line=234,left='（空）',right='/')
  dialog=BomImportIssuesDialog(BomImportError(['子BOM位置不一致','另有必填项缺失'],[comparison]*40))
  try:
   dialog.show();self.app.processEvents();table=dialog.table
   self.assertEqual(table.rowCount(),40);self.assertEqual(table.columnCount(),7)
   self.assertIn('212',table.item(0,3).text());self.assertIn('234',table.item(0,5).text())
   self.assertEqual(table.item(0,4).text(),'（空）');self.assertEqual(table.item(0,6).text(),'/')
   self.assertTrue(table.item(0,4).font().bold());self.assertEqual(table.editTriggers(),QAbstractItemView.NoEditTriggers)
   self.assertEqual(table.selectionBehavior(),QAbstractItemView.SelectRows)
   self.assertGreater(table.verticalScrollBar().maximum(),0)
   self.assertIn('必填项缺失',dialog.details.toPlainText())
   self.assertIs(dialog.findChild(QTabWidget).currentWidget(),table);self.assertEqual(dialog.windowModality(),Qt.NonModal)
  finally:dialog.close();dialog.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
 def test_absent_child_is_explicit_and_regular_validation_retained(self):
  comparison=dict(parent='P',material='C',field='子物料存在性',left_path='A/P',right_path='B/P',left_line=8,right_line=None,left='存在',right='不存在')
  dialog=BomImportIssuesDialog(BomImportError(['缺少物料'],[comparison]));regular=BomImportIssuesDialog(BomImportError(['单位错误']))
  try:
   self.assertEqual(dialog.table.item(0,6).text(),'不存在');self.assertIn('无对应子项行',dialog.table.item(0,5).text())
   self.assertEqual(regular.details.toPlainText(),'单位错误')
  finally:
   for w in (dialog,regular):w.close();w.deleteLater()
   self.app.sendPostedEvents(None,QEvent.DeferredDelete)

 def test_legacy_conflict_dialog_has_no_override_actions(self):
  from ui.main_window import BomImportConflictDialog
  from PyQt5.QtWidgets import QDialogButtonBox
  dialog=BomImportConflictDialog([])
  try:
   self.assertEqual([b.text() for b in dialog.findChild(QDialogButtonBox).buttons()],['关闭'])
   dialog.finish('incoming');self.assertEqual(dialog.choice,'stop');self.assertEqual(dialog.result(),0)
  finally:dialog.close()

 def test_system_import_states_identify_parent_and_added_missing_children(self):
  base=dict(parent='P100 电机组件',material='C100 转子',left_path='P',right_path='P',left_line=None,right_line=12,comparison_kind='system_import')
  comparisons=[dict(base,field='数量',left='2',right='4'),dict(base,field='子物料存在性',left='不存在',right='存在；数量=1；位置=A'),dict(base,field='子物料存在性',left='存在；数量=2',right='不存在',right_line=None)]
  dialog=BomImportIssuesDialog(BomImportError(['不一致'],comparisons))
  try:
   table=dialog.table
   self.assertEqual(table.horizontalHeaderItem(4).text(),'系统当前子BOM状态')
   self.assertEqual(table.horizontalHeaderItem(6).text(),'待导入子BOM状态')
   self.assertEqual(table.item(0,0).text(),'P100 电机组件')
   self.assertEqual(table.item(0,4).text(),'系统当前数量：2')
   self.assertEqual(table.item(0,6).text(),'待导入数量：4')
   self.assertIn('Excel第12行',table.item(0,5).text())
   self.assertEqual(table.item(1,2).text(),'待导入BOM新增子物料')
   self.assertEqual(table.item(1,4).text(),'系统未包含此子物料')
   self.assertIn('数量=1\n位置=A',table.item(1,6).text())
   self.assertEqual(table.item(2,2).text(),'待导入BOM缺少子物料')
   self.assertEqual(table.item(2,6).text(),'待导入BOM未包含此子物料')
   self.assertIn('文件中没有此子物料行',table.item(2,5).text())
  finally:dialog.close()
