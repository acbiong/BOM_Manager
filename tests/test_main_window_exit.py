"""Closing the application must honor unsaved BOM decisions before hiding it."""
import os
os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import QCoreApplication,QEvent,QTimer
from PyQt5.QtWidgets import QApplication,QMessageBox
from config.config_service import ConfigService
from infrastructure.events import WindowRefreshBus
from services.services import Services
from ui.main_window import MainWindow
from ui.sku_change_description import DESCRIPTION_ROLE


class MainWindowExitTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.config=ConfigService(self.tmp.name)
  self.main=MainWindow(Services(None,self.config));self.main.show()
  self.assertTrue(self.main.switch_project(Path(self.tmp.name)/'project.db',create=True))
  self.svc=self.main.svc;self.db=self.svc.db
  self.root,self.child=[self.svc.create_material(dict(base_code=code,version='1',name=code,unit='pcs')) for code in ('SKU','CHILD')]
  self.sid=self.svc.create_sku(self.root);self.mirror=self.svc.for_sku(self.sid)
  self.mirror.save_bom(self.root,[dict(material_id=self.child,quantity=1,unit='pcs')])
  self.editor=self.main.open_bom_id(self.sid)
  self.editor.show_item_info(self.editor.root_item.child(0));self.editor.fields['quantity'].setText('2')
  self.assertTrue(self.editor.dirty);self.app.processEvents()
 def tearDown(self):
  for editor in set(self.main._bom_windows.values())|set(self.main._material_bom_windows.values()):editor.dirty=False;editor.close()
  if self.main._materials is not None:self.main._materials.close()
  self.main.close();self.main.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
  self.db.close();self.tmp.cleanup()
 def close_with(self,label):
  original=QMessageBox.exec_;self.prompts=[]
  def choose(box):
   self.prompts.append(box.windowTitle())
   button=next(b for b in box.buttons() if b.text()==label)
   QTimer.singleShot(0,button.click)
   return original(box)
  with patch.object(QMessageBox,'exec_',choose),patch.object(QMessageBox,'information'):
   return self.main.close()
 def test_cancel_keeps_main_editor_auxiliary_windows_and_updates_alive(self):
  self.main.show_materials();library=self.main._materials
  self.main.compare_boms();compare=self.main._compare_dialog
  create=self.main.new_material();create.e['name'].setText('未保存物料')
  self.assertFalse(self.close_with('取消'))
  self.assertEqual(self.prompts,['BOM未保存'])
  for window in (self.main,self.editor,library,compare,create):self.assertTrue(window.isVisible())
  self.assertTrue(self.editor.dirty);self.assertEqual(self.editor.fields['quantity'].text(),'2')
  self.assertEqual(self.mirror.bom(self.root)[0]['quantity'],1)
  self.assertIn(self.main.on_data_change,WindowRefreshBus._handlers)
  self.svc.update_sku_change_description(self.sid,'取消退出后仍可编辑')
  self.assertEqual(self.main.table.item(0,4).data(DESCRIPTION_ROLE),'取消退出后仍可编辑')
  self.assertEqual(create.e['name'].text(),'未保存物料')
 def test_save_failure_cancels_main_close_and_keeps_draft(self):
  with patch.object(self.editor,'save',return_value=False) as save:
   self.assertFalse(self.close_with('保存并退出'));save.assert_called_once()
  self.assertTrue(self.main.isVisible());self.assertTrue(self.editor.isVisible());self.assertTrue(self.editor.dirty)
  self.assertEqual(self.mirror.bom(self.root)[0]['quantity'],1)
 def test_save_before_exit_persists_and_unregisters_all_owned_windows(self):
  self.main.show_materials();library=self.main._materials
  self.main.compare_boms();compare=self.main._compare_dialog
  self.assertTrue(self.close_with('保存并退出'))
  self.assertEqual(self.prompts,['BOM未保存']);self.assertEqual(self.mirror.bom(self.root)[0]['quantity'],2)
  self.assertFalse(self.main.isVisible());self.assertFalse(library.isVisible());self.assertFalse(compare.isVisible())
  self.assertFalse(self.main._bom_windows)
  self.assertNotIn(self.main.on_data_change,WindowRefreshBus._handlers)
  self.assertNotIn(library.on_event,WindowRefreshBus._handlers)
  self.assertNotIn(self.editor.on_external_change,WindowRefreshBus._handlers)
 def test_discard_closes_editor_once_without_writing_database(self):
  closed=[];self.editor.closed.connect(lambda:closed.append(True))
  self.assertTrue(self.close_with('不保存退出'))
  self.assertEqual(self.prompts,['BOM未保存']);self.assertEqual(closed,[True])
  self.assertEqual(self.mirror.bom(self.root)[0]['quantity'],1);self.assertFalse(self.main._bom_windows)
