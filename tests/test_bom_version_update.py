import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox
from PyQt5.QtCore import Qt,QPoint
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MaterialSelectionDialog

class VersionUpdateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.ids={k:self.s.create_material(dict(base_code=code,version=version,name=k,unit='pcs')) for k,code,version in [('r','R','1'),('old','P','1'),('new','P','2'),('c','C','1'),('a','A','1')]}
  self.s.save_bom(self.ids['old'],[dict(material_id=self.ids['c'],quantity=2,unit='pcs',position='C1',remark='子项备注')])
  self.s.add_alternate(self.s.bom(self.ids['old'])[0]['id'],self.ids['a'])
  self.s.save_bom(self.ids['r'],[dict(material_id=self.ids['old'],quantity=3,unit='pcs',position='P1',remark='原备注')]);self.w=BomWindow(self.s,self.ids['r'])
 def tearDown(self):self.w.dirty=False;self.w.close();self.db.close();self.tmp.cleanup()
 def update(self,answer=QMessageBox.Yes):
  with patch.object(MaterialSelectionDialog,'getItem',return_value=('P2 new',True)),patch.object(QMessageBox,'question',return_value=answer):return self.w.update_material_version(self.w.root_item.child(0))
 def save(self):
  with patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning') as warning:self.assertTrue(self.w.save());warning.assert_not_called()
 def test_copy_draft_subtree_and_alternates_only_on_save(self):
  child=self.w.root_item.child(0).child(0);self.w.show_item_info(child);self.w.fields['quantity'].setValue(4.25)
  new=self.update();self.assertEqual(new.text(1),'3');self.assertEqual(new.text(3),'P1');self.assertEqual(new.child(0).text(1),'4.25');self.assertEqual(self.w.alternate_ids(new.child(0)),[self.ids['a']])
  self.assertEqual(self.s.bom(self.ids['new']),[]);self.assertEqual(self.s.bom(self.ids['r'])[0]['material_id'],self.ids['old'])
  self.save();rows=self.s.bom(self.ids['new']);self.assertEqual(rows[0]['quantity'],4.25);self.assertEqual(self.s.alternates(rows[0]['id'])[0]['material_id'],self.ids['a'])
 def test_no_and_cancel(self):
  self.assertIsNone(self.update(QMessageBox.Cancel));self.assertFalse(self.w.dirty)
  new=self.update(QMessageBox.No);self.assertEqual(new.childCount(),0);self.save();self.assertEqual(self.s.bom(self.ids['new']),[])
 def test_existing_target_subtree(self):
  self.s.save_bom(self.ids['new'],[dict(material_id=self.ids['a'],quantity=7,unit='pcs')])
  with patch.object(QMessageBox,'question') as question:new=self.update();question.assert_not_called()
  self.assertEqual(new.child(0).data(0,Qt.UserRole)['material_id'],self.ids['a']);self.save()
  self.assertEqual(self.s.bom(self.ids['new'])[0]['quantity'],7)
 def test_versions_and_disabled_menu(self):
  old=self.w.root_item.child(0);self.assertEqual([r['id'] for r in self.w.material_versions(old)],[self.ids['new']])
  child=old.child(0);self.assertEqual(self.w.material_versions(child),[])
  from PyQt5.QtWidgets import QMenu
  actions={}
  def inspect(menu,*args):actions.update({a.text():a.isEnabled() for a in menu.actions()});return None
  with patch.object(self.w.tree,'itemAt',return_value=child),patch.object(QMenu,'exec_',inspect):self.w.context_menu(QPoint())
  self.assertFalse(actions['物料版本更新'])
 def test_duplicate_and_cycle_rejected(self):
  self.w.insert_material(self.w.root_item,self.s.material_snapshot(self.ids['new']))
  with patch.object(QMessageBox,'warning') as warning:self.assertIsNone(self.update());warning.assert_called_once()
 def test_copy_cycle_rejected(self):
  self.w.insert_material(self.w.root_item.child(0),self.s.material_snapshot(self.ids['new']))
  with patch.object(QMessageBox,'warning') as warning:self.assertIsNone(self.update());warning.assert_called_once()
 def test_mirror_target_definition_and_alternate_isolation(self):
  sid=self.s.create_sku(self.ids['r']);copy=self.s.copy_sku_bom(sid);mirror=self.s.for_sku(copy)
  self.s.save_bom(self.ids['new'],[dict(material_id=self.ids['a'],quantity=9,unit='pcs')]);self.s.add_alternate(self.s.bom(self.ids['new'])[0]['id'],self.ids['c'])
  self.w.close();self.w=BomWindow(mirror,self.ids['r']);new=self.update()
  self.assertEqual(new.child(0).text(1),'9');self.assertEqual(self.w.alternate_ids(new.child(0)),[self.ids['c']]);self.save()
  self.assertEqual(mirror.bom(self.ids['r'])[0]['material_id'],self.ids['new']);self.assertEqual(self.s.bom(self.ids['r'])[0]['material_id'],self.ids['old'])
 def test_shared_parent_occurrences(self):
  p=self.s.create_material(dict(base_code='PARENT',version='1',name='parent',unit='pcs'))
  b=self.s.create_material(dict(base_code='B',version='1',name='b',unit='pcs'))
  self.s.save_bom(p,[dict(material_id=self.ids['old'],quantity=3,unit='pcs')])
  self.s.save_bom(b,[dict(material_id=p,quantity=1,unit='pcs')])
  self.s.save_bom(self.ids['r'],[dict(material_id=p,quantity=1,unit='pcs'),dict(material_id=b,quantity=1,unit='pcs')])
  self.w.close();self.w=BomWindow(self.s,self.ids['r'])
  with patch.object(MaterialSelectionDialog,'getItem',return_value=('P2 new',True)),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):self.w.update_material_version(self.w.root_item.child(0).child(0))
  for parent in [self.w.root_item.child(0),self.w.root_item.child(1).child(0)]:
   self.assertTrue(parent.child(0).data(0,Qt.UserRole)['_deleted']);self.assertEqual(parent.child(1).child(0).text(1),'2')
  self.save();self.assertEqual(self.s.bom(p)[0]['material_id'],self.ids['new'])
 def test_regular_replace_mirror_107_copies_children_and_library_flag(self):
  from ui.main_window import MaterialWindow
  sid=self.s.create_sku(self.ids['r']);copy=self.s.copy_sku_bom(sid);self.s.change_mirror_version(copy,107);mirror=self.s.for_sku(copy)
  self.w.close();self.w=BomWindow(mirror,self.ids['r']);library=MaterialWindow(self.s)
  def flag():return next(row['has_bom'] for row in self.s.materials() if row['id']==self.ids['new'])
  try:
   self.assertEqual(flag(),'N')
   with patch.object(MaterialSelectionDialog,'getItem',return_value=('P2 new',True)),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes) as question:
    new=self.w.replace_material(self.w.root_item.child(0));question.assert_called_once()
   self.assertEqual(new.child(0).data(0,Qt.UserRole)['material_id'],self.ids['c']);self.assertEqual(flag(),'N')
   self.save();self.assertEqual(flag(),'Y');self.assertEqual(self.s.bom(self.ids['new']),[])
   self.assertEqual(mirror.bom(self.ids['new'])[0]['material_id'],self.ids['c'])
   index=next(i for i in range(library.t.rowCount()) if library.t.item(i,0).text()=='P' and library.t.item(i,1).text()=='2')
   self.assertEqual(library.t.item(index,9).text(),'Y')
   child=self.w.root_item.child(0).child(0);self.w.remove_relation(child);self.save();self.assertEqual(flag(),'N')
   self.w.insert_material(self.w.root_item.child(0),mirror.material_snapshot(self.ids['c']));self.save();self.assertEqual(flag(),'Y')
   self.s.delete_sku(copy);self.assertEqual(flag(),'N')
  finally:library.close()
 def test_regular_replace_copy_cancel_and_decline(self):
  for answer in (QMessageBox.Cancel,QMessageBox.No):
   with patch.object(MaterialSelectionDialog,'getItem',return_value=('P2 new',True)),patch.object(QMessageBox,'question',return_value=answer):new=self.w.replace_material(self.w.root_item.child(0))
   if answer==QMessageBox.Cancel:self.assertIsNone(new);self.assertFalse(self.w.dirty)
   else:self.assertEqual(new.childCount(),0);self.save();self.assertEqual(self.s.bom(self.ids['new']),[])
