import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QFileDialog,QMessageBox,QAction
from ui.interactive_windows import QFileDialog,QMessageBox
from PyQt5.QtCore import QSettings
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow,MaterialWindow,BomWindow,export_start_path,remember_export_path

class ExportPathTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_export_directory_remembered_and_defaults_to_app_dir(self):
  from config.config_service import ConfigService
  with tempfile.TemporaryDirectory() as tmp:
   config=ConfigService(tmp);svc=Services(None,config);folder=Path(tmp)/'saved';folder.mkdir()
   remember_export_path(folder/'one.xlsx',svc)
   with patch.dict(os.environ,{'APPIMAGE':'/tmp/new-version.AppImage'}):
    self.assertEqual(Path(export_start_path('two.xlsx',Services(None,ConfigService(tmp)))).parent,folder)
   folder.rmdir()
   self.assertEqual(Path(export_start_path('three.xlsx',svc)).parent,Path(tmp))
   self.assertEqual(config.load()['database']['last_export_dir'],'saved')
 def test_import_export_paths_survive_project_reactivation_and_relocation(self):
  from config.config_service import ConfigService
  from config.project_registry import ProjectRegistry
  from ui.import_paths import remember_bom_import,bom_import_directory,remember_external_bom,external_bom_selection
  import shutil
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp)/'app';base.mkdir();config=ConfigService(base);registry=ProjectRegistry(config)
   key=registry.remember(base/'one.db',{'project_name':'One'},active=True)
   target=base/'files';target.mkdir();book=target/'bom.xlsx';book.touch()
   remember_export_path(target/'out.xlsx',Services(None,config));remember_bom_import(config,book);remember_external_bom(config,book)
   cfg=config.load();cfg['database']['last_import_dir']=str(target);config.save(cfg)
   other=registry.remember(base/'two.db',{'project_name':'Two'},settings={'database':{}});registry.activate(other);registry.activate(key)
   moved=Path(tmp)/'moved';shutil.copytree(base,moved);new=ConfigService(moved)
   self.assertEqual(Path(export_start_path('out.xlsx',Services(None,new))).parent,moved/'files')
   self.assertEqual(Path(bom_import_directory(new)),moved/'files')
   self.assertEqual(Path(external_bom_selection(new)),moved/'files'/'bom.xlsx')
   self.assertEqual(new.load()['database']['last_import_dir'],'files')
 def test_old_active_snapshot_does_not_overwrite_newer_top_level_paths(self):
  from config.config_service import ConfigService
  from config.project_registry import ProjectRegistry
  with tempfile.TemporaryDirectory() as tmp:
   config=ConfigService(tmp);registry=ProjectRegistry(config)
   key=registry.remember(Path(tmp)/'one.db',{},settings={'database':{'last_import_dir':'old'}},active=True)
   cfg=config.load();cfg['database']['last_import_dir']='new';config._write(cfg)
   registry.activate(key);self.assertEqual(config.load()['database']['last_import_dir'],'new')
 def test_sku_context_export_bom(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db);mid=s.create_material(dict(base_code='R',version='1',name='SKU',unit='pcs'));sid=s.create_sku(mid);main=MainWindow(s)
   try:
    with patch('ui.main_window.QMenu.exec_',return_value=None):pass
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(Path(tmp)/'bom.xlsx'),'')),patch.object(QMessageBox,'information'):
     main.export_sku_id(sid)
    self.assertTrue(Path(tmp,'bom.xlsx').exists())
   finally:main.close();db.close()

 def test_legacy_qt_directory_migrates_to_portable_config_once(self):
  from config.config_service import ConfigService
  with tempfile.TemporaryDirectory() as tmp:
   config=ConfigService(tmp);svc=Services(None,config);folder=Path(tmp)/'legacy';folder.mkdir()
   with patch('ui.main_window.QSettings') as settings:
    settings.return_value.value.return_value=str(folder)
    self.assertEqual(Path(export_start_path('one.xlsx',svc)).parent,folder)
   self.assertEqual(config.load()['database']['last_export_dir'],'legacy')
   with patch('ui.main_window.QSettings',side_effect=AssertionError('must use portable ini')):
    self.assertEqual(Path(export_start_path('two.xlsx',Services(None,ConfigService(tmp)))).parent,folder)
