import unittest,json
from unittest.mock import patch
import test_material_history as fixture
from services import material_history as h,history_selection as hs
from services.history_state import pending,matching_skus,Reader,matches
from PyQt5.QtCore import Qt
from ui.main_window import BomWindow,QMenu,QMessageBox
from ui.material_history import MaterialHistoryChoiceDialog


class HistoryStateFilterTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MaterialHistoryTests.setUpClass.__func__)
 rows=fixture.MaterialHistoryTests.rows
 def setUp(self):
  fixture.MaterialHistoryTests.setUp(self)
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  h.save(self.new,self.r,rows,{},hs.select(self.new,self.c,impact_mid=self.p))
  self.w=BomWindow(self.new,self.r)
 def tearDown(self):
  self.w.dirty=False;self.w.close();fixture.MaterialHistoryTests.tearDown(self)
 def proposed(self):return self.w.alternate_change_rows(self.w.root_item.child(0).child(0),[])
 def comparison(self):return pending(self.new,self.c,self.proposed(),self.w._material_edits)
 def matches(self):return matching_skus(self.new,self.c,self.comparison(),hs.references(self.new,self.c))
 def mutate_record(self,svc,mid,field,value):
  old=h.read(svc,mid,svc.material_snapshot(mid)['history_version']);old['attributes'][field]=value
  with self.db.transaction():
   version=h.record(self.db.conn,mid,old['attributes'],old['children'])
   self.db.conn.execute('UPDATE material_history_bindings SET history_version=? WHERE sku_id=? AND material_id=?',(version,svc.sku_id,mid))
 def add_other(self):
  rows=[dict(r,alternate_material_ids=[a['material_id'] for a in self.other.alternates(r['id'])],replace_children=True) for r in self.other.bom(self.t)]
  rows[-1]['alternate_material_ids']=[self.a]
  h.save(self.other,self.t,rows,{},hs.select(self.other,self.c,impact_mid=self.p))
 def test_already_identical_all_excluded_no_dialog_or_writes_and_save_reuses(self):
  self.s.set_sku_locked(self.sid,True);before=list(self.db.conn.iterdump())
  item=self.w.root_item.child(0).child(0);self.w.show_item_info(item)
  def remove(menu,*args):return next(a for a in menu.actions() if a.text()=='删除替代料')
  with patch.object(MaterialHistoryChoiceDialog,'exec_') as dialog,patch.object(QMenu,'exec_',remove),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):
   self.w.alternate_menu(self.w.alt_table.visualItemRect(self.w.alt_table.item(0,0)).center());dialog.assert_not_called()
  self.assertEqual(self.w.alternate_ids(item),[]);self.assertEqual(before,list(self.db.conn.iterdump()))
  old_version=self.old.material_snapshot(self.p)['history_version']
  old_rows=self.old.bom(self.r);old_time=next(s['updated_at'] for s in self.s.skus() if s['id']==self.sid)
  with patch.object(MaterialHistoryChoiceDialog,'exec_') as dialog,patch.object(QMessageBox,'information'):
   self.assertTrue(self.w.save());dialog.assert_not_called()
  self.assertEqual(self.new.material_snapshot(self.p)['history_version'],old_version)
  self.assertEqual(self.old.bom(self.r),old_rows)
  self.assertEqual(next(s['updated_at'] for s in self.s.skus() if s['id']==self.sid),old_time)
 def test_only_different_target_displayed_locked_matching_target_is_hidden(self):
  self.add_other();self.s.set_sku_locked(self.sid,True)
  dialog=MaterialHistoryChoiceDialog(self.new,self.c,'删除替代料',impact_mid=self.p,comparison=self.comparison())
  try:
   self.assertEqual([dialog.table.item(i,0).data(Qt.UserRole) for i in range(dialog.table.rowCount())],[self.tid])
   self.assertEqual(dialog.mode().matching_sku_ids,{self.sid})
   dialog.select_all(True);choice=dialog.mode();self.assertEqual(choice.sku_ids,{self.tid})
   h.save(self.new,self.r,self.proposed(),{},choice)
   self.assertFalse(self.other.alternates(self.other.bom(self.p)[0]['id']))
  finally:dialog.close()
 def test_material_attributes_and_draft_edits_are_compared(self):
  self.mutate_record(self.old,self.c,'name','changed')
  self.assertEqual(self.matches(),{self.tid})
  self.w._material_edits[self.c]={**self.new.material_snapshot(self.c),'name':'changed'}
  self.assertEqual(self.matches(),{self.sid})
 def test_history_number_alone_does_not_create_a_difference(self):
  old=h.read(self.old,self.c,100)
  with self.db.transaction():
   self.db.conn.execute('INSERT INTO material_histories VALUES(?,?,?,?,?,?)',(self.c,999,h.encode(old['attributes']),h.encode(old['children']),old['created_at'],self.sid))
   self.db.conn.execute('UPDATE material_history_bindings SET history_version=999 WHERE sku_id=? AND material_id=?',(self.sid,self.c))
  self.assertEqual(self.matches(),{self.sid,self.tid})
 def test_remaining_alternate_attributes_are_compared(self):
  extra=self.s.create_material(dict(base_code='EXTRA',version='100',name='extra',unit='pcs'))
  self.add_other()
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a,extra]
  h.save(self.new,self.r,rows,{},hs.select(self.new,self.c,impact_mid=self.p))
  self.w.load();item=self.w.root_item.child(0).child(0)
  comparison=pending(self.new,self.c,self.w.alternate_change_rows(item,[self.a]))
  self.assertEqual(matching_skus(self.new,self.c,comparison,hs.references(self.new,self.c)),{self.tid})
  self.mutate_record(self.other,self.a,'description','different alternate')
  self.assertFalse(matching_skus(self.new,self.c,comparison,hs.references(self.new,self.c)))
 def test_child_bom_content_is_compared(self):
  old=h.read(self.old,self.c,100)
  with self.db.transaction():
   version=h.record(self.db.conn,self.c,old['attributes'],[dict(material_id=self.a,history_version=100,quantity=2,unit='pcs',position='',remark='',alternates=[])])
   self.db.conn.execute('UPDATE material_history_bindings SET history_version=? WHERE sku_id=? AND material_id=?',(version,self.sid,self.c))
  self.assertEqual(self.matches(),{self.tid})
 def test_every_target_occurrence_must_match_despite_different_parents(self):
  root,parent=[self.s.create_material(dict(base_code=x,version='100',name=x,unit='pcs')) for x in ('MULTIROOT','MULTIPARENT')]
  sid=self.s.create_sku(root);svc=self.s.for_sku(sid)
  svc.save_bom(root,[dict(material_id=parent,quantity=1,unit='pcs'),dict(material_id=self.c,parent_material_id=parent,quantity=8,unit='pcs',position='x'),dict(material_id=self.c,parent_material_id=parent,quantity=9,unit='pcs',position='y',alternate_material_ids=[self.a])])
  self.assertNotIn(sid,self.matches())
  rows=[dict(r,alternate_material_ids=[]) for r in svc.bom(root)]
  h.save(svc,root,rows,{},hs.select(svc,self.c,impact_mid=parent))
  self.assertIn(sid,self.matches())
 def test_hidden_target_changed_before_save_rejected_without_writes(self):
  choice=self.w.choose_material_history(self.c,'删除替代料',self.p,rows=self.proposed())
  self.mutate_record(self.old,self.c,'name','changed after confirmation');before=list(self.db.conn.iterdump())
  with self.assertRaisesRegex(ValueError,'重新选择'):h.save(self.new,self.r,self.proposed(),{},choice)
  self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_changed_draft_requires_reconfirmation(self):
  choice=self.w.choose_material_history(self.c,'删除替代料',self.p,rows=self.proposed())
  self.assertFalse(hs.current(self.new,choice,self.w.history_rows(),{}))
 def test_further_edits_can_preview_but_cannot_save_stale_scope(self):
  choice=self.w.choose_material_history(self.c,'删除替代料',self.p,rows=self.proposed())
  edits={self.c:{**self.new.material_snapshot(self.c),'name':'later edit'}}
  before=list(self.db.conn.iterdump())
  self.assertTrue(h.collect_conflicts(self.new,self.r,self.proposed(),edits,choice))
  self.assertFalse(hs.current(self.new,choice,self.proposed(),edits))
  with self.assertRaisesRegex(ValueError,'重新选择'):h.save(self.new,self.r,self.proposed(),edits,choice)
  self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_alternate_cycles_are_compared_without_recursion_failure(self):
  old=h.read(self.s,self.a,100)
  with self.db.transaction():
   self.db.conn.execute('UPDATE material_histories SET children=? WHERE material_id=? AND history_version=100',(h.encode([dict(material_id=self.c,history_version=100,quantity=1,unit='pcs',position='',remark='',alternates=[dict(material_id=self.a,history_version=100)])]),self.a))
  reader=Reader(self.new);state=reader.state(self.new,self.c,self.w.history_rows())
  self.assertTrue(matches(state,state))
 def test_detached_captured_parent_does_not_create_difference(self):
  parent=self.s.create_material(dict(base_code='DETACHED',version='100',name='detached',unit='pcs'))
  with self.db.transaction():
   relation=self.old.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit) VALUES(?,?,?,?)',(parent,self.c,1,'pcs')).lastrowid
   self.old.db.conn.execute('INSERT INTO alternates(bom_item_id,material_id,sort_no) VALUES(?,?,?)',(relation,self.a,1))
  self.assertEqual(self.matches(),{self.sid,self.tid})
 def test_differing_locked_target_stays_visible_and_unselectable(self):
  self.add_other();self.s.set_sku_locked(self.tid,True)
  dialog=MaterialHistoryChoiceDialog(self.new,self.c,'删除替代料',impact_mid=self.p,comparison=self.comparison())
  try:
   self.assertEqual(dialog.table.rowCount(),1);dialog.select_all(True)
   self.assertFalse(dialog.mode().sku_ids)
   before=self.other.bom(self.t)
   h.save(self.new,self.r,self.proposed(),{},dialog.mode())
   self.assertEqual(self.other.bom(self.t),before)
  finally:dialog.close()
 def test_cancel_keeps_draft_and_database(self):
  self.add_other();before=list(self.db.conn.iterdump());rows=self.w.history_rows()
  with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=0):
   self.assertIsNone(self.w.choose_material_history(self.c,'删除替代料',self.p,rows=self.proposed()))
  self.assertEqual(self.w.history_rows(),rows);self.assertEqual(before,list(self.db.conn.iterdump()))
