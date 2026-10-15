import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate,revision_conflicts,save_with_revisions,ParentRevisionRequired,latest_usage

class SnapshotTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.r,self.p,self.c,self.a=[self.material(x) for x in ('R','P','C','A')]
  self.sid=self.s.create_sku(self.r)
  self.s.save_bom(self.p,[self.row(self.c)])
  self.s.save_bom(self.r,[self.row(self.p)])
  migrate(self.db);self.m=self.s.for_sku(self.sid)
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def material(self,code,version='1'):return self.s.create_material(dict(base_code=code,version=version,name=code,unit='pcs'))
 def row(self,mid,**kw):return dict(material_id=mid,quantity=1,unit='pcs',**kw)
 def test_sku_exempt_add_delete_replace_without_version_change(self):
  copy=self.s.copy_sku_bom(self.sid)
  self.m.save_bom(self.r,[self.row(self.a)])
  self.assertEqual(self.s.material_snapshot(self.r)['version'],'1')
  self.assertEqual(self.s.for_sku(copy).bom(self.r)[0]['material_id'],self.p)
  self.m.save_bom(self.r,[]);self.assertEqual(self.m.bom(self.r),[])
 def test_non_sku_change_requires_revision_and_preserves_history(self):
  copy=self.s.copy_sku_bom(self.sid)
  rows=[self.row(self.p),self.row(self.a,parent_material_id=self.p)]
  with self.assertRaises(ParentRevisionRequired):self.m.save_bom(self.r,rows)
  mapping=save_with_revisions(self.m,self.r,rows,{self.p:'2'})
  self.assertEqual(self.m.bom(self.r)[0]['material_id'],mapping[self.p])
  self.assertEqual(self.m.bom(self.r)[1]['material_id'],self.a)
  self.assertEqual(self.s.for_sku(copy).bom(self.r)[1]['material_id'],self.c)
  self.assertEqual(self.s.material_snapshot(self.r)['version'],'1')
 def test_child_revision_and_attributes_do_not_require_parent_revision(self):
  c2=self.material('C','2');copy=self.s.copy_sku_bom(self.sid)
  self.m.save_bom(self.r,[self.row(self.p),dict(material_id=c2,parent_material_id=self.p,quantity=2.345,unit='pcs',position='x',remark='new',alternate_material_ids=[self.a])])
  self.assertEqual(self.m.bom(self.r)[0]['material_id'],self.p)
  self.assertEqual(self.s.for_sku(copy).bom(self.r)[1]['material_id'],self.c)
  self.assertEqual(self.s.for_sku(copy).alternates(self.s.for_sku(copy).bom(self.r)[1]['id']),[])
 def test_delete_children_requires_revision_preview_does_not(self):
  rows=[self.row(self.p,replace_children=True)]
  self.assertEqual([x['material_id'] for x in revision_conflicts(self.m,self.r,rows)],[self.p])
  self.m.save_bom(self.r,rows,preview=True)
  save_with_revisions(self.m,self.r,rows,{self.p:'2'})
  self.assertEqual(len(self.m.bom(self.r)),1)
 def test_revision_failure_rolls_back_material_and_tree(self):
  rows=[self.row(self.p),self.row(self.a,parent_material_id=self.p)]
  before=[dict(r) for r in self.m.bom(self.r)]
  with patch.object(self.m,'save_bom',side_effect=ValueError('failure')):
   with self.assertRaises(ValueError):save_with_revisions(self.m,self.r,rows,{self.p:'2'})
  self.assertIsNone(self.db.conn.execute("SELECT id FROM materials WHERE base_code='P' AND version='2'").fetchone())
  self.assertEqual(self.m.bom(self.r),before)
 def test_latest_usage_and_new_sku_atomicity(self):
  copy=self.s.copy_sku_bom(self.sid);self.s.for_sku(copy).save_bom(self.r,[self.row(self.a)])
  self.assertEqual(latest_usage(self.s),{self.r,self.a})
  self.assertEqual({r['id']:r['latest_used'] for r in self.s.materials()}[self.c],'N')
  with patch('services.mirrors.create_namespace',side_effect=RuntimeError('failure')):
   with self.assertRaises(RuntimeError):self.s.create_sku(self.a)
  self.assertEqual(len(self.s.skus()),2)
 def test_migration_backup_and_usage_reopen(self):
  self.assertTrue(self.s.material_is_bom_referenced(self.c))
  self.assertEqual(len(list(Path(self.tmp.name).glob('*.pre-whole-tree-*.db'))),1)
  migrate(self.db);self.assertEqual(len(list(Path(self.tmp.name).glob('*.pre-whole-tree-*.db'))),1)
  self.db.close();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.assertEqual(self.s.for_sku(self.sid).bom(self.r)[1]['material_id'],self.c)
 def test_sku_material_used_as_parent_is_also_exempt(self):
  self.s.create_sku(self.p)
  self.m.save_bom(self.r,[self.row(self.p),self.row(self.a,parent_material_id=self.p)])
  self.assertEqual(self.s.material_snapshot(self.p)['version'],'1')
 def test_legacy_conflict_preserved_and_requires_explicit_revision(self):
  copy=self.s.copy_sku_bom(self.sid)
  self.db.conn.execute('DELETE FROM app_metadata WHERE key=?',('whole_tree_snapshots_v2',))
  self.db.conn.execute(f'UPDATE mirror_{copy}_material_bom_items SET child_material_id=? WHERE parent_material_id=?',(self.a,self.p));self.db.conn.commit()
  migrate(self.db)
  target=self.s.for_sku(copy)
  self.assertEqual(target.bom(self.r)[1]['material_id'],self.a)
  self.assertEqual(self.m.bom(self.r)[1]['material_id'],self.c)
  self.assertEqual(len(revision_conflicts(target,self.r,target.bom(self.r))),1)
 def test_revision_retains_unedited_alternates(self):
  self.m.add_alternate(self.m.bom(self.r)[0]['id'],self.a)
  rows=[dict(r) for r in self.m.bom(self.r)];rows[1]['material_id']=self.a
  save_with_revisions(self.m,self.r,rows,{self.p:'2'})
  self.assertEqual(self.m.alternates(self.m.bom(self.r)[0]['id'])[0]['material_id'],self.a)
 def test_existing_incompatible_revision_rejected(self):
  p2=self.material('P','2')
  self.db.conn.execute('INSERT INTO bom_revision_definitions VALUES(?,?)',(p2,'["C"]'));self.db.conn.commit()
  rows=[self.row(self.p),self.row(self.a,parent_material_id=self.p)]
  with self.assertRaisesRegex(ValueError,'不同的子料'):save_with_revisions(self.m,self.r,rows,{self.p:'2'})
  self.assertEqual(self.m.bom(self.r)[0]['material_id'],self.p)
 def test_parent_dialog_cancel_retains_draft_and_sku_save_no_dialog(self):
  from PyQt5.QtWidgets import QApplication,QMessageBox,QDialog
  from ui.main_window import BomWindow
  from ui.parent_revision import ParentRevisionDialog
  app=QApplication.instance() or QApplication([])
  w=BomWindow(self.m,self.r)
  try:
   w.remove_relation(w.root_item.child(0).child(0))
   with patch.object(ParentRevisionDialog,'exec_',return_value=QDialog.Rejected):self.assertFalse(w.save())
   self.assertTrue(w.dirty);self.assertEqual(len(self.m.bom(self.r)),2)
   w.load();w.dirty=False
   w.remove_relation(w.root_item.child(0))
   with patch.object(ParentRevisionDialog,'exec_') as dialog,patch.object(QMessageBox,'information'):
    self.assertTrue(w.save());dialog.assert_not_called()
   self.assertEqual(self.s.material_snapshot(self.r)['version'],'1')
  finally:w.dirty=False;w.close()

 def test_sku_revision_remains_manually_editable_when_referenced(self):
  self.s.create_sku(self.p)
  sid=next(r['id'] for r in self.s.skus() if r['material_id']==self.p)
  self.s.change_sku_version(sid,'2')
  self.assertEqual(self.s.material_snapshot(self.p)['version'],'2')
  self.assertEqual(self.s.for_sku(sid).bom(self.p)[0]['material_id'],self.c)
