import os,sys,tempfile,unittest,json
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QFileDialog,QInputDialog,QMessageBox
from PyQt5.QtCore import QCoreApplication,QEvent
from config.config_service import ConfigService
from config.project_registry import ProjectRegistry
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from ui.startup_project import restore_project
import main

class StartupProjectRestoreTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.config=ConfigService(self.base);self.registry=ProjectRegistry(self.config);self.windows=[];self.dbs=[]
  self.path=self.base/'first.db';db=Database(str(self.path));self.dbs.append(db);self.s=Services(db,self.config)
  self.s.update_project(dict(project_code='P1',project_name='项目一'));mid=self.s.create_material(dict(base_code='SKU',version='100',name='原名',unit='pcs'));self.sid=self.s.create_sku(mid);self.mid=mid
  w=MainWindow(self.s);self.windows.append(w);self.key=w._project_id
 def tearDown(self):
  for w in self.windows:
   for editor in set(w._bom_windows.values())|set(w._material_bom_windows.values()):editor.dirty=False;editor.close()
   w.close();w.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
  for db in self.dbs:db.close()
  self.tmp.cleanup()
 def missing(self):
  self.s.db.close();self.path.unlink()
 def assert_startup_only_sku(self,locked):
  from services.snapshot_bom import migrate
  from services.current_catalog import initialize
  migrate(self.s.db);initialize(self.s.db)
  self.s.set_sku_locked(self.sid,locked)
  cfg=self.config.load();cfg['project:'+self.key]['last_bom']=json.dumps(dict(id=self.sid,mirror_version=100,base_code='SKU',version='100'));self.config.save(cfg)
  self.s.db.conn.execute("UPDATE materials SET name='最新名称' WHERE id=?",(self.mid,));self.s.db.conn.commit()
  self.windows[0].close();self.s.db.close()
  def event_loop():
   visible=[w for w in self.app.topLevelWidgets() if w.isVisible()]
   self.assertEqual(len(visible),1);w=visible[0];self.assertIsInstance(w,MainWindow);self.windows.append(w)
   self.assertEqual(w._bom_windows,{});self.assertEqual(w._material_bom_windows,{})
   self.assertIn('最新名称',w.table.item(0,2).text());self.assertIn('P1',w.windowTitle())
   editor=w.open_bom_id(self.sid);self.assertTrue(editor.isVisible());self.assertEqual(editor.is_locked(),locked)
   w.close();return 0
  with patch.object(main,'QApplication',return_value=self.app),patch.object(main,'app_base',return_value=self.base),patch.object(self.app,'exec_',side_effect=event_loop),patch.object(main.QMessageBox,'critical') as error:
   self.assertEqual(main.main(),0);error.assert_not_called()
  manager=getattr(self.app,'_bom_save_shortcuts',None)
  if manager is not None:del self.app._bom_save_shortcuts;manager.deleteLater()
 def test_startup_only_sku_with_legacy_unlocked_bom(self):self.assert_startup_only_sku(False)
 def test_startup_only_sku_with_legacy_locked_bom(self):self.assert_startup_only_sku(True)
 def test_missing_close_keeps_history_and_subsequent_launch_empty(self):
  self.missing();cfg=self.config.load()
  with patch('ui.startup_project.recovery_choice',return_value='close'):self.assertIsNone(restore_project(self.config,cfg))
  self.assertEqual(cfg['database']['path'],'');self.assertIsNotNone(self.registry.get(self.key));self.assertEqual(self.config.load()['database']['path'],'')
  with patch('ui.startup_project.recovery_choice') as choice:self.assertIsNone(restore_project(self.config,self.config.load()));choice.assert_not_called()
  self.assertFalse(self.path.exists())
 def test_missing_specify_database_relinks_existing_history(self):
  self.s.db.close();moved=self.base/'moved.db';self.path.rename(moved)
  with patch('ui.startup_project.recovery_choice',return_value='select'),patch.object(QFileDialog,'getOpenFileName',return_value=(str(moved),'')):db=restore_project(self.config,self.config.load())
  self.dbs.append(db);self.assertEqual(Path(db.path),moved);self.assertEqual(self.registry.get(self.key)['path'],'moved.db');self.assertEqual(len(self.registry.entries()),1)
 def test_open_other_project_uses_its_metadata_and_settings(self):
  other=self.base/'other.db';db=Database(str(other));s=Services(db);s.update_project(dict(project_code='P2',project_name='项目二'));db.close()
  key=self.registry.remember(other,dict(project_code='P2',project_name='项目二'),settings={'materials':{'units':'pcs,米'}});self.missing()
  def choose(*args):return next(label for label in args[3] if label.startswith('P2 ')),True
  with patch('ui.startup_project.recovery_choice',return_value='other'),patch.object(QInputDialog,'getItem',side_effect=choose):db=restore_project(self.config,self.config.load())
  self.dbs.append(db);self.assertEqual(db.path,str(other));self.assertEqual(self.config.load()['projects']['active'],key);self.assertEqual(self.config.material_units(),['pcs','米'])
 def test_corrupt_file_and_bad_selection_remain_untouched_then_close(self):
  self.s.db.close();self.path.write_bytes(b'corrupt');bad=self.base/'bad.db';bad.write_bytes(b'not sqlite')
  with patch('ui.startup_project.recovery_choice',side_effect=['select','close']) as choose,patch.object(QFileDialog,'getOpenFileName',return_value=(str(bad),'')):
   self.assertIsNone(restore_project(self.config,self.config.load()));self.assertEqual(choose.call_count,2)
  self.assertEqual(self.path.read_bytes(),b'corrupt');self.assertEqual(bad.read_bytes(),b'not sqlite')
 def test_cancel_database_selection_returns_to_three_choices(self):
  self.missing()
  with patch('ui.startup_project.recovery_choice',side_effect=['select','close']) as choose,patch.object(QFileDialog,'getOpenFileName',return_value=('','')):
   self.assertIsNone(restore_project(self.config,self.config.load()));self.assertEqual(choose.call_count,2)
