"""Portable config paths: native migration, moved projects, Windows/Unix spelling."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from config.config_service import ConfigService,relative_config_path
from database.database import Database
import main

class ConfigPathTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.config=ConfigService(self.base/'原项目')
 def tearDown(self):self.tmp.cleanup()
 def test_default_and_absolute_path_migration(self):
  cfg=self.config.load();self.assertEqual(cfg['database']['path'],'')
  target=self.config.base/'数据'/'50% BOM.db'
  cfg['database']['path']=str(target);cfg['database']['last_import_dir']=str(self.base/'Excel 文件')
  self.config.save(cfg)
  loaded=self.config.load()
  self.assertEqual(loaded['database']['path'],'数据/50% BOM.db')
  self.assertEqual(loaded['database']['last_import_dir'],'../Excel 文件')
  self.assertEqual(self.config.resolve_path(loaded['database']['path']),target)
  # Legacy INI values are migrated without changing the selected target.
  self.config.path.write_text(f'[database]\npath = {target}\nlast_import_dir = {self.base / "Excel 文件"}\n',encoding='utf-8')
  self.assertEqual(self.config.load()['database']['path'],'数据/50% BOM.db')
 def test_copy_project_and_open_from_different_cwd(self):
  cfg=self.config.load();folder=self.config.base/'数据库';folder.mkdir()
  db=Database(str(folder/'项目.db'));db.conn.execute("UPDATE project SET project_name='迁移验证'");db.conn.commit();db.close()
  cfg['database']['path']=str(folder/'项目.db');self.config.save(cfg)
  relocated=self.base/'新位置'/'新项目';shutil.copytree(self.config.base,relocated)
  copied=ConfigService(relocated)
  with patch('pathlib.Path.cwd',return_value=self.base/'无关目录'),patch.object(main,'choose_database_recovery') as choice:
   db=main.startup_database(copied,copied.load())
   try:
    self.assertEqual(Path(db.path),relocated/'数据库'/'项目.db')
    self.assertEqual(db.conn.execute('SELECT project_name FROM project').fetchone()[0],'迁移验证')
   finally:db.close()
   choice.assert_not_called()
 def test_windows_relative_separators_and_migration_across_platforms(self):
  self.assertEqual(relative_config_path(r'C:\项目\BOM\数据\bom.db',r'C:\项目\BOM'),'数据/bom.db')
  self.assertEqual(relative_config_path(r'..\数据\bom.db',r'D:\项目\BOM'),'../数据/bom.db')
  self.assertEqual(relative_config_path('/mnt/project/数据/bom.db','/mnt/project/BOM'),'../数据/bom.db')
  self.assertEqual(relative_config_path(r'\\server\share\项目\data\bom.db',r'\\server\share\项目'),'data/bom.db')
  self.assertEqual(relative_config_path('数据/bom.db',r'E:\复制后项目'),'数据/bom.db')
  self.assertEqual(self.config.resolve_path(r'数据\bom.db'),self.config.base/'数据'/'bom.db')
 def test_unresolvable_foreign_and_cross_drive_paths_rejected(self):
  for value,base in [(r'D:\bom.db',r'C:\项目'),(r'C:\bom.db','/home/project'),('/home/project/bom.db',r'C:\项目'),('smb://host/share/bom.db','/home/project'),(r'C:bom.db',r'C:\项目')]:
   with self.subTest(value=value,base=base),self.assertRaises(ValueError):relative_config_path(value,base)
 def test_foreign_legacy_database_prompts_without_guessing_local_file(self):
  foreign=r'Z:\旧电脑\bom.db' if os.name!='nt' else '/old-computer/bom.db'
  self.config.base.mkdir();self.config.path.write_text(f'[database]\npath = {foreign}\nlast_import_dir = {foreign}\n',encoding='utf-8')
  cfg=self.config.load();self.assertEqual(cfg['database']['path'],foreign)
  self.assertNotIn('last_import_dir',cfg['database'])
  # Even an existing local bom.db must not silently replace the configured DB.
  Database(str(self.config.base/'bom.db')).close()
  with patch.object(main,'choose_database_recovery',return_value=None) as choice:
   self.assertIsNone(main.startup_database(self.config,cfg));choice.assert_called_once()
