import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication,QDialog
from PyQt5.QtTest import QTest
from config.config_service import ConfigService
from database.database import Database
from services.services import Services
from ui.window_geometry import WindowGeometryMemory
from ui.main_window import MainWindow,MaterialWindow

class WindowGeometryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_persist_reopen_reset_and_corrupt_geometry(self):
  with tempfile.TemporaryDirectory() as tmp:
   cfg=ConfigService(tmp);memory=WindowGeometryMemory(self.app,cfg)
   self.assertFalse(cfg.load().getboolean('ui','reset_window_geometry'))
   def dialog():
    w=QDialog();w.setWindowTitle('测试窗口');w.resize(300,180);return w
   w=dialog();w.show();self.app.processEvents();w.resize(510,320);w.move(70,90);self.app.processEvents();w.close()
   reopened=dialog();reopened.show();self.app.processEvents()
   self.assertEqual(reopened.size(),w.size());self.assertEqual(reopened.pos(),w.pos());reopened.close()
   self.app.removeEventFilter(memory)
   settings=cfg.load();settings['ui']['reset_window_geometry']='true';cfg.save(settings)
   memory2=WindowGeometryMemory(self.app,ConfigService(tmp))
   default=dialog();default.show();self.app.processEvents();self.assertEqual(default.width(),300);self.assertEqual(default.height(),180);default.close()
   self.app.removeEventFilter(memory2)
   settings=cfg.load();settings['ui']['reset_window_geometry']='false';settings['window_geometry'][memory.key(default)]='broken';cfg.save(settings)
   memory3=WindowGeometryMemory(self.app,cfg);bad=dialog();bad.show();self.app.processEvents();self.assertEqual(bad.width(),300);bad.close();self.app.removeEventFilter(memory3)
   for obj in (memory,memory2,memory3):self.app.aboutToQuit.disconnect(obj.save_visible);obj.deleteLater()
 def test_ctrl_n_only_triggers_active_window(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));svc=Services(db)
   with patch.object(MainWindow,'new_sku') as sku,patch.object(MainWindow,'new_material') as material:
    main=MainWindow(svc);library=MaterialWindow(svc,main)
    try:
     main.show();main.activateWindow();self.app.processEvents();QTest.keyClick(main,Qt.Key_N,Qt.ControlModifier);self.assertEqual(sku.call_count,1);material.assert_not_called()
     library.show();library.activateWindow();self.app.processEvents();QTest.keyClick(library,Qt.Key_N,Qt.ControlModifier);self.assertEqual(material.call_count,1);self.assertEqual(sku.call_count,1)
    finally:library.close();main.close();db.close()
