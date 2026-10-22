import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from openpyxl import Workbook
from PyQt5.QtWidgets import QApplication,QDialog,QMessageBox
from ui.interactive_windows import QMessageBox
from ui.main_window import MaterialHeaderMappingDialog,MaterialImportResultDialog

class ImportDialogTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_long_results_scroll_to_last_complete_reason(self):
  fail=[(i+2,f'CODE{i}',f'物料{i}','详细失败原因'*100) for i in range(300)]
  dialog=MaterialImportResultDialog(['成功'],fail); dialog.show(); self.app.processEvents()
  self.assertLessEqual(dialog.height(),dialog.maximumHeight())
  self.assertLessEqual(dialog.maximumHeight(),640)
  bar=dialog.details.verticalScrollBar(); self.assertGreater(bar.maximum(),0)
  bar.setValue(bar.maximum()); self.app.processEvents()
  self.assertEqual(bar.value(),bar.maximum())
  self.assertIn('CODE299 物料299',dialog.details.toPlainText())
  self.assertTrue(dialog.details.toPlainText().endswith('详细失败原因'*100))
  dialog.close()
 def test_two_row_mapping_validates_and_preserves_choices(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'input.xlsx'; headers=['编码','版本','名称','描述','单位','厂家','料号']
   wb=Workbook(); wb.active.append(headers); wb.active.append(['A','1','名称','','pcs','厂家','M']); wb.save(path); wb.close()
   dialog=MaterialHeaderMappingDialog(path,headers,headers)
   self.assertEqual((dialog.mapping_table.rowCount(),dialog.mapping_table.columnCount()),(2,9))
   for column,need in enumerate(dialog.required):
    self.assertEqual(dialog.mapping_table.item(0,column).text(),need if need in dialog.optional else need+' *')
    self.assertIs(dialog.mapping_table.cellWidget(1,column),dialog.combos[need])
    if need not in dialog.optional:dialog.combos[need].setCurrentText(headers[[field for field in dialog.required if field not in dialog.optional].index(need)])
   dialog.combos[dialog.required[-1]].setCurrentIndex(0)
   with patch.object(QMessageBox,'warning') as warning:
    dialog.validate_mapping(); self.assertEqual(dialog.result(),QDialog.Rejected); self.assertIn('物料MPN',warning.call_args.args[2])
   self.assertEqual(dialog.mapping()[dialog.required[0]],'编码')
   dialog.combos[dialog.required[-1]].setCurrentText('料号'); dialog.validate_mapping()
   self.assertEqual(dialog.result(),QDialog.Accepted); dialog.close()
 def test_results_separate_auto_skips_and_errors(self):
  rows=[(2,'ERR','失败物料','必填项缺失：单位'),(3,'SAME','重复物料','重复物料信息相同，自动跳过'),(4,'SKIP','手动跳过','跳过重复物料')]
  dialog=MaterialImportResultDialog(['OK'],rows)
  self.assertEqual([dialog.tabs.tabText(i) for i in range(3)],['导入失败（1）','自动跳过（1）','其他未导入（1）'])
  self.assertIn('ERR 失败物料',dialog.details.toPlainText());self.assertNotIn('SAME',dialog.details.toPlainText())
  self.assertIn('SAME 重复物料',dialog.skipped_details.toPlainText());self.assertNotIn('ERR',dialog.skipped_details.toPlainText())
  self.assertIn('SKIP 手动跳过',dialog.other_details.toPlainText());dialog.close()
 def test_preview_both_scrollbars_reach_overflow(self):
  from PyQt5.QtCore import Qt
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'wide.xlsx';wb=Workbook();headers=['字段'+str(i)+'较长的名称'*4 for i in range(20)];wb.active.append(headers)
   for i in range(30):wb.active.append([str(i)+'行内容'*20]*20)
   wb.save(path);wb.close();dialog=MaterialHeaderMappingDialog(path,headers,headers);dialog.resize(600,420);dialog.show();self.app.processEvents()
   self.assertEqual(dialog.preview.horizontalScrollBarPolicy(),Qt.ScrollBarAsNeeded);self.assertEqual(dialog.preview.verticalScrollBarPolicy(),Qt.ScrollBarAlwaysOn)
   for bar in (dialog.preview.horizontalScrollBar(),dialog.preview.verticalScrollBar()):
    self.assertGreater(bar.maximum(),0);bar.setValue(bar.maximum());self.assertEqual(bar.value(),bar.maximum())
   dialog.close()
 def test_conflict_two_rows_highlight_changed_fields_and_choices(self):
  from ui.main_window import MaterialConflictDialog
  from PyQt5.QtGui import QColor
  incoming={'物料基础编码':'A','物料版本号':'100','物料名称':'新名称','物料规格描述':'新描述','单位':'pcs','物料制造商':'厂','物料MPN':'123'}
  existing=dict(base_code='A',version='100',name='旧名称',description='旧描述',unit='pcs',manufacturer='厂',mpn='123')
  dialog=MaterialConflictDialog(incoming,existing)
  self.assertEqual(dialog.table.rowCount(),2);self.assertEqual(dialog.table.item(0,2).text(),'旧名称');self.assertEqual(dialog.table.item(1,2).text(),'新名称')
  for row in (0,1):self.assertEqual(dialog.table.item(row,2).background().color(),QColor('#ffe082'))
  self.assertEqual(dialog.choice,'cancel')
  for choice in ('overwrite','skip','cancel'):dialog.finish(choice);self.assertEqual(dialog.choice,choice)
  dialog.close()
 def test_mapping_width_tracks_selected_column_not_longest_unselected_option(self):
  from PyQt5.QtCore import Qt
  long='非常长的表头名称'*20
  dialog=MaterialHeaderMappingDialog('不存在.xlsx',['编码',long],[]);dialog.show()
  combo=dialog.combos[dialog.required[0]];combo.setCurrentText('编码')
  for _ in range(5):self.app.processEvents()
  initial=dialog.mapping_table.columnWidth(0);combo.setCurrentText(long)
  for _ in range(5):self.app.processEvents()
  expanded=dialog.mapping_table.columnWidth(0);self.assertGreater(expanded,initial)
  self.assertLess(dialog.mapping_table.columnWidth(1),expanded)
  combo.setCurrentText('编码')
  for _ in range(5):self.app.processEvents()
  self.assertLess(dialog.mapping_table.columnWidth(0),expanded)
  self.assertEqual(dialog.mapping_table.horizontalScrollBarPolicy(),Qt.ScrollBarAlwaysOn);dialog.close()
