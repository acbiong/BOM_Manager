import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate, ParentRevisionRequired, revision_conflicts
from services.current_catalog import initialize as catalog
from services import material_history as h
from services.sku_lock import LockedBomError
from PyQt5.QtWidgets import QApplication,QDialog
from PyQt5.QtCore import Qt


class MaterialHistoryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.temp.name)/'db'));self.s=Services(self.db)
  self.r,self.t,self.p,self.c,self.a=[self.s.create_material(dict(base_code=x,version='100',name=x,unit='pcs')) for x in ('R','T','P','C','A')]
  self.s.save_bom(self.p,[dict(material_id=self.c,quantity=2,unit='pcs')])
  for root in (self.r,self.t):self.s.save_bom(root,[dict(material_id=self.p,quantity=1,unit='pcs')])
  self.sid=self.s.create_sku(self.r);self.tid=self.s.create_sku(self.t)
  migrate(self.db);catalog(self.db);h.initialize(self.db)
  self.old=self.s.for_sku(self.sid);self.newid=self.s.copy_sku_bom(self.sid);self.new=self.s.for_sku(self.newid);self.other=self.s.for_sku(self.tid)
 def tearDown(self):self.db.close();self.temp.cleanup()
 def rows(self,service=None):
  service=service or self.new
  return [dict(r,alternate_material_ids=[a['material_id'] for a in service.alternates(r['id'])],replace_children=True) for r in service.bom(self.r)]
 def test_migration_initial_copy_and_noop(self):
  self.assertTrue(list(Path(self.temp.name).glob('*.pre-material-history-*')))
  self.assertEqual(h.versions(self.s,self.c)[0]['history_version'],100)
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  h.save(self.new,self.r,self.rows(),{},'fork')
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
  h.initialize(self.db);self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
 def test_metadata_fork_parent_code_rule_and_old_export(self):
  attrs={**self.new.material_snapshot(self.c),'name':'new child'}
  with self.assertRaises(ParentRevisionRequired):h.save(self.new,self.r,self.rows(),{self.c:attrs},'fork')
  mapping=h.save(self.new,self.r,self.rows(),{self.c:attrs},'fork',{self.p:'101'})
  self.assertNotEqual(mapping[self.p],self.p)
  self.assertEqual(self.new.material_snapshot(self.c)['name'],'new child')
  self.assertEqual(self.old.material_snapshot(self.c)['name'],'C')
  self.assertEqual(self.other.material_snapshot(self.c)['name'],'C')
  self.assertEqual(self.s.material_snapshot(self.c)['name'],'new child')
  self.assertEqual(h.versions(self.s,self.c)[0]['history_version'],101)
  from openpyxl import Workbook
  wb=Workbook();self.old.write_bom_sheet(wb.active,self.r)
  self.assertEqual(wb.active.cell(4,7).value,'C');wb.close()
 def test_sync_latest_only_with_new_parent_code(self):
  attrs={**self.new.material_snapshot(self.c),'name':'shared new'}
  mapping=h.save(self.new,self.r,self.rows(),{self.c:attrs},'sync',{self.p:'101'})
  self.assertEqual(self.other.material_snapshot(self.c)['name'],'shared new')
  self.assertEqual(self.other.bom(self.t)[0]['material_id'],mapping[self.p])
  self.assertEqual(self.old.bom(self.r)[0]['material_id'],self.p)
  self.assertEqual(self.old.material_snapshot(self.c)['name'],'C')
 def test_alternate_add_exempt_delete_requires_code(self):
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  self.assertFalse(revision_conflicts(self.new,self.r,rows))
  h.save(self.new,self.r,rows,{},'fork')
  self.assertEqual(self.new.bom(self.r)[0]['material_id'],self.p)
  self.assertEqual(h.versions(self.s,self.p)[0]['history_version'],101)
  self.assertEqual(h.versions(self.s,self.c)[0]['history_version'],101)
  self.assertFalse(self.other.alternates(self.other.bom(self.t)[-1]['id']))
  rows=self.rows();rows[-1]['alternate_material_ids']=[]
  self.assertEqual(revision_conflicts(self.new,self.r,rows)[0]['material_id'],self.p)
  with self.assertRaises(ParentRevisionRequired):h.save(self.new,self.r,rows,{},'fork')
 def test_locked_target_rolls_back_and_fork_is_allowed(self):
  self.s.set_sku_locked(self.tid,True)
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  with self.assertRaises(LockedBomError):h.save(self.new,self.r,rows,{},'sync')
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
  self.assertFalse(self.new.alternates(self.new.bom(self.r)[-1]['id']))
  h.save(self.new,self.r,rows,{},'fork')
  self.assertFalse(self.other.alternates(self.other.bom(self.t)[-1]['id']))
 def test_history_view_and_library_column(self):
  from ui.main_window import MaterialWindow
  from ui.material_history import MaterialHistoryDialog
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a];h.save(self.new,self.r,rows,{},'fork')
  window=MaterialWindow(self.s);viewer=MaterialHistoryDialog(self.s,self.p,100,window)
  try:
   index=window._base_column_labels.index('物料历史版本')
   row=next(i for i in range(window.t.rowCount()) if window.t.item(i,0).data(Qt.UserRole)==self.p)
   self.assertEqual(window.t.item(row,index).text(),'101');self.assertTrue(window.t.item(row,index).font().bold())
   self.assertEqual(viewer.tree.topLevelItem(0).child(0).text(7),'')
   self.assertEqual(viewer.windowModality(),Qt.NonModal)
  finally:viewer.close();window.close()
 def test_immediate_decision_cancel_draft_undo_and_save(self):
  from ui.main_window import BomWindow,MaterialDialog,MaterialSelectionDialog
  from ui.material_history import MaterialHistoryChoiceDialog
  from ui.parent_revision import ParentRevisionDialog
  w=BomWindow(self.new,self.r);item=w.root_item.child(0).child(0);w.tree.setCurrentItem(item)
  try:
   with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=QDialog.Rejected),patch.object(MaterialDialog,'exec_') as edit:
    w.edit_tree_material(item);edit.assert_not_called()
   def edit(dialog):dialog.e['name'].setText('draft name');return QDialog.Accepted
   with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=QDialog.Accepted),patch.object(MaterialDialog,'exec_',edit),patch.object(ParentRevisionDialog,'exec_',return_value=QDialog.Accepted),patch.object(ParentRevisionDialog,'versions',return_value={self.p:'101'}):
    w.edit_tree_material(item)
   self.assertTrue(w.dirty);self.assertEqual(self.s.material_snapshot(self.c)['name'],'C')
   self.assertIn('draft name',w.fields['name'].text());w.history.undo();self.assertFalse(w._material_edits);w.history.redo();self.assertEqual(w._material_edits[self.c]['name'],'draft name')
  finally:w.dirty=False;w.close()

 def test_add_alternate_prompts_before_picker_and_cancel_is_noop(self):
  from ui.main_window import BomWindow,MaterialSelectionDialog
  from ui.material_history import MaterialHistoryChoiceDialog
  w=BomWindow(self.new,self.r);w.tree.setCurrentItem(w.root_item.child(0).child(0))
  try:
   with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=QDialog.Rejected),patch.object(MaterialSelectionDialog,'getItem') as picker:
    w.add_alternate();picker.assert_not_called()
   self.assertFalse(w.dirty);self.assertFalse(w._alternate_edits);self.assertFalse(w.history.undo_stack)
  finally:w.dirty=False;w.close()
 def test_parent_metadata_and_child_metadata_keep_new_code(self):
  edits={mid:{**self.new.material_snapshot(mid),'name':'new '+str(mid)} for mid in (self.p,self.c)}
  mapping=h.save(self.new,self.r,self.rows(),edits,'fork',{self.p:'101'})
  self.assertEqual(self.new.material_snapshot(mapping[self.p])['version'],'101')
  self.assertEqual(self.new.material_snapshot(mapping[self.p])['name'],'new '+str(self.p))
 def test_latest_catalog_state_and_new_selection_are_immutable(self):
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a];h.save(self.new,self.r,rows,{},'fork')
  from services.current_catalog import selection_tree
  nodes=selection_tree(self.old,self.p)
  self.assertEqual(nodes[0]['data']['alternate_material_ids'],[self.a])
  self.assertFalse(self.old.alternates(self.old.bom(self.r)[-1]['id']))
  record=h.read(self.s,self.p,100)
  self.s.copy_sku_bom(self.sid)
  self.assertEqual(h.read(self.s,self.p,100),record)
 def test_invalid_edit_and_deleted_identity_do_not_corrupt_history(self):
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  with self.assertRaises(ValueError):h.save(self.new,self.r,self.rows(),{self.c:{'name':'','unit':'pcs'}},'fork')
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
  last=self.s.create_material(dict(base_code='OLD',version='1',name='old',unit='pcs'))
  self.s.delete_material(last)
  new=self.s.create_material(dict(base_code='NEW',version='1',name='new',unit='pcs'))
  self.assertGreater(new,last);self.assertEqual(h.read(self.s,last,100)['attributes']['name'],'old')
 def test_sync_checks_different_parents_in_other_latest_skus(self):
  q=self.s.create_material(dict(base_code='Q',version='100',name='other parent',unit='pcs'))
  u=self.s.create_material(dict(base_code='U',version='100',name='third SKU',unit='pcs'))
  uid=self.s.create_sku(u);target=self.s.for_sku(uid)
  target.save_bom(u,[dict(material_id=q,quantity=1,unit='pcs'),dict(parent_material_id=q,material_id=self.c,quantity=1,unit='pcs')])
  latest=self.s.copy_sku_bom(uid);target=self.s.for_sku(latest)
  edits={self.c:{**self.new.material_snapshot(self.c),'name':'all latest','unit':'米'}}
  required=h.collect_conflicts(self.new,self.r,self.rows(),edits,'sync')
  self.assertEqual({c['material_id'] for c in required},{self.p,q})
  with self.assertRaises(ParentRevisionRequired):h.save(self.new,self.r,self.rows(),edits,'sync',{self.p:'101'})
  h.save(self.new,self.r,self.rows(),edits,'sync',{self.p:'101',q:'101'})
  self.assertEqual(target.bom(u)[0]['version'],'101')
  self.assertEqual(target.material_snapshot(self.c)['name'],'all latest')
  self.assertEqual(self.s.for_sku(uid).material_snapshot(self.c)['name'],'C')
  self.assertEqual(self.s.for_sku(uid).bom(u)[0]['version'],'100')
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  h.save(self.new,self.r,self.rows(),{},'fork')
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))


if __name__=='__main__':unittest.main()
