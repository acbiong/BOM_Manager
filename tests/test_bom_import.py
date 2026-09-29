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
