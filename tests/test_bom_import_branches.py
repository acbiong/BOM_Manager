import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from openpyxl import Workbook
from database.database import Database
from services.services import Services,BomImportError

class BranchImportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'bom.xlsx'
  self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.ids={c:self.s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in 'RABPCDEX'}
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def rows(self):
  return [[0,'ROOT','ROOT','R','1',1,'根','','',''],
          [1,'R','1','A','1',2,'A','','',''],[2,'A','1','P','1',3,'四指','','',''],
          [3,'P','1','C','1',2,'C1','备注','X','1'],[4,'C','1','E','1',4,'E1','','',''],
          [3,'P','1','D','1',1,'D1','','',''],
          [1,'R','1','B','1',1,'B','','',''],[2,'B','1','P','1',1,'拇指','','',''],
          [3,'P','1','C','1',2,'C1','备注','X','1'],[4,'C','1','E','1',4,'E1','','',''],
          [3,'P','1','D','1',1,'D1','','','']]
 def write(self,rows,levels=True):
  book=Workbook();headers=['层级']+self.s.BOM_HEADERS+['备注','替代料1编码','替代料1版本号']
  book.active.append(headers if levels else headers[1:])
  for row in rows:book.active.append(row if levels else row[1:])
  book.save(self.path);book.close()
 def preview(self,resolver=None):
  mapping={field:field for field in self.s.BOM_HEADERS+['替代料1编码','替代料1版本号']}
  return self.s.import_bom(self.path,self.ids['R'],header_mapping=mapping,persist=False,conflict_resolver=resolver)
 def test_equal_branches_expand_twice_without_writes_or_prompt(self):
  self.write(self.rows());before=list(self.db.conn.iterdump());resolver=Mock()
  nodes=self.preview(resolver);resolver.assert_not_called()
  self.assertEqual(len(nodes),2)
  for node in nodes:
   p=node['children'][0];self.assertEqual(len(p['children']),2)
   self.assertEqual(p['children'][0]['data']['remark'],'备注')
   self.assertEqual(p['children'][0]['data']['alternate_material_ids'],[self.ids['X']])
   self.assertEqual(p['children'][0]['children'][0]['data']['material_id'],self.ids['E'])
  self.assertEqual(list(self.db.conn.iterdump()),before)
 def test_every_relation_field_difference_blocks_before_system_resolver(self):
  for field,value,label in [(5,5,'数量'),(6,'C2','位置'),(7,'另一备注','备注'),(8,'D','替代料')]:
   with self.subTest(field=label):
    rows=self.rows();rows[8][field]=value;self.write(rows);resolver=Mock(return_value='incoming');before=list(self.db.conn.iterdump())
    with self.assertRaises(BomImportError) as error:self.preview(resolver)
    text=str(error.exception);self.assertIn('子BOM不一致',text);self.assertIn(label,text);self.assertIn('第5行 / 第10行',text)
    self.assertIn('A1',text);self.assertIn('B1',text);resolver.assert_not_called();self.assertEqual(list(self.db.conn.iterdump()),before)
 def test_nested_missing_extra_and_empty_subtrees_are_not_union_merged(self):
  for remove in ([9],[8,9],[8,9,10]):
   rows=[row for index,row in enumerate(self.rows()) if index not in remove];self.write(rows)
   with self.assertRaisesRegex(BomImportError,'缺少子物料'):self.preview()
  rows=self.rows();rows[9][3]='D';self.write(rows)
  with self.assertRaisesRegex(BomImportError,'子BOM不一致'):self.preview()
 def test_duplicate_within_one_branch_still_rejected(self):
  rows=self.rows();rows.insert(6,list(rows[5]));self.write(rows)
  with self.assertRaisesRegex(BomImportError,'同一父级重复包含相同物料'):self.preview()
 def test_preorder_without_levels_and_reordered_siblings(self):
  rows=self.rows();self.write(rows,levels=False);self.assertEqual(len(self.preview()),2)
  rows=self.rows();rows[8:]=[rows[10],rows[8],rows[9]];self.write(rows)
  self.assertEqual(len(self.preview()),2)
 def test_invalid_level_or_parent_cannot_hide_branch_difference(self):
  for field,value in ((0,6),(1,'A')):
   rows=self.rows();rows[8][field]=value;self.write(rows)
   with self.assertRaisesRegex(BomImportError,'层级与父项编码不匹配'):self.preview()
 def test_normalized_shared_definition_is_persisted_once(self):
  self.write(self.rows())
  mapping={field:field for field in self.s.BOM_HEADERS+['替代料1编码','替代料1版本号']}
  self.assertEqual(self.s.import_bom(self.path,self.ids['R'],header_mapping=mapping),7)
  self.assertEqual(self.db.conn.execute('SELECT COUNT(*) FROM material_bom_items').fetchone()[0],7)
  self.assertEqual(len(self.s.bom(self.ids['R'])),10)
