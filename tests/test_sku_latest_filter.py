import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from database.database import Database
from services.services import Services
from config.config_service import ConfigService
from ui.main_window import MainWindow

class LatestSkuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db,ConfigService(self.tmp.name))
  self.a=self.s.create_sku(self.s.create_material(dict(base_code='A',version='1',name='A',unit='pcs')))
  self.a2=self.s.copy_sku_bom(self.a);self.s.change_mirror_version(self.a,9)
  self.b=self.s.create_sku(self.s.create_material(dict(base_code='B',version='1',name='B',unit='pcs')))
  self.b2=self.s.copy_sku_bom(self.b)
  self.c=self.s.create_sku(self.s.create_material(dict(base_code='A',version='2',name='A新版',unit='pcs')))
  self.w=MainWindow(self.s)
 def tearDown(self):self.w.close();self.db.close();self.tmp.cleanup()
 def visible(self):return {int(self.w.table.item(i,6).text()) for i in range(self.w.table.rowCount()) if not self.w.table.isRowHidden(i)}
 def test_numeric_latest_per_sku_toggle_sort_and_count(self):
  self.assertFalse(self.w.latest_bom_only.isChecked());self.assertEqual(self.visible(),{self.a,self.a2,self.b,self.b2,self.c})
  self.w.latest_bom_only.setChecked(True);self.assertEqual(self.visible(),{self.a2,self.b2,self.c});self.assertEqual(self.w.count_label.text(),'显示3 / 共计5个SKU')
  for col in (1,2,4,5):
   self.w.sort_skus(col);self.w.sort_skus(col);self.assertEqual(self.visible(),{self.a2,self.b2,self.c})
  self.w.latest_bom_only.setChecked(False);self.assertEqual(len(self.visible()),5);self.assertEqual(self.w.count_label.text(),'共计5个SKU')
 def test_existing_filters_are_intersected_without_old_version_fallback(self):
  self.w._sku_filters={4:('',{'9'})};self.w.apply_sku_filters();self.assertEqual(self.visible(),{self.a})
  self.w.latest_bom_only.setChecked(True);self.assertEqual(self.visible(),set())
  self.w.latest_bom_only.setChecked(False);self.assertEqual(self.visible(),{self.a})
  self.w._sku_filters.clear();self.w.apply_sku_filters();self.assertEqual(len(self.visible()),5)
 def test_live_copy_version_change_and_delete_recompute_latest(self):
  self.w.latest_bom_only.setChecked(True)
  copied=self.s.copy_sku_bom(self.a2);self.assertEqual(self.visible(),{copied,self.b2,self.c})
  self.s.change_mirror_version(self.a,1000);self.assertEqual(self.visible(),{self.a,self.b2,self.c})
  self.s.delete_sku(self.a);self.assertEqual(self.visible(),{copied,self.b2,self.c});self.assertTrue(self.w.latest_bom_only.isChecked())
 def test_empty_list(self):
  for sku in list(self.s.skus()):self.s.delete_sku(sku['id'])
  self.w.latest_bom_only.setChecked(True);self.assertEqual(self.visible(),set());self.assertEqual(self.w.count_label.text(),'显示0 / 共计0个SKU')
