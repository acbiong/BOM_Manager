import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QDialog
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from ui.main_window import MaterialWindow,MaterialDialog,MaterialColumnFilterDialog,MaterialHeaderMappingDialog

class MaterialFilterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.db=Database(str(Path(self.tmp.name)/'test.db')); self.s=Services(self.db)
  for code,unit,manufacturer in [('A','pcs','Alpha'),('B','套','Alpha'),('C','pcs','Beta')]:self.s.create_material(dict(base_code=code,version='1',name=code,unit=unit,manufacturer=manufacturer))
  self.w=MaterialWindow(self.s)
 def tearDown(self):self.w.close(); self.db.close(); self.tmp.cleanup()
 def visible(self):return [self.w.t.item(i,0).text() for i in range(self.w.t.rowCount()) if not self.w.t.isRowHidden(i)]
 def test_combined_filters_refresh_empty_and_clear(self):
  self.w._filters={4:('',{'pcs'}),5:('ALP',None)}; self.w.apply_filters(); self.assertEqual(self.visible(),['A'])
  self.s.create_material(dict(base_code='D',version='1',name='D',unit='pcs',manufacturer='Alpha')); self.assertEqual(self.visible(),['A','D'])
  self.w._filters[4]=('',set()); self.w.apply_filters(); self.assertEqual(self.visible(),[])
  self.w._filters.clear(); self.w.apply_filters(); self.assertEqual(self.visible(),['A','B','C','D'])
 def test_filtered_edit_targets_correct_material(self):
  self.w._filters={0:('',{'C'})}; self.w.apply_filters()
  with patch.object(MaterialDialog,'exec_',return_value=QDialog.Rejected),patch.object(MaterialDialog,'__init__',autospec=True,return_value=None) as init:
   self.w.edit_current(2,0); self.assertEqual(init.call_args.args[2]['base_code'],'C')
 def test_filter_selection_and_blank(self):
  dialog=MaterialColumnFilterDialog('制造商',['','Alpha','Beta']); dialog.set_checks(Qt.Unchecked)
  dialog.list.item(0).setCheckState(Qt.Checked); self.assertEqual(dialog.condition(),('',{''}))
  dialog.set_checks(Qt.Checked); dialog.query.setText('Alpha'); self.assertEqual(dialog.condition(),('Alpha',None)); dialog.close()
 def test_mapping_long_text_gets_full_control_width(self):
  title='很长的源文件表头'*12
  dialog=MaterialHeaderMappingDialog('不存在.xlsx',[title],[]); dialog.show(); self.app.processEvents()
  for column,need in enumerate(dialog.required):
   combo=dialog.combos[need]; combo.setCurrentText(title)
   for _ in range(5):self.app.processEvents()
   self.assertGreaterEqual(dialog.mapping_table.columnWidth(column),combo.sizeHint().width())
   self.assertGreater(combo.width(),combo.fontMetrics().horizontalAdvance(title))
  self.assertGreater(dialog.mapping_table.horizontalScrollBar().maximum(),0); dialog.close()
 def test_mapping_reflows_after_show_theme_font_and_resize(self):
  from PyQt5.QtWidgets import QStyleOptionComboBox,QStyle
  dialog=MaterialHeaderMappingDialog('不存在.xlsx',['制造商字段','版本'],[]); dialog.show()
  for _ in range(4):self.app.processEvents()
  for combo in dialog.combos.values():
   combo.setCurrentText('制造商字段'); combo.setStyleSheet('QComboBox { padding: 10px 24px; font-size: 24px; }')
  dialog.resize(1300,720)
  for _ in range(6):self.app.processEvents()
  for column,need in enumerate(dialog.required):
   combo=dialog.combos[need]; option=QStyleOptionComboBox(); combo.initStyleOption(option)
   rect=combo.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxEditField,combo)
   self.assertGreaterEqual(rect.width(),combo.fontMetrics().horizontalAdvance(combo.currentText()))
   self.assertGreaterEqual(rect.height(),combo.fontMetrics().height())
   self.assertGreaterEqual(dialog.mapping_table.rowHeight(1),combo.sizeHint().height())
  dialog.resize(600,500)
  for _ in range(6):self.app.processEvents()
  self.assertGreater(dialog.mapping_table.horizontalScrollBar().maximum(),0)
  self.assertEqual(dialog.mapping_table.verticalScrollBar().maximum(),0)
  dialog.close()
