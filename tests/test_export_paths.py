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
  with tempfile.TemporaryDirectory() as tmp:
   settings=QSettings('Biong','BOMManager');settings.clear();fallback=Path(tmp)/'saved';fallback.mkdir();remember_export_path(str(fallback/'one.xlsx'));self.assertEqual(Path(export_start_path('two.xlsx')).parent,fallback)
   settings.clear()
   with patch.dict(os.environ,{},clear=True):self.assertTrue(Path(export_start_path('three.xlsx')).parent.exists())
 def test_sku_context_export_bom(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db);mid=s.create_material(dict(base_code='R',version='1',name='SKU',unit='pcs'));sid=s.create_sku(mid);main=MainWindow(s)
   try:
    with patch('ui.main_window.QMenu.exec_',return_value=None):pass
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(Path(tmp)/'bom.xlsx'),'')),patch.object(QMessageBox,'information'):
     main.export_sku_id(sid)
    self.assertTrue(Path(tmp,'bom.xlsx').exists())
   finally:main.close();db.close()
