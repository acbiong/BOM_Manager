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
  rows=self.s.bom(self.ids['R','1']);self.assertEqual([(r['material_id'],r['level_no']) for r in rows],[(self.ids['P','2'],1),(self.ids['C','1'],2)]);self.assertEqual(rows[1]['quantity'],2.3);self.assertEqual(self.s.bom(self.ids['P','1']),[]);dialog.close()
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
  from ui.main_window import BomWindow
  self.s.save_bom(self.ids['R','1'],[dict(material_id=self.ids['C','1'],quantity=5,unit='pcs')])
  before=[dict(row) for row in self.s.bom(self.ids['R','1'])]
  for code,version in [('P','1'),('R','2')]:
   self.write([['R','1','P','2',1,''],['root','ROOT',code,version,None,None]])
   with self.assertRaisesRegex(ValueError,'BOM选择错误'):self.s.import_bom(self.path,self.ids['R','1'],sheet_name='BOM')
   self.assertEqual([dict(row) for row in self.s.bom(self.ids['R','1'])],before)
  window=BomWindow(self.s,self.ids['R','1'])
  try:
   with patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.path),'')),patch.object(QInputDialog,'getItem',return_value=('BOM',True)),patch.object(QMessageBox,'warning') as warning:
    window.import_bom();self.assertIn('BOM选择错误',warning.call_args.args[2])
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
  from PyQt5.QtCore import Qt
  from ui.main_window import BomWindow,BomTreeWidget
  root=self.ids['R','1'];old=self.ids['C','1'];new=self.ids['P','2']
  self.s.save_bom(root,[dict(material_id=old,quantity=5,unit='pcs')])
  self.write([['ROOT','ROOT','R','1',None,None],['R','1','P','2',2.3,'new']])
  before=[tuple(r) for r in self.db.conn.execute('SELECT * FROM material_bom_items')]
  for save in (False,True):
   window=BomWindow(self.s,root)
   try:
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.path),'')),patch.object(QInputDialog,'getItem',return_value=('BOM',True)),patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning') as warning:
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
