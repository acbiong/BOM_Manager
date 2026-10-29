import os,sys,time,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QWidget
from ui.operation_progress import operation,OperationProgress,RECENT_OPERATIONS
from infrastructure.operation_progress import checkpoint,file_work,suspend_progress,_current

class OperationProgressTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_threshold_cleanup_and_pause(self):
  owner=QWidget();owner.show()
  clock=[0.0]
  with patch('ui.operation_progress.time.perf_counter',side_effect=lambda:clock[0]):
   controller=OperationProgress(owner,'test');token=_current.set(controller)
   try:
    clock[0]=.099;checkpoint('测试',1,10);self.assertIsNone(controller.dialog)
    clock[0]=.101;checkpoint('测试',2,10)
    self.assertTrue(controller.dialog.isVisible());self.assertEqual(controller.dialog.value(),2)
    screen=owner.screen().availableGeometry();self.assertLess((controller.dialog.frameGeometry().center()-screen.center()).manhattanLength(),30)
    with suspend_progress():
     self.assertIsNone(_current.get());self.assertFalse(controller.dialog.isVisible());clock[0]=3.101
    self.assertAlmostEqual(clock[0]-controller.started,.101)
    controller.close();self.assertFalse(controller.dialog.isVisible())
   finally:_current.reset(token);owner.close()
 def test_file_worker_shows_progress_and_propagates_error_without_input_dispatch(self):
  ids=[];main=threading.get_ident();seen=[]
  original=OperationProgress.update
  def observe(controller,*args,**kwargs):
   ids.append(threading.get_ident());original(controller,*args,**kwargs)
   if controller.dialog is not None:seen.append(controller.dialog.isVisible())
  def work():
   time.sleep(.16);return threading.get_ident()
  @operation('文件测试')
  def run():return file_work(work)
  with patch.object(OperationProgress,'update',observe):worker=run()
  self.assertNotEqual(worker,main);self.assertEqual(set(ids),{main});self.assertIn(True,seen)
  self.assertTrue(RECENT_OPERATIONS[-1]['progress_shown']);self.assertIsNone(_current.get())
  @operation('异常测试')
  def failure():return file_work(lambda:(_ for _ in ()).throw(ValueError('失败')))
  with self.assertRaisesRegex(ValueError,'失败'):failure()
  self.assertTrue(RECENT_OPERATIONS[-1]['failed']);self.assertIsNone(_current.get())
 def test_fast_and_nested_operations_do_not_duplicate_windows(self):
  @operation('inner')
  def inner():checkpoint();return _current.get()
  @operation('outer')
  def outer():self.assertIs(inner(),_current.get());return 42
  RECENT_OPERATIONS.clear();size=len(RECENT_OPERATIONS);self.assertEqual(outer(),42)
  self.assertEqual(len(RECENT_OPERATIONS),size+1);self.assertFalse(RECENT_OPERATIONS[-1]['progress_shown'])

 def test_qt_signal_argument_and_no_event_reentry(self):
  from PyQt5.QtWidgets import QPushButton
  from PyQt5.QtCore import QTimer
  calls=[]
  @operation('按钮测试')
  def handler():
   timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(lambda:calls.append('timer'));timer.start(0)
   self.timer=timer
   time.sleep(.105);checkpoint('处理中')
   self.assertNotIn('timer',calls)
   calls.append('done')
  button=QPushButton();button.clicked.connect(handler);button.click()
  self.assertEqual(calls,['done']);self.app.processEvents();self.assertIn('timer',calls)
  button.close()

 def test_queued_operation_waits_until_current_operation_finishes(self):
  from PyQt5.QtCore import QTimer
  calls=[]
  @operation('排队保存')
  def save():calls.append('save')
  @operation('导出')
  def export():
   QTimer.singleShot(0,save)
   time.sleep(.105);checkpoint('正在导出',1,2)
   self.assertEqual(calls,[])
   calls.append('export done')
  export()
  self.assertEqual(calls,['export done'])
  self.app.processEvents()
  self.assertEqual(calls,['export done','save'])
