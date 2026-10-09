import os,sys,tempfile,unittest,sqlite3
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from infrastructure.events import WindowRefreshBus
from PyQt5.QtWidgets import QApplication,QDialog,QInputDialog
from PyQt5.QtCore import Qt
from ui.main_window import MaterialVersionDialog,MaterialWindow,BomWindow

class MaterialVersionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.db=Database(str(Path(self.tmp.name)/'versions.db')); self.s=Services(self.db)
  self.ids={name:self.s.create_material(dict(base_code=name,version='100',name=name+'名称',unit='pcs',description='描述',manufacturer='制造商',mpn='MPN',mp_flag='P')) for name in ['SKU1','SKU2','P1','P2','PART','LEAF']}
  a=self.ids
  for parent,children in [('SKU1',['P1','P2']),('SKU2',['P1']),('P1',['PART']),('P2',['PART']),('PART',['LEAF'])]:
   self.s.save_bom(a[parent],[dict(material_id=a[c],quantity=2.3,unit='pcs',position='A',remark='备注') for c in children])
  self.s.create_sku(a['SKU1']); self.s.create_sku(a['SKU2'])
 def tearDown(self): self.db.close(); self.tmp.cleanup()
 def material(self,i):return dict(self.db.conn.execute('SELECT * FROM materials WHERE id=?',(i,)).fetchone())
 def test_references_include_all_shared_skus_and_independent_boms(self):
  a=self.ids; refs={r['parent_id']:r for r in self.s.material_version_references(a['PART'])}
  self.assertEqual(len(refs[a['P1']]['labels']),2)
  self.assertIn('SKU1100 SKU1名称/P1100 P1名称',refs[a['P1']]['labels'])
  self.assertIn('SKU2100 SKU2名称/P1100 P1名称',refs[a['P1']]['labels'])
  self.assertEqual(len(refs[a['P2']]['labels']),1)
  self.s.create_material(dict(base_code='UNUSED',version='1',name='未使用',unit='pcs'))
 def test_all_selected_updates_original_without_duplicate(self):
  a=self.ids; before=len(self.s.materials()); old_relation_ids=[r['id'] for r in self.s.bom(a['SKU1'])]
  result=self.s.change_material_version(a['PART'],'101',{a['P1'],a['P2']})
  self.assertEqual(result,a['PART']); self.assertEqual(len(self.s.materials()),before)
  self.assertEqual(self.material(result)['version'],'101')
  self.assertEqual(old_relation_ids,[r['id'] for r in self.s.bom(a['SKU1'])])
 def test_partial_selection_preserves_old_and_copies_bom(self):
  a=self.ids; original=self.material(a['PART']); edge=self.s.bom(a['PART'])[0]['id']; self.s.add_alternate(edge,a['P2'])
  result=self.s.change_material_version(a['PART'],'101',{a['P1']})
  self.assertNotEqual(result,a['PART']); self.assertEqual(self.material(a['PART']),original)
  self.assertEqual(self.s.bom(a['P1'])[0]['material_id'],result)
  self.assertEqual(self.s.bom(a['P2'])[0]['material_id'],a['PART'])
  relation=self.s.bom(a['P1'])[0]; self.assertEqual((relation['quantity'],relation['position'],relation['remark']),(2.3,'A','备注'))
  self.assertEqual(self.s.bom(result)[0]['material_id'],a['LEAF'])
  self.assertEqual(self.s.alternates(self.s.bom(result)[0]['id'])[0]['material_id'],a['P2'])
  for field in ['base_code','name','description','unit','manufacturer','mpn','mp_flag']: self.assertEqual(self.material(result)[field],original[field])
 def test_none_selected_creates_unused_new_version(self):
  a=self.ids; result=self.s.change_material_version(a['PART'],'101',set())
  self.assertNotEqual(result,a['PART']); self.assertEqual(self.material(a['PART'])['version'],'100')
  self.assertEqual(self.s.bom(a['P1'])[0]['material_id'],a['PART'])
  self.assertEqual({r['id']:r['idle'] for r in self.s.materials()}[result],'Y')
 def test_unused_material_changes_in_place(self):
  i=self.s.create_material(dict(base_code='NEW',version='100',name='新物料',unit='pcs'))
  self.assertEqual(self.s.material_version_references(i),[])
  self.assertEqual(self.s.change_material_version(i,'101',set()),i)
 def test_validation_and_write_failure_roll_back(self):
  a=self.ids; old=list(self.db.conn.execute('SELECT * FROM materials'))
  for version,selected,expected in [('',set(),None),('100',set(),None),('101',{999},None),('101',set(),set())]:
   with self.assertRaises(ValueError):self.s.change_material_version(a['PART'],version,selected,expected)
  self.db.conn.execute("CREATE TEMP TRIGGER stop_version BEFORE UPDATE OF child_material_id ON material_bom_items BEGIN SELECT RAISE(ABORT,'failure'); END")
  with self.assertRaises(sqlite3.IntegrityError):self.s.change_material_version(a['PART'],'101',{a['P1']})
  self.assertEqual(old,list(self.db.conn.execute('SELECT * FROM materials')))
  self.assertEqual(self.s.bom(a['P1'])[0]['material_id'],a['PART'])
 def test_dialog_selection_and_affected_windows(self):
  a=self.ids; refs=self.s.material_version_references(a['PART']); dialog=MaterialVersionDialog(self.material(a['PART']),refs)
  self.assertEqual(dialog.selected_parents(),{a['P1'],a['P2']})
  for n in range(dialog.references.topLevelItemCount()):
   item=dialog.references.topLevelItem(n)
   if item.data(0,Qt.UserRole)==a['P2']:item.setCheckState(0,Qt.Unchecked)
  self.assertEqual(dialog.selected_parents(),{a['P1']})
  dialog.version.setText('101')
  windows=[BomWindow(self.s,a['SKU1']),BomWindow(self.s,a['SKU2']),BomWindow(self.s,a['P2'])]; material_window=MaterialWindow(self.s)
  try:
   with patch('ui.main_window.MaterialVersionDialog',return_value=dialog),patch.object(dialog,'exec_',return_value=QDialog.Accepted): material_window.change_version(a['PART'])
   self.assertTrue(windows[0].refresh_action.isEnabled()); self.assertTrue(windows[1].refresh_action.isEnabled()); self.assertFalse(windows[2].refresh_action.isEnabled())
   windows[1].refresh_external(); self.assertIn('101',[r['version'] for r in self.s.bom(a['SKU2']) if r['base_code']=='PART'])
  finally:
   for window in windows:window.close()
   material_window.close(); dialog.close()
 def test_cancel_version_dialog_makes_no_changes(self):
  a=self.ids; window=MaterialWindow(self.s)
  try:
   with patch('ui.main_window.MaterialVersionDialog') as dialog:
    dialog.return_value.exec_.return_value=QDialog.Rejected; window.change_version(a['PART'])
   self.assertEqual(self.material(a['PART'])['version'],'100'); self.assertEqual(len(self.s.materials()),6)
  finally:window.close()
 def test_independent_bom_is_listed_and_preserves_old_version(self):
  a=self.ids; parent=self.s.create_material(dict(base_code='INDEPENDENT',version='100',name='独立BOM',unit='pcs'))
  self.s.save_bom(parent,[dict(material_id=a['PART'],quantity=1,unit='pcs')])
  refs={r['parent_id']:r for r in self.s.material_version_references(a['PART'])}
  self.assertEqual(refs[parent]['labels'],['未包含在SKU中/INDEPENDENT100 独立BOM'])
  new=self.s.change_material_version(a['PART'],'101',{a['P1'],a['P2']})
  self.assertNotEqual(new,a['PART']); self.assertEqual(self.s.bom(parent)[0]['material_id'],a['PART'])
 def test_unused_ui_only_requests_version(self):
  i=self.s.create_material(dict(base_code='UNUSED',version='100',name='无引用',unit='pcs')); window=MaterialWindow(self.s)
  try:
   with patch.object(QInputDialog,'getText',return_value=('101',True)) as simple,patch('ui.main_window.MaterialVersionDialog') as references:
    window.change_version(i); simple.assert_called_once(); references.assert_not_called()
   self.assertEqual(self.material(i)['version'],'101')
  finally:window.close()
 def test_version_dialog_three_columns_checkbox_left(self):
  a=self.ids; dialog=MaterialVersionDialog(self.material(a['PART']),self.s.material_version_references(a['PART']))
  try:
   self.assertEqual(dialog.references.columnCount(),3)
   self.assertFalse(dialog.references.rootIsDecorated())
   item=dialog.references.topLevelItem(0)
   self.assertEqual(item.checkState(0),Qt.Checked)
   self.assertEqual(item.text(0),''); self.assertIn('SKU1100 SKU1名称',item.text(1)); self.assertIn('SKU2100 SKU2名称',item.text(1))
   self.assertEqual(item.text(2),'P1100 P1名称')
   self.assertEqual([dialog.references.headerItem().text(n) for n in range(3)],['','SKU','父项物料'])
   self.assertLess(dialog.note.font().pointSizeF(),dialog.font().pointSizeF())
   self.assertGreater(dialog.layout().indexOf(dialog.note),dialog.layout().indexOf(dialog.references))
  finally:dialog.close()
 def test_reverse_lookup_two_lines_and_independent_parent(self):
  from ui.main_window import MaterialUsageDialog
  a=self.ids; parent=self.s.create_material(dict(base_code='LOOSE',version='1',name='独立',unit='pcs'))
  self.s.save_bom(parent,[dict(material_id=a['PART'],quantity=1,unit='pcs')])
  usages=self.s.material_usage(a['PART'])
  self.assertEqual(len(usages),4)
  self.assertIn({'sku_id':None,'sku':'未包含在SKU中','parent':'LOOSE1 独立'},usages)
  dialog=MaterialUsageDialog(self.material(a['PART']),usages)
  try:
   for i,usage in enumerate(usages):
    self.assertEqual(dialog.table.item(i,0).text().splitlines(),['SKU：'+usage['sku'],'父级物料：'+usage['parent']])
  finally:dialog.close()
 def test_nonidle_context_delete_disabled_and_lookup_opens(self):
  from PyQt5.QtWidgets import QMenu
  from PyQt5.QtCore import QPoint
  a=self.ids; window=MaterialWindow(self.s)
  try:
   def capture(menu,pos):
    actions={action.text():action for action in menu.actions()}
    self.assertFalse(actions['删除物料'].isEnabled()); self.assertIn('物料反查',actions)
    return actions['物料反查']
   row=next(n for n,r in enumerate(self.s.materials()) if r['id']==a['PART'])
   with patch.object(window.t,'rowAt',return_value=row),patch.object(QMenu,'exec_',capture),patch('ui.main_window.MaterialUsageDialog') as usage:
    window.menu(QPoint()); usage.return_value.exec_.assert_called_once()
   with self.assertRaises(ValueError):self.s.delete_material(a['PART'])
   with self.assertRaises(ValueError):self.s.delete_material(a['SKU1'])
   unused=self.s.create_material(dict(base_code='FREE',version='1',name='未使用',unit='pcs'))
   row=next(n for n,r in enumerate(self.s.materials()) if r['id']==unused)
   def capture_idle(menu,pos):
    actions={action.text():action for action in menu.actions()}
    self.assertTrue(actions['删除物料'].isEnabled()); self.assertNotIn('物料反查',actions)
    return None
   with patch.object(window.t,'rowAt',return_value=row),patch.object(QMenu,'exec_',capture_idle):window.menu(QPoint())
  finally:window.close()
 def test_reverse_double_click_reuses_sku_window(self):
  from ui.main_window import MainWindow,MaterialUsageDialog
  a=self.ids; main=MainWindow(self.s); main.show_materials()
  def dialog():return MaterialUsageDialog(self.material(a['PART']),self.s.material_usage(a['PART']),main._materials)
  try:
   first=dialog(); sid=first.table.item(0,0).data(Qt.UserRole)
   first.table.cellDoubleClicked.emit(0,0)
   self.assertEqual(first.result(),QDialog.Accepted); self.assertEqual(len(main._bom_windows),1)
   original=main._bom_windows[sid]; original.show_item_info(original.root_item.child(0)); original.fields['quantity'].setValue(7.3); original.showMinimized()
   second=dialog(); second.table.cellDoubleClicked.emit(0,0)
   self.assertIs(main._bom_windows[sid],original); self.assertEqual(len(main._bom_windows),1)
   self.assertFalse(original.isMinimized()); self.assertEqual(original.root_item.child(0).text(1),'7.3')
   independent=MaterialUsageDialog(self.material(a['PART']),[{'sku_id':None,'sku':'未包含在SKU中','parent':'独立'}],main._materials)
   with patch('ui.main_window.QMessageBox.information') as info:
    independent.table.cellDoubleClicked.emit(0,0); info.assert_called_once()
   self.assertEqual(len(main._bom_windows),1); independent.close()
  finally:
   for window in list(main._bom_windows.values()): window.dirty=False; window.close()
   main._materials.close(); main.close()
 def test_sku_version_menu_disabled_only_in_material_library(self):
  from PyQt5.QtWidgets import QMenu
  from PyQt5.QtCore import QPoint
  window=MaterialWindow(self.s)
  try:
   for name,enabled in [('SKU1',False),('PART',True)]:
    row=next(n for n,m in enumerate(self.s.materials()) if m['id']==self.ids[name])
    def inspect(menu,pos):
     action=next(a for a in menu.actions() if a.text()=='物料版本变更'); self.assertEqual(action.isEnabled(),enabled); return None
    with patch.object(window.t,'rowAt',return_value=row),patch.object(QMenu,'exec_',inspect):window.menu(QPoint())
   with patch.object(QInputDialog,'getText') as text,patch('ui.main_window.QMessageBox.information') as message:
    window.change_version(self.ids['SKU1']); text.assert_not_called(); message.assert_called_once()
  finally:window.close()
