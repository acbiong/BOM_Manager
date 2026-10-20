"""BOM跨窗口复制、插入顺序和安全校验回归。"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMenu,QMessageBox
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
 def test_delete_key_enter_cancel_and_text_edit_focus(self):
  from PyQt5.QtTest import QTest
  from PyQt5.QtCore import QTimer
  self.w.show();self.w.activateWindow();item=self.w.root_item.child(0);self.w.tree.setCurrentItem(item);self.w.tree.setFocus();self.app.processEvents()
  with patch.object(QMessageBox,'question',return_value=QMessageBox.No) as question:
   QTest.keyClick(self.w.tree,Qt.Key_Delete);self.assertEqual(question.call_count,1)
  self.assertFalse(item.data(0,Qt.UserRole).get('_deleted',False))
  def confirm():
   box=self.app.activeModalWidget()
   if box is not None:QTest.keyClick(box,Qt.Key_Return)
  QTimer.singleShot(30,confirm);QTest.keyClick(self.w.tree,Qt.Key_Delete)
  self.assertTrue(item.data(0,Qt.UserRole)['_deleted'])
  other=self.w.root_item.child(1);self.w.tree.setCurrentItem(other);self.w.show_item_info(other)
  field=self.w.fields['position'];field.setFocus();self.app.processEvents()
  with patch.object(QMessageBox,'question') as question:
   QTest.keyClick(field,Qt.Key_Delete);question.assert_not_called()
