"""SMB URI及SQLite锁失败恢复，不关闭SQLite锁、不覆盖已有文件。"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,sqlite3,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
import main
from config.config_service import ConfigService
from database.database import Database

class LockRecoveryTests(unittest.TestCase):
 def test_locked_new_file_is_cleaned_and_next_create_uses_local(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);share=root/'share';share.mkdir();local=root/'local';local.mkdir()
   config=ConfigService(share);cfg=config.load();cfg['database']['path']='bom.db';target=share/'locked.db'
   def create(path):
    if Path(path)==target:raise sqlite3.OperationalError('database is locked')
    return Database(path)
   with patch.object(main,'Database',side_effect=create),patch.object(main,'database_local_fallback',return_value=local),patch.object(main,'choose_database_recovery',side_effect=['create','create']) as prompt,patch.object(main.QFileDialog,'getSaveFileName',side_effect=[(str(target),''),(str(local/'good.db'),'')]) as chooser:
    db=main.startup_database(config,cfg)
    try:self.assertTrue(db.validate_schema()[0])
    finally:db.close()
   self.assertFalse(target.exists());self.assertEqual(Path(chooser.call_args_list[1].args[2]).parent,local);self.assertIn('SQLite文件锁',prompt.call_args_list[1].args[0]);self.assertIn('config.ini',prompt.call_args_list[1].args[0])
 def test_smb_uri_rejected_without_creating_relative_smb_directory(self):
  with self.assertRaisesRegex(ValueError,'不能直接使用smb://'):main.selected_database_path('smb://server/share/new.db')
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'含空格 测试.db';self.assertEqual(main.selected_database_path(path.as_uri()),path)
