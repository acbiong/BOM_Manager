import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QWidget
from infrastructure.single_instance import SingleInstance,installation_directory

class SingleInstanceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_same_directory_alias_and_activation(self):
  directory=self.path/'软件';directory.mkdir();alias=self.path/'链接'
  if os.name=='nt':alias=directory/'.'
  else:alias.symlink_to(directory,target_is_directory=True)
  first=SingleInstance(directory,self.path);second=SingleInstance(alias,self.path);window=QWidget()
  try:
   self.assertTrue(first.acquire());first.set_window(window)
   self.assertFalse(second.acquire())
   with patch.object(first,'activate') as activate:
    self.assertTrue(second.notify_existing());self.app.processEvents();activate.assert_called_once()
   second.close();self.assertFalse(SingleInstance(directory,self.path).acquire())
  finally:window.close();second.close();first.close()
  # 正常退出后不需删除残留锁文件即可再次启动。
  self.assertTrue(first.lock_path.exists())
  third=SingleInstance(directory,self.path)
  try:self.assertTrue(third.acquire())
  finally:third.close()
 def test_different_directories_independent(self):
  a=SingleInstance(self.path/'A',self.path);b=SingleInstance(self.path/'B',self.path)
  try:self.assertTrue(a.acquire());self.assertTrue(b.acquire());self.assertNotEqual(a.key,b.key)
  finally:a.close();b.close()
 def test_real_process_exclusion_and_kill_recovery(self):
  source=Path(__file__).parents[1]/'src'
  code="""import sys
from PyQt5.QtCore import QCoreApplication
from infrastructure.single_instance import SingleInstance
app=QCoreApplication([])
guard=SingleInstance(sys.argv[1],sys.argv[2])
owned=guard.acquire()
print('owner' if owned else 'blocked',flush=True)
if owned and sys.argv[3]=='hold':sys.stdin.readline()
guard.close()
"""
  env=dict(os.environ,PYTHONPATH=str(source),QT_QPA_PLATFORM='offscreen')
  args=[sys.executable,'-c',code,str(self.path/'app'),str(self.path)]
  owner=subprocess.Popen(args+['hold'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,cwd=tempfile.gettempdir())
  try:
   self.assertEqual(owner.stdout.readline().strip(),'owner')
   result=subprocess.run(args+['exit'],capture_output=True,text=True,env=env,timeout=10)
   self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'blocked')
   owner.kill();owner.wait(timeout=10)
   result=subprocess.run(args+['exit'],capture_output=True,text=True,env=env,timeout=10)
   self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'owner')
  finally:
   if owner.poll() is None:owner.kill();owner.wait(timeout=10)
   owner.stdin.close();owner.stdout.close();owner.stderr.close()
 def test_appimage_location_ignores_mount_version_and_cwd(self):
  with patch.object(sys,'frozen',True,create=True),patch.dict(os.environ,APPIMAGE=str(self.path/'软件'/'v1.AppImage')):
   first=installation_directory()
   with patch.dict(os.environ,APPIMAGE=str(self.path/'软件'/'v2.AppImage')):self.assertEqual(first,installation_directory())
   with patch.dict(os.environ,APPIMAGE=''),patch.object(sys,'executable',str(self.path/'standalone'/'bom')):self.assertEqual(installation_directory(),self.path/'standalone')
 def test_duplicate_stops_before_config_and_database(self):
  import main
  guard=SingleInstance(self.path/'app',self.path)
  with patch.object(main,'QApplication',return_value=self.app),patch.object(main,'SingleInstance',return_value=guard),patch.object(guard,'acquire',return_value=False),patch.object(guard,'notify_existing',return_value=True),patch.object(main,'ConfigService') as config,patch.object(main,'startup_database') as database,patch.object(main,'app_base') as base:
   self.assertEqual(main.main(),0);config.assert_not_called();database.assert_not_called();base.assert_not_called()
 def test_startup_cancel_releases_lock(self):
  import main
  guard=SingleInstance(self.path/'app',self.path)
  with patch.object(main,'QApplication',return_value=self.app),patch.object(main,'SingleInstance',return_value=guard),patch.object(main,'ConfigService'),patch.object(main,'startup_database',return_value=None),patch.object(main,'app_base',return_value=self.path),patch.object(main.QMessageBox,'critical'):self.assertEqual(main.main(),0)
  replacement=SingleInstance(self.path/'app',self.path)
  try:self.assertTrue(replacement.acquire())
  finally:replacement.close()
