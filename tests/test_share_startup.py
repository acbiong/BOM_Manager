"""只读共享数据库恢复、SMB写权限探测及短路径启动器回归。"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import main
from config.config_service import ConfigService
from install_desktop_launcher import install,desktop_exec

class ShareStartupTests(unittest.TestCase):
 def test_readonly_database_choice_falls_back_and_creates(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);share=root/'smb';share.mkdir();local=root/'local';local.mkdir()
   config=ConfigService(local);cfg=config.load();cfg['database']['path']=str(share/'absent.db')
   with patch.object(main,'writable_directory',side_effect=lambda p:Path(p)!=share),patch.object(main,'choose_database_recovery',side_effect=['create','create']),patch.object(main.QFileDialog,'getSaveFileName',side_effect=[(str(share/'fail.db'),''),(str(local/'new.db'),'')]) as chooser:
    db=main.startup_database(config,cfg)
    try:
     self.assertTrue((local/'new.db').is_file());self.assertFalse((share/'fail.db').exists())
     self.assertTrue(all(Path(c.args[2]).parent==local for c in chooser.call_args_list))
     check=main.open_existing_database(local/'new.db');check.close()
    finally:db.close()
 def test_probe_uses_normal_named_file_and_cleans(self):
  with tempfile.TemporaryDirectory() as tmp:
   with patch.object(main.tempfile,'TemporaryFile',side_effect=OSError('SMB unsupported')):
    self.assertTrue(main.writable_directory(tmp))
   self.assertEqual(list(Path(tmp).iterdir()),[])
 def test_launcher_short_name_and_quoted_path(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);image=root/'共享 空格!'/ 'BOM.AppImage';image.parent.mkdir();image.touch();image.chmod(0o755)
   with patch('install_desktop_launcher.Path.home',return_value=root):paths=install(image,root/'Desktop')
   for path in paths:
    self.assertEqual(path.name,'bom-manager.desktop');self.assertIn('Exec="'+str(image)+'"',path.read_text());self.assertIn('Terminal=false',path.read_text())
   self.assertIn('%%',desktop_exec('/tmp/a%f.AppImage'))
