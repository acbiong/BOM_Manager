import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QPoint,QEvent,QItemSelectionModel
from PyQt5.QtWidgets import QApplication,QMenu
from database.database import Database
from services.services import Services
from ui.main_window import MaterialWindow,BomWindow

class BatchMaterialDeleteTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db);self.windows=[]
  self.ids=[self.s.create_material(dict(base_code=f'M{i}',version='100',name=f'物料{i}',unit='pcs')) for i in range(5)]
 def tearDown(self):
  for w in self.windows:
   if isinstance(w,BomWindow):w.dirty=False
   w.close();w.deleteLater()
  self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.db.close();self.tmp.cleanup()
 def library(self):
  w=MaterialWindow(self.s);self.windows.append(w);return w
 def select_rows(self,w,*rows):
  w.t.clearSelection()
  for r in rows:w.t.selectionModel().select(w.t.model().index(r,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
 def library_menu(self,w,row,label='删除物料'):
  actions={}
  def choose(menu,*args):
   actions.update({a.text():a for a in menu.actions() if not a.isSeparator()});return actions[label]
  with patch.object(w.t,'rowAt',return_value=row),patch.object(QMenu,'exec_',choose):w.menu(QPoint())
  return actions
 def test_library_cancel_then_delete_selected_only(self):
  w=self.library();self.select_rows(w,0,2)
  with patch('ui.main_window.confirm_material_deletion',return_value=False) as confirm:self.library_menu(w,0)
  self.assertEqual(len(confirm.call_args.args[1]),2);self.assertEqual(len(self.s.materials()),5)
  with patch('ui.main_window.confirm_material_deletion',return_value=True),patch.object(w,'refresh',wraps=w.refresh) as refresh:self.library_menu(w,0)
  self.assertEqual(refresh.call_count,1);self.assertEqual({r['id'] for r in self.s.materials()},set(self.ids)-{self.ids[0],self.ids[2]})
 def test_right_click_unselected_row_targets_only_that_row(self):
  w=self.library();self.select_rows(w,0,1)
  with patch('ui.main_window.confirm_material_deletion',return_value=True) as confirm:self.library_menu(w,3)
  self.assertEqual(len(confirm.call_args.args[1]),1);self.assertEqual(len(self.s.materials()),4);self.assertFalse(self.s.material_snapshot(self.ids[3]))
 def test_referenced_material_disables_batch_delete(self):
  self.s.create_sku(self.ids[0]);self.s.save_bom(self.ids[0],[dict(material_id=self.ids[1],quantity=1,unit='pcs')])
  w=self.library();self.select_rows(w,1,2)
  with patch('ui.main_window.confirm_material_deletion') as confirm:actions=self.library_menu(w,1)
  self.assertFalse(actions['删除物料'].isEnabled());confirm.assert_not_called();self.assertEqual(len(self.s.materials()),5)
 def test_transaction_rolls_back_whole_batch_on_failure(self):
  w=self.library();delete=self.s.delete_material;calls=[]
  def fail_second(mid):
   calls.append(mid)
   if len(calls)==2:raise ValueError('模拟删除失败')
   delete(mid)
  with patch('ui.main_window.confirm_material_deletion',return_value=True),patch.object(self.s,'delete_material',fail_second),patch('ui.main_window.show_operation_error') as error:
   w.delete_materials(self.s.materials()[:2])
  error.assert_called_once();self.assertEqual(len(self.s.materials()),5);self.assertFalse(self.db.conn.in_transaction)
 def bom(self):
  self.s.create_sku(self.ids[0]);self.s.save_bom(self.ids[0],[dict(material_id=i,quantity=1,unit='pcs') for i in self.ids[1:3]]+[dict(parent_material_id=self.ids[1],material_id=self.ids[3],quantity=2,unit='pcs')])
  w=BomWindow(self.s,self.ids[0]);self.windows.append(w);w.tree.clearSelection()
  nodes=[w.root_item.child(i) for i in range(2)];w.tree.setCurrentItem(nodes[0])
  for node in nodes:node.setSelected(True)
  return w,nodes
 def test_bom_batch_delete_confirmation_and_one_undo(self):
  w,nodes=self.bom()
  with patch('ui.main_window.confirm_material_deletion',return_value=False):w.confirm_delete(nodes[0])
  self.assertFalse(w.dirty)
  with patch('ui.main_window.confirm_material_deletion',return_value=True) as confirm:w.confirm_delete(nodes[0])
  self.assertEqual(len(confirm.call_args.args[1]),2)
  self.assertTrue(all(n.data(0,Qt.UserRole).get('_deleted') for n in nodes));self.assertEqual(len(self.s.bom(self.ids[0])),3)
  self.assertTrue(nodes[0].child(0).data(0,Qt.UserRole).get('_deleted'))
  self.assertEqual(len(w.history.undo_stack),1);w.history.undo()
  self.assertTrue(all(not w.root_item.child(i).data(0,Qt.UserRole).get('_deleted') for i in range(2)))
 def test_locked_bom_multi_menu_delete_disabled(self):
  w,nodes=self.bom();captured={}
  def choose(menu,*args):
   captured.update({a.text():a for a in menu.actions()});return captured['删除物料']
  with patch.object(w,'is_locked',return_value=True),patch.object(w.tree,'itemAt',return_value=nodes[0]),patch.object(QMenu,'exec_',choose),patch('ui.main_window.confirm_material_deletion') as confirm:w.context_menu(QPoint())
  self.assertFalse(captured['删除物料'].isEnabled());confirm.assert_not_called()

 def test_ctrl_selection_and_right_click_preserve_frozen_rows(self):
  from PyQt5.QtTest import QTest
  w=self.library();w.show();self.app.processEvents()
  view=w.t.frozen
  for row,modifier in ((0,Qt.NoModifier),(2,Qt.ControlModifier)):
   QTest.mouseClick(view.viewport(),Qt.LeftButton,modifier,view.visualRect(view.model().index(row,1)).center())
  self.assertEqual({i.row() for i in w.t.selectionModel().selectedRows()},{0,2})
  with patch.object(QMenu,'exec_',return_value=None):
   QTest.mouseClick(view.viewport(),Qt.RightButton,Qt.NoModifier,view.visualRect(view.model().index(0,1)).center())
  self.assertEqual({i.row() for i in w.t.selectionModel().selectedRows()},{0,2})
