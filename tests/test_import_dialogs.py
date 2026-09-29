import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from openpyxl import Workbook
from PyQt5.QtWidgets import QApplication,QDialog,QMessageBox
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
   self.assertEqual((dialog.mapping_table.rowCount(),dialog.mapping_table.columnCount()),(2,7))
   for column,need in enumerate(dialog.required):
    self.assertEqual(dialog.mapping_table.item(0,column).text(),need)
    self.assertIs(dialog.mapping_table.cellWidget(1,column),dialog.combos[need])
    dialog.combos[need].setCurrentText(headers[column])
   dialog.combos[dialog.required[-1]].setCurrentIndex(0)
   with patch.object(QMessageBox,'warning') as warning:
    dialog.validate_mapping(); self.assertEqual(dialog.result(),QDialog.Rejected); self.assertIn('物料MPN',warning.call_args.args[2])
   self.assertEqual(dialog.mapping()[dialog.required[0]],'编码')
   dialog.combos[dialog.required[-1]].setCurrentText('料号'); dialog.validate_mapping()
   self.assertEqual(dialog.result(),QDialog.Accepted); dialog.close()
