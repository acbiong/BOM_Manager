import os,sys,tempfile,unittest,json,subprocess
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QSettings,QPoint,QEvent
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication,QTreeWidgetItem,QStyleOptionViewItem,QStyledItemDelegate
from PyQt5.QtTest import QTest
from ui.main_window import BomTreeWidget,BomWindow
from ui.bom_tree_layout import BomTreeColumns
from ui.table_layout import fit_columns
from database.database import Database
from services.services import Services


class BomTreeLayoutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.settings=QSettings(str(Path(self.tmp.name)/'layout.ini'),QSettings.IniFormat)
  self.patch=patch('ui.bom_tree_layout.QSettings',return_value=self.settings);self.patch.start();self.widgets=[]
 def tearDown(self):
  for w in self.widgets:
   if hasattr(w,'dirty'):w.dirty=False
   w.close();w.deleteLater()
  self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.patch.stop();self.tmp.cleanup()
 def settle(self):
  for _ in range(8):self.app.processEvents()
 def tree(self):
  tree=BomTreeWidget();tree.setHeaderLabels(['物料编码/名称','数量','单位','位置','备注'])
  tree._bom_columns=BomTreeColumns(tree);self.widgets.append(tree);tree.resize(1000,600)
  root=QTreeWidgetItem(tree,['ROOT100 根物料','','','','']);root.setExpanded(True)
  child=QTreeWidgetItem(root,['C100 '+('超长物料名称LongToken'*8),'1.25','pcs','A1','备注'])
  tree.show();fit_columns(tree);self.settle();return tree,child
 def drag(self,tree,column,width):
  h=tree.header();start=QPoint(h.sectionViewportPosition(column)+h.sectionSize(column)-1,h.height()//2)
  end=start+QPoint(width-h.sectionSize(column),0)
  QTest.mousePress(h.viewport(),Qt.LeftButton,pos=start)
  self.app.sendEvent(h.viewport(),QMouseEvent(QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
  QTest.mouseRelease(h.viewport(),Qt.LeftButton,pos=end);self.settle()
 def test_wrap_and_row_height_follow_width_including_depth(self):
  tree,child=self.tree();child.setExpanded(True)
  nested=QTreeWidgetItem(child,['C'*95+' 中文材料','2','pcs','P1','']);self.settle()
  self.drag(tree,0,240);narrow=tree.visualItemRect(child).height()
  self.assertGreater(narrow,tree.fontMetrics().height()*2)
  for node in (child,nested):
   index=tree.indexFromItem(node);opt=QStyleOptionViewItem();opt.initFrom(tree)
   self.assertGreaterEqual(tree.visualItemRect(node).height(),tree.itemDelegate().sizeHint(opt,index).height())
  self.assertGreaterEqual(tree.visualItemRect(nested).top(),tree.visualItemRect(child).bottom())
  self.drag(tree,0,500);self.assertLess(tree.visualItemRect(child).height(),narrow)
  self.assertEqual(child.text(0),'C100 '+('超长物料名称LongToken'*8))
  child.setText(0,'C100 短名称');self.settle()
  native=QStyledItemDelegate(tree);option=QStyleOptionViewItem();option.initFrom(tree)
  self.assertEqual(tree.visualItemRect(child).height(),max(native.sizeHint(option,tree.indexFromItem(child,c)).height() for c in range(5)))
 def test_auto_compact_columns_include_collapsed_content_and_update(self):
  tree,child=self.tree();child.setExpanded(False)
  QTreeWidgetItem(child,['hidden','123456.789012','millimetres','Location ABCDEF',''])
  self.settle()
  for col,text in ((1,'123456.789012'),(2,'millimetres'),(3,'Location ABCDEF')):
   self.assertGreaterEqual(tree.columnWidth(col),tree.fontMetrics().horizontalAdvance(text)+8)
  widths=[tree.columnWidth(c) for c in (1,2,3)];tree.resize(1400,600);self.settle()
  self.assertEqual([tree.columnWidth(c) for c in (1,2,3)],widths)
  child.setText(3,'1234567890'*3);self.settle();self.assertGreater(tree.columnWidth(3),widths[2])
 def test_actual_drag_persists_across_refresh_and_new_tree(self):
  tree,child=self.tree()
  for col,width in ((0,280),(1,100),(2,90),(3,160),(4,140)):self.drag(tree,col,width)
  saved=[tree.columnWidth(c) for c in range(5)]
  self.assertEqual(saved,[280,100,90,160,140]);self.assertEqual(len(json.loads(self.settings.value(BomTreeColumns.KEY))),5)
  child.setText(3,'位置'*80);fit_columns(tree);tree.resize(1200,600);self.settle()
  self.assertEqual([tree.columnWidth(c) for c in range(5)],saved)
  other,_=self.tree();self.assertEqual([other.columnWidth(c) for c in range(5)],saved)
 def test_programmatic_resize_is_not_remembered_and_double_click_restores_auto(self):
  tree,child=self.tree();tree.setColumnWidth(1,190);self.settle()
  self.assertEqual(self.settings.value(BomTreeColumns.KEY,'{}'),'{}')
  self.drag(tree,1,150);self.assertEqual(tree.columnWidth(1),150)
  h=tree.header();point=QPoint(h.sectionViewportPosition(1)+h.sectionSize(1)-1,h.height()//2)
  QTest.mouseDClick(h.viewport(),Qt.LeftButton,pos=point);self.settle()
  self.assertNotIn('1',json.loads(self.settings.value(BomTreeColumns.KEY)));self.assertLess(tree.columnWidth(1),150)
 def test_unchanged_fit_and_non_display_data_do_not_repeat_layout(self):
  tree,child=self.tree()
  original=tree.doItemsLayout
  with patch.object(tree,'doItemsLayout',side_effect=lambda:original()) as layout:
   for _ in range(5):fit_columns(tree)
   child.setData(0,Qt.UserRole,{'draft':True});self.settle();self.assertEqual(layout.call_count,0)
   child.setText(0,'新的更长名称'*60);self.settle();self.assertGreater(layout.call_count,0)
 def test_editor_save_and_locked_browser_share_widths_without_dirtying_bom(self):
  db=Database(str(Path(self.tmp.name)/'db'));svc=Services(db)
  try:
   root=svc.create_material(dict(base_code='R',version='100',name='长物料名称'*12,unit='pcs'))
   child=svc.create_material(dict(base_code='C',version='100',name='子物料'*40,unit='pcs'))
   sid=svc.create_sku(root);svc.save_bom(root,[dict(material_id=child,quantity=1,unit='pcs')])
   w=BomWindow(svc.for_sku(sid),root);self.widgets.append(w);w.show();self.settle()
   self.drag(w.tree,1,105);self.assertFalse(w.dirty)
   w.tree.setCurrentItem(w.root_item.child(0));w.show_item_info(w.root_item.child(0));w.fields['quantity'].setValue(2.5)
   with patch('ui.main_window.QMessageBox.information'):self.assertTrue(w.save())
   self.settle();self.assertEqual(w.tree.columnWidth(1),105);self.assertEqual(w.tree.currentItem().data(0,Qt.UserRole)['material_id'],child)
   svc.set_sku_locked(sid,True)
   other=BomWindow(svc.for_sku(sid),root);self.widgets.append(other);other.show();self.settle()
   self.assertTrue(other.is_locked());self.assertEqual(other.tree.columnWidth(1),105)
   self.assertGreater(other.tree.visualItemRect(other.root_item.child(0)).height(),other.tree.fontMetrics().height())
  finally:
   for w in self.widgets:w.dirty=False;w.close()
   self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.widgets=[];db.close()
 def test_standalone_theme_initialization_and_close_lifecycle(self):
  code='''
import sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,'src')
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEvent
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MainWindow
app=QApplication([]);calls=[];original=app.setStyle
def style(*args):calls.append(args);return original(*args)
with tempfile.TemporaryDirectory() as tmp,patch.object(app,'setStyle',side_effect=style):
 db=Database(str(Path(tmp)/'db'));s=Services(db)
 root=s.create_material(dict(base_code='R',version='100',name='换行物料名称'*30,unit='pcs'));s.create_sku(root)
 try:
  for _ in range(4):
   w=BomWindow(s,root);w.show();app.processEvents()
   assert app.property('bom_fusion_initialized') and len(calls)==1
   layout=w.tree._bom_columns;layout.invalidate();assert layout.timer.isActive()
   w.close();assert layout.closed and not layout.timer.isActive()
   # Deliberately leave deferred destruction pending while opening the main window.
   main=MainWindow(s);main.toggle_theme();main.toggle_theme()
   assert len(calls)==1
   main.close();main.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)
 finally:db.close()
from tools.run_test_module import release_qt
release_qt()
'''
  result=subprocess.run([sys.executable,'-X','faulthandler','-c',code],cwd=Path(__file__).parents[1],capture_output=True,text=True,timeout=60)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
