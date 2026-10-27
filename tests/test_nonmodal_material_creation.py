import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox,QPushButton
from ui.interactive_windows import QMessageBox
from PyQt5.QtCore import Qt,QEvent,QCoreApplication
from PyQt5.QtTest import QTest
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow,MaterialWindow

class NonmodalMaterialCreationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  root=self.s.create_material(dict(base_code='R',version='1',name='Root',unit='pcs'));sid=self.s.create_sku(root)
  self.main=MainWindow(self.s);self.main.show();self.main.show_materials();self.library=self.main._materials;self.bom=self.main.open_bom_id(sid)
 def tearDown(self):
  self.library.close();self.bom.dirty=False;self.bom.close();self.main.close();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.db.close();self.tmp.cleanup()
 def fill(self,dialog,code='NEW'):
  for key,value in dict(base_code=code,version='100',name='New material').items():dialog.e[key].setText(value)
 def test_other_windows_clickable_reuse_and_success_refresh(self):
  dialog=self.main.new_material();self.app.processEvents()
  self.assertFalse(dialog.isModal());self.assertIsNone(self.app.activeModalWidget());self.assertIs(self.main.new_material(),dialog)
  for owner in (self.main,self.library,self.bom):
   button=QPushButton('test',owner);button.show();clicked=[];button.clicked.connect(lambda:clicked.append(True))
   owner.activateWindow();self.app.processEvents();QTest.mouseClick(button,Qt.LeftButton);self.assertEqual(clicked,[True]);button.deleteLater()
  self.fill(dialog);before=self.library.t.rowCount();dialog.accept();self.app.processEvents()
  self.assertEqual(self.library.t.rowCount(),before+1);self.assertFalse(dialog.isVisible());self.assertIsNone(self.library._create_material_dialog)
  dialog.accept();self.assertEqual(len([m for m in self.s.materials() if m['base_code']=='NEW']),1)
 def test_failure_preserves_input_and_cancel_does_not_insert(self):
  dialog=self.main.new_material();self.fill(dialog,'R');dialog.e['version'].setText('1')
  with patch.object(QMessageBox,'warning') as warning:dialog.accept();warning.assert_not_called()
  self.assertIn('当前物料编码已经存在',dialog.duplicate_notice.text())
  self.assertEqual(len([m for m in self.s.materials() if m['base_code']=='R']),1)
  self.assertTrue(dialog.isVisible());self.assertEqual(dialog.e['name'].text(),'New material')
  dialog.e['base_code'].setText('FIXED');dialog.accept();self.assertTrue(any(m['base_code']=='FIXED' for m in self.s.materials()))
  other=self.main.new_material();self.fill(other,'CANCEL');other.reject();self.assertFalse(any(m['base_code']=='CANCEL' for m in self.s.materials()))
 def test_owner_close_and_database_switch_guard(self):
  dialog=self.main.new_material();self.fill(dialog)
  other=Database(str(Path(self.tmp.name)/'other'));original=self.s.db
  try:
   self.s.db=other
   with patch.object(QMessageBox,'warning') as warning:dialog.accept();warning.assert_called_once()
   self.assertEqual(other.conn.execute('SELECT COUNT(*) FROM materials').fetchone()[0],0)
  finally:self.s.db=original;other.close()
  self.library.close();self.assertFalse(dialog.isVisible())
 def test_standalone_library_is_nonmodal(self):
  library=MaterialWindow(self.s);library.show()
  try:
   dialog=library.new_material();self.assertFalse(dialog.isModal());self.fill(dialog,'SOLO');dialog.accept()
   self.assertTrue(any(library.t.item(i,0).text()=='SOLO' for i in range(library.t.rowCount())))
  finally:library.close()
