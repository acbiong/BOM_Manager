"""物料多条件查找与稳定身份定位回归。"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox
from ui.interactive_windows import QMessageBox
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from ui.main_window import MaterialWindow
from ui.material_search import MaterialSearchDialog

class MaterialSearchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.ids=[self.s.create_material(dict(base_code=code,version='100',name=name,description=spec,unit='pcs',manufacturer=maker,mpn=mpn)) for code,name,spec,maker,mpn in [('B01','电阻','10K 0603','ACME','R100'),('B02','电阻','20K 0603','ACME','R200'),('C01','电容','10uF','Other','C100')]]
  self.w=MaterialWindow(self.s);self.d=MaterialSearchDialog(self.w)
 def tearDown(self):self.d.close();self.w.close();self.db.close();self.tmp.cleanup()
 def test_each_field_and_combined_conditions(self):
  self.assertIn('查找物料',[a.text() for a in self.w.menuBar().actions()])
  for field,value,count in [('code','B01',1),('code','B01100',1),('name','电阻',2),('description','0603',2),('manufacturer',' acme ',2),('mpn','r100',1)]:
   for edit in self.d.fields.values():edit.clear()
   self.d.fields[field].setText(value);self.d.search();self.assertEqual(self.d.table.rowCount(),count)
  self.d.fields['name'].setText('电阻');self.d.fields['description'].setText('20K');self.d.search();self.assertEqual(self.d.table.rowCount(),0)
  self.d.fields['mpn'].setText('r200');self.d.search();self.assertEqual(self.d.table.rowCount(),1)
  self.assertEqual([self.d.table.item(0,c).text() for c in range(6)],['2','B02100','电阻','20K 0603','ACME','R200'])
 def test_double_click_locates_after_row_changes_and_clears_hiding_filter(self):
  self.d.show();self.d.fields['code'].setText('B02');self.d.search()
  self.s.create_material(dict(base_code='A00',version='1',name='插入行',unit='pcs'))
  self.w._filters={2:('电容',None)};self.w.apply_filters()
  self.d.table.cellDoubleClicked.emit(0,0)
  row=self.w.t.currentRow();self.assertEqual(row,2);self.assertEqual(self.w.t.item(row,0).data(Qt.UserRole),self.ids[1]);self.assertFalse(self.w.t.isRowHidden(row));self.assertEqual(self.d.result(),0);self.assertTrue(self.d.isVisible());self.assertFalse(self.d.isModal())
 def test_empty_and_deleted_result(self):
  self.d.search();self.assertEqual(self.d.table.rowCount(),0);self.assertIn('至少',self.d.count_label.text())
  self.d.fields['mpn'].setText('R100');self.d.search();self.s.delete_material(self.ids[0])
  with patch.object(QMessageBox,'information') as info:self.d.locate(0);info.assert_called_once()
  self.assertEqual(self.d.table.rowCount(),0)
