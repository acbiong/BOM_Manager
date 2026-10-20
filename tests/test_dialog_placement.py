"""Popup placement must ignore old transient geometry without breaking window memory."""
import os
# QMessageBox needs the native Windows platform integration in Qt 5.15.
os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import QRect,QEvent,QCoreApplication
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication,QDialog,QWidget,QProgressDialog,QMessageBox,QInputDialog,QFileDialog
from config.config_service import ConfigService
from ui.window_geometry import WindowGeometryMemory

class DialogPlacementTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.cfg=ConfigService(self.tmp.name)
  self.memory=WindowGeometryMemory(self.app,self.cfg);self.windows=[]
 def track(self,window):self.windows.append(window);return window
 def tearDown(self):
  for w in reversed(self.windows):w.close();w.deleteLater()
  self.app.removeEventFilter(self.memory);self.app.aboutToQuit.disconnect(self.memory.save_visible)
  self.memory.timer.stop();self.memory.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.tmp.cleanup()
 def assert_centered(self,window,screen=None):
  screen=screen or self.memory.target_screen(window)
  delta=window.frameGeometry().center()-screen.availableGeometry().center()
  self.assertLessEqual(abs(delta.x()),2);self.assertLessEqual(abs(delta.y()),2)
 def test_transients_ignore_stale_geometry_resize_and_reshow(self):
  parent=self.track(QWidget());parent.resize(320,200);parent.move(10,20);parent.show()
  for dialog in (QProgressDialog('正在导入物料','取消',0,100,parent),QMessageBox(parent),QInputDialog(parent)):
   self.track(dialog);dialog.setWindowTitle('定位验证');dialog.resize(250,140);dialog.move(0,0)
   key=self.memory.key(dialog);stale=self.memory.geometry(dialog);self.memory.values[key]=stale
   dialog.show();self.app.processEvents();self.assert_centered(dialog)
   if isinstance(dialog,QProgressDialog):
    dialog.setLabelText('正在保存较长的BOM资料，请稍候……'*4);self.app.processEvents();self.assert_centered(dialog)
   dialog.hide();dialog.move(0,0);dialog.show();self.app.processEvents();self.assert_centered(dialog)
   dialog.close();self.assertEqual(self.memory.values[key],stale);self.assertNotIn(key,self.memory.pending)
 def test_parent_screen_wins_over_cursor_and_supports_negative_origin(self):
  parent=self.track(QWidget());parent.show();self.app.processEvents()
  dialog=self.track(QProgressDialog('正在保存',None,0,100,parent))
  screen=SimpleNamespace(availableGeometry=lambda:QRect(-1600,40,1600,860))
  with patch.object(QApplication,'screenAt',return_value=screen) as screen_at:
   dialog.show()
   # Native window decorations settle asynchronously; include all three
   # bounded placement passes before checking the final frame position.
   QTest.qWait(180)
   self.assert_centered(dialog,screen)
   self.assertEqual(screen_at.call_args.args[0],parent.frameGeometry().center())
   self.assertTrue(screen.availableGeometry().contains(dialog.frameGeometry()))
 def test_new_and_corrupt_dialog_center_but_saved_business_geometry_survives(self):
  for corrupt in (False,True):
   dialog=self.track(QDialog());dialog.setWindowTitle('业务窗口'+str(corrupt));dialog.resize(320,180)
   if corrupt:self.memory.values[self.memory.key(dialog)]='invalid'
   dialog.show();self.app.processEvents();self.assert_centered(dialog)
   dialog.resize(420,220);dialog.move(35,60);self.app.processEvents();dialog.close()
   reopened=self.track(QDialog());reopened.setWindowTitle(dialog.windowTitle());reopened.show();self.app.processEvents()
   self.assertEqual(reopened.size(),dialog.size());self.assertEqual(reopened.pos(),dialog.pos());reopened.close()
 def test_material_import_uses_library_as_popup_owner(self):
  from database.database import Database
  from services.services import Services
  from ui.main_window import MainWindow,MaterialImportResultDialog,MaterialHeaderMappingDialog
  from services.services import MaterialHeaderError
  db=Database(str(Path(self.tmp.name)/'db'));svc=Services(db,self.cfg)
  main=self.track(MainWindow(svc));main.show();main.show_materials();library=main._materials
  calls=[]
  def importing(*args,**kwargs):
   visible=[w for w in QApplication.topLevelWidgets() if isinstance(w,QProgressDialog) and w.isVisible()]
   self.assertEqual(len(visible),1);self.assertIs(visible[0].parentWidget(),library);self.assert_centered(visible[0])
   calls.append(visible[0])
   if len(calls)==1:raise MaterialHeaderError(['编码'],['物料基础编码'])
   return [],[]
  try:
   with patch.object(QFileDialog,'getOpenFileName',return_value=(str(Path(self.tmp.name)/'input.xlsx'),'')),patch('ui.main_window.choose_material_sheet',return_value='Sheet'),patch.object(svc,'import_materials',side_effect=importing),patch.object(MaterialHeaderMappingDialog,'exec_',return_value=QDialog.Accepted),patch.object(MaterialImportResultDialog,'exec_',return_value=QDialog.Accepted):
    main.import_materials()
   self.assertEqual(len(calls),2)
  finally:library.close();main.close();db.close()

 def test_bom_save_progress_is_centered_and_owned_by_editor(self):
  from database.database import Database
  from services.services import Services
  from ui.main_window import BomWindow
  db=Database(str(Path(self.tmp.name)/'save.db'));svc=Services(db,self.cfg)
  root=svc.create_material(dict(base_code='R',version='100',name='root',unit='pcs'));svc.create_sku(root)
  window=self.track(BomWindow(svc,root));window.show();self.app.processEvents()
  checked=[];original=QProgressDialog.setValue
  def update(progress,value):
   original(progress,value)
   for _ in range(3):self.app.processEvents()
   self.assertIs(progress.parentWidget(),window);self.assert_centered(progress);checked.append(value)
  try:
   with patch.object(QProgressDialog,'setValue',update),patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning',side_effect=AssertionError('BOM save failed')):
    self.assertTrue(window.save())
   self.assertIn(100,checked)
  finally:window.dirty=False;window.close();db.close()

 def test_settling_stops_and_does_not_override_later_user_move(self):
  dialog=self.track(QProgressDialog('正在导入',None,0,100));dialog.show()
  QTest.qWait(180);self.assert_centered(dialog)
  self.assertFalse(dialog._bom_placement_timer.isActive())
  dialog.move(30,40);expected=dialog.pos();QTest.qWait(100)
  self.assertEqual(dialog.pos(),expected)
