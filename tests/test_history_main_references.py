import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
import test_material_history as fixture
from services import material_history as h, history_selection as hs


class MainReferenceTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MaterialHistoryTests.setUpClass.__func__)
 setUp=fixture.MaterialHistoryTests.setUp
 tearDown=fixture.MaterialHistoryTests.tearDown
 rows=fixture.MaterialHistoryTests.rows
 def alternate_owner(self,mid,both=False):
  n=len(self.s.skus())
  root=self.s.create_material(dict(base_code=f'X{n}',version='100',name='兼有主料和替代料引用' if both else '仅作替代料引用',unit='pcs'))
  child=self.s.create_material(dict(base_code=f'Y{n}',version='100',name='main child',unit='pcs'))
  sid=self.s.create_sku(root);target=self.s.for_sku(sid)
  rows=[dict(material_id=child,quantity=2,unit='pcs',alternate_material_ids=[mid])]
  if both:rows.append(dict(material_id=mid,quantity=5,unit='pcs'))
  target.save_bom(root,rows)
  return target,root
 def test_scope_excludes_alternate_only_and_includes_both_and_old_main(self):
  alt,_=self.alternate_owner(self.c);both,_=self.alternate_owner(self.c,True)
  self.assertEqual({s['id'] for s in hs.references(self.new,self.c)},{self.sid,self.tid,both.sku_id})
  self.assertEqual({s['id'] for s in h.sku_references(self.s,self.c,100)},{self.sid,self.newid,self.tid,both.sku_id})
  self.assertTrue(self.db.conn.execute('SELECT 1 FROM material_history_bindings WHERE sku_id=? AND material_id=?',(alt.sku_id,self.c)).fetchone())
  self.assertEqual({r['sku_id'] for r in h.main_bindings(self.s,self.r)},{self.sid,self.newid})
  from services.snapshot_bom import other_sku_usages
  self.assertEqual({s['id'] for s in other_sku_usages(self.new,self.c)},{self.sid,self.tid,both.sku_id})
 def test_dialog_loads_scope_once_and_does_not_show_alternate_only(self):
  from ui.material_history import MaterialHistoryChoiceDialog
  from PyQt5.QtCore import Qt
  alt,_=self.alternate_owner(self.c)
  with patch.object(hs,'references',wraps=hs.references) as query:
   w=MaterialHistoryChoiceDialog(self.new,self.c,'删除替代料',impact_mid=self.p)
   self.assertEqual(query.call_count,1)
  try:
   self.assertEqual({w.table.item(i,0).data(Qt.UserRole) for i in range(w.table.rowCount())},{self.sid,self.tid})
   w.select_all(True);self.assertEqual(w.mode().sku_ids,{self.sid,self.tid})
  finally:w.close()
 def test_alternate_only_lock_does_not_invalidate_scope_but_main_role_does(self):
  alt,root=self.alternate_owner(self.c);before=hs.token(self.new,self.c)
  self.s.set_sku_locked(alt.sku_id,True);self.assertEqual(before,hs.token(self.new,self.c))
  self.s.set_sku_locked(alt.sku_id,False)
  alt.save_bom(root,[dict(r,alternate_material_ids=[self.c]) for r in alt.bom(root)]+[dict(material_id=self.c,quantity=1,unit='pcs')])
  self.assertNotEqual(before,hs.token(self.new,self.c))
 def test_all_main_owners_reuse_parent_history_despite_locked_alternate_owner(self):
  alt,root=self.alternate_owner(self.p);self.s.set_sku_locked(alt.sku_id,True)
  unchanged=alt.bom(root);rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  choice=hs.select(self.new,self.c,[self.sid,self.tid],impact_mid=self.p)
  with patch.object(hs,'plans',wraps=hs.plans) as plan:
   h.save(self.new,self.r,rows,{},choice);self.assertEqual(plan.call_count,1)
  for s in (self.new,self.old,self.other):self.assertEqual(s.material_snapshot(self.p)['history_version'],100)
  self.assertEqual(alt.bom(root),unchanged)
  self.assertEqual(alt.material_snapshot(self.p)['history_version'],100)
 def test_partial_main_selection_still_preserves_unselected_main_history(self):
  self.alternate_owner(self.c);old=h.read(self.s,self.p,100)
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  h.save(self.new,self.r,rows,{},hs.select(self.new,self.c,[self.tid],impact_mid=self.p))
  self.assertEqual(h.read(self.s,self.p,100),old)
  self.assertEqual(self.old.material_snapshot(self.p)['history_version'],100)
  self.assertNotEqual(self.new.material_snapshot(self.p)['history_version'],100)
 def test_root_metadata_reuses_history_and_alternate_binding_follows(self):
  alt,root=self.alternate_owner(self.r)
  before=alt.bom(root);versions=h.versions(self.s,self.r)
  attrs={**self.new.material_snapshot(self.r),'name':'main owners updated'}
  h.save(self.new,self.r,self.rows(),{self.r:attrs},hs.select(self.new,self.r,[self.sid]))
  self.assertEqual(h.versions(self.s,self.r),versions)
  self.assertEqual(alt.bom(root),before)
  self.assertEqual(alt.material_snapshot(self.r)['name'],'main owners updated')
  self.assertEqual(alt.material_snapshot(self.r)['history_version'],100)
 def test_alternate_only_library_edit_reuses_current_without_prompt_or_deletion_bypass(self):
  from types import SimpleNamespace
  from ui.material_history import update_library_material,MaterialHistoryChoiceDialog
  alt,_=self.alternate_owner(self.a)
  self.assertEqual(h.catalog_source(self.s,self.a),(self.s,None))
  attrs={**self.s.material_snapshot(self.a),'name':'updated alternative'};versions=h.versions(self.s,self.a)
  with patch.object(MaterialHistoryChoiceDialog,'exec_') as prompt:
   update_library_material(SimpleNamespace(svc=self.s),self.a,attrs);prompt.assert_not_called()
  self.assertEqual(h.versions(self.s,self.a),versions)
  self.assertEqual(alt.material_snapshot(self.a)['name'],'updated alternative')
  with self.assertRaises(ValueError):self.s.delete_material(self.a)
 def test_actual_locked_alternate_metadata_change_remains_protected(self):
  from services.sku_lock import LockedBomError
  alt,_=self.alternate_owner(self.r);self.s.set_sku_locked(alt.sku_id,True)
  self.assertNotIn(alt.sku_id,{s['id'] for s in hs.references(self.new,self.r)})
  before=list(self.db.conn.iterdump())
  with self.assertRaises(LockedBomError):
   h.save(self.new,self.r,self.rows(),{self.r:{**self.new.material_snapshot(self.r),'name':'blocked'}},hs.select(self.new,self.r,[self.sid]))
  self.assertEqual(list(self.db.conn.iterdump()),before)
 def test_only_alternate_elsewhere_does_not_prompt_for_current_main_edit(self):
  from ui.main_window import BomWindow
  from ui.material_history import MaterialHistoryChoiceDialog
  x=self.s.create_material(dict(base_code='EX',version='100',name='exclusive',unit='pcs'))
  child=self.s.create_material(dict(base_code='EC',version='100',name='exclusive child',unit='pcs'))
  target=self.s.for_sku(self.s.create_sku(x));target.save_bom(x,[dict(material_id=child,quantity=1,unit='pcs',alternate_material_ids=[self.a])])
  alt,_=self.alternate_owner(child);self.s.set_sku_locked(alt.sku_id,True)
  w=BomWindow(target,x)
  try:
   with patch.object(MaterialHistoryChoiceDialog,'exec_') as prompt:
    choice=w.choose_material_history(child,'删除替代料',impact_mid=x);prompt.assert_not_called()
   rows=[dict(r,alternate_material_ids=[]) for r in target.bom(x)]
   before=h.versions(self.s,x);h.save(target,x,rows,{},choice)
   self.assertEqual(h.versions(self.s,x),before)
  finally:w.dirty=False;w.close()
 def test_library_source_finds_old_main_bom_when_latest_is_alternate_only(self):
  target,root=self.alternate_owner(self.a,True)
  newer=self.s.for_sku(self.s.copy_sku_bom(target.sku_id))
  rows=[dict(r,alternate_material_ids=[self.a]) for r in newer.bom(root) if r['material_id']!=self.a]
  newer.save_bom(root,rows)
  source,found=h.catalog_source(self.s,self.a)
  self.assertEqual((source.sku_id,found),(target.sku_id,root))


if __name__=='__main__':unittest.main()
