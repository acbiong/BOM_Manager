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
