import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox,QDialog
from ui.interactive_windows import QMessageBox
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from ui.main_window import NewSkuDialog
class NewSkuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=str(Path(self.tmp.name)/'db');self.db=Database(self.path);self.s=Services(self.db)
  self.ids=[self.s.create_material(dict(base_code=code,version='100',name=name,unit='pcs')) for code,name in [('AAA','电源'),('BBB','组件'),('CCC','零件')]]
  self.s.save_bom(self.ids[1],[dict(material_id=self.ids[2],quantity=1,unit='pcs')])
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def test_filter_and_disabled_selection(self):
  dialog=NewSkuDialog(self.s)
  dialog.filter_materials('bbb');self.assertEqual(dialog.proxy.rowCount(),1);self.assertFalse(dialog.proxy.flags(dialog.proxy.index(0,0)) & Qt.ItemIsEnabled)
  dialog.combo.setEditText(dialog.model.item(1).text())
  with patch.object(QMessageBox,'warning'):dialog.accept();self.assertEqual(dialog.result(),QDialog.Rejected)
  dialog.filter_materials('电源');self.assertEqual(dialog.proxy.rowCount(),1)
  dialog.combo.setEditText(dialog.model.item(0).text());dialog.accept();self.assertEqual(dialog.material_id,self.ids[0]);dialog.close()
  with self.assertRaises(ValueError):self.s.create_sku(self.ids[1],require_empty_bom=True)
 def test_delete_clears_root_bom_and_alternates_preserves_shared_child_bom(self):
  root,parent,child=self.ids;sid=self.s.create_sku(root,require_empty_bom=True)
  self.s.save_bom(root,[dict(material_id=parent,quantity=1,unit='pcs')]+[dict(row) for row in self.s.bom(parent)])
  relation=self.s.bom(root)[0]['id'];self.s.add_alternate(relation,child)
  self.s.delete_sku(sid);self.assertEqual(self.s.bom(root),[]);self.assertEqual(self.s.alternates(relation),[]);self.assertEqual(len(self.s.bom(parent)),1)
  self.assertEqual(self.s.material_snapshot(root)['has_bom'],0)
  self.db.close();self.db=Database(self.path);self.s=Services(self.db);self.assertEqual(self.s.bom(root),[])
