import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow
from infrastructure.events import WindowRefreshBus

class BomUiTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.db=Database(str(Path(self.tmp.name)/'test.db')); self.s=Services(self.db)
  self.ids=[self.s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ['ROOT','PARENT','CHILD','OTHER','CYCLE']]
  r,p,c,o,x=self.ids
  self.s.save_bom(r,[dict(id=10,material_id=p,quantity=1,unit='pcs'),dict(id=11,parent_item_id=10,material_id=c,quantity=2.3,unit='pcs')])
  self.s.save_bom(x,[dict(material_id=r,quantity=1,unit='pcs')])
  self.w=BomWindow(self.s,r)
 def tearDown(self):
  self.w.dirty=False; self.w.close(); self.db.conn.close(); self.tmp.cleanup()
 def test_material_update_refresh_and_quantity_cache(self):
  r,p,c,o,x=self.ids; parent=self.w.root_item.child(0)
  self.assertEqual(parent.text(1),'1.0')
  self.w.show_item_info(parent); self.w.fields['quantity'].setValue(2.34)
  self.assertEqual(parent.text(1),'2.3')
  self.s.update_material(p,dict(name='修改后的名称',unit='pcs'))
  self.assertTrue(self.w.refresh_action.isEnabled()); self.assertTrue(self.w.statusBar().currentMessage())
  self.w.refresh_external()
  self.assertEqual(self.w.statusBar().currentMessage(),''); self.assertEqual(self.w.notice.text(),'')
  self.assertFalse(self.w.refresh_action.isEnabled()); self.assertTrue(self.w.save_action.isEnabled())
  parent=self.w.root_item.child(0); self.assertIn('修改后的名称',parent.text(0)); self.assertEqual(parent.text(1),'2.3')
  self.w.show_item_info(parent); self.assertEqual(self.w.fields['quantity'].text(),'2.3')
  self.s.update_material(o,dict(name='无关',unit='pcs')); self.assertFalse(self.w.refresh_action.isEnabled())
 def test_sibling_and_child_candidates_block_cycles(self):
  parent=self.w.root_item.child(0); child=parent.child(0)
  for selected,is_child in [(child,False),(parent,True)]:
   with patch.object(QInputDialog,'getItem',return_value=('',False)) as dialog:
    self.w.add_relative(selected.data(0,Qt.UserRole),is_child)
    options=dialog.call_args.args[3]
    self.assertEqual([s.split()[0] for s in options],['OTHER'])
 def test_new_child_quantity_and_export(self):
  parent=self.w.root_item.child(0)
  with patch.object(QInputDialog,'getItem',return_value=('OTHER 1 OTHER',True)):
   self.w.add_relative(parent.data(0,Qt.UserRole),True)
  self.assertEqual(self.w.tree.currentItem().text(1),'1.0'); self.assertEqual(self.w.fields['quantity'].text(),'1.0')
  self.w.fields['quantity'].setValue(3.27)
  with patch.object(QMessageBox,'information'):
   self.w.save()
  self.assertEqual([row['quantity'] for row in self.s.bom(self.ids[0]) if row['material_id']==self.ids[3]],[3.3])
  self.w.load(); self.assertEqual(self.w.root_item.child(0).child(1).text(1),'3.3')
  from openpyxl import load_workbook
  sid=self.s.create_sku(self.ids[0]); path=Path(self.tmp.name)/'bom.xlsx'; self.s.export_sku(sid,path)
  wb=load_workbook(path); self.assertEqual(wb['SKU对应的BOM'].cell(2,9).number_format,'0.0'); wb.close()
