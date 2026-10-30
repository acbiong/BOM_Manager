import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import QTimer,QEvent
from PyQt5.QtWidgets import QApplication
from openpyxl import Workbook
from database.database import Database
from services.services import Services,MATERIAL_IMPORT_HEADERS
from infrastructure.events import WindowRefreshBus
from infrastructure.operation_progress import checkpoint,_current
from ui.operation_progress import operation,OperationProgress,RECENT_OPERATIONS
from ui.main_window import MainWindow,MaterialWindow

class BulkImportProgressTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_bulk_import_refreshes_once_and_keeps_single_progress(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));svc=Services(db)
   main=MainWindow(svc);library=MaterialWindow(svc,main)
   book=Workbook();book.active.append(MATERIAL_IMPORT_HEADERS)
   for i in range(120):book.active.append([f'M{i}','100',f'测试物料{i}','规格','pcs','','M','厂商',''])
   path=Path(tmp)/'materials.xlsx';book.save(path);book.close()
   counts={'main':0,'library':0};events=[];controllers=set();dialogs=set();sized_rows=[]
   resize_row=library.t.resizeRowToContents
   def row_size(row):sized_rows.append(row);resize_row(row)
   main_refresh=main.refresh;library_refresh=library.refresh;update=OperationProgress.update
   def refresh_main():counts['main']+=1;main_refresh()
   def refresh_library():counts['library']+=1;library_refresh()
   def observe(controller,*args,**kwargs):
    update(controller,*args,**kwargs);controllers.add(id(controller))
    if controller.dialog:dialogs.add(id(controller.dialog))
   def collect(event):
    if event.get('type')=='material_changed':events.append(event['id'])
   WindowRefreshBus.subscribe(collect);RECENT_OPERATIONS.clear()
   try:
    with patch.object(library.t,'resizeRowToContents',row_size),patch.object(main,'refresh',refresh_main),patch.object(library,'refresh',refresh_library),patch.object(OperationProgress,'threshold',0),patch.object(OperationProgress,'update',observe):
     ok,failed=operation('导入物料')(lambda:svc.import_materials(path))()
     self.app.processEvents()
    self.assertEqual(len(ok),120);self.assertEqual(failed,[])
    self.assertEqual(counts,{'main':1,'library':1});self.assertEqual(len(set(events)),120)
    self.assertEqual(library.t.rowCount(),120)
    self.assertEqual(sized_rows,list(range(120)))
    self.assertEqual(len(controllers),1);self.assertEqual(len(dialogs),1)
    self.assertEqual([r['operation'] for r in RECENT_OPERATIONS],['导入物料'])
   finally:
    WindowRefreshBus.unsubscribe(collect)
    library.close();main.close();library.deleteLater();main.deleteLater()
    self.app.sendPostedEvents(None,QEvent.DeferredDelete);db.close()
 def test_progress_geometry_and_heartbeat_do_not_jump(self):
  controller=OperationProgress(None,'导出资料库');controller.threshold=0;controller.paint_interval=0
  try:
   controller.update('短提示',2,10);dialog=controller.dialog;geometry=dialog.geometry()
   controller.update();self.assertEqual((dialog.value(),dialog.maximum()),(2,10))
   controller.update('很长的工作表名称和路径'*30,3,10)
   self.assertEqual(dialog.geometry(),geometry);self.assertIs(controller.dialog,dialog)
  finally:controller.close();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
 def test_repeated_queued_refreshes_share_original_operation(self):
  calls=[];controllers=[]
  @operation('刷新清单')
  def refresh():calls.append('refresh');controllers.append(_current.get());checkpoint('刷新…',1,1)
  @operation('导出资料库')
  def export():
   controllers.append(_current.get())
   for _ in range(20):QTimer.singleShot(0,refresh)
   checkpoint('导出…',1,2);calls.append('export')
  RECENT_OPERATIONS.clear()
  with patch.object(OperationProgress,'threshold',0):export()
  self.app.processEvents()
  self.assertEqual(calls,['export','refresh']);self.assertIs(controllers[0],controllers[1])
  self.assertEqual(len(RECENT_OPERATIONS),1)

 def test_idle_layout_timer_does_not_repeat_row_sizing(self):
  from PyQt5.QtWidgets import QTableWidget,QTableWidgetItem
  from ui.table_layout import fit_columns
  table=QTableWidget(3,2)
  for r in range(3):table.setItem(r,0,QTableWidgetItem('自动换行文字'*5))
  try:
   with patch.object(table,'resizeRowsToContents',wraps=table.resizeRowsToContents) as resize:
    fit_columns(table);table._proportional_columns.apply();table._proportional_columns.apply()
    self.assertEqual(resize.call_count,1)
    # A real content change must still recalculate row heights.
    table.item(0,0).setText('更长文字'*80);fit_columns(table)
    self.assertEqual(resize.call_count,2)
  finally:table.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)

 def test_root_bom_import_adjusts_tree_only_after_final_styles(self):
  from ui.main_window import BomWindow
  from ui.table_layout import fit_columns
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));svc=Services(db)
   root=svc.create_material(dict(base_code='R',version='1',name='根节点',unit='pcs'))
   child=svc.create_material(dict(base_code='C',version='1',name='子物料',unit='pcs'))
   svc.create_sku(root);svc.save_bom(root,[dict(material_id=child,quantity=1,unit='pcs')])
   window=BomWindow(svc,root);adjusted=[]
   def fit(widget,*args,**kwargs):
    if widget is window.tree:adjusted.append(widget)
    return fit_columns(widget,*args,**kwargs)
   try:
    with patch('ui.main_window.fit_columns',fit):window.stage_import([])
    self.assertEqual(len(adjusted),1);self.assertTrue(window.dirty)
   finally:
    window.dirty=False;window.close();window.deleteLater()
    self.app.sendPostedEvents(None,QEvent.DeferredDelete);db.close()
