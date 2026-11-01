import os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMenu,QDialog
from PyQt5.QtCore import Qt,QPoint
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from ui.sku_ecn import EcnDialog
from ui.bom_compare import BomCompareDialog


class EcnCompareUiTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.temp.name)/'db'));self.s=Services(self.db)
  self.root=self.s.create_material(dict(base_code='R',version='100',name='root',unit='pcs'));self.sid=self.s.create_sku(self.root);self.w=MainWindow(self.s)
 def tearDown(self):self.w.close();self.db.close();self.temp.cleanup()
 def test_copy_local_external_and_empty_compare_cell(self):
  dialog=BomCompareDialog(self.s)
  try:
   table=dialog.tables[0];table.setRowCount(1)
   for external in (False,True):
    node=dict(base_code='ABC-',version='101',name='名称 <原文>',_external=external)
    dialog._rows=[SimpleNamespace(left=node,right=None)]
    for label,expected in [('复制物料编码','ABC-101'),('复制物料名称','名称 <原文>')]:
     def choose(menu,*_):
      actions={a.text():a for a in menu.actions()};self.assertEqual('打开BOM进行编辑' in actions,not external);return actions[label]
     with patch.object(QMenu,'exec_',choose):dialog.context_menu(table,table.model().index(0,0),QPoint())
     self.assertEqual(self.app.clipboard().text(),expected)
   dialog._rows=[SimpleNamespace(left=None,right=None)]
   with patch.object(QMenu,'exec_') as menu:dialog.context_menu(table,table.model().index(0,0),QPoint());menu.assert_not_called()
  finally:dialog.close()
 def test_ecn_edit_does_not_reload_or_discard_dirty_bom(self):
  bom=self.w.open_bom_id(self.sid);bom.mark_dirty();before=bom.history_rows()
  try:
   def edit(dialog):dialog.number.setText('E1');dialog.editor.setPlainText('改动');return QDialog.Accepted
   with patch.object(bom,'load') as load,patch.object(EcnDialog,'exec_',edit):self.w.sku_double_clicked(0,8);self.app.processEvents();load.assert_not_called()
   self.assertTrue(bom.dirty);self.assertEqual(bom.history_rows(),before)
   with patch.object(QMenu,'exec_',lambda menu,*_:self.assertNotIn('编辑变更描述',[a.text() for a in menu.actions()])):
    self.w.sku_context_menu(self.w.table.visualItemRect(self.w.table.item(0,1)).center())
  finally:bom.dirty=False;bom.close()
 def test_locked_ecn_is_readonly(self):
  self.s.set_sku_locked(self.sid,True)
  def inspect(dialog):
   self.assertTrue(dialog.number.isReadOnly());self.assertTrue(dialog.editor.isReadOnly());return QDialog.Rejected
  with patch.object(EcnDialog,'exec_',inspect),patch.object(self.s,'update_sku_ecn') as save:
   self.w.sku_double_clicked(0,8);save.assert_not_called()
