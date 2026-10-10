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
  self.assertTrue(added.data(0,Qt.UserRole)['_added']);self.assertTrue(added.child(0).data(0,Qt.UserRole)['_added']);self.assertEqual(added.text(1),'1.0');self.assertIs(self.w.tree.currentItem(),added)
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
