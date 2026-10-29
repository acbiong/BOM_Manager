import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QPoint
from PyQt5.QtWidgets import QApplication,QMenu,QDialog
from openpyxl import Workbook,load_workbook
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow,MaterialWindow,MaterialUsageDialog

class HistoryWordingMenuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.root,self.part,self.alt=[self.s.create_material(dict(base_code=c,version='100',name=c,unit='pcs')) for c in ('ROOT','PART','ALT')]
  self.sid=self.s.create_sku(self.root);self.s.save_bom(self.root,[dict(material_id=self.part,quantity=1,unit='pcs')])
  from services.snapshot_bom import migrate
  from services.current_catalog import initialize
  migrate(self.db);initialize(self.db)
  self.other=self.s.copy_sku_bom(self.sid);self.main=MainWindow(self.s);self.window=self.main.open_bom_id(self.sid)
 def tearDown(self):
  if self.main._materials:self.main._materials.close()
  for w in list(self.main._bom_windows.values()):w.dirty=False;w.close()
  self.main.close();self.db.close();self.tmp.cleanup()
 def menu_groups(self,menu):
  groups=[[]]
  for a in menu.actions():
   if a.isSeparator():
    self.assertTrue(groups[-1]);groups.append([])
   else:groups[-1].append(a.text())
  self.assertTrue(groups[-1]);return groups
 def test_tree_reverse_uses_all_saved_versions_and_reuses_editor(self):
  window=self.window;child=window.root_item.child(0);seen=[]
  def choose(menu,pos):
   groups=self.menu_groups(menu);self.assertEqual(groups[0],['编辑此物料','物料反查']);self.assertEqual(groups[-1],['删除物料'])
   self.assertIn(['物料上移','物料下移'],groups)
   return next(a for a in menu.actions() if a.text()=='物料反查')
  def inspect(dialog):
   self.assertIs(dialog.parent(),window);self.assertEqual(dialog.material_id,self.part)
   self.assertEqual({u['sku_id'] for u in dialog.usages},{self.sid,self.other})
   self.assertTrue(all('历史版本' in u['sku'] and '镜像' not in u['sku'] for u in dialog.usages))
   row=next(i for i,u in enumerate(dialog.usages) if u['sku_id']==self.sid)
   before=len(self.main._bom_windows);dialog.open_sku(row);self.assertEqual(len(self.main._bom_windows),before)
   self.assertEqual(window.tree.currentItem().data(0,Qt.UserRole)['material_id'],self.part);seen.append(True)
   return QDialog.Accepted
  with patch.object(window.tree,'itemAt',return_value=child),patch.object(QMenu,'exec_',choose),patch.object(MaterialUsageDialog,'exec_',inspect):window.context_menu(QPoint())
  self.assertEqual(seen,[True])
 def test_root_and_deleted_node_keep_safe_menu_and_reverse(self):
  for node,deleted in ((self.window.root_item,False),(self.window.root_item.child(0),True)):
   if deleted:self.window.remove_relation(node)
   def choose(menu,pos):
    groups=self.menu_groups(menu);labels=[a.text() for a in menu.actions() if not a.isSeparator()]
    self.assertIn('物料反查',labels);self.assertNotIn('删除物料',labels)
    if deleted:self.assertEqual(groups,[['取消删除'],['复制物料'],['物料反查']])
    else:self.assertIn('新增子级物料',labels)
    return next(a for a in menu.actions() if a.text()=='物料反查')
   with patch.object(self.window.tree,'itemAt',return_value=node),patch.object(QMenu,'exec_',choose),patch.object(MaterialUsageDialog,'exec_',return_value=QDialog.Rejected) as dialog:self.window.context_menu(QPoint());dialog.assert_called_once()
 def test_sku_material_and_alternate_menus_group_dangerous_operations_last(self):
  captured=[]
  def capture(menu,pos):captured.append(self.menu_groups(menu));return None
  with patch.object(QMenu,'exec_',capture),patch.object(self.main.table,'rowAt',return_value=0):self.main.sku_context_menu(QPoint())
  self.assertIn('历史版本变更',captured[-1][0]);self.assertEqual(captured[-1][-2],['导出BOM','采购BOM导出']);self.assertEqual(captured[-1][-1],['删除SKU'])
  self.main.show_materials();library=self.main._materials;row=next(i for i,m in enumerate(self.s.materials()) if m['id']==self.part)
  with patch.object(QMenu,'exec_',capture),patch.object(library.t,'rowAt',return_value=row):library.menu(QPoint())
  self.assertEqual(captured[-1][-3],['类似新增物料','复制物料']);self.assertEqual(captured[-1][-2],['复制物料编码','复制物料名称']);self.assertEqual(captured[-1][-1],['删除物料']);self.assertIn('物料反查',sum(captured[-1],[]))
 def test_legacy_export_wording_converted_without_rewriting_stored_history(self):
  scoped=self.s.for_sku(self.other)
  with self.db.transaction():
   scoped.log('sku',self.other,'copy','复制BOM；源镜像版本：100；新镜像版本：101')
   scoped.log('sku',self.other,'mirror_version','镜像版本号：101 → 102')
   scoped.log('bom',self.root,'update','物料：PART100 PART\n增加替代料：ALT100 ALT')
  records=list(scoped.db.conn.execute('SELECT * FROM change_logs ORDER BY id'));before=[r['detail'] for r in records]
  path=Path(self.tmp.name)/'history.xlsx';self.s.export_sku(self.other,path);wb=load_workbook(path)
  try:
   text='\n'.join(str(c.value or '') for row in wb['变更记录'] for c in row)
   self.assertNotIn('镜像',text);self.assertNotIn('增加替代料',text)
   self.assertIn('源历史版本：100',text);self.assertIn('历史版本变更',text);self.assertIn('新增替代料：ALT100 ALT',text)
  finally:wb.close()
  self.assertEqual([r['detail'] for r in scoped.db.conn.execute('SELECT * FROM change_logs ORDER BY id')],before)
  self.s.change_mirror_version(self.other,103)
  self.assertIn('历史版本号',scoped.db.conn.execute("SELECT detail FROM change_logs WHERE action='mirror_version' ORDER BY id DESC LIMIT 1").fetchone()[0])
 def test_visible_titles_and_new_alternate_label(self):
  self.assertIn('历史版本',self.window.windowTitle());self.assertNotIn('镜像',self.window.windowTitle())
  from ui.main_window import MaterialHeaderMappingDialog
  from PyQt5.QtWidgets import QPushButton
  dialog=MaterialHeaderMappingDialog('missing.xlsx',['编码'],[],required=['编码'])
  try:self.assertIn('新增替代料',[b.text() for b in dialog.findChildren(QPushButton)])
  finally:dialog.close()
