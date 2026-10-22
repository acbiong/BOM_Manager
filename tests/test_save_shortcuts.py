import os,sys,tempfile,unittest
# Exercise real message boxes with the Windows platform integration.
os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QEvent,QCoreApplication
from PyQt5.QtWidgets import QApplication,QDialog,QDialogButtonBox,QMessageBox,QInputDialog
from ui.interactive_windows import QMessageBox
from PyQt5.QtTest import QTest
from ui.save_shortcut import install_save_shortcuts
from ui.main_window import MaterialDialog,MaterialHeaderMappingDialog,ProjectDialog,MainWindow
from ui.sku_change_description import ChangeDescriptionDialog
from database.database import Database
from services.services import Services

class SaveShortcutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([]);install_save_shortcuts(cls.app)
 @classmethod
 def tearDownClass(cls):
  manager=cls.app._bom_save_shortcuts;manager.shutdown();del cls.app._bom_save_shortcuts
  manager.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
 def press(self,dialog,editor=None):
  dialog.show();dialog.activateWindow()
  if editor:editor.setFocus()
  self.app.processEvents();QTest.keyClick(editor or dialog,Qt.Key_S,Qt.ControlModifier)
  # Acceptance may hide the receiver before QtTest delivers modifier release.
  QTest.keyRelease(self.app.activeWindow() or dialog,Qt.Key_Control)
  self.app.processEvents()
 def dispose(self,*windows):
  for w in windows:w.close();w.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
 def test_forms_and_multiline_save_use_existing_confirmation(self):
  for dialog in (MaterialDialog(),ProjectDialog(),ChangeDescriptionDialog('原描述')):
   try:
    editor=getattr(dialog,'editor',None)
    if editor:editor.setPlainText('第一行\n第二行')
    self.press(dialog,editor);self.assertEqual(dialog.result(),QDialog.Accepted)
    if editor:self.assertEqual(dialog.description(),'第一行\n第二行')
   finally:self.dispose(dialog)
 def test_mapping_validation_is_not_bypassed_and_disabled_ok_stays_disabled(self):
  dialog=MaterialHeaderMappingDialog('missing.xlsx',['源列'],[],required=['必需字段'])
  try:
   with patch.object(QMessageBox,'warning') as warning:self.press(dialog);warning.assert_called_once()
   self.assertTrue(dialog.isVisible());self.assertEqual(dialog.result(),QDialog.Rejected)
   dialog.combos['必需字段'].setCurrentText('源列');button=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok);button.setEnabled(False)
   self.press(dialog);self.assertTrue(dialog.isVisible())
   button.setEnabled(True);self.press(dialog);self.assertEqual(dialog.result(),QDialog.Accepted)
  finally:self.dispose(dialog)
 def test_input_dialog_and_dangerous_choice_dialog(self):
  dialog=QInputDialog();dialog.setInputMode(QInputDialog.IntInput);dialog.setIntRange(1,1000);dialog.setIntValue(105)
  try:self.press(dialog);self.assertEqual(dialog.result(),QDialog.Accepted);self.assertEqual(dialog.intValue(),105)
  finally:self.dispose(dialog)
  box=QMessageBox(QMessageBox.Question,'删除','确认删除？',QMessageBox.Yes|QMessageBox.No)
  try:self.press(box);self.assertTrue(box.isVisible());self.assertIsNone(box.clickedButton())
  finally:self.dispose(box)
 def test_bom_save_enabled_state_and_modeless_create_isolation(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   root=s.create_material(dict(base_code='R',version='1',name='Root',unit='pcs'));sid=s.create_sku(root)
   main=MainWindow(s);bom=main.open_bom_id(sid)
   try:
    with patch.object(QMessageBox,'information') as message:
     self.press(bom);message.assert_not_called()
     bom.mark_dirty();self.press(bom);message.assert_called_once();self.assertFalse(bom.dirty)
    bom.mark_dirty();dialog=main.new_material()
    for key,value in dict(base_code='NEW',version='1',name='New').items():dialog.e[key].setText(value)
    self.press(dialog,dialog.e['name']);self.assertTrue(bom.dirty);self.assertTrue(any(m['base_code']=='NEW' for m in s.materials()))
   finally:bom.dirty=False;self.dispose(bom,main);db.close()

 def test_modal_child_does_not_save_parent_and_save_on_close_button(self):
  parent=ChangeDescriptionDialog('父窗口草稿');child=MaterialDialog(parent)
  try:
   parent.show();child.setWindowModality(Qt.WindowModal);self.press(child)
   self.assertEqual(child.result(),QDialog.Accepted);self.assertTrue(parent.isVisible());self.assertEqual(parent.result(),QDialog.Rejected)
  finally:self.dispose(child,parent)
  box=QMessageBox();box.setStandardButtons(QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
  try:self.press(box);self.assertIs(box.clickedButton(),box.button(QMessageBox.Save))
  finally:self.dispose(box)

 def test_custom_unsaved_bom_prompt_saves_instead_of_discard(self):
  box=QMessageBox();save=box.addButton('保存并退出',QMessageBox.AcceptRole)
  box.addButton('不保存退出',QMessageBox.DestructiveRole);box.addButton('取消',QMessageBox.RejectRole)
  try:self.press(box);self.assertIs(box.clickedButton(),save)
  finally:self.dispose(box)
