import os,sys,unittest,tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QWidget
from PyQt5.QtCore import QTimer,QEvent,QObject
from ui.interactive_windows import QInputDialog,QFileDialog,QColorDialog,QMessageBox
from infrastructure.events import WindowRefreshBus

class WindowDestructionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_pending_helpers_cancel_safely_when_owner_is_destroyed(self):
  calls=[lambda p:QInputDialog.getText(p,'输入','名称'),lambda p:QInputDialog.getInt(p,'输入','数量'),lambda p:QInputDialog.getItem(p,'选择','物料',['A']),lambda p:QFileDialog.getOpenFileName(p),lambda p:QFileDialog.getSaveFileName(p),lambda p:QFileDialog.getExistingDirectory(p),lambda p:QColorDialog.getColor(parent=p),lambda p:QMessageBox.question(p,'确认','继续？')]
  for call in calls:
   owner=QWidget();owner.show();QTimer.singleShot(20,owner.deleteLater)
   result=call(owner)
   if isinstance(result,tuple):self.assertFalse(result[1])
   elif isinstance(result,str):self.assertEqual(result,'')
   elif hasattr(result,'isValid'):self.assertFalse(result.isValid())
   else:self.assertNotEqual(result,QMessageBox.Yes)
 def test_destroyed_refresh_subscriber_is_removed_before_publish(self):
  class Receiver(QObject):
   def handle(self,event):self.objectName() # raises if the C++ object is deleted
  receiver=Receiver();WindowRefreshBus.subscribe(receiver.handle);receiver.deleteLater()
  self.app.sendPostedEvents(None,QEvent.DeferredDelete)
  WindowRefreshBus.publish({'type':'bom_changed','root':1})
  self.assertNotIn(receiver.handle,WindowRefreshBus._handlers)
 def test_unsubscribed_handler_is_not_called_from_old_dispatch_snapshot(self):
  calls=[]
  def second(event):calls.append('second')
  def first(event):calls.append('first');WindowRefreshBus.unsubscribe(second)
  WindowRefreshBus.subscribe(first);WindowRefreshBus.subscribe(second)
  try:WindowRefreshBus.publish({'type':'test'});self.assertEqual(calls,['first'])
  finally:WindowRefreshBus.unsubscribe(first);WindowRefreshBus.unsubscribe(second)
