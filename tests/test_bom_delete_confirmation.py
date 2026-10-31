"""Real Delete/Enter confirmation, without using the shared system clipboard."""
import os
# QMessageBox accesses native Windows window handles in Qt 5.15.
os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QTimer,QEvent,QCoreApplication,QElapsedTimer
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
  answered=[];failures=[];elapsed=QElapsedTimer();elapsed.start();timer=QTimer()
  def confirm():
   boxes=[w for w in self.app.topLevelWidgets() if isinstance(w,QMessageBox) and w.isVisible()]
   if not boxes and elapsed.elapsed()<5000:return
   timer.stop()
   try:
    self.assertEqual(len(boxes),1,'Delete must open one real confirmation')
    QTest.keyClick(boxes[0],Qt.Key_Return)
    self.assertFalse(boxes[0].isVisible(),'Enter must close the confirmation')
    answered.append(True)
   except BaseException as error:
    failures.append(error)
    for box in boxes:box.reject()
    self.w.close()
  timer.timeout.connect(confirm);timer.start(30)
  try:QTest.keyClick(self.w.tree,Qt.Key_Delete)
  finally:timer.stop()
  if failures:raise failures[0]
  self.assertTrue(answered)
  self.assertTrue(item.data(0,Qt.UserRole)['_deleted'])
  other=self.w.root_item.child(1);self.w.tree.setCurrentItem(other);self.w.show_item_info(other)
  field=self.w.fields['position'];field.setFocus();self.app.processEvents()
  with patch.object(QMessageBox,'question') as question:
   QTest.keyClick(field,Qt.Key_Delete);question.assert_not_called()
