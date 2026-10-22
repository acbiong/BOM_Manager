import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from config.config_service import ConfigService,read_config_file
from config.project_registry import ProjectRegistry

class LegacyConfigEncodingTests(unittest.TestCase):
 def test_old_windows_encodings_preserve_database_projects_and_mapping(self):
  text='[database]\npath = 数据库/项目.db\n[project]\nproject_code = 旧项目\nproject_name = 中文名称\n[projects]\nactive = old\n[project:old]\npath = 数据库/项目.db\nproject_name = 中文名称\n[import_mappings]\nbom = {"物料名称": "名称"}\n'
  for encoding in ('utf-8','utf-8-sig','utf-16','gb18030'):
   with self.subTest(encoding=encoding),tempfile.TemporaryDirectory() as tmp:
    config=ConfigService(tmp);config.path.write_bytes(text.encode(encoding))
    loaded=config.load();self.assertEqual(loaded['database']['path'],'数据库/项目.db')
    self.assertEqual(loaded['project:old']['project_name'],'中文名称');self.assertEqual(config.import_mapping('bom'),{'物料名称':'名称'})
    loaded['ui']['reset_window_geometry']='true';config.save(loaded)
    self.assertEqual(config.load()['projects']['active'],'old')
    # Importing a legacy config also reads all supported encodings without rewriting it.
    source=Path(tmp)/'old.ini';source.write_bytes(text.encode(encoding));before=source.read_bytes()
    path,metadata,settings=ProjectRegistry(config).read_import(source)
    self.assertEqual(path,Path(tmp)/'数据库/项目.db');self.assertEqual(metadata['project_name'],'中文名称')
    self.assertEqual(source.read_bytes(),before)
 def test_malformed_config_is_not_overwritten(self):
  with tempfile.TemporaryDirectory() as tmp:
   config=ConfigService(tmp);raw=b'not a valid ini';config.path.write_bytes(raw)
   with self.assertRaises(Exception):config.load()
   self.assertEqual(config.path.read_bytes(),raw)
