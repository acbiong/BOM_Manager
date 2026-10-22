import os,sys,tempfile,unittest,sqlite3
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QFileDialog,QMessageBox,QDialog,QMenu
from ui.interactive_windows import QFileDialog,QMessageBox
from PyQt5.QtCore import QCoreApplication,QEvent
from config.config_service import ConfigService
from config.project_registry import ProjectRegistry
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow,ProjectDialog

class MultiProjectTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.config=ConfigService(self.base)
  self.s=Services(Database(str(self.base/'first.db')),self.config)
  self.s.update_project(dict(project_code='P1',project_name='项目一',product_name='产品一',product_model='A'))
  self.root=self.s.create_material(dict(base_code='SKU1',version='100',name='第一个SKU',unit='pcs'));self.sid=self.s.create_sku(self.root)
  self.window=MainWindow(self.s);self.first=self.window._project_id
 def tearDown(self):
  for window in list(self.window._bom_windows.values()):window.dirty=False;window.close()
  if self.window._materials:self.window._materials.close()
  self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.s.db.close();self.tmp.cleanup()
 def other(self,name='second.db'):
  path=self.base/name;db=Database(str(path));s=Services(db)
  s.update_project(dict(project_code='P2',project_name='项目二',product_name='产品二',product_model='B'))
  mid=s.create_material(dict(base_code='SKU2',version='100',name='第二个SKU',unit='pcs'));s.create_sku(mid);db.close();return path
 def test_switch_restores_data_metadata_settings_and_relative_paths(self):
  self.config.save_import_mapping('bom',{'物料名称':'旧表头'});path=self.other()
  self.window.show_materials();old_library=self.window._materials;self.window.open_bom_id(self.sid)
  self.assertTrue(self.window.switch_project(path));second=self.window._project_id
  self.assertFalse(old_library.isVisible());self.assertFalse(self.window._bom_windows);self.assertIn('P2 项目二',self.window.windowTitle())
  self.assertEqual(self.window.table.item(0,1).text(),'SKU2100')
  self.config.save_import_mapping('bom',{'物料名称':'新表头'})
  self.window.open_history_project(self.first)
  self.assertEqual(self.window.table.item(0,1).text(),'SKU1100');self.assertEqual(self.config.import_mapping('bom'),{'物料名称':'旧表头'})
  self.window.open_history_project(second);self.assertEqual(self.config.import_mapping('bom'),{'物料名称':'新表头'})
  self.assertEqual(len(self.window.projects.entries()),2)
  self.assertTrue(all(not Path(r['path']).is_absolute() for r in self.window.projects.entries()))
  self.assertEqual(self.config.load()['database']['path'],'second.db')
 def test_legacy_config_import_rebases_paths_and_never_rewrites_source(self):
  old=self.base/'legacy';old.mkdir();path=self.other('legacy/legacy.db')
  source=old/'old.ini';source.write_text('[database]\ndriver=sqlite\npath=legacy.db\nlast_bom_import_dir=.\n[materials]\nunits=pcs,米\n[project]\nproject_code=IMPORT\nproject_name=导入项目\n',encoding='utf-8');before=source.read_bytes()
  with patch.object(QFileDialog,'getOpenFileName',return_value=(str(source),'')):self.window.import_project()
  self.assertEqual(Path(self.s.db.path),path);self.assertEqual(self.s.project()['project_code'],'IMPORT');self.assertEqual(source.read_bytes(),before)
  record=self.window.projects.get(self.window._project_id);self.assertEqual(record['path'],'legacy/legacy.db')
  self.assertEqual(self.config.load()['database']['last_bom_import_dir'],'legacy');self.assertEqual(self.s.UNITS,['pcs','米'])
  source.unlink();self.window.open_history_project(self.first);self.window.open_history_project(record['id']);self.assertEqual(Path(self.s.db.path),path)
 def test_database_import_validation_rejects_unrelated_or_missing_without_mutation(self):
  unrelated=self.base/'unrelated.db';conn=sqlite3.connect(unrelated);conn.execute('CREATE TABLE example(id)');conn.close();before=unrelated.read_bytes()
  config_before=self.config.path.read_bytes()
  with patch.object(QMessageBox,'critical') as error:
   for path in (unrelated,self.base/'missing.db'):
    self.assertFalse(self.window.switch_project(path))
   self.assertEqual(error.call_count,2)
  self.assertEqual(unrelated.read_bytes(),before);self.assertFalse((self.base/'missing.db').exists());self.assertEqual(config_before,self.config.path.read_bytes());self.assertEqual(self.window._project_id,self.first)
 def test_new_project_form_persists_draft_before_database_chooser_and_no_overwrite(self):
  metadata=dict(project_code='NEW',project_name='新项目',product_name='新产品',product_model='X')
  def choose(dialog):
   self.assertEqual(self.window.projects.draft(),metadata);return QDialog.Accepted
  with patch.object(ProjectDialog,'exec_',return_value=QDialog.Accepted),patch.object(ProjectDialog,'data',return_value=metadata),patch.object(QFileDialog,'exec_',choose),patch.object(QFileDialog,'selectedFiles',return_value=[str(self.base/'new.db')]):self.window.new_project()
  self.assertEqual(self.s.project()['project_code'],'NEW');self.assertEqual(self.window.projects.draft(),{});self.assertEqual(len(self.s.skus()),0)
  before=(self.base/'first.db').read_bytes()
  with patch.object(QMessageBox,'critical'):self.assertFalse(self.window.switch_project(self.base/'first.db',create=True,metadata=metadata))
  self.assertEqual((self.base/'first.db').read_bytes(),before)
 def test_cancel_unsaved_bom_keeps_current_config_and_removes_new_database(self):
  editor=self.window.open_bom_id(self.sid);before=self.config.path.read_bytes()
  with patch.object(editor,'close',return_value=False):self.assertFalse(self.window.switch_project(self.base/'cancel.db',create=True))
  self.assertFalse((self.base/'cancel.db').exists());self.assertEqual(before,self.config.path.read_bytes());self.assertEqual(self.window._project_id,self.first)
 def test_menu_labels_edit_and_delete_history_preserve_database(self):
  self.window.refresh_project_menu();self.assertEqual([a.text() for a in self.window.history_menu.actions()],['P1 项目一'])
  metadata=dict(project_code='EDIT',project_name='修改项目',product_name='',product_model='')
  with patch.object(ProjectDialog,'exec_',return_value=QDialog.Accepted),patch.object(ProjectDialog,'data',return_value=metadata):self.window.edit_project()
  self.window.refresh_project_menu();self.assertEqual(self.window.history_menu.actions()[0].text(),'EDIT 修改项目')
  path=Path(self.s.db.path)
  with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):self.window.delete_history_project(self.first)
  self.assertTrue(path.exists());self.assertEqual(self.window.projects.entries(),[]);self.assertEqual(self.s.project()['project_code'],'EDIT')
 def test_missing_history_cancel_and_relink(self):
  path=self.other();key=self.window.projects.remember(path,dict(project_code='P2',project_name='项目二'));moved=self.base/'moved.db';path.rename(moved)
  with patch.object(QMessageBox,'exec_'),patch.object(QMessageBox,'clickedButton',return_value=None):self.window.open_history_project(key)
  self.assertEqual(self.window._project_id,self.first)
  def select(box):return next(b for b in box.buttons() if b.text()=='指定数据库')
  with patch.object(QMessageBox,'exec_'),patch.object(QMessageBox,'clickedButton',select),patch.object(QFileDialog,'getOpenFileName',return_value=(str(moved),'')):self.window.open_history_project(key)
  self.assertEqual(self.window._project_id,key);self.assertEqual(self.window.projects.get(key)['path'],'moved.db')
 def test_file_database_import_and_history_action(self):
  path=self.other()
  with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'')):self.window.import_project_database()
  self.window.refresh_project_menu();actions=self.window.history_menu.actions();self.assertEqual(len(actions),2)
  next(a for a in actions if a.data()==self.first).trigger();self.assertEqual(self.window._project_id,self.first)
  self.assertTrue(self.window.switch_project(path));self.assertEqual(len(self.window.projects.entries()),2)

 def test_restart_restores_active_project_and_deleted_history_stays_deleted(self):
  path=self.other();self.assertTrue(self.window.switch_project(path));key=self.window._project_id
  self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
  self.s.db.close();self.s=Services(Database(str(self.config.resolve_path(self.config.load()['database']['path']))),ConfigService(self.base));self.window=MainWindow(self.s)
  self.assertEqual(self.window._project_id,key);self.assertEqual(self.window.table.item(0,1).text(),'SKU2100')
  with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):self.window.delete_history_project(key)
  self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
  self.window=MainWindow(self.s);self.assertIsNone(self.window._project_id);self.assertEqual(len(self.window.projects.entries()),1)
 def test_missing_history_delete_and_right_click_remove_only_record(self):
  path=self.other();key=self.window.projects.remember(path,dict(project_code='P2',project_name='项目二'));path.unlink()
  def delete(box):return next(b for b in box.buttons() if b.text()=='删除历史项目')
  with patch.object(QMessageBox,'exec_'),patch.object(QMessageBox,'clickedButton',delete),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):self.window.open_history_project(key)
  self.assertIsNone(self.window.projects.get(key));self.assertEqual(self.window._project_id,self.first)
  self.window.refresh_project_menu();action=self.window.history_menu.actions()[0]
  with patch.object(self.window.history_menu,'actionAt',return_value=action),patch.object(QMenu,'exec_',lambda menu,pos:menu.actions()[0]),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):self.window.project_context_menu(self.window.pos())
  self.assertEqual(self.window.projects.entries(),[]);self.assertTrue((self.base/'first.db').exists())
 def test_new_project_cancel_database_retains_only_metadata_draft(self):
  metadata=dict(project_code='DRAFT',project_name='草稿',product_name='',product_model='')
  with patch.object(ProjectDialog,'exec_',return_value=QDialog.Accepted),patch.object(ProjectDialog,'data',return_value=metadata),patch.object(QFileDialog,'exec_',return_value=QDialog.Rejected):self.window.new_project()
  self.assertEqual(self.window.projects.draft(),metadata);self.assertEqual(self.window._project_id,self.first);self.assertEqual(len(self.window.projects.entries()),1)
