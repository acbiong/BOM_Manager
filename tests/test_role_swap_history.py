import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
import test_material_history as fixture
from services import material_history as h,history_selection as hs
from services.snapshot_bom import revision_conflicts,ParentRevisionRequired


class RoleSwapHistoryTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MaterialHistoryTests.setUpClass.__func__)
 tearDown=fixture.MaterialHistoryTests.tearDown
 rows=fixture.MaterialHistoryTests.rows
 def setUp(self):
  fixture.MaterialHistoryTests.setUp(self)
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  h.save(self.new,self.r,rows,{},hs.select(self.new,self.c,[self.sid,self.tid],impact_mid=self.p))
 def swap(self):
  rows=self.rows();rows[-1].update(material_id=self.a,alternate_material_ids=[self.c]);return rows
 def test_swap_partial_preserves_parent_code_and_other_main_boms(self):
  original=self.old.bom(self.r);old=h.read(self.s,self.p,100);rows=self.swap()
  choice=hs.select(self.new,self.p)
  self.assertFalse(h.collect_conflicts(self.new,self.r,rows,{},choice))
  self.assertEqual(h.save(self.new,self.r,rows,{},choice),{})
  self.assertEqual(self.new.bom(self.p)[0]['material_id'],self.a)
  self.assertEqual(self.new.material_snapshot(self.p)['version'],'100')
  self.assertEqual(self.old.bom(self.r),original);self.assertEqual(h.read(self.s,self.p,100),old)
  self.assertFalse(revision_conflicts(self.new,self.r,self.rows()))
  h.save(self.new,self.r,self.rows(),{},hs.select(self.new,self.p))
 def test_swap_all_and_swap_back_reuses_history_and_remains_saveable(self):
  choice=hs.select(self.new,self.p,[self.sid,self.tid]);h.save(self.new,self.r,self.swap(),{},choice)
  for s in (self.new,self.old,self.other):
   self.assertEqual(s.material_snapshot(self.p)['history_version'],100)
   self.assertEqual(s.bom(self.p)[0]['material_id'],self.a)
  rows=self.rows();rows[-1].update(material_id=self.c,alternate_material_ids=[self.a])
  h.save(self.new,self.r,rows,{},hs.select(self.new,self.p,[self.sid,self.tid]))
  self.assertFalse(revision_conflicts(self.new,self.r,self.rows()))
  self.assertEqual(self.new.bom(self.p)[0]['material_id'],self.c)
 def test_arbitrary_replacement_or_missing_old_main_still_requires_revision(self):
  for alts in ([],[self.a]):
   rows=self.swap();rows[-1]['alternate_material_ids']=alts
   self.assertTrue(revision_conflicts(self.new,self.r,rows))
 def test_quantity_position_unit_remark_changes_are_not_hidden_by_swap(self):
  for key,value in [('quantity',9),('position','changed'),('unit','套'),('remark','changed')]:
   with self.subTest(key=key):
    rows=self.swap();rows[-1][key]=value
    before=list(self.db.conn.iterdump())
    with self.assertRaises(ParentRevisionRequired):h.save(self.new,self.r,rows,{},hs.select(self.new,self.p))
    self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_failed_save_does_not_register_equivalent_definition(self):
  before=list(self.db.conn.iterdump())
  with patch.object(h,'capture',side_effect=ValueError('fail after relation save')):
   with self.assertRaises(ValueError):h.save(self.new,self.r,self.swap(),{},hs.select(self.new,self.p))
  self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_native_editor_swap_undo_save_and_reopen_without_parent_prompt(self):
  from ui.main_window import BomWindow,QMessageBox
  from ui.material_history import MaterialHistoryChoiceDialog
  from ui.parent_revision import ParentRevisionDialog
  from PyQt5.QtWidgets import QDialog
  from PyQt5.QtCore import Qt
  w=BomWindow(self.new,self.r)
  try:
   node=w.root_item.child(0).child(0);new=w.promote_alternate(node,self.a)
   self.assertEqual(new.data(0,Qt.UserRole)['material_id'],self.a)
   self.assertEqual(w.alternate_ids(new),[self.c]);self.assertEqual(new.text(1),'2')
   w.history.undo();w.history.redo()
   with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=QDialog.Accepted),patch.object(ParentRevisionDialog,'exec_') as parent,patch.object(QMessageBox,'information'):
    self.assertTrue(w.save());parent.assert_not_called()
   self.assertEqual(self.new.material_snapshot(self.p)['version'],'100')
  finally:w.dirty=False;w.close()
  from database.database import Database
  from services.services import Services
  path=self.db.path;self.db.close();self.db=Database(path);self.s=Services(self.db)
  reopened=self.s.for_sku(self.newid)
  self.assertFalse(revision_conflicts(reopened,self.r,reopened.bom(self.r)))
 def editor_swapped(self):
  from ui.main_window import BomWindow
  from PyQt5.QtCore import Qt
  w=BomWindow(self.new,self.r);self.addCleanup(lambda:(setattr(w,'dirty',False),w.close()))
  node=w.promote_alternate(w.root_item.child(0).child(0),self.a)
  return w,node
 def test_unsaved_swap_delete_new_alternate_menu_save_and_undo(self):
  from ui.main_window import QMenu,QMessageBox
  from ui.parent_revision import ParentRevisionDialog
  from PyQt5.QtCore import Qt
  from services import bom_role_swap
  w,node=self.editor_swapped();w.show_item_info(node);before=list(self.db.conn.iterdump())
  def remove(menu,*args):return next(a for a in menu.actions() if a.text()=='删除替代料')
  with patch.object(QMenu,'exec_',remove),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(ParentRevisionDialog,'exec_') as parent:
   w.alternate_menu(w.alt_table.visualItemRect(w.alt_table.item(0,0)).center());parent.assert_not_called()
  self.assertEqual(w.alternate_ids(node),[]);self.assertEqual(before,list(self.db.conn.iterdump()))
  with patch.object(bom_role_swap,'is_exchange',side_effect=bom_role_swap.is_swap):
   self.assertTrue(revision_conflicts(self.new,self.r,w.history_rows()))
  self.assertFalse(revision_conflicts(self.new,self.r,w.history_rows()))
  w.history.undo();node=next(n for _,n in w.expansion_nodes() if n.data(0,Qt.UserRole).get('material_id')==self.a and not n.data(0,Qt.UserRole).get('_deleted'))
  self.assertEqual(w.alternate_ids(node),[self.c]);w.history.redo()
  from ui.material_history import MaterialHistoryChoiceDialog
  with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=1),patch.object(ParentRevisionDialog,'exec_') as parent,patch.object(QMessageBox,'information'):
   self.assertTrue(w.save());parent.assert_not_called()
  self.assertEqual(self.new.material_snapshot(self.p)['version'],'100')
  self.assertEqual(self.new.bom(self.p)[0]['material_id'],self.a)
  self.assertFalse(self.new.alternates(self.new.bom(self.p)[0]['id']))
  self.assertEqual(self.old.bom(self.p)[0]['material_id'],self.c)
  self.assertFalse(revision_conflicts(self.new,self.r,self.rows()))
 def test_unsaved_swap_then_delete_still_checks_relation_changes(self):
  w,node=self.editor_swapped();w.stage_alternate_change(node,[])
  for key,value in [('quantity',5),('unit','套'),('position','new'),('remark','new')]:
   with self.subTest(field=key):
    rows=w.history_rows();rows[-1][key]=value
    with self.assertRaises(ParentRevisionRequired):h.save(self.new,self.r,rows,{},hs.select(self.new,self.p))
 def test_swap_proof_rejects_stale_origin_and_arbitrary_replacement(self):
  w,node=self.editor_swapped();w.stage_alternate_change(node,[]);rows=w.history_rows()
  for key,value in [('material_id',self.t),('parent_material_id',self.t),('position','different'),('alternate_material_ids',[]),('target_material_id',self.c)]:
   from copy import deepcopy
   changed=deepcopy(rows);changed[-1]['_role_swap_origin'][key]=value
   self.assertTrue(revision_conflicts(self.new,self.r,changed))
 def test_swap_delete_refresh_and_all_selected_save(self):
  w,node=self.editor_swapped();w.stage_alternate_change(node,[]);w.mark_dirty();w.refresh_external()
  self.assertFalse(revision_conflicts(self.new,self.r,w.history_rows()))
  h.save(self.new,self.r,w.history_rows(),{},hs.select(self.new,self.p,[self.sid,self.tid]))
  for svc in (self.new,self.old,self.other):
   self.assertEqual(svc.material_snapshot(self.p)['version'],'100');self.assertEqual(svc.bom(self.p)[0]['material_id'],self.a)
   self.assertFalse(svc.alternates(svc.bom(self.p)[0]['id']))
