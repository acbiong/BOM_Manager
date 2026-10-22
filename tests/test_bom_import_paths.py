import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QFileDialog,QMessageBox
from ui.interactive_windows import QFileDialog,QMessageBox
from config.config_service import ConfigService
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from ui.import_paths import local_import_path,remember_bom_import,bom_import_directory

class BomImportPathTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.config=ConfigService(self.base/'app');self.folder=self.base/'共享目录'/'中文 BOM';self.folder.mkdir(parents=True);self.file=self.folder/'BOM.xlsx';self.file.touch()
 def tearDown(self):self.tmp.cleanup()
 def test_relative_directory_persists_across_restarts_and_file_uri(self):
  self.assertEqual(remember_bom_import(self.config,self.file.as_uri()),str(self.file))
  saved=self.config.load()['database']['last_bom_import_dir'];self.assertFalse(Path(saved).is_absolute());self.assertNotIn('\\',saved)
  self.assertEqual(bom_import_directory(ConfigService(self.config.base)),str(self.folder))
 def test_smb_mount_resolution_and_remembered_directory(self):
  with patch('ui.import_paths.sys.platform','linux'),patch('ui.import_paths.mounted_smb_roots',return_value=[('//server/共享',self.base/'共享目录')]):
   path=remember_bom_import(self.config,'smb://server/共享/中文%20BOM/BOM.xlsx')
  self.assertEqual(path,str(self.file));self.assertEqual(bom_import_directory(self.config),str(self.folder))
 def test_missing_folder_falls_back_without_erasing_memory(self):
  remember_bom_import(self.config,self.file);self.file.unlink();self.folder.rmdir()
  self.assertNotEqual(bom_import_directory(self.config),str(self.folder));self.assertIn('last_bom_import_dir',self.config.load()['database'])
 def test_missing_mount_does_not_overwrite_previous_directory(self):
  remember_bom_import(self.config,self.file)
  with patch('ui.import_paths.sys.platform','linux'),patch('ui.import_paths.mounted_smb_roots',return_value=[]),self.assertRaises(ValueError):remember_bom_import(self.config,'smb://missing/share/a.xlsx')
  self.assertEqual(bom_import_directory(self.config),str(self.folder))
 def test_ui_remembers_selection_even_when_import_fails_and_cancel_preserves(self):
  db=Database(str(self.base/'db'));s=Services(db,self.config);mid=s.create_material(dict(base_code='R',version='1',name='R',unit='pcs'));sid=s.create_sku(mid);main=MainWindow(s);w=main.open_bom_id(sid)
  try:
   with patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.file),'')),patch.object(QMessageBox,'warning'):w.import_bom()
   with patch.object(QFileDialog,'getOpenFileName',return_value=('','')) as chooser:w.import_bom();self.assertEqual(chooser.call_args.args[2],str(self.folder))
   self.assertEqual(bom_import_directory(self.config),str(self.folder));self.assertFalse(w.dirty)
  finally:w.close();main.close();db.close()
