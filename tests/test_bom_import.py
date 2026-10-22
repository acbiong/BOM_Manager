import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from openpyxl import Workbook
from database.database import Database
from services.services import Services,MaterialHeaderError
from ui.main_window import MaterialHeaderMappingDialog
from PyQt5.QtWidgets import QApplication
class BomImportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'bom.xlsx';self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.ids={key:self.s.create_material(dict(base_code=key[0],version=key[1],name=str(key),unit='pcs')) for key in [('R','1'),('P','1'),('P','2'),('C','1')]}
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def write(self,rows,headers=None):
  wb=Workbook();wb.active.title='说明';wb.active.append(['BOM']);ws=wb.create_sheet('BOM');ws.append(headers or self.s.BOM_HEADERS)
  for row in rows:ws.append(row)
  wb.save(self.path);wb.close()
 def test_selected_sheet_mapping_unordered_tree_and_versions(self):
  headers=['父编码','父版本','子编码','子版本','用量','安装位置']
  self.write([['P','2','C','1',2.34,'x'],['R','1','P','2',1,'']],headers)
  with self.assertRaises(MaterialHeaderError) as error:self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM')
  dialog=MaterialHeaderMappingDialog(self.path,error.exception.headers,error.exception.missing,sheet_name='BOM',required=self.s.BOM_HEADERS)
  self.assertEqual(dialog.preview.item(0,0).text(),'P');self.assertEqual(dialog.mapping_table.columnCount(),6)
  mapping=dict(zip(self.s.BOM_HEADERS,headers));self.assertEqual(self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM',header_mapping=mapping),2)
  rows=self.s.bom(self.ids['R','1']);self.assertEqual([(r['material_id'],r['level_no']) for r in rows],[(self.ids['P','2'],1),(self.ids['C','1'],2)]);self.assertEqual(rows[1]['quantity'],2.34);self.assertEqual(self.s.bom(self.ids['P','1']),[]);dialog.close()
 def test_validation_failure_never_partially_writes(self):
  valid=['R','1','P','2',1,'']
  bad_rows=[['P','2','R','1',1,''],['R','1','P','2',2,'different'],['P','1','C','1',1,''],['P','9','C','1',1,''],['P','2','C','1','nan',''],['P','2','P','2',1,'']]
  for bad in bad_rows:
   with self.subTest(bad=bad):
    self.write([valid,bad]);before=list(self.db.conn.execute('SELECT * FROM material_bom_items'))
    with self.assertRaises(ValueError):self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM')
    self.assertEqual(list(self.db.conn.execute('SELECT * FROM material_bom_items')),before)
 def test_existing_shared_cycle_checked_and_root_inferred(self):
  self.s.save_bom(self.ids['C','1'],[dict(material_id=self.ids['R','1'],quantity=1,unit='pcs')])
  self.write([['R','1','C','1',1,'']])
  with self.assertRaises(ValueError):self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM')
  self.assertEqual(self.s.bom(self.ids['R','1']),[])
  self.write([['R','1','P','2',1,'']]);self.s.import_bom(self.path,sheet_name='BOM');self.assertEqual(self.s.bom(self.ids['R','1'])[0]['material_id'],self.ids['P','2'])
 def test_root_marker_case_and_mapping(self):
  headers=['父编码','父版本','子编码','子版本','用量','安装位置']
  for marker in ('ROOT','root','Root'):
   self.write([['R','1','P','2',1,''],[marker,marker,'R','1',None,None]],headers)
   self.assertEqual(self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM',header_mapping=dict(zip(self.s.BOM_HEADERS,headers))),1)
   self.assertEqual(len(self.s.bom(self.ids['R','1'])),1)
 def test_root_mismatch_before_any_write_and_ui_warning(self):
  from unittest.mock import patch
  from PyQt5.QtWidgets import QFileDialog,QInputDialog,QMessageBox
  from ui.interactive_windows import QFileDialog,QInputDialog,QMessageBox
  from ui.main_window import BomWindow,BomImportIssuesDialog
  self.s.save_bom(self.ids['R','1'],[dict(material_id=self.ids['C','1'],quantity=5,unit='pcs')])
  before=[dict(row) for row in self.s.bom(self.ids['R','1'])]
  for code,version in [('P','1'),('R','2')]:
   self.write([['R','1','P','2',1,''],['root','ROOT',code,version,None,None]])
   with self.assertRaisesRegex(ValueError,'BOM选择错误'):self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM')
   self.assertEqual([dict(row) for row in self.s.bom(self.ids['R','1'])],before)
  window=BomWindow(self.s,self.ids['R','1']);shown=[]
  try:
   with patch.object(MaterialHeaderMappingDialog,'exec_',return_value=1),patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.path),'')),patch.object(QInputDialog,'getItem',return_value=('BOM',True)),patch.object(BomImportIssuesDialog,'exec_',lambda dialog: shown.append(dialog)):
    window.import_bom();self.assertIn('BOM选择错误',shown[0].details.toPlainText())
  finally:window.close()
 def test_duplicate_incomplete_and_root_only(self):
  for rows in ([['ROOT','1','R','1',1,'']],[['ROOT','ROOT','R','1',1,''],['root','root','R','1',1,'']]):
   self.write(rows)
   with self.assertRaises(ValueError):self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM')
  self.s.save_bom(self.ids['R','1'],[dict(material_id=self.ids['C','1'],quantity=1,unit='pcs')])
  self.write([['ROOT','root','R','1',None,None]])
  self.assertEqual(self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM'),0);self.assertEqual(self.s.bom(self.ids['R','1']),[])

 def test_blank_headers_ignored_and_cannot_be_mapped(self):
  headers=['',*self.s.BOM_HEADERS,'   ',None]
  self.write([['ignored','R','1','P','2',1,'x','ignored','ignored']],headers)
  nodes=self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM',persist=False)
  self.assertEqual(nodes[0]['data']['material_id'],self.ids['P','2'])
  self.assertEqual(self.s.bom(self.ids['R','1']),[])
  mapping={field:field for field in self.s.BOM_HEADERS};mapping['位置']=''
  with self.assertRaises(MaterialHeaderError):self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM',header_mapping=mapping,persist=False)
  dialog=MaterialHeaderMappingDialog(self.path,['',*self.s.BOM_HEADERS,'',''],['位置'],sheet_name='BOM',required=self.s.BOM_HEADERS)
  self.assertTrue(dialog.preview.isColumnHidden(0))
  self.assertEqual(dialog.combos['位置'].count(),7);dialog.close()
 def test_ui_import_is_cached_until_save_and_discard_does_not_write(self):
  from unittest.mock import patch
  from PyQt5.QtWidgets import QFileDialog,QInputDialog,QMessageBox
  from ui.interactive_windows import QFileDialog,QInputDialog,QMessageBox
  from PyQt5.QtCore import Qt
  from ui.main_window import BomWindow,BomTreeWidget,BomImportConflictDialog
  root=self.ids['R','1'];old=self.ids['C','1'];new=self.ids['P','2']
  self.s.save_bom(root,[dict(material_id=old,quantity=5,unit='pcs')])
  self.write([['ROOT','ROOT','R','1',None,None],['R','1','P','2',2.3,'new']])
  before=[tuple(r) for r in self.db.conn.execute('SELECT * FROM material_bom_items')]
  for save in (False,True):
   window=BomWindow(self.s,root)
   try:
    with patch.object(MaterialHeaderMappingDialog,'exec_',return_value=1),patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.path),'')),patch.object(QInputDialog,'getItem',return_value=('BOM',True)),patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning') as warning,patch.object(BomImportConflictDialog,'exec_',lambda dialog:dialog.finish('incoming')):
     window.import_bom();warning.assert_not_called()
     self.assertTrue(window.dirty);self.assertTrue(window.save_action.isEnabled())
     self.assertEqual([tuple(r) for r in self.db.conn.execute('SELECT * FROM material_bom_items')],before)
     self.assertEqual(window.root_item.childCount(),2)
     self.assertTrue(window.root_item.child(0).data(0,Qt.UserRole)['_added'])
     self.assertTrue(window.root_item.child(1).data(0,Qt.UserRole)['_deleted'])
     self.assertIsInstance(window.tree,BomTreeWidget)
     window.show();self.app.processEvents();self.assertFalse(window.tree.grab().isNull())
     if save:
      self.assertTrue(window.save());rows=self.s.bom(root)
      self.assertEqual([(r['material_id'],r['quantity']) for r in rows],[(new,2.3)])
      self.assertFalse(window.dirty);self.assertEqual(window.root_item.childCount(),1)
   finally:window.dirty=False;window.close()
 def test_preview_rejects_shared_cycles_without_writes(self):
  self.s.save_bom(self.ids['C','1'],[dict(material_id=self.ids['R','1'],quantity=1,unit='pcs')])
  self.write([['R','1','C','1',1,'']])
  with self.assertRaisesRegex(ValueError,'循环'):self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM',persist=False)
  self.assertEqual(self.s.bom(self.ids['R','1']),[])

 def test_all_rows_and_multiple_errors_per_row_are_reported(self):
  from services.services import BomImportError
  self.write([
   ['ROOT','ROOT','P','1',None,None],
   ['MISSING','9','UNKNOWN','2','bad',''],
   ['R','1','P','2',1,''],
   ['R','1','P','2',2,'duplicate'],
   ['P','2','P','2',0,''],
   ['P','1','C','1',1,''],
   ['R','1','','',None,''],
  ])
  before=self.db.conn.total_changes
  for persist in (False,True):
   with self.assertRaises(BomImportError) as result:self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM',persist=persist)
   message=str(result.exception)
   for expected in ['第2行ROOT','第3行父项不存在','第3行子物料不存在','第3行数量不是','第5行同一父级重复','第6行物料不能','第6行数量必须','第7行存在','第8行必填项缺失','循环包含']:
    self.assertIn(expected,message)
   self.assertIn('物料基础编码、物料版本号、物料数量',message)
   self.assertEqual(self.db.conn.total_changes,before)
 def test_error_dialog_preserves_unsaved_cache_and_scrolls(self):
  from unittest.mock import patch
  from PyQt5.QtWidgets import QFileDialog,QInputDialog,QMessageBox
  from ui.interactive_windows import QFileDialog,QInputDialog,QMessageBox
  from ui.main_window import BomWindow,BomImportIssuesDialog
  self.s.save_bom(self.ids['R','1'],[dict(material_id=self.ids['C','1'],quantity=1,unit='pcs')])
  window=BomWindow(self.s,self.ids['R','1']);shown=[]
  try:
   window.show_item_info(window.root_item.child(0));window.fields['quantity'].setValue(3.2)
   original=window.capture_tree()
   self.write([['R','1','UNKNOWN',str(i),'invalid',''] for i in range(70)])
   with patch.object(MaterialHeaderMappingDialog,'exec_',return_value=1),patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.path),'')),patch.object(QInputDialog,'getItem',return_value=('BOM',True)),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(BomImportIssuesDialog,'exec_',lambda dialog: shown.append(dialog)):
    window.import_bom()
    dialog=shown[0];dialog.show();self.app.processEvents()
    self.assertIn('第71行',dialog.details.toPlainText())
    self.assertGreater(dialog.details.verticalScrollBar().maximum(),0);dialog.close()
   self.assertEqual(window.capture_tree(),original);self.assertTrue(window.dirty)
   self.assertEqual(self.s.bom(self.ids['R','1'])[0]['quantity'],1)
  finally:window.dirty=False;window.close()
 def test_combined_code_preserves_base_code_hyphens(self):
  from ui.main_window import BomWindow,NewSkuDialog
  mid=self.s.create_material(dict(base_code='BC3-0000197',version='100',name='测试',unit='pcs'))
  window=BomWindow(self.s,mid)
  try:
   self.assertEqual(window.windowTitle(),'BC3-0000197100 测试')
   self.assertEqual(window.root_item.text(0),'BC3-0000197100 测试')
  finally:window.close()

 def test_alternate_mapping_groups_cache_save_and_clear(self):
  from ui.main_window import BomWindow
  from PyQt5.QtWidgets import QMessageBox
  from ui.interactive_windows import QMessageBox
  from unittest.mock import patch
  root=self.ids['R','1'];child=self.ids['P','2'];alt=self.ids['C','1']
  headers=self.s.BOM_HEADERS+['替代编码','替代版本']
  self.write([['R','1','P','2',1,'','C','1']],headers)
  dialog=MaterialHeaderMappingDialog(self.path,headers,[],sheet_name='BOM',required=self.s.BOM_HEADERS)
  dialog.add_alternate_mapping();dialog.add_alternate_mapping()
  dialog.remove_alternate_mapping('替代料1版本号');self.assertEqual(dialog.mapping_table.columnCount(),8)
  dialog.combos['替代料2编码'].setCurrentText('替代编码');dialog.combos['替代料2版本号'].setCurrentText('替代版本')
  dialog.validate_mapping();self.assertEqual(dialog.result(),1)
  self.assertEqual(len(self.s.BOM_HEADERS),6)
  nodes=self.s.import_bom(self.path,root,sheet_name='BOM',header_mapping=dialog.mapping(),persist=False);dialog.close()
  window=BomWindow(self.s,root)
  try:
   window.stage_import(nodes);window.show_item_info(window.root_item.child(0));self.assertEqual(window.alt_table.item(0,0).text(),'C');self.assertEqual(self.s.bom(root),[])
   with patch.object(QMessageBox,'information'):self.assertTrue(window.save())
   relation=self.s.bom(root)[0]['id'];self.assertEqual(self.s.alternates(relation)[0]['material_id'],alt)
   # 无映射时明确清空当前关系的替代料，保存前数据库仍保持原值。
   nodes=self.s.import_bom(self.path,root,sheet_name='BOM',persist=False,conflict_resolver=lambda _: 'incoming');window.stage_import(nodes)
   window.show_item_info(window.root_item.child(0));self.assertEqual(window.alt_table.rowCount(),0);self.assertEqual(len(self.s.alternates(relation)),1)
   with patch.object(QMessageBox,'information'):self.assertTrue(window.save())
   self.assertEqual(self.s.alternates(relation),[])
  finally:window.dirty=False;window.close()
 def test_alternate_errors_accumulate_and_blank_pair_allowed(self):
  from services.services import BomImportError
  headers=self.s.BOM_HEADERS+['替代料1编码','替代料1版本号'];mapping={h:h for h in headers}
  self.write([['R','1','P','2',1,'','未知','1'],['P','2','C','1',1,'','P','']],headers)
  with self.assertRaises(BomImportError) as error:self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM',header_mapping=mapping,persist=False)
  self.assertIn('第2行替代料1不存在',str(error.exception));self.assertIn('第3行替代料1编码和版本号',str(error.exception));self.assertEqual(self.s.bom(self.ids['R','1']),[])
  self.write([['R','1','P','2',1,'','','']],headers)
  nodes=self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM',header_mapping=mapping,persist=False)
  self.assertEqual(nodes[0]['data']['alternate_material_ids'],[])
