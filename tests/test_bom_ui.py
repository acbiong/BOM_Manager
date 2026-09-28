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
 def test_shared_sub_bom_save_twice_and_edit(self):
  # CHILD已有下阶物料，添加为ROOT的另一个子项时再次展开同一关系。
  r,p,c,o,x=self.ids
  self.s.save_bom(c,[dict(material_id=o,quantity=1,unit='pcs')]); self.w.load()
  with patch.object(QInputDialog,'getItem',return_value=('CHILD 1 CHILD',True)):
   self.w.add_relative(self.w.root_item.data(0,Qt.UserRole),True)
  self.assertEqual(self.w.tree.currentItem().childCount(),1)
  with patch.object(QMessageBox,'information'), patch.object(QMessageBox,'warning') as warning:
   self.assertTrue(self.w.save()); self.assertTrue(self.w.save()); warning.assert_not_called()
  count=self.db.conn.execute('SELECT count(*) FROM material_bom_items WHERE parent_material_id=? AND child_material_id=?',(c,o)).fetchone()[0]
  self.assertEqual(count,1)
  self.w.show_item_info(self.w.root_item.child(0)); self.w.fields['quantity'].setValue(4.2)
  with patch.object(QMessageBox,'information'): self.assertTrue(self.w.save())
  self.assertEqual(self.s.bom(r)[0]['quantity'],4.2)
 def test_save_failure_keeps_edit_and_close_cancelled(self):
  import sqlite3
  from PyQt5.QtGui import QCloseEvent
  self.w.show_item_info(self.w.root_item.child(0)); self.w.fields['quantity'].setValue(5.6)
  with patch.object(self.s,'save_bom',side_effect=sqlite3.IntegrityError('constraint test')), patch.object(QMessageBox,'warning') as warning:
   self.assertFalse(self.w.save()); warning.assert_called_once()
   self.assertTrue(self.w.dirty); self.assertFalse(self.w._saving); self.assertTrue(self.w.save_action.isEnabled())
   self.assertEqual(self.w.root_item.child(0).text(1),'5.6')
   with patch('ui.main_window.QMessageBox') as box:
    save,discard,cancel=object(),object(),object()
    box.return_value.addButton.side_effect=[save,discard,cancel]; box.return_value.clickedButton.return_value=save
    event=QCloseEvent(); self.w.closeEvent(event); self.assertFalse(event.isAccepted())
 def test_conflicting_shared_edits_do_not_write(self):
  r,p,c,o,x=self.ids
  before=[dict(row) for row in self.db.conn.execute('SELECT * FROM material_bom_items')]
  rows=[dict(material_id=p,parent_material_id=r,quantity=q,unit='pcs') for q in (2,3)]
  with self.assertRaisesRegex(ValueError,'共享子BOM'):
   self.s.save_bom(r,rows)
  self.assertEqual(before,[dict(row) for row in self.db.conn.execute('SELECT * FROM material_bom_items')])
 def test_unchanged_shared_occurrence_does_not_override_edit(self):
  r,p,c,o,x=self.ids
  for quantities in [(1,2),(3,2)]:
   self.s.save_bom(r,[dict(material_id=p,parent_material_id=r,quantity=q,unit='pcs') for q in quantities])
  self.assertEqual(self.s.bom(r)[0]['quantity'],3)
 def test_sqlite_failure_rolls_back_database(self):
  r,p,c,o,x=self.ids
  before=[dict(row) for row in self.db.conn.execute('SELECT * FROM material_bom_items')]
  self.db.conn.execute("CREATE TEMP TRIGGER fail_bom_update BEFORE UPDATE ON material_bom_items BEGIN SELECT RAISE(ABORT,'模拟数据库写入失败'); END")
  self.w.show_item_info(self.w.root_item.child(0)); self.w.fields['quantity'].setValue(6.7)
  with patch.object(QMessageBox,'warning') as warning:
   self.assertFalse(self.w.save()); self.assertIn('模拟数据库写入失败',warning.call_args.args[2])
  self.assertEqual(before,[dict(row) for row in self.db.conn.execute('SELECT * FROM material_bom_items')])
  self.assertEqual(self.w.root_item.child(0).text(1),'6.7')
  self.db.conn.execute('DROP TRIGGER fail_bom_update')
  with patch.object(QMessageBox,'information'): self.assertTrue(self.w.save())
 def test_save_preserves_relation_id_and_alternates(self):
  r,p,c,o,x=self.ids; relation=self.s.bom(r)[0]['id']
  self.s.add_alternate(relation,o)
  with patch.object(QMessageBox,'information'): self.assertTrue(self.w.save())
  self.assertEqual(self.s.bom(r)[0]['id'],relation)
  self.assertEqual(self.s.alternates(relation)[0]['material_id'],o)
