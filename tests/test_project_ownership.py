import os,sys,tempfile,subprocess,unittest,sqlite3
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication,QEvent
from infrastructure.project_lock import ProjectLock,ProjectInUseError
from database.database import Database
from config.config_service import ConfigService
from services.services import Services
from ui.main_window import MainWindow
from ui.startup_project import restore_project

SRC=str(Path(__file__).parents[1]/'src')
class ProjectOwnershipTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.path=self.base/'one.db';Database(str(self.path)).close();self.children=[];self.windows=[];self.dbs=[]
 def tearDown(self):
  for w in self.windows:w.close();w.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
  for db in self.dbs:db.close()
  for child in self.children:
   if child.poll() is None:child.communicate('',timeout=10)
   if child.stdin and not child.stdin.closed:child.stdin.close()
   if child.stdout:child.stdout.close()
  self.tmp.cleanup()
 def child(self,code,*args):
  p=subprocess.Popen([sys.executable,'-c','import sys;sys.path.insert(0,'+repr(SRC)+');'+code,*map(str,args)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True);self.children.append(p)
  self.assertEqual(p.stdout.readline().strip(),'READY');return p
 def test_cross_process_same_project_blocked_other_project_available_and_crash_releases(self):
  p=self.child('from infrastructure.project_lock import ProjectLock;lock=ProjectLock(sys.argv[1]).require();print("READY",flush=True);sys.stdin.read();lock.close()',self.path)
  with self.assertRaises(ProjectInUseError):Database(str(self.path),exclusive=True)
  other=self.base/'two.db';Database(str(other)).close();db=Database(str(other),exclusive=True);db.close()
  p.kill();p.communicate(timeout=10)
  db=Database(str(self.path),exclusive=True);db.close()
 def test_same_file_aliases_cannot_bypass_ownership(self):
  owner=ProjectLock(self.path).require()
  try:
   hard=self.base/'hard.db'
   try:os.link(self.path,hard)
   except OSError:self.skipTest('hard links unsupported')
   with self.assertRaises(ProjectInUseError):ProjectLock(hard).require()
   if os.name!='nt':
    alias=self.base/'alias.db';alias.symlink_to(self.path)
    with self.assertRaises(ProjectInUseError):ProjectLock(alias).require()
  finally:owner.close()
 def test_database_open_failure_and_normal_close_release_lock(self):
  with patch('database.database.sqlite3.connect',side_effect=sqlite3.OperationalError('failure')):
   with self.assertRaises(sqlite3.OperationalError):Database(str(self.path),exclusive=True)
  db=Database(str(self.path),exclusive=True);db.close();db.close();ProjectLock(self.path).require().close()
 def test_busy_startup_offers_other_or_close_and_owner_remains_usable(self):
  config=ConfigService(self.base);cfg=config.load();cfg['database']['path']='one.db';config.save(cfg)
  owner=Database(str(self.path),exclusive=True);self.dbs.append(owner)
  with patch('ui.startup_project.occupied_choice',return_value='close') as choice,patch('ui.startup_project.recovery_choice') as recovery:
   self.assertIsNone(restore_project(config,config.load()));choice.assert_called_once();recovery.assert_not_called()
  self.assertEqual(owner.conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
  self.assertEqual(config.load()['database']['path'],'one.db')
  with self.assertRaises(ProjectInUseError):ProjectLock(self.path).require()
 def test_two_windows_different_projects_busy_switch_close_only_requesting_window(self):
  config=ConfigService(self.base)
  w1=MainWindow(Services(None,config));w2=MainWindow(Services(None,ConfigService(self.base)));self.windows.extend([w1,w2])
  self.assertTrue(w1.switch_project(self.path));self.dbs.append(w1.svc.db)
  other=self.base/'two.db';self.assertTrue(w2.switch_project(other,create=True));old=w2.svc.db;self.dbs.append(old)
  with patch('ui.startup_project.occupied_choice',return_value='close'):self.assertFalse(w2.switch_project(self.path))
  self.assertIsNone(w2.svc.db);self.assertEqual(w2.table.rowCount(),0);self.assertIsNotNone(w1.svc.db)
  ProjectLock(other).require().close()
  with self.assertRaises(ProjectInUseError):ProjectLock(self.path).require()
 def test_same_directory_two_real_app_processes_can_enter_main_window(self):
  code='from pathlib import Path;from unittest.mock import patch;from PyQt5.QtWidgets import QApplication;import main;app=QApplication([]);ctx1=patch.object(main,"QApplication",return_value=app);ctx2=patch.object(main,"app_base",return_value=Path(sys.argv[1]));ctx3=patch.object(app,"exec_",side_effect=lambda:(print("READY",flush=True),sys.stdin.read(),0)[2]);ctx1.start();ctx2.start();ctx3.start();sys.exit(main.main())'
  first=self.child(code,self.base);second=self.child(code,self.base)
  self.assertIsNone(first.poll());self.assertIsNone(second.poll())
 def test_shared_config_stale_snapshots_merge_without_lost_project_or_ui_changes(self):
  a=ConfigService(self.base);b=ConfigService(self.base);left=a.load();right=b.load()
  left['project:left']={'path':'one.db','project_name':'左'};right['project:right']={'path':'two.db','project_name':'右'}
  left['ui']['test_left']='1';right['ui']['test_right']='2';a.save(left);b.save(right)
  result=a.load();self.assertTrue(result.has_section('project:left'));self.assertTrue(result.has_section('project:right'));self.assertEqual(result['ui']['test_left'],'1');self.assertEqual(result['ui']['test_right'],'2')
 def test_shared_config_concurrent_process_writes_preserve_both_changes(self):
  ConfigService(self.base).load()
  code='from config.config_service import ConfigService;c=ConfigService(sys.argv[1]);cfg=c.load();print("READY",flush=True);sys.stdin.read();cfg[sys.argv[2]]={"value":sys.argv[2]};c.save(cfg)'
  first=self.child(code,self.base,'project:first');second=self.child(code,self.base,'project:second')
  first.stdin.write('go');first.stdin.close();first.stdin=None
  second.communicate('go',timeout=10);first.wait(timeout=10)
  self.assertEqual(first.returncode,0);self.assertEqual(second.returncode,0)
  config=ConfigService(self.base).load();self.assertTrue(config.has_section('project:first'));self.assertTrue(config.has_section('project:second'))

 def test_busy_startup_can_select_another_project(self):
  from config.project_registry import ProjectRegistry
  from PyQt5.QtWidgets import QInputDialog
  from ui.interactive_windows import QInputDialog
  config=ConfigService(self.base);registry=ProjectRegistry(config)
  owner=Database(str(self.path),exclusive=True);self.dbs.append(owner);registry.remember(self.path,dict(project_code='ONE',project_name='占用项目'),active=True)
  other=self.base/'two.db';Database(str(other)).close();key=registry.remember(other,dict(project_code='TWO',project_name='其他项目'))
  def choose(*args):return next(x for x in args[3] if x.startswith('TWO ')),True
  with patch('ui.startup_project.occupied_choice',return_value='other'),patch.object(QInputDialog,'getItem',side_effect=choose):opened=restore_project(config,config.load())
  self.dbs.append(opened);self.assertEqual(Path(opened.path),other);self.assertEqual(config.load()['projects']['active'],key)
  with self.assertRaises(ProjectInUseError):ProjectLock(self.path).require()
 def test_occupied_prompt_contains_only_other_and_close(self):
  from PyQt5.QtWidgets import QMessageBox
  from ui.interactive_windows import QMessageBox
  from ui.startup_project import occupied_choice
  def inspect(box):
   self.assertEqual([b.text() for b in box.buttons()],['关闭项目','打开其他项目'])
   return 0
  with patch.object(QMessageBox,'exec_',inspect):self.assertEqual(occupied_choice('占用'), 'close')

 def test_closed_mapping_window_does_not_run_deferred_layout(self):
  from ui.main_window import MaterialHeaderMappingDialog
  from PyQt5 import sip
  dialog=MaterialHeaderMappingDialog('missing.xlsx',['物料名称'],[],required=['物料名称'])
  try:
   dialog.show();self.app.processEvents();dialog.schedule_mapping_fit();dialog.close()
   self.assertFalse(dialog._mapping_fit_timer.isActive())
   with patch.object(dialog,'fit_mapping_columns') as fit:dialog.run_mapping_fit();fit.assert_not_called()
   sip.delete(dialog.combos['物料名称']);dialog.fit_mapping_columns()
  finally:dialog.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

 def test_busy_empty_instance_preserves_memory_through_window_close_and_next_launch(self):
  from config.project_registry import ProjectRegistry
  config=ConfigService(self.base);registry=ProjectRegistry(config)
  key=registry.remember(self.path,dict(project_code='ONE',project_name='工程一'),active=True)
  owner=Database(str(self.path),exclusive=True);self.dbs.append(owner)
  before=config.path.read_bytes();launch=config.load()
  with patch('ui.startup_project.occupied_choice',return_value='close'):
   self.assertIsNone(restore_project(config,launch))
  self.assertEqual(launch['database']['path'],'')
  self.assertEqual(config.path.read_bytes(),before)
  empty=MainWindow(Services(None,config));self.windows.append(empty)
  self.assertIsNone(empty.svc.db);self.assertEqual(empty.table.rowCount(),0)
  with patch('ui.startup_project.occupied_choice',return_value='close'):
   self.assertFalse(empty.switch_project(self.path))
  self.assertTrue(empty.close_project());empty.close()
  persisted=config.load();self.assertEqual(persisted['database']['path'],'one.db')
  self.assertEqual(persisted['projects']['active'],key);self.assertFalse(persisted.getboolean('projects','closed'))
  owner.close()
  reopened=restore_project(config,config.load());self.dbs.append(reopened)
  self.assertEqual(Path(reopened.path),self.path)

 def test_empty_instance_does_not_clear_project_selected_by_another_instance(self):
  from config.project_registry import ProjectRegistry
  config=ConfigService(self.base);empty=MainWindow(Services(None,config));self.windows.append(empty)
  other=self.base/'two.db';Database(str(other)).close()
  key=ProjectRegistry(ConfigService(self.base)).remember(other,dict(project_name='另一个项目'),active=True)
  before=config.path.read_bytes();self.assertTrue(empty.close_project());empty.close()
  self.assertEqual(config.path.read_bytes(),before);self.assertEqual(config.load()['projects']['active'],key)
