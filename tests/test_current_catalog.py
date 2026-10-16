import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate
from services.current_catalog import initialize,selection_tree
from ui.main_window import BomWindow,MaterialSelectionDialog

class CurrentCatalogTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.r,self.t,self.p,self.c,self.a,self.p2=[self.s.create_material(dict(base_code=code,version=version,name=code,unit='pcs')) for code,version in [('R','1'),('T','1'),('P','1'),('C','1'),('A','1'),('P','2')]]
  self.s.save_bom(self.p,[self.row(self.c,quantity=2)])
  self.s.save_bom(self.r,[self.row(self.p)])
  self.s.save_bom(self.t,[self.row(self.p)])
  self.sid=self.s.create_sku(self.r);self.tid=self.s.create_sku(self.t)
  migrate(self.db);initialize(self.db)
  self.m=self.s.for_sku(self.sid)
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def row(self,mid,quantity=1,**kw):return dict(material_id=mid,quantity=quantity,unit='pcs',**kw)
 def change_quantity(self,service,root,value):
  rows=service.bom(root)
  for row in rows:
   if row['parent_material_id']==self.p:row.update(quantity=value,alternate_material_ids=[self.a],remark='latest')
  service.save_bom(root,rows)
 def test_latest_sync_public_and_history_isolated(self):
  copy=self.s.copy_sku_bom(self.sid)
  self.change_quantity(self.s.for_sku(copy),self.r,7.25)
  self.assertEqual(self.s.bom(self.p)[0]['quantity'],7.25)
  self.assertEqual(self.s.for_sku(self.tid).bom(self.p)[0]['quantity'],7.25)
  self.assertEqual(self.m.bom(self.p)[0]['quantity'],2)
  self.assertEqual(self.s.for_sku(self.tid).alternates(self.s.for_sku(self.tid).bom(self.p)[0]['id'])[0]['material_id'],self.a)
  self.change_quantity(self.m,self.r,4)
  self.assertEqual(self.s.bom(self.p)[0]['quantity'],7.25)
 def test_add_uses_public_not_historical_capture_and_does_not_write_draft(self):
  copy=self.s.copy_sku_bom(self.sid);self.change_quantity(self.s.for_sku(copy),self.r,9)
  w=BomWindow(self.m,self.r)
  try:
   old=w.root_item.child(0);w.remove_relation(old)
   material=self.s.material_snapshot(self.p);material['name']='stale'
   before=[dict(r) for r in self.m.bom(self.r)]
   added=w.insert_material(w.root_item,material)
   self.assertEqual(added.child(0).text(1),'9');self.assertIn('P1 P',added.text(0))
   self.assertEqual(w.alternate_ids(added.child(0)),[self.a])
   self.assertEqual(self.m.bom(self.r),before)
  finally:w.dirty=False;w.close()
 def test_replacement_and_version_use_public_target(self):
  self.s.save_bom(self.p2,[self.row(self.a,quantity=6)])
  for version in (False,True):
   w=BomWindow(self.m,self.r)
   try:
    with patch.object(MaterialSelectionDialog,'getItem',return_value=('P2 P',True)),patch.object(QMessageBox,'question') as question:
     node=w.update_material_version(w.root_item.child(0)) if version else w.replace_material(w.root_item.child(0))
    question.assert_not_called();self.assertEqual(node.child(0).text(1),'6')
    self.assertEqual(node.child(0).data(0,Qt.UserRole)['material_id'],self.a)
    self.assertEqual(self.m.bom(self.r)[0]['material_id'],self.p)
   finally:w.dirty=False;w.close()
 def test_delete_prunes_namespace_cache_and_preserves_other_history(self):
  copy=self.s.copy_sku_bom(self.sid);scoped=self.s.for_sku(copy)
  scoped.save_bom(self.r,[])
  for table in ('material_bom_items','alternates','bom_items'):
   self.assertEqual(scoped.db.conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
  self.assertEqual([r[0] for r in self.db.conn.execute('SELECT material_id FROM mirror_captured_materials WHERE sku_id=?',(copy,))],[self.r])
  self.assertEqual(self.m.bom(self.r)[1]['material_id'],self.c)
  self.assertEqual(self.s.for_sku(self.tid).bom(self.t)[1]['material_id'],self.c)
  self.assertTrue(self.s.material_snapshot(self.p))
  self.s.for_sku(self.tid).save_bom(self.t,[])
  self.assertEqual(self.s.bom(self.p),[])
  self.assertEqual(self.m.bom(self.p)[0]['material_id'],self.c)
 def test_sync_failure_rolls_back_and_does_not_notify(self):
  from services.mirror_service import MirrorServices
  from infrastructure.events import WindowRefreshBus
  original=MirrorServices.save_bom;events=[]
  def fail(service,*args,**kwargs):
   if getattr(service,'_catalog_sync',False):raise RuntimeError('sync failure')
   return original(service,*args,**kwargs)
  WindowRefreshBus.subscribe(events.append)
  try:
   with patch.object(MirrorServices,'save_bom',fail):
    with self.assertRaisesRegex(RuntimeError,'sync failure'):self.change_quantity(self.m,self.r,8)
   self.assertEqual(events,[])
   self.assertEqual(self.m.bom(self.p)[0]['quantity'],2);self.assertEqual(self.s.bom(self.p)[0]['quantity'],2)
  finally:WindowRefreshBus.unsubscribe(events.append)
 def test_migration_reconciles_latest_and_backs_up(self):
  self.assertEqual(len(list(Path(self.tmp.name).glob('*.pre-latest-catalog-*.db'))),1)
  initialize(self.db)
  self.assertEqual(len(list(Path(self.tmp.name).glob('*.pre-latest-catalog-*.db'))),1)
  self.assertEqual(self.db.conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_latest_empty_structure_does_not_resurrect_historical_cache(self):
  # Remove the other SKU reference, then clear the exclusively owned parent.
  self.s.for_sku(self.tid).save_bom(self.t,[])
  self.m.save_bom(self.r,[self.row(self.p,replace_children=True)])
  self.assertEqual(selection_tree(self.m,self.p),[])
  self.assertEqual(next(r['has_bom'] for r in self.s.materials() if r['id']==self.p),'N')
  w=BomWindow(self.m,self.r)
  try:
   w.remove_relation(w.root_item.child(0));node=w.insert_material(w.root_item,self.s.material_snapshot(self.p))
   self.assertEqual(node.childCount(),0)
  finally:w.dirty=False;w.close()
 def test_sync_refresh_notification_preserves_local_draft(self):
  other=self.s.for_sku(self.tid);w=BomWindow(other,self.t)
  try:
   w.show_item_info(w.root_item.child(0));w.fields['remark'].setText('local draft')
   self.change_quantity(self.m,self.r,12)
   self.assertTrue(w.refresh_action.isEnabled());self.assertFalse(w.export_action.isEnabled())
   w.refresh_external()
   self.assertEqual(w.root_item.child(0).text(4),'local draft')
   self.assertEqual(w.root_item.child(0).child(0).text(1),'12')
   self.assertTrue(w.save_action.isEnabled())
  finally:w.dirty=False;w.close()
 def test_initialize_reconciles_conflicting_latest_by_save_time_preserving_history(self):
  copy=self.s.copy_sku_bom(self.sid)
  self.db.conn.execute('DELETE FROM app_metadata WHERE key=?',('latest_mirror_catalog_v1',))
  self.db.conn.execute(f'UPDATE mirror_{copy}_material_bom_items SET quantity=17 WHERE parent_material_id=?',(self.p,))
  self.db.conn.execute("UPDATE skus SET updated_at='2099-01-01 00:00:00' WHERE id=?",(copy,));self.db.conn.commit()
  initialize(self.db)
  self.assertEqual(self.s.bom(self.p)[0]['quantity'],17)
  self.assertEqual(self.s.for_sku(self.tid).bom(self.p)[0]['quantity'],17)
  self.assertEqual(self.m.bom(self.p)[0]['quantity'],2)
 def test_latest_changes_reopen_and_indexes(self):
  self.change_quantity(self.m,self.r,11)
  self.db.close();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db);initialize(self.db)
  self.assertEqual(self.s.for_sku(self.tid).bom(self.p)[0]['quantity'],11)
  indexes={r[0] for r in self.db.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
  self.assertIn('mirror_usage_parent',indexes);self.assertIn(f'mirror_{self.sid}_alternates_relation',indexes)
  self.assertEqual(self.db.conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_sync_cycle_rolls_back_public_and_all_latest(self):
  # The destination SKU root is a descendant in an imported shared subtree.
  before=[dict(r) for r in self.m.bom(self.r)]
  from services.current_catalog import synchronize
  with self.assertRaisesRegex(ValueError,'循环'):
   with self.db.transaction():
    self.m.db.conn.execute('UPDATE material_bom_items SET child_material_id=? WHERE parent_material_id=?',(self.t,self.p))
    self.m.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit) VALUES(?,?,1,?)',(self.t,self.p,'pcs'))
    synchronize(self.m,{self.p})
  self.assertEqual(self.m.bom(self.r),before)
  self.assertEqual(self.s.bom(self.p)[0]['material_id'],self.c)
 def test_confirm_all_syncs_base_code_change_without_parent_revision(self):
  from services.current_catalog import synchronization_plan,save_confirmed
  latest=self.s.copy_sku_bom(self.sid);self.m=self.s.for_sku(latest)
  rows=[self.row(self.p,replace_children=True),self.row(self.a,parent_material_id=self.p)]
  plan=synchronization_plan(self.m,self.r,rows)
  self.assertEqual(len(plan),1);self.assertIn('新增物料：A1 A',plan[0]['detail'])
  self.assertIn('删除物料：C1 C',plan[0]['detail'])
  save_confirmed(self.m,self.r,rows,plan,{self.p:{self.tid}},{})
  self.assertEqual(self.s.material_snapshot(self.p)['version'],'1')
  self.assertEqual(self.s.for_sku(self.tid).bom(self.p)[0]['material_id'],self.a)
  self.assertEqual(self.s.for_sku(self.sid).bom(self.p)[0]['material_id'],self.c)
 def test_partial_confirmation_forks_parent_and_updates_only_checked_sku(self):
  from services.current_catalog import synchronization_plan,save_confirmed
  u=self.s.create_material(dict(base_code='U',version='1',name='third',unit='pcs'))
  uid=self.s.create_sku(u);self.s.for_sku(uid).save_bom(u,[self.row(self.p),self.row(self.c,parent_material_id=self.p,quantity=2)])
  rows=self.m.bom(self.r);rows[1]['quantity']=8
  plan=synchronization_plan(self.m,self.r,rows)
  self.assertEqual({r['id'] for r in plan[0]['other_skus']},{self.tid,uid})
  result=save_confirmed(self.m,self.r,rows,plan,{self.p:{self.tid}},{self.p:'3'})
  new=result[self.p]
  self.assertEqual(self.m.bom(self.r)[0]['material_id'],new)
  self.assertEqual(self.s.for_sku(self.tid).bom(self.t)[0]['material_id'],new)
  self.assertEqual(self.s.for_sku(self.tid).bom(new)[0]['quantity'],8)
  self.assertEqual(self.s.for_sku(uid).bom(u)[0]['material_id'],self.p)
  self.assertEqual(self.s.for_sku(uid).bom(self.p)[0]['quantity'],2)
  self.assertEqual(self.s.bom(self.p)[0]['quantity'],2)
  self.assertEqual(self.s.bom(new)[0]['quantity'],8)
 def test_unchecked_requires_new_version_and_stale_confirmation_rejected(self):
  from services.current_catalog import synchronization_plan,save_confirmed
  rows=self.m.bom(self.r);rows[1]['quantity']=8
  plan=synchronization_plan(self.m,self.r,rows)
  with self.assertRaises(ValueError):save_confirmed(self.m,self.r,rows,plan,{self.p:set()},{})
  self.assertEqual(self.m.bom(self.p)[0]['quantity'],2)
  self.s.for_sku(self.tid).save_bom(self.t,[])
  with self.assertRaisesRegex(ValueError,'已变化'):save_confirmed(self.m,self.r,rows,plan,{self.p:{self.tid}},{})
 def test_confirmation_ui_cancel_retains_draft_and_all_checked_saves(self):
  from PyQt5.QtWidgets import QDialog
  from ui.bom_sync_confirmation import BomSyncConfirmationDialog
  w=BomWindow(self.m,self.r)
  try:
   w.show_item_info(w.root_item.child(0).child(0));w.fields['quantity'].setValue(14)
   with patch.object(BomSyncConfirmationDialog,'exec_',return_value=QDialog.Rejected):self.assertFalse(w.save())
   self.assertTrue(w.dirty);self.assertEqual(self.m.bom(self.p)[0]['quantity'],2)
   def accept(dialog):
    self.assertIn('T1 T / 镜像100',dialog.table.item(0,3).text())
    self.assertIn('数量：2 → 14',dialog.table.item(0,2).text())
    self.assertEqual(dialog.selections(),{self.p:{self.tid}})
    return QDialog.Accepted
   with patch.object(BomSyncConfirmationDialog,'exec_',accept),patch.object(QMessageBox,'information'):
    self.assertTrue(w.save())
   self.assertEqual(self.s.for_sku(self.tid).bom(self.p)[0]['quantity'],14)
  finally:w.dirty=False;w.close()
