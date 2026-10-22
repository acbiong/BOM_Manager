"""BOM同级排序、刷新缓存与保存回归。"""
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
from ui.main_window import BomWindow

class MoveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.ids={c:self.s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in 'RPQABC'}
  rel=lambda c,p:dict(material_id=self.ids[c],parent_material_id=self.ids[p],quantity=1,unit='pcs')
  self.s.save_bom(self.ids['R'],[rel('P','R'),rel('Q','R'),rel('P','Q'),rel('A','P'),rel('B','P'),rel('C','A')])
  self.w=BomWindow(self.s,self.ids['R']);self.app.clipboard().clear()
 def tearDown(self):
  self.w.dirty=False;self.w.close();self.db.close();self.tmp.cleanup()
 def order(self,item):return [item.child(i).data(0,Qt.UserRole)['material_id'] for i in range(item.childCount())]
 def test_move_shared_subtree_save_and_no_order_change_log(self):
  parent=self.w.root_item.child(0);item=parent.child(0);sub=item.child(0);item.setExpanded(True)
  self.assertFalse(self.w.can_move_item(item,-1));self.assertTrue(self.w.can_move_item(item,1))
  self.w.move_item(item,1)
  self.assertEqual(self.order(parent),[self.ids['B'],self.ids['A']]);self.assertIs(item.child(0),sub);self.assertTrue(item.isExpanded())
  self.assertEqual(self.order(self.w.root_item.child(1).child(0)),self.order(parent))
  self.assertEqual(item.background(0).color().name(),'#f8d7e3');self.assertIs(self.w.tree.currentItem(),item)
  self.assertFalse(self.w.can_move_item(item,1));self.assertTrue(self.w.save_action.isEnabled());self.assertFalse(self.w.export_action.isEnabled())
  before=self.db.conn.execute('SELECT count(*) FROM change_logs').fetchone()[0]
  self.assertEqual(self.s.bom(self.ids['P'])[0]['material_id'],self.ids['A'])
  with patch.object(QMessageBox,'information'):self.assertTrue(self.w.save())
  self.assertEqual(self.s.bom(self.ids['P'])[0]['material_id'],self.ids['B'])
  self.assertEqual(self.db.conn.execute('SELECT count(*) FROM change_logs').fetchone()[0],before)
  self.assertNotEqual(self.w.root_item.child(0).child(1).background(0).color().name(),'#f8d7e3')
 def test_refresh_preserves_order_marker_and_menu_boundaries(self):
  parent=self.w.root_item.child(0);item=parent.child(1)
  def menu_check(menu,*args):
   actions={a.text():a for a in menu.actions()}
   self.assertTrue(actions['物料上移'].isEnabled());self.assertFalse(actions['物料下移'].isEnabled())
  with patch.object(self.w.tree,'itemAt',return_value=item),patch.object(QMenu,'exec_',menu_check):self.w.context_menu(QPoint())
  self.w.move_item(item,-1)
  self.s.update_material(self.ids['A'],dict(name='新名称',unit='pcs'))
  self.w.refresh_external();parent=self.w.root_item.child(0)
  self.assertEqual(self.order(parent),[self.ids['B'],self.ids['A']]);self.assertEqual(parent.child(0).background(0).color().name(),'#f8d7e3')
  self.assertFalse(self.w.can_move_item(self.w.root_item,1))
  self.assertFalse(self.w.can_move_item(parent.child(0),-1))
