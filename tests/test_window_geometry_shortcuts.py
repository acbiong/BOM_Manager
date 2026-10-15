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
from ui.main_window import MainWindow,MaterialWindow,BomWindow

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

 def test_ctrl_f_opens_corresponding_search_and_reuses_dialog(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));svc=Services(db)
   root=svc.create_material(dict(base_code='R',version='1',name='Root',unit='pcs'))
   main=MainWindow(svc);library=MaterialWindow(svc,main);bom=BomWindow(svc,root,main)
   try:
    for window in (library,bom):
     window.show();window.activateWindow();self.app.processEvents()
     QTest.keyClick(window,Qt.Key_F,Qt.ControlModifier);self.app.processEvents()
     dialog=window._search_dialog;self.assertTrue(dialog.isVisible());self.assertIs(dialog.library,window)
     dialog.hide();window.activateWindow();self.app.processEvents()
     QTest.keyClick(window,Qt.Key_F,Qt.ControlModifier);self.app.processEvents()
     self.assertIs(window._search_dialog,dialog);self.assertTrue(dialog.isVisible());dialog.hide()
    self.assertFalse(library._search_dialog.isVisible())
   finally:bom.close();library.close();main.close();db.close()

 def test_live_same_type_bom_geometry_cross_root_mirror_and_old_close(self):
  with tempfile.TemporaryDirectory() as tmp:
   cfg=ConfigService(tmp);db=Database(str(Path(tmp)/'db'));svc=Services(db,cfg);memory=WindowGeometryMemory(self.app,cfg)
   roots=[svc.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('A','B','C')]
   sid=svc.create_sku(roots[0]);mirror=svc.copy_sku_bom(sid)
   windows=[]
   try:
    first=BomWindow(svc,roots[0]);windows.append(first);first.show();self.app.processEvents()
    first.resize(700,450);self.app.processEvents()
    with patch.object(cfg,'save',wraps=cfg.save) as save:
     for width in (710,720,730):first.resize(width,460)
     save.assert_not_called()
     second=BomWindow(svc,roots[1]);windows.append(second);second.show();self.app.processEvents()
     self.assertEqual(second.size(),first.size())
    second.resize(760,500);self.app.processEvents();latest=second.size()
    first.close() # Must not restore first's older 730-pixel width.
    third=BomWindow(svc.for_sku(mirror),roots[0]);windows.append(third);third.show();self.app.processEvents()
    self.assertEqual(third.size(),latest);self.assertEqual(memory.key(first),memory.key(third))
    self.assertEqual(second.size(),latest)
    memory.save_visible()
    self.assertIn(memory.key(third),cfg.load()['window_geometry'])
   finally:
    for w in windows:w.dirty=False;w.close()
    self.app.removeEventFilter(memory);self.app.aboutToQuit.disconnect(memory.save_visible);memory.timer.stop();memory.deleteLater();db.close()

 def test_custom_dialog_type_shared_across_titles_and_restart(self):
  class SearchDialog(QDialog):pass
  class OtherDialog(QDialog):pass
  with tempfile.TemporaryDirectory() as tmp:
   cfg=ConfigService(tmp);memory=WindowGeometryMemory(self.app,cfg);windows=[]
   try:
    first=SearchDialog();first.setWindowTitle('SKU A 查找');first.resize(300,180);first.show();windows.append(first);self.app.processEvents();first.resize(560,340);self.app.processEvents()
    second=SearchDialog();second.setWindowTitle('SKU B 查找');second.resize(300,180);second.show();windows.append(second);self.app.processEvents();self.assertEqual(second.size(),first.size())
    other=OtherDialog();other.resize(320,210);other.show();windows.append(other);self.app.processEvents();self.assertEqual(other.width(),320)
    for w in windows:w.close()
    self.app.removeEventFilter(memory);self.app.aboutToQuit.disconnect(memory.save_visible);memory.timer.stop();memory.deleteLater()
    memory=WindowGeometryMemory(self.app,ConfigService(tmp))
    reopened=SearchDialog();reopened.setWindowTitle('SKU C 查找');reopened.resize(300,180);reopened.show();windows.append(reopened);self.app.processEvents();self.assertEqual(reopened.size(),first.size())
   finally:
    for w in windows:w.close()
    self.app.removeEventFilter(memory);self.app.aboutToQuit.disconnect(memory.save_visible);memory.timer.stop();memory.deleteLater()

 def test_legacy_bom_geometry_migrates_to_type(self):
  with tempfile.TemporaryDirectory() as tmp:
   cfg=ConfigService(tmp);db=Database(str(Path(tmp)/'db'));svc=Services(db,cfg);memory=WindowGeometryMemory(self.app,cfg)
   roots=[svc.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('A','B')]
   first=BomWindow(svc,roots[0]);first.resize(750,480)
   memory.values[memory.key(first,legacy=True)]=memory.geometry(first)
   second=BomWindow(svc,roots[1])
   try:
    first.show();self.app.processEvents();second.show();self.app.processEvents();self.assertEqual(second.size(),first.size())
    self.assertEqual(second.width(),750)
   finally:
    first.close();second.close();self.app.removeEventFilter(memory);self.app.aboutToQuit.disconnect(memory.save_visible);memory.timer.stop();memory.deleteLater();db.close()
