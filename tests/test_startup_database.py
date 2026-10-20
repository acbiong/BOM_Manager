import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest,sqlite3
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from config.config_service import ConfigService
from database.database import Database
import main

class StartupDatabaseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.config=ConfigService(self.base);self.cfg=self.config.load();self.cfg['database']['path']='bom.db'
 def tearDown(self):self.tmp.cleanup()
 def test_missing_prompts_and_creates_named_file(self):
  target=self.base/'用户自定义.sqlite'
  with patch.object(main,'choose_database_recovery',return_value='create') as choose,patch.object(main.QFileDialog,'getSaveFileName',return_value=(str(target),'')):
   db=main.startup_database(self.config,self.cfg)
  try:self.assertEqual(db.path,str(target));self.assertTrue(db.validate_schema()[0])
  finally:db.close()
  self.assertIn('不存在',choose.call_args.args[0]);self.assertEqual(self.config.load()['database']['path'],target.name);self.assertFalse((self.base/'bom.db').exists())
 def test_corrupt_file_preserved_select_valid_database(self):
  corrupt=self.base/'bom.db';corrupt.write_bytes(b'not sqlite');valid=self.base/'valid.db';db=Database(str(valid));db.conn.execute("UPDATE project SET project_name='原项目'");db.conn.commit();db.close()
  with patch.object(main,'choose_database_recovery',return_value='select'),patch.object(main.QFileDialog,'getOpenFileName',return_value=(str(valid),'')):
   db=main.startup_database(self.config,self.cfg)
  self.assertEqual(db.conn.execute('SELECT project_name FROM project').fetchone()[0],'原项目');db.close();self.assertEqual(corrupt.read_bytes(),b'not sqlite')
 def test_existing_create_name_not_overwritten_and_cancel_returns_to_choice(self):
  target=self.base/'existing.db';target.write_bytes(b'original')
  with patch.object(main,'choose_database_recovery',side_effect=['create','select',None]) as choices,patch.object(main.QFileDialog,'getSaveFileName',return_value=(str(target),'')),patch.object(main.QFileDialog,'getOpenFileName',return_value=('','')):
   self.assertIsNone(main.startup_database(self.config,self.cfg))
  self.assertEqual(target.read_bytes(),b'original');self.assertIn('同名文件',choices.call_args_list[1].args[0]);self.assertFalse((self.base/'bom.db').exists())
 def test_invalid_schema_and_empty_file_rejected_without_changes(self):
  path=self.base/'unrelated.db';conn=sqlite3.connect(path);conn.execute('CREATE TABLE unrelated(value)');conn.commit();conn.close();before=path.read_bytes()
  with self.assertRaises(sqlite3.Error):main.open_existing_database(path)
  self.assertEqual(path.read_bytes(),before)
  empty=self.base/'empty.db';empty.touch()
  with self.assertRaises(ValueError):main.open_existing_database(empty)
  self.assertEqual(empty.stat().st_size,0)
 def test_valid_relative_database_opens_without_prompt(self):
  path=self.base/'valid.db';Database(str(path)).close();self.cfg['database']['path']='valid.db'
  with patch.object(main,'choose_database_recovery') as choose:
   db=main.startup_database(self.config,self.cfg);db.close();choose.assert_not_called()
 def test_bad_selected_file_reprompts_then_valid_selection(self):
  bad=self.base/'bad.db';bad.write_bytes(b'bad');valid=self.base/'good.db';Database(str(valid)).close()
  with patch.object(main,'choose_database_recovery',side_effect=['select','select']) as choose,patch.object(main.QFileDialog,'getOpenFileName',side_effect=[(str(bad),''),(str(valid),'')]):
   db=main.startup_database(self.config,self.cfg);db.close()
  self.assertEqual(choose.call_count,2);self.assertEqual(bad.read_bytes(),b'bad')
