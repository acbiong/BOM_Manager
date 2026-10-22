"""Exercise real nonmodal result loops, focus transfer and cancellation."""
import os,sys,unittest,tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QTimer,QEvent
from PyQt5.QtWidgets import QApplication,QPushButton
from PyQt5.QtTest import QTest
from ui.interactive_windows import QDialog,QMainWindow,QInputDialog,QFileDialog,QColorDialog,QMessageBox,QProgressDialog
from ui.main_window import MaterialDialog

class InteractiveWindowsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.owner=QMainWindow();self.owner.svc=type('Service',(),{'db':object(),'config_service':None,'UNITS':['pcs']})()
  self.button=QPushButton('SKU操作',self.owner);self.owner.setCentralWidget(self.button)
  self.clicks=0;self.button.clicked.connect(self.clicked);self.owner.show()
 def clicked(self):self.clicks+=1
 def tearDown(self):
  self.owner.close();self.owner.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
 def interact(self,dialog,complete):
  failures=[]
  def step():
   try:
    self.assertTrue(dialog.isVisible());self.assertEqual(dialog.windowModality(),Qt.NonModal)
    self.assertIsNone(self.app.activeModalWidget());self.assertIsNone(dialog.windowHandle().transientParent())
    self.owner.raise_();self.owner.activateWindow();self.app.processEvents()
    self.assertIs(self.app.activeWindow(),self.owner)
    QTest.mouseClick(self.button,Qt.LeftButton);self.assertEqual(self.clicks,1)
    dialog.raise_();dialog.activateWindow();self.app.processEvents()
    self.assertIs(self.app.activeWindow(),dialog);complete(dialog)
   except BaseException as error:failures.append(error);dialog.reject()
  QTimer.singleShot(0,step);result=dialog.exec_()
  if failures:raise failures[0]
  return result
 def test_material_input_accept_cancel_and_focus_roundtrip(self):
  dialog=MaterialDialog(self.owner)
  try:
   def complete(d):d.e['name'].setText('输入保留');d.accept()
   self.assertEqual(self.interact(dialog,complete),QDialog.Accepted);self.assertEqual(dialog.data()['name'],'输入保留')
   self.clicks=0;self.assertEqual(self.interact(dialog,lambda d:d.reject()),QDialog.Rejected)
  finally:dialog.deleteLater()
 def test_file_color_input_and_confirmation_windows_are_independent(self):
  dialogs=[QFileDialog(self.owner),QColorDialog(self.owner),QInputDialog(self.owner),QMessageBox(self.owner)]
  dialogs[-1].setStandardButtons(QMessageBox.Yes|QMessageBox.No)
  try:
   for dialog in dialogs:
    self.clicks=0
    if isinstance(dialog,QMessageBox):
     self.assertEqual(self.interact(dialog,lambda d:d.button(QMessageBox.Yes).click()),QMessageBox.Yes)
    else:self.assertEqual(self.interact(dialog,lambda d:d.reject()),QDialog.Rejected)
  finally:
   for dialog in dialogs:dialog.deleteLater()
 def test_owner_close_and_project_switch_cancel_pending_result(self):
  dialog=QDialog(self.owner)
  try:
   QTimer.singleShot(0,self.owner.close);self.assertEqual(dialog.exec_(),QDialog.Rejected)
   self.owner.show()
   def switch():self.owner.svc=object();dialog.accept()
   QTimer.singleShot(0,switch);self.assertEqual(dialog.exec_(),QDialog.Rejected)
  finally:dialog.deleteLater()
 def test_project_switch_invalidates_custom_confirmation_button(self):
  box=QMessageBox(self.owner);button=box.addButton('执行',QMessageBox.AcceptRole)
  def switch():self.owner.svc=object();button.click()
  try:
   QTimer.singleShot(0,switch);self.assertEqual(box.exec_(),QDialog.Rejected);self.assertIsNone(box.clickedButton())
  finally:box.deleteLater()
 def test_modeless_show_and_progress_have_no_owner_stacking(self):
  for dialog in (MaterialDialog(self.owner),QProgressDialog('导入','取消',0,100,self.owner)):
   try:
    dialog.show();self.app.processEvents();self.assertEqual(dialog.windowModality(),Qt.NonModal)
    self.assertIsNone(dialog.windowHandle().transientParent());self.owner.activateWindow();self.app.processEvents()
    self.assertIs(self.app.activeWindow(),self.owner)
   finally:dialog.close();dialog.deleteLater()
 def test_static_input_and_file_helpers_keep_return_contract(self):
  def answer():
   window=self.app.activeWindow()
   self.assertIsInstance(window,QInputDialog);window.setTextValue('新名称');window.accept()
  QTimer.singleShot(30,answer)
  self.assertEqual(QInputDialog.getText(self.owner,'输入','名称'),('新名称',True))
  def cancel():self.app.activeWindow().reject()
  QTimer.singleShot(30,cancel)
  self.assertEqual(QFileDialog.getOpenFileName(self.owner,'选择文件')[0],'')
