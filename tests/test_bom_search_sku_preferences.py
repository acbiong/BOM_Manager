import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication,QDialog,QListWidget
from ui.interactive_windows import QDialog
from database.database import Database
from services.services import Services
from config.config_service import ConfigService
from ui.main_window import MaterialWindow,BomWindow
from ui.material_search import BomSearchDialog

class SearchPreferencesTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_sku_defaults_persistence_new_skus_and_database_isolation(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));svc=Services(db)
   def create(code):return svc.create_sku(svc.create_material(dict(base_code=code,version='1',name=code,unit='pcs')))
   a=create('A');b=create('B');w=MaterialWindow(svc)
   try:
    self.assertEqual(w._hidden_skus,{a,b})
    def select(dialog):
     choices=dialog.findChild(QListWidget)
     for i in range(choices.count()):choices.item(i).setCheckState(Qt.Checked if choices.item(i).data(Qt.UserRole)==a else Qt.Unchecked)
     return QDialog.Accepted
    with patch.object(QDialog,'exec_',select):w.choose_sku_columns()
    w.close();w=MaterialWindow(svc)
    self.assertEqual(w._hidden_skus,{b});self.assertFalse(w.t.isColumnHidden(11))
    c=create('C');self.assertIn(c,w._hidden_skus)
    config=ConfigService(tmp);self.assertEqual(config.sku_columns(db.path),{a})
    self.assertEqual(config.sku_columns(str(Path(tmp)/'different.db')),set())
    config.save_sku_columns(db.path,set());w.close();w=MaterialWindow(svc)
    self.assertEqual(w._hidden_skus,{a,b,c})
   finally:w.close();db.close()
 def test_bom_search_paths_draft_deleted_no_results_and_refresh(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));svc=Services(db)
   ids={code:svc.create_material(dict(base_code=code,version='1',name=code,description='规格',manufacturer='ACME',mpn='PN',unit='pcs')) for code in ('R','A','B','C','D')}
   for parent in ('A','B'):svc.save_bom(ids[parent],[dict(material_id=ids['C'],quantity=1,unit='pcs')])
   svc.save_bom(ids['R'],[dict(material_id=ids[x],quantity=1,unit='pcs') for x in ('A','B')])
   w=BomWindow(svc,ids['R']);d=BomSearchDialog(w)
   try:
    self.assertEqual(d.windowTitle(),'R1 R 物料查找')
    d.fields['code'].setText('C1');d.fields['manufacturer'].setText('acme');d.search()
    self.assertEqual(d.table.rowCount(),2)
    w.tree.collapseAll();d.locate(1)
    self.assertEqual(w.tree.currentItem().parent().data(0,Qt.UserRole)['material_id'],ids['B'])
    self.assertTrue(w.tree.currentItem().parent().isExpanded())
    # Search paths remain valid after a complete tree rebuild.
    w.load();d.locate(0)
    self.assertEqual(w.tree.currentItem().parent().data(0,Qt.UserRole)['material_id'],ids['A'])
    data=dict(next(m for m in svc.materials() if m['id']==ids['D']));data['material_id']=ids['D'];data['quantity']=1;data['position']='';data['remark']=''
    w.insert_material(w.root_item,data)
    d.fields['code'].setText('D1');d.search();self.assertEqual(d.table.rowCount(),1)
    w.remove_relation(w.tree.currentItem());d.search();self.assertEqual(d.table.rowCount(),0);self.assertEqual(d.count_label.text(),'未查到物料')
    d.fields['code'].setText('C1');d.fields['mpn'].setText('missing');d.search();self.assertEqual(d.table.rowCount(),0)
   finally:w.dirty=False;d.close();w.close();db.close()
