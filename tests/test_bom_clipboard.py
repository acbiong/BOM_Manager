"""BOM跨窗口复制、插入顺序和安全校验回归。"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMenu,QMessageBox
from ui.interactive_windows import QMessageBox
from PyQt5.QtCore import Qt,QPoint
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MaterialWindow
from ui.material_clipboard import copy_material,clipboard_material

class ClipboardTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.ids={c:self.s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ['R','S','A','B','C','D']}
  self.s.save_bom(self.ids['C'],[self.rel('D')]);self.s.save_bom(self.ids['R'],[self.rel('A'),self.rel('B')]);self.s.save_bom(self.ids['S'],[self.rel('C')])
  self.w=BomWindow(self.s,self.ids['R']);self.other=BomWindow(self.s,self.ids['S']);self.app.clipboard().clear()
 def rel(self,c):return dict(material_id=self.ids[c],quantity=1,unit='pcs')
 def tearDown(self):
  self.app.clipboard().clear()
  for w in [self.w,self.other]:w.dirty=False;w.close()
  self.db.close();self.tmp.cleanup()
 def test_cross_window_sibling_position_subtree_and_save(self):
  item=self.other.root_item.child(0);actions=self.other.clipboard_actions(QMenu(self.w),item)
  self.other.handle_clipboard_action(actions['copy'],actions,item)
  added=self.w.paste_material(self.w.root_item.child(0),False)
  self.assertEqual([self.w.root_item.child(i).data(0,Qt.UserRole)['material_id'] for i in range(3)],[self.ids[c] for c in ['A','C','B']])
  self.assertTrue(added.data(0,Qt.UserRole)['_added']);self.assertTrue(added.child(0).data(0,Qt.UserRole)['_added']);self.assertEqual(added.text(1),'1');self.assertIs(self.w.tree.currentItem(),added)
  self.assertEqual(len(self.s.bom(self.ids['R'])),2)
  self.assertFalse(self.w.export_action.isEnabled())
  with patch.object(QMessageBox,'information'):self.assertTrue(self.w.save())
  self.assertEqual([r['material_id'] for r in self.s.bom(self.ids['R'])],[self.ids[c] for c in ['A','C','D','B']])
 def test_library_copy_child_append_and_duplicate_disabled(self):
  library=MaterialWindow(self.s)
  row=next(i for i,r in enumerate(self.s.materials()) if r['id']==self.ids['C'])
  def choose(menu,*args):return next(a for a in menu.actions() if a.text()=='复制物料')
  try:
   with patch.object(library.t,'rowAt',return_value=row),patch.object(QMenu,'exec_',choose):library.menu(QPoint())
   added=self.w.paste_material(self.w.root_item,True)
   self.assertIs(self.w.root_item.child(2),added)
   actions=self.w.clipboard_actions(QMenu(self.w),self.w.root_item.child(0))
   self.assertFalse(actions['same'].isEnabled())
   self.assertTrue(actions['child'].isEnabled())
   self.assertIsNone(self.w.paste_material(self.w.root_item,True))
  finally:library.close()
 def test_cycles_self_ancestor_and_unsaved_graph(self):
  copy_material(self.s,self.ids['R'])
  actions=self.w.clipboard_actions(QMenu(self.w),self.w.root_item.child(0))
  self.assertFalse(actions['same'].isEnabled());self.assertFalse(actions['child'].isEnabled())
  copy_material(self.s,self.ids['A'])
  self.assertIsNone(self.w.paste_material(self.w.root_item.child(0),True))
  added=self.w.paste_material(self.w.root_item.child(1),True) # B -> A draft
  copy_material(self.s,self.ids['B'])
  self.assertIn('循环',self.w.paste_block_reason(self.w.root_item.child(0),True,self.ids['B']))
  self.assertIsNone(self.w.paste_material(added,True))
 def test_same_window_copy_and_invalid_clipboard(self):
  copy_material(self.s,self.ids['A']);added=self.w.paste_material(self.w.root_item.child(1),True)
  self.assertEqual(added.data(0,Qt.UserRole)['material_id'],self.ids['A'])
  actions=self.w.clipboard_actions(QMenu(self.w),self.w.root_item)
  self.assertFalse(actions['same'].isEnabled())
  self.app.clipboard().setText('不是物料');self.assertEqual(set(self.w.clipboard_actions(QMenu(self.w),self.w.root_item)),{'copy'})
  copy_material(self.s,self.ids['A'])
  other=Database(str(Path(self.tmp.name)/'other'))
  try:self.assertIsNone(clipboard_material(Services(other)))
  finally:other.close()

 def test_cut_paste_deleted_copy_restore_duplicate_and_save(self):
  original=self.w.root_item.child(0)
  self.w.show_item_info(original);self.w.fields['quantity'].setText('2.5');self.w.fields['position'].setText('位号');self.w.fields['remark'].setText('备注');self.w._alternate_edits[self.w.alternate_key(original)]=[self.ids['D']]
  self.assertTrue(self.w.cut_material(original))
  self.assertTrue(original.data(0,Qt.UserRole)['_deleted'])
  self.assertEqual(len(self.s.bom(self.ids['R'])),2)
  added=self.w.paste_material(self.w.root_item.child(1),False)
  self.assertIsNotNone(added);self.assertTrue(added.data(0,Qt.UserRole)['_added'])
  self.assertEqual([added.text(i) for i in (1,3,4)],['2.5','位号','备注']);self.assertEqual(self.w.alternate_ids(added),[self.ids['D']])
  with patch.object(QMessageBox,'warning') as warning:
   self.w.restore_relation(original);warning.assert_called_once()
  self.assertTrue(original.data(0,Qt.UserRole)['_deleted'])
  def choose(menu,*args):return next(a for a in menu.actions() if a.text()=='复制物料')
  with patch.object(self.w.tree,'itemAt',return_value=original),patch.object(QMenu,'exec_',choose):self.w.context_menu(QPoint())
  self.assertEqual(clipboard_material(self.s)['id'],self.ids['A'])
  copied=self.other.paste_material(self.other.root_item,True)
  self.assertIsNotNone(copied)
  with patch.object(QMessageBox,'information'):self.assertTrue(self.w.save())
  self.assertEqual([r['material_id'] for r in self.s.bom(self.ids['R'])],[self.ids['B'],self.ids['A']])
 def test_cut_subtree_and_readonly_guards(self):
  item=self.other.root_item.child(0)
  self.assertTrue(self.other.cut_material(item));self.assertTrue(item.child(0).data(0,Qt.UserRole)['_deleted'])
  self.assertIsNone(self.other.paste_material(item,True))
  added=self.w.paste_material(self.w.root_item,True)
  self.assertEqual(added.childCount(),1)
  self.assertFalse(self.w.cut_material(self.w.root_item))
  with patch.object(self.w,'is_locked',return_value=True),patch.object(QMessageBox,'question') as question:
   self.assertFalse(self.w.cut_material(added));self.w.confirm_delete(added);question.assert_not_called()

 def test_copy_draft_attributes_cross_window_and_persist(self):
  source=self.other.root_item.child(0);self.other.show_item_info(source)
  self.other.fields['quantity'].setText('2.375');self.other.fields['position'].setText('U1\nU2');self.other.fields['remark'].setText('真实备注\n第二行')
  self.other._alternate_edits[self.other.alternate_key(source)]=[self.ids['A'],self.ids['B']]
  source.setText(4,'真实备注\n第二行\n有其他BOM更新导入此变更')
  actions=self.other.clipboard_actions(QMenu(self.other),source);self.other.handle_clipboard_action(actions['copy'],actions,source)
  self.other.fields['quantity'].setText('9');self.other._alternate_edits[self.other.alternate_key(source)]=[]
  added=self.w.paste_material(self.w.root_item.child(0),False)
  self.assertEqual([added.text(i) for i in (1,3,4)],['2.375','U1\nU2','真实备注\n第二行'])
  self.assertEqual(self.w.alternate_ids(added),[self.ids['A'],self.ids['B']]);self.assertEqual(added.childCount(),1)
  self.assertEqual(self.w.fields['quantity'].text(),'2.375');self.assertEqual(self.w.alt_table.rowCount(),2)
  self.assertEqual(self.s.bom(self.ids['S'])[0]['quantity'],1)
  with patch.object(QMessageBox,'information'):self.assertTrue(self.w.save())
  self.w.load();restored=next(self.w.root_item.child(i) for i in range(self.w.root_item.childCount()) if self.w.root_item.child(i).data(0,Qt.UserRole)['material_id']==self.ids['C'])
  self.assertEqual([restored.text(i) for i in (1,3,4)],['2.375','U1\nU2','真实备注\n第二行']);self.assertEqual(self.w.alternate_ids(restored),[self.ids['A'],self.ids['B']])
 def test_locked_and_deleted_context_copy_carries_relation(self):
  from ui.material_clipboard import clipboard_relation
  source=self.other.root_item.child(0);self.other.show_item_info(source)
  self.other.fields['quantity'].setText('4.25');self.other.fields['remark'].setText('保留备注');self.other._alternate_edits[self.other.alternate_key(source)]=[self.ids['A']]
  def choose(menu,*args):return next(a for a in menu.actions() if a.text()=='复制物料')
  for deleted in (False,True):
   if deleted:self.other.remove_relation(source)
   with patch.object(self.other,'is_locked',return_value=not deleted),patch.object(self.other.tree,'itemAt',return_value=source),patch.object(QMenu,'exec_',choose):self.other.context_menu(QPoint())
   relation=clipboard_relation(self.s);self.assertEqual(relation['quantity'],4.25);self.assertEqual(relation['alternate_material_ids'],[self.ids['A']])
   target=self.w.root_item.child(0 if not deleted else 1);added=self.w.paste_material(target,True)
   self.assertEqual(added.text(1),'4.25');self.assertEqual(added.text(4),'保留备注');self.assertEqual(self.w.alternate_ids(added),[self.ids['A']])
  self.other.copy_bom_material(self.other.root_item);self.assertIsNone(clipboard_relation(self.s))
 def test_multi_copy_original_order_attributes_and_batch_rejection(self):
  from ui.material_clipboard import clipboard_entries
  a,b=self.w.root_item.child(0),self.w.root_item.child(1)
  self.w.show_item_info(a);self.w.fields['quantity'].setText('2.5');self.w.fields['remark'].setText('A备注');self.w._alternate_edits[self.w.alternate_key(a)]=[self.ids['D']]
  self.w.tree.clearSelection();b.setSelected(True);a.setSelected(True)
  self.assertTrue(self.w.copy_bom_material(b));self.assertEqual([m['id'] for m,r in clipboard_entries(self.s)],[self.ids['A'],self.ids['B']])
  self.other.paste_material(self.other.root_item.child(0),False)
  self.assertEqual([self.other.root_item.child(i).data(0,Qt.UserRole)['material_id'] for i in range(3)],[self.ids[c] for c in ('C','A','B')])
  added=self.other.root_item.child(1);self.assertEqual(added.text(1),'2.5');self.assertEqual(added.text(4),'A备注');self.assertEqual(self.other.alternate_ids(added),[self.ids['D']])
  self.assertIsNone(self.other.paste_material(self.other.root_item,True));self.assertEqual(self.other.root_item.childCount(),3)
  with patch.object(QMessageBox,'information'):self.assertTrue(self.other.save())
  self.assertEqual([r['material_id'] for r in self.s.bom(self.ids['S']) if r['level_no']==1],[self.ids[c] for c in ('C','A','B')])
 def test_multi_cut_and_locked_copy_only(self):
  a,b=self.w.root_item.child(0),self.w.root_item.child(1);self.w.tree.clearSelection();a.setSelected(True);b.setSelected(True)
  with patch.object(self.w,'is_locked',return_value=True):
   actions=self.w.clipboard_actions(QMenu(self.w),a);self.assertEqual(set(actions),{'copy'});self.assertFalse(self.w.cut_material(a));self.assertTrue(self.w.copy_bom_material(a))
  self.assertTrue(self.w.cut_material(a));self.assertTrue(a.data(0,Qt.UserRole)['_deleted']);self.assertTrue(b.data(0,Qt.UserRole)['_deleted'])
  target=self.other.root_item.child(0);self.other.paste_material(target,True)
  self.assertEqual([target.child(i).data(0,Qt.UserRole)['material_id'] for i in range(3)],[self.ids[c] for c in ('D','A','B')])
 def test_ctrl_shift_same_parent_and_right_click_preserves_selection(self):
  from PyQt5.QtTest import QTest
  self.w.show();self.w.activateWindow();self.app.processEvents();tree=self.w.tree
  a,b=tree.topLevelItem(0).child(0),tree.topLevelItem(0).child(1)
  def click(node,mod=Qt.NoModifier):QTest.mouseClick(tree.viewport(),Qt.LeftButton,mod,tree.visualItemRect(node).center())
  click(a);click(b,Qt.ControlModifier);self.assertEqual(len(tree.selectedItems()),2)
  QTest.mouseClick(tree.viewport(),Qt.RightButton,Qt.NoModifier,tree.visualItemRect(a).center());self.assertEqual(len(tree.selectedItems()),2)
  click(a);click(b,Qt.ShiftModifier);self.assertEqual(len(tree.selectedItems()),2)
  click(self.w.root_item,Qt.ControlModifier);self.assertEqual(tree.selectedItems(),[self.w.root_item])
