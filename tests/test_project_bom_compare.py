import os,sys,tempfile,unittest,sqlite3,hashlib
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from services.project_bom_compare import read_project
from services.bom_compare import snapshot,compare_trees
from config.config_service import ConfigService
from config.project_registry import ProjectRegistry
from ui.main_window import MainWindow


class ProjectBomCompareTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
  self.db=Database(str(self.base/'local.db'));self.foreign=Database(str(self.base/'其他项目.db'))
  self.config=ConfigService(self.base);self.s=Services(self.db,self.config);self.other=Services(self.foreign)
  for svc in (self.s,self.other):
   root,child=[svc.create_material(dict(base_code=c,version='100',name=c,unit='pcs')) for c in ('ROOT','PART')]
   svc.create_sku(root);svc.save_bom(root,[dict(material_id=child,quantity=2,unit='pcs')])
  self.other.update_project(dict(project_code='OTHER',project_name='其他项目'))
  self.registry=ProjectRegistry(self.config);self.registry.remember(self.foreign.path,dict(self.other.project()))
  self.main=MainWindow(self.s);self.main.compare_boms();self.dialog=self.main._compare_dialog
  self.dialog.left.setCurrentIndex(self.dialog.left.findData(1));self.dialog.right.setCurrentIndex(self.dialog.right.findData(1));self.dialog.compare()
 def tearDown(self):
  for window in self.main._bom_windows.values():window.dirty=False
  self.main.close();self.dialog.close();self.db.close();self.foreign.close();self.app.processEvents();self.tmp.cleanup()
 def choose(self,side=1,cancel=None,browse=None):
  count=0
  def pick(parent,title,label,items,*args):
   nonlocal count
   count+=1
   return (items[-1] if browse and count==1 else items[0],count!=cancel)
  combo=(self.dialog.left,self.dialog.right)[side];combo.setCurrentIndex(combo.findData('load_project'))
  with patch('ui.bom_compare.QInputDialog.getItem',side_effect=pick),patch('ui.bom_compare.QFileDialog.getOpenFileName',return_value=(str(browse or ''),'')):
   self.dialog.choose_source(side)
 def test_load_both_sides_and_read_only_same_ids(self):
  before=(self.db.conn.total_changes,self.foreign.conn.total_changes,Path(self.foreign.path).read_bytes(),self.config.path.read_bytes())
  self.choose();self.assertTrue(self.dialog.right.currentData().startswith('project:'))
  self.assertEqual(self.dialog.right.itemText(self.dialog.right.count()-1),'载入其他项目')
  self.assertTrue(all(r.status=='same' for r in self.dialog._rows))
  with patch.object(self.main,'open_bom_id') as editor,patch.object(self.s,'update_material') as edit:
   self.dialog.open_editor(1,1);self.dialog.edit_material(1,1);editor.assert_not_called();edit.assert_not_called()
  self.choose(0);self.assertTrue(all(r.status=='same' for r in self.dialog._rows))
  self.assertEqual(before,(self.db.conn.total_changes,self.foreign.conn.total_changes,Path(self.foreign.path).read_bytes(),self.config.path.read_bytes()))
  self.assertIs(self.main.svc.db,self.db)
 def test_cancel_each_stage_preserves_results_and_selection(self):
  rows=self.dialog._rows
  for stage in (1,2):
   self.choose(cancel=stage);self.assertEqual(self.dialog.right.currentData(),1)
   self.assertIs(self.dialog._rows,rows);self.assertTrue(self.dialog._compared)
  self.choose(browse='');self.assertTrue(self.dialog._compared)
 def test_browse_and_failure_leave_previous_comparison(self):
  self.choose(browse=self.foreign.path);key=self.dialog.right.currentData();rows=self.dialog._rows
  for path in (self.base/'missing.db',self.base/'not-sqlite.db',Path(self.db.path)):
   if path.name=='not-sqlite.db':path.write_text('invalid')
   with patch('ui.bom_compare.QMessageBox.warning') as warning:
    self.choose(browse=path);warning.assert_called_once()
   self.assertEqual(self.dialog.right.currentData(),key);self.assertIs(self.dialog._rows,rows)
  self.assertFalse((self.base/'missing.db').exists())
 def test_empty_and_unrelated_database_rejected(self):
  for name in ('empty.db','unrelated.db'):
   path=self.base/name
   if name=='empty.db':Database(str(path)).close()
   else:
    conn=sqlite3.connect(str(path));conn.execute('CREATE TABLE unrelated(id)');conn.close()
   before=path.read_bytes()
   with patch('ui.bom_compare.QMessageBox.warning') as warning:self.choose(browse=path);warning.assert_called_once()
   self.assertEqual(path.read_bytes(),before);self.assertEqual(self.dialog.right.currentData(),1)
 def test_local_unsaved_draft_not_replaced_by_foreign_same_id(self):
  bom=self.main.open_bom_id(1);item=bom.root_item.child(0)
  data=dict(item.data(0,Qt.UserRole));data['quantity']=9;item.setData(0,Qt.UserRole,data);bom.mark_dirty()
  self.choose()
  self.assertEqual(self.dialog._rows[1].left['quantity'],9);self.assertEqual(self.dialog._rows[1].right['quantity'],2)
  self.assertTrue(bom.dirty);self.assertEqual(self.s.bom(1)[0]['quantity'],2)
  self.assertEqual(item.data(0,Qt.UserRole)['quantity'],9)
 def test_refresh_reads_committed_wal_and_missing_sku_clears_results(self):
  self.foreign.conn.execute('PRAGMA journal_mode=WAL');self.choose()
  self.other.save_bom(1,[dict(material_id=2,quantity=7,unit='pcs')]);self.dialog.compare()
  self.assertEqual(self.dialog._rows[1].right['quantity'],7)
  self.foreign.conn.execute('DELETE FROM skus WHERE id=1');self.foreign.conn.commit()
  with patch('ui.bom_compare.QMessageBox.warning') as warning:self.dialog.compare();warning.assert_called_once()
  self.assertFalse(self.dialog._compared);self.assertEqual(self.dialog._rows,[])
 def test_historical_bindings_and_alternates_are_preserved(self):
  from services.snapshot_bom import migrate
  from services.current_catalog import initialize
  from services.material_history import initialize as histories
  alt=self.other.create_material(dict(base_code='ALT',version='100',name='替代料',unit='pcs'))
  self.other.add_alternate(self.other.bom(1)[0]['id'],alt)
  migrate(self.foreign);initialize(self.foreign);histories(self.foreign)
  newer=self.other.copy_sku_bom(1)
  scoped=self.other.for_sku(newer);scoped.save_bom(1,[dict(material_id=2,quantity=5,unit='pcs',alternate_material_ids=[alt])])
  before=Path(self.foreign.path).read_bytes()
  catalogue=read_project(self.foreign.path);self.assertEqual(len(catalogue['skus']),2)
  for sku in self.other.skus():
   tree=read_project(self.foreign.path,sku['id']);expected=snapshot(self.other,dict(sku))
   self.assertTrue(all(r.status=='same' for r in compare_trees(expected,tree)))
   self.assertEqual(tree['children'][0]['alternate_codes'],{('ALT','100')})
  self.assertEqual(read_project(self.foreign.path,1)['children'][0]['quantity'],2)
  self.assertEqual(read_project(self.foreign.path,newer)['children'][0]['quantity'],5)
  self.assertEqual(Path(self.foreign.path).read_bytes(),before)
 def test_live_foreign_draft_refresh_discard_and_no_idle_rebuild(self):
  from PyQt5.QtTest import QTest
  other=MainWindow(Services(self.foreign,ConfigService(self.base/'other-config')))
  try:
   editor=other.open_bom_id(1);other._live_project.flush();self.choose()
   item=editor.root_item.child(0);editor.show_item_info(item);editor.fields['quantity'].setText('8')
   QTest.qWait(750)
   self.assertTrue(editor.dirty);self.assertEqual(self.other.bom(1)[0]['quantity'],2)
   self.assertEqual(self.dialog._rows[1].right['quantity'],8)
   self.assertIn('未保存草稿',self.dialog.summary.text())
   with patch.object(self.dialog,'compare',wraps=self.dialog.compare) as compare:
    QTest.qWait(750);self.assertEqual(compare.call_count,0)
   editor.history.undo();QTest.qWait(750)
   self.assertEqual(self.dialog._rows[1].right['quantity'],2)
   editor.history.redo();QTest.qWait(750)
   self.assertEqual(self.dialog._rows[1].right['quantity'],8)
   editor.dirty=False;editor.close();QTest.qWait(750)
   self.assertEqual(self.dialog._rows[1].right['quantity'],2)
   self.assertIn('已保存BOM',self.dialog.summary.text())
  finally:
   for w in other._bom_windows.values():w.dirty=False
   other.close()
 def test_stale_or_failed_live_cache_not_used_as_saved_data(self):
  from infrastructure.live_project_cache import LiveProjectWriter,read_live_project,project_signature
  writer=LiveProjectWriter(self.foreign.path)
  try:
   writer.write({'error':'草稿不可用'});self.assertTrue(writer.active)
   with self.assertRaisesRegex(ValueError,'草稿不可用'):read_project(self.foreign.path,1)
   signature=project_signature(self.foreign.path);writer.write({'error':'草稿不可用'})
   self.assertEqual(project_signature(self.foreign.path),signature)
   # Simulate a dead owner that cannot remove its cache.
   writer.lock.close();writer.active=False
   self.assertIsNone(read_live_project(self.foreign.path))
   self.assertEqual(read_project(self.foreign.path,1)['children'][0]['quantity'],2)
  finally:writer.close();writer.cache.unlink(missing_ok=True)


if __name__=='__main__':unittest.main()
