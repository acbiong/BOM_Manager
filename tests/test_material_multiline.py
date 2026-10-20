import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QPlainTextEdit,QLabel,QScrollArea,QDialog
from PyQt5.QtCore import Qt,QEvent
from PyQt5.QtTest import QTest
from database.database import Database
from services.services import Services
from ui.main_window import MaterialDialog,MaterialWindow,CreateMaterialDialog
from ui.save_shortcut import install_save_shortcuts

class MaterialMultilineTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def dispose(self,w):w.close();w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
 def test_long_text_wrap_and_scroll_without_changing_content(self):
  text='长物料规格描述ABC123'*60
  dialog=MaterialDialog(data={'name':text,'mpn':'ABCDEFGHIJ'*100});dialog.resize(430,360);dialog.show();self.app.processEvents()
  try:
   for widget in dialog.e.values():
    self.assertIsInstance(widget,QPlainTextEdit);self.assertEqual(widget.lineWrapMode(),QPlainTextEdit.WidgetWidth)
    self.assertEqual(widget.document().defaultTextOption().alignment(),Qt.AlignLeft)
   name=dialog.e['name'];self.assertGreater(name.document().firstBlock().layout().lineCount(),1)
   self.assertEqual(dialog.data()['name'],text);self.assertGreater(name.verticalScrollBar().maximum(),0)
   self.assertGreater(dialog.findChild(QScrollArea).verticalScrollBar().maximum(),0)
   self.assertEqual(name.horizontalScrollBar().maximum(),0)
  finally:self.dispose(dialog)
 def test_readonly_identity_and_enter_adds_newline(self):
  dialog=MaterialDialog(data={'base_code':'PART','version':'100','description':'第一行'},readonly_keys={'base_code','version'});dialog.show();dialog.activateWindow()
  try:
   self.assertIsInstance(dialog.e['base_code'],QLabel);self.assertTrue(dialog.e['base_code'].wordWrap())
   editor=dialog.e['description'];editor.setFocus();editor.moveCursor(editor.textCursor().End);self.app.processEvents();QTest.keyClick(editor,Qt.Key_Return)
   QTest.keyClicks(editor,'line2');self.assertTrue(dialog.isVisible());self.assertEqual(dialog.data()['description'],'第一行\nline2')
   self.assertEqual(dialog.data()['base_code'],'PART')
  finally:self.dispose(dialog)
 def test_create_ctrl_s_and_edit_roundtrip(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));svc=Services(db);owner=MaterialWindow(svc);dialog=CreateMaterialDialog(owner)
   manager=install_save_shortcuts(self.app)
   values=dict(base_code='NEW',version='100',name='名称\n第二行',description='规格\n多行描述',manufacturer='厂家\n地址',mpn='MPN-1',grade='工业级')
   try:
    for key,value in values.items():dialog.e[key].setText(value)
    dialog.show();dialog.activateWindow();dialog.e['description'].setFocus();self.app.processEvents();QTest.keyClick(dialog.e['description'],Qt.Key_S,Qt.ControlModifier);self.app.processEvents()
    self.assertEqual(dialog.result(),QDialog.Accepted)
    record=svc.materials()[0]
    for key,value in values.items():self.assertEqual(record[key],value)
    edit=MaterialDialog(owner,dict(record),readonly_keys={'base_code','version'})
    try:
     edit.e['description'].setText('编辑后\n新规格');svc.update_material(record['id'],edit.data());self.assertEqual(svc.material_snapshot(record['id'])['description'],'编辑后\n新规格')
    finally:self.dispose(edit)
   finally:
    self.dispose(dialog);self.dispose(owner);db.close();manager.shutdown()
    if getattr(self.app,'_bom_save_shortcuts',None) is manager:del self.app._bom_save_shortcuts
    manager.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
