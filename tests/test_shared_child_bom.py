import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox,QDialog
from ui.interactive_windows import QMessageBox
from database.database import Database
from services.services import Services
from services.shared_bom import migrate,migration_candidates,conflicts,is_shared
from services.mirrors import create_namespace,table_name
from ui.shared_bom_migration import SharedBomMigrationDialog
from ui.main_window import MainWindow

class SharedChildBomTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';self.db=Database(str(self.path));self.s=Services(self.db)
  self.r,self.p,self.c,self.a=[self.s.create_material(dict(base_code=v,version='1',name=v,unit='pcs')) for v in ('R','P','C','A')]
  self.sid=self.s.create_sku(self.r);self.s.save_bom(self.p,[dict(material_id=self.c,quantity=2,unit='pcs')]);self.s.save_bom(self.r,[dict(material_id=self.p,quantity=3,unit='pcs')])
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def legacy(self):
  sid=self.db.conn.execute('INSERT INTO skus(material_id,mirror_version) VALUES(?,107)',(self.r,)).lastrowid
  self.db.conn.execute('UPDATE skus SET scope_id=? WHERE id=?',(sid,sid))
  with patch('services.shared_bom.is_shared',return_value=False):create_namespace(self.db,sid,self.s)
  self.db.conn.execute(f'UPDATE {table_name(sid,"material_bom_items")} SET quantity=7 WHERE parent_material_id=?',(self.p,))
  self.db.conn.execute(f'UPDATE {table_name(sid,"material_bom_items")} SET quantity=4 WHERE parent_material_id=?',(self.r,))
  self.db.conn.execute("DELETE FROM app_metadata WHERE key='shared_child_bom_v1'");self.db.conn.commit();return sid
 def test_migration_requires_choices_backup_preserves_roots_and_shared_alternates(self):
  sid=self.legacy();pending=conflicts(migration_candidates(self.db));self.assertEqual(set(pending),{self.p})
  with self.assertRaisesRegex(ValueError,'逐项'):migrate(self.db)
  self.assertFalse(is_shared(self.db.conn));self.assertEqual(self.s.bom(self.p)[0]['quantity'],2)
  dialog=SharedBomMigrationDialog(self.db,pending)
  try:
   with patch.object(QMessageBox,'warning') as warn:dialog.validate();warn.assert_called_once()
   self.assertFalse(is_shared(self.db.conn));self.assertIn('历史版本107',dialog.preview.toPlainText())
   combo=dialog.combos[self.p];combo.setCurrentIndex(combo.findData(sid));dialog.validate();self.assertEqual(dialog.result(),QDialog.Accepted)
  finally:dialog.close()
  self.assertTrue(is_shared(self.db.conn));self.assertEqual(len(list(self.path.parent.glob('*.pre-shared-bom-*.db'))),1)
  mirror=self.s.for_sku(sid);self.assertEqual(self.s.bom(self.p)[0]['quantity'],7);self.assertEqual(mirror.bom(self.r)[0]['quantity'],4);self.assertEqual(self.s.bom(self.r)[0]['quantity'],3)
  from services.snapshot_bom import migrate as migrate_snapshots
  migrate_snapshots(self.db)
  rid=mirror.bom(self.p)[0]['id'];mirror.add_alternate(rid,self.a);self.assertEqual(self.s.alternates(rid),[])
  self.assertEqual(mirror.alternates(rid)[0]['material_id'],self.a)
  self.db.close();self.db=Database(str(self.path));self.s=Services(self.db);self.assertEqual(self.s.for_sku(sid).bom(self.p)[0]['quantity'],7)
 def test_private_edit_notifies_only_its_mirror(self):
  copy=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copy);main=MainWindow(self.s);a=main.open_bom_id(self.sid);b=main.open_bom_id(copy)
  try:
   mirror.save_bom(self.p,[dict(material_id=self.c,quantity=8,unit='pcs',alternate_material_ids=[self.a])])
   self.assertEqual(self.s.bom(self.p)[0]['quantity'],2);self.assertFalse(a.refresh_action.isEnabled());self.assertTrue(b.refresh_action.isEnabled())
   refs=self.s.material_version_references(self.c);self.assertEqual(len(refs),2);self.assertEqual({sid for ref in refs for sid in ref['sku_ids']},{self.sid,copy})
   a.refresh_external();b.refresh_external();a.dirty=False;b.dirty=False
   self.s.save_bom(self.r,[dict(material_id=self.p,quantity=6,unit='pcs'),dict(material_id=self.c,parent_material_id=self.p,quantity=8,unit='pcs',alternate_material_ids=[self.a])])
   self.assertEqual(mirror.bom(self.r)[0]['quantity'],3);self.assertEqual(self.s.bom(self.r)[0]['quantity'],6)
   mirror.save_bom(self.r,[]);self.assertEqual(self.s.bom(self.p)[0]['quantity'],8);self.assertEqual(mirror.bom(self.r),[])
   self.s.delete_sku(copy);self.assertEqual(self.s.bom(self.p)[0]['quantity'],8)
  finally:
   for w in list(main._bom_windows.values()):w.dirty=False;w.close()
   main.close()
 def test_public_choice_empty_choice_and_cancel_leave_no_silent_overwrite(self):
  sid=self.legacy();pending=conflicts(migration_candidates(self.db));dialog=SharedBomMigrationDialog(self.db,pending);dialog.reject();dialog.close()
  self.assertFalse(is_shared(self.db.conn));migrate(self.db,{self.p:0});self.assertEqual(self.s.for_sku(sid).bom(self.p)[0]['quantity'],2)
  self.assertTrue(self.db.conn.execute('SELECT 1 FROM shared_bom_migration_archive WHERE material_id=?',(self.p,)).fetchone())
 def test_copy_mirror_root_alternates_and_shared_history_export(self):
  from openpyxl import load_workbook
  self.s.add_alternate(self.s.bom(self.r)[0]['id'],self.a)
  self.s.add_alternate(self.s.bom(self.p)[0]['id'],self.a)
  one=self.s.copy_sku_bom(self.sid);two=self.s.copy_sku_bom(one);mirror=self.s.for_sku(two)
  root_id=mirror.bom(self.r)[0]['id'];self.assertEqual(mirror.alternates(root_id)[0]['material_id'],self.a)
  mirror.save_bom(self.p,[dict(material_id=self.c,quantity=9,unit='pcs',remark='公共子BOM测试备注')])
  self.s.for_sku(one).save_bom(self.p,[dict(material_id=self.c,quantity=10,unit='pcs',remark='再次公共编辑')])
  path=Path(self.tmp.name)/'out.xlsx';self.s.export_sku(two,path);wb=load_workbook(path)
  try:
   text='\n'.join(str(cell.value or '') for row in wb['变更记录'] for cell in row)
   self.assertIn('公共子BOM测试备注',text);self.assertNotIn('再次公共编辑',text)
  finally:wb.close()
  mirror.save_bom(self.r,[dict(material_id=self.p,quantity=4,unit='pcs',alternate_material_ids=[]),dict(material_id=self.c,parent_material_id=self.p,quantity=10,unit='pcs',remark='再次公共编辑')])
  self.assertEqual(mirror.alternates(root_id),[]);self.assertEqual(self.s.for_sku(one).alternates(self.s.for_sku(one).bom(self.r)[0]['id'])[0]['material_id'],self.a)
 def test_migration_empty_definition_and_cycle_validation(self):
  sid=self.legacy();table=table_name(sid,'material_bom_items')
  self.db.conn.execute(f'DELETE FROM {table} WHERE parent_material_id=?',(self.p,));self.db.conn.commit()
  pending=conflicts(migration_candidates(self.db));self.assertEqual(pending[self.p][1]['rows'],[])
  migrate(self.db,{self.p:sid});self.assertEqual(self.s.bom(self.p),[]);self.assertEqual(self.s.for_sku(sid).bom(self.p),[])
 def test_migration_cycle_and_transaction_rollback(self):
  sid=self.legacy();table=table_name(sid,'material_bom_items')
  self.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit) VALUES(?,?,1,?)',(self.a,self.p,'pcs'))
  self.db.conn.execute(f'UPDATE {table} SET child_material_id=? WHERE parent_material_id=?',(self.a,self.p));self.db.conn.commit()
  with self.assertRaisesRegex(ValueError,'循环'):migrate(self.db,{self.p:sid})
  self.assertFalse(is_shared(self.db.conn));self.assertEqual(self.s.bom(self.p)[0]['material_id'],self.c)
  with patch('services.shared_bom.install_overlay',side_effect=RuntimeError('模拟迁移失败')):
   with self.assertRaisesRegex(RuntimeError,'模拟'):migrate(self.db,{self.p:0})
  self.assertFalse(is_shared(self.db.conn));self.assertEqual(self.s.bom(self.p)[0]['material_id'],self.c)
  self.assertEqual(self.db.conn.execute('SELECT type FROM sqlite_master WHERE name=?',(table,)).fetchone()[0],'table')
 def test_shared_change_cannot_create_cycle_in_another_root_mirror(self):
  copy=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copy)
  # Public root no longer contains P; only the copied SKU still does.
  self.s.save_bom(self.r,[])
  before=[dict(r) for r in self.s.bom(self.p)]
  self.s.save_bom(self.p,[dict(material_id=self.r,quantity=1,unit='pcs')])
  self.assertEqual(mirror.bom(self.p)[0]['material_id'],self.c)
  self.assertEqual(mirror.bom(self.r)[0]['material_id'],self.p)
