import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
import test_material_history as fixture
from services import material_history as h,history_selection as hs
from services.sku_lock import LockedBomError


class HistorySelectionTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MaterialHistoryTests.setUpClass.__func__)
 setUp=fixture.MaterialHistoryTests.setUp
 tearDown=fixture.MaterialHistoryTests.tearDown
 rows=fixture.MaterialHistoryTests.rows
 def choice(self,ids=None,service=None):
  service=service or self.new
  if ids is None:ids=[s['id'] for s in hs.references(service,self.c)]
  return hs.select(service,self.c,ids,impact_mid=self.p)
 def add(self,ids=None,service=None):
  service=service or self.new;rows=self.rows(service);rows[-1]['alternate_material_ids']=[self.a]
  h.save(service,self.r,rows,{},self.choice(ids,service))
 def test_select_all_includes_old_same_sku_and_keeps_history_number(self):
  self.assertEqual({s['id'] for s in hs.references(self.new,self.c)},{self.sid,self.tid})
  before=[tuple(r) for r in self.db.conn.execute('SELECT material_id,history_version FROM material_histories')]
  self.add()
  for service in (self.new,self.old,self.other):
   self.assertEqual(service.material_snapshot(self.p)['history_version'],100)
   self.assertEqual([r['material_id'] for r in service.alternates(service.bom(self.p)[0]['id'])],[self.a])
  self.assertEqual(before,[tuple(r) for r in self.db.conn.execute('SELECT material_id,history_version FROM material_histories')])
 def test_partial_preserves_unselected_old_bom_and_allocates_history(self):
  old=h.read(self.s,self.p,100);old_rows=self.old.bom(self.r)
  self.add([self.tid])
  self.assertEqual(h.read(self.s,self.p,100),old)
  self.assertEqual(self.old.bom(self.r),old_rows)
  self.assertEqual(self.new.material_snapshot(self.p)['history_version'],101)
  self.assertEqual(self.other.material_snapshot(self.p)['history_version'],101)
  self.assertFalse(self.old.alternates(self.old.bom(self.p)[0]['id']))
 def test_exclusive_change_does_not_prompt_or_add_history(self):
  from ui.main_window import BomWindow,MaterialSelectionDialog
  from ui.material_history import MaterialHistoryChoiceDialog
  from PyQt5.QtCore import Qt
  x=self.s.create_material(dict(base_code='X',version='1',name='X',unit='pcs'))
  y=self.s.create_material(dict(base_code='Y',version='1',name='Y',unit='pcs'))
  sid=self.s.create_sku(x);service=self.s.for_sku(sid)
  service.save_bom(x,[dict(material_id=y,quantity=1,unit='pcs')])
  before=[tuple(r) for r in self.db.conn.execute('SELECT material_id,history_version FROM material_histories')]
  w=BomWindow(service,x);w.tree.setCurrentItem(w.root_item.child(0))
  try:
   def pick(*args):return next(s for s in args[3] if s.startswith('A100 ')),True
   with patch.object(MaterialHistoryChoiceDialog,'exec_') as prompt,patch.object(MaterialSelectionDialog,'getItem',side_effect=pick):
    w.add_alternate();prompt.assert_not_called()
   self.assertTrue(w.dirty);self.assertFalse(service.alternates(service.bom(x)[0]['id']))
   with patch.object(MaterialHistoryChoiceDialog,'exec_') as prompt,patch('ui.main_window.QMessageBox.information'):
    self.assertTrue(w.save());prompt.assert_not_called()
   self.assertEqual(before,[tuple(r) for r in self.db.conn.execute('SELECT material_id,history_version FROM material_histories')])
  finally:w.dirty=False;w.close()
 def test_locked_selected_rolls_back_and_unselected_is_preserved(self):
  self.s.set_sku_locked(self.tid,True)
  before=list(self.db.conn.iterdump())
  with self.assertRaises(LockedBomError):self.add()
  self.assertEqual(before,list(self.db.conn.iterdump()))
  self.add([self.sid])
  self.assertEqual(self.other.material_snapshot(self.p)['history_version'],100)
  self.assertFalse(self.other.alternates(self.other.bom(self.p)[0]['id']))
 def test_stale_selection_rejected_without_writes(self):
  choice=self.choice();self.s.copy_sku_bom(self.sid);before=list(self.db.conn.iterdump())
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  with self.assertRaisesRegex(ValueError,'重新选择'):h.save(self.new,self.r,rows,{},choice)
  self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_selected_old_source_can_update_all_references(self):
  self.add(service=self.old)
  for service in (self.new,self.old,self.other):self.assertEqual(service.material_snapshot(self.p)['history_version'],100)
  self.assertTrue(self.new.alternates(self.new.bom(self.p)[0]['id']))
 def test_all_positions_under_different_parents_keep_quantity_and_position(self):
  q=self.s.create_material(dict(base_code='Q',version='1',name='Q',unit='pcs'))
  u=self.s.create_material(dict(base_code='U',version='1',name='U',unit='pcs'))
  sid=self.s.create_sku(u);target=self.s.for_sku(sid)
  target.save_bom(u,[dict(material_id=q,quantity=3,unit='pcs'),dict(parent_material_id=q,material_id=self.c,quantity=7,unit='pcs',position='P1'),dict(parent_material_id=q,material_id=self.c,quantity=8,unit='pcs',position='P2')])
  old=target.material_snapshot(q)['history_version'];self.add()
  for row in target.bom(q):self.assertEqual([a['material_id'] for a in target.alternates(row['id'])],[self.a])
  self.assertEqual([(r['quantity'],r['position']) for r in target.bom(q)],[(7,'P1'),(8,'P2')])
  self.assertEqual(target.material_snapshot(q)['history_version'],old)
 def test_distinct_existing_histories_are_listed_and_keep_unrelated_content(self):
  rows=self.rows();rows[-1]['quantity']=5
  h.save(self.new,self.r,rows,{},'fork',{self.p:'101'})
  new_parent=self.new.bom(self.r)[0]['material_id']
  choice=hs.select(self.new,self.c,[self.sid,self.tid],impact_mid=new_parent)
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  h.save(self.new,self.r,rows,{},choice)
  self.assertEqual(self.new.bom(new_parent)[0]['quantity'],5)
  self.assertEqual(self.old.bom(self.p)[0]['quantity'],2)
  self.assertTrue(self.old.alternates(self.old.bom(self.p)[0]['id']))
 def test_metadata_all_references_reuses_number_and_noop_is_stable(self):
  choice=hs.select(self.new,self.r,[self.sid]);before=len(h.versions(self.s,self.r))
  h.save(self.new,self.r,self.rows(),{self.r:{**self.new.material_snapshot(self.r),'name':'changed'}},choice)
  self.assertEqual(len(h.versions(self.s,self.r)),before)
  self.assertEqual(self.old.material_snapshot(self.r)['name'],'changed')
  self.assertEqual(self.new.material_snapshot(self.r)['history_version'],self.old.material_snapshot(self.r)['history_version'])
  records=list(self.db.conn.execute('SELECT * FROM material_histories'))
  h.save(self.new,self.r,self.rows(),{},hs.select(self.new,self.r,[self.sid]))
  self.assertEqual(records,list(self.db.conn.execute('SELECT * FROM material_histories')))
 def test_partial_different_material_history_still_creates_new_revision(self):
  h.save(self.new,self.r,self.rows(),{self.r:{**self.new.material_snapshot(self.r),'name':'different'}},'fork')
  previous=self.new.material_snapshot(self.r)['history_version']
  self.assertNotEqual(previous,self.old.material_snapshot(self.r)['history_version'])
  choice=hs.select(self.new,self.r)
  h.save(self.new,self.r,self.rows(),{self.r:{**self.new.material_snapshot(self.r),'name':'partial'}},choice)
  self.assertGreater(self.new.material_snapshot(self.r)['history_version'],previous)
  self.assertEqual(self.old.material_snapshot(self.r)['name'],'R')
 def test_all_different_material_histories_remain_selectable(self):
  h.save(self.new,self.r,self.rows(),{self.r:{**self.new.material_snapshot(self.r),'name':'different'}},'fork')
  versions={r['history_version'] for r in h.versions(self.s,self.r)}
  choice=hs.select(self.new,self.r,[self.sid])
  h.save(self.new,self.r,self.rows(),{self.r:{**self.new.material_snapshot(self.r),'name':'together'}},choice)
  self.assertEqual(self.old.material_snapshot(self.r)['name'],'together')
  self.assertEqual(self.new.material_snapshot(self.r)['name'],'together')
  self.assertEqual({r['history_version'] for r in h.versions(self.s,self.r)},versions)
 def test_metadata_sync_preserves_other_history_relationship_values(self):
  rows=self.rows();rows[0]['quantity']=9;rows[0]['remark']='source only'
  h.save(self.new,self.r,rows,{},'fork')
  previous=[(r['material_id'],r['quantity'],r['remark']) for r in self.old.bom(self.r)]
  choice=hs.select(self.new,self.r,[self.sid])
  h.save(self.new,self.r,self.rows(),{self.r:{**self.new.material_snapshot(self.r),'name':'shared name'}},choice)
  self.assertEqual([(r['material_id'],r['quantity'],r['remark']) for r in self.old.bom(self.r)],previous)
  self.assertEqual(self.old.material_snapshot(self.r)['name'],'shared name')
 def test_ui_alternate_draft_updates_all_positions_and_undo_restores_choices(self):
  from ui.main_window import BomWindow,MaterialSelectionDialog
  from ui.material_history import MaterialHistoryChoiceDialog
  from PyQt5.QtWidgets import QDialog
  from PyQt5.QtCore import Qt
  q=self.s.create_material(dict(base_code='Q',version='1',name='Q',unit='pcs'))
  rows=self.rows()+[dict(material_id=q,quantity=1,unit='pcs',parent_material_id=self.r),dict(material_id=self.c,quantity=7,unit='pcs',parent_material_id=q)]
  self.new.save_bom(self.r,rows)
  w=BomWindow(self.new,self.r);w.tree.setCurrentItem(w.root_item.child(0).child(0))
  def choose(dialog):dialog.select_all(True);return QDialog.Accepted
  def pick(*args):return next(s for s in args[3] if s.startswith('A100 ')),True
  try:
   with patch.object(MaterialHistoryChoiceDialog,'exec_',choose),patch.object(MaterialSelectionDialog,'getItem',side_effect=pick):w.add_alternate()
   nodes=[n for _,n in w.expansion_nodes() if (n.data(0,Qt.UserRole) or {}).get('material_id')==self.c]
   self.assertEqual(len(nodes),2)
   self.assertTrue(all(w.alternate_ids(n)==[self.a] for n in nodes))
   self.assertTrue(w._history_choices);w.history.undo();self.assertFalse(w._history_choices);self.assertFalse(w._alternate_edits)
   w.history.redo();self.assertTrue(w._history_choices)
  finally:w.dirty=False;w.close()
 def test_first_draft_use_of_exclusive_material_reuses_initial_history(self):
  x=self.s.create_material(dict(base_code='X',version='1',name='X',unit='pcs'))
  y=self.s.create_material(dict(base_code='Y',version='1',name='Y',unit='pcs'))
  sid=self.s.create_sku(x);service=self.s.for_sku(sid)
  rows=[dict(material_id=y,parent_material_id=x,quantity=1,unit='pcs')]
  mode={x:hs.select(service,x),y:hs.select(service,y)}
  h.save(service,x,rows,{y:{**service.material_snapshot(y),'name':'draft name'}},mode)
  self.assertEqual(service.material_snapshot(y)['history_version'],100)
  self.assertEqual(service.material_snapshot(y)['name'],'draft name')
  self.assertEqual(len(h.versions(self.s,y)),1)
