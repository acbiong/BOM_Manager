"""Real Delete/Enter confirmation, without using the shared system clipboard."""
import os
# QMessageBox accesses native Windows window handles in Qt 5.15.
os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QTimer,QEvent,QCoreApplication
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication,QMessageBox
from ui.interactive_windows import QMessageBox
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow


class DeleteConfirmationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));svc=Services(self.db)
  root,first,second=[svc.create_material(dict(base_code=code,version='1',name=code,unit='pcs')) for code in ('R','A','B')]
  svc.create_sku(root);svc.save_bom(root,[dict(material_id=mid,quantity=1,unit='pcs') for mid in (first,second)])
  self.w=BomWindow(svc,root)
 def tearDown(self):
  self.w.dirty=False;self.w.close()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
  self.db.close();self.tmp.cleanup()
 def test_delete_key_enter_cancel_and_text_edit_focus(self):
  self.w.show();self.w.activateWindow();item=self.w.root_item.child(0);self.w.tree.setCurrentItem(item);self.w.tree.setFocus();self.app.processEvents()
  with patch.object(QMessageBox,'question',return_value=QMessageBox.No) as question:
   QTest.keyClick(self.w.tree,Qt.Key_Delete);self.assertEqual(question.call_count,1)
  self.assertFalse(item.data(0,Qt.UserRole).get('_deleted',False))
  def confirm():
   box=self.app.activeWindow()
   if box is not None:QTest.keyClick(box,Qt.Key_Return)
  QTimer.singleShot(30,confirm);QTest.keyClick(self.w.tree,Qt.Key_Delete)
  self.assertTrue(item.data(0,Qt.UserRole)['_deleted'])
  other=self.w.root_item.child(1);self.w.tree.setCurrentItem(other);self.w.show_item_info(other)
  field=self.w.fields['position'];field.setFocus();self.app.processEvents()
  with patch.object(QMessageBox,'question') as question:
   QTest.keyClick(field,Qt.Key_Delete);question.assert_not_called()
