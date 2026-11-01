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
