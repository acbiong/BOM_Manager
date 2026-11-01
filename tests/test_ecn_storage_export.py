import sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from services.sku_ecn import parse_legacy,values
from services.sku_lock import LockedBomError
from openpyxl import load_workbook


class EcnStorageExportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.db=Database(str(self.path/'db'));self.s=Services(self.db)
  self.mid=self.s.create_material(dict(base_code='SKU',version='100',name='产品',unit='pcs'));self.sid=self.s.create_sku(self.mid);self.other=self.s.copy_sku_bom(self.sid)
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def test_defaults_copy_custom_blank_and_version_change(self):
  self.assertEqual([r['ecn_number'] for r in self.s.skus()],['/',''])
  self.s.update_sku_ecn(self.sid,'','','');self.s.change_mirror_version(self.sid,99)
  self.s.change_mirror_version(self.sid,100);self.assertEqual(self.s.skus()[0]['ecn_number'],'')
  self.s.update_sku_ecn(self.other,'E1','名称','正文');new=self.s.copy_sku_bom(self.other)
  self.assertEqual(values(next(r for r in self.s.skus() if r['id']==new)),('','',''))
 def test_noop_lock_stale_and_raw_write_protection(self):
  self.s.update_sku_ecn(self.sid,'E1','名称','正文');before=list(self.db.conn.iterdump())
  self.s.update_sku_ecn(self.sid,'E1','名称','正文');self.assertEqual(before,list(self.db.conn.iterdump()))
  with self.assertRaisesRegex(ValueError,'已被修改'):self.s.update_sku_ecn(self.sid,'E2','','',expected=('/','',''))
  self.s.set_sku_locked(self.sid,True)
  with self.assertRaises(LockedBomError):self.s.update_sku_ecn(self.sid,'E2','','')
  with self.assertRaises(LockedBomError):
   with self.db.transaction():self.db.conn.execute("UPDATE skus SET ecn_content='raw change' WHERE id=?",(self.sid,))
  self.assertEqual(self.s.skus()[0]['ecn_content'],'正文')
 def test_single_line_validation_and_specific_refresh(self):
  with self.assertRaises(ValueError):self.s.update_sku_ecn(self.sid,'E\n2','','')
  with self.assertRaises(ValueError):self.s.update_sku_ecn(self.sid,'E','name\rnext','')
  with patch.object(self.s,'publish') as event:self.s.update_sku_ecn(self.sid,'E','name','one\ntwo')
  self.assertEqual(event.call_args.args[0]['type'],'sku_ecn_changed')
 def legacy(self):
  path=self.path/'legacy.db';c=sqlite3.connect(path)
  c.execute("CREATE TABLE skus(id INTEGER PRIMARY KEY,material_id INTEGER,updated_at TEXT,mirror_version INTEGER DEFAULT 100,scope_id INTEGER DEFAULT 0,change_description TEXT DEFAULT '',locked INTEGER DEFAULT 0)")
  c.executemany('INSERT INTO skus VALUES(?,?,?,?,?,?,?)',[(1,1,'old',100,0,'',1),(2,1,'old',101,0,'【ECN-001】\n第一行\n\n末行\n',1),(3,1,'old',102,0,'[ECN-002]\r\n内容',0),(4,1,'old',103,0,'未加括号的编号',0)])
  c.commit();c.close();return path
 def test_legacy_backup_migration_locked_rows_and_idempotence(self):
  path=self.legacy();db=Database(str(path))
  try:
   rows=[dict(r) for r in db.conn.execute('SELECT * FROM skus ORDER BY id')]
   self.assertEqual(values(rows[0]),('/','',''));self.assertEqual(values(rows[1]),('ECN-001','','第一行\n\n末行\n'))
   self.assertEqual(values(rows[2]),('ECN-002','','内容'));self.assertEqual(values(rows[3]),('未加括号的编号','',''))
   self.assertTrue(all(r['change_description']=='' and r['updated_at']=='old' for r in rows))
   self.assertEqual(rows[1]['locked'],1)
   backups=list(self.path.glob('legacy.db.pre-ecn-*.db'));self.assertEqual(len(backups),1)
   c=sqlite3.connect(backups[0]);self.assertEqual(c.execute('SELECT change_description FROM skus WHERE id=2').fetchone()[0],'【ECN-001】\n第一行\n\n末行\n');c.close()
  finally:db.close()
  db=Database(str(path));self.assertEqual([dict(r) for r in db.conn.execute('SELECT * FROM skus ORDER BY id')],rows);db.close()
  self.assertEqual(len(list(self.path.glob('legacy.db.pre-ecn-*.db'))),1)
 def test_migration_failure_does_not_clear_original_note(self):
  path=self.legacy()
  with patch('services.sku_ecn.parse_legacy',side_effect=ValueError('invalid')):
   with self.assertRaises(ValueError):Database(str(path))
  c=sqlite3.connect(path);self.assertTrue(c.execute('SELECT change_description FROM skus WHERE id=2').fetchone()[0].startswith('【ECN-001】'));c.close()
  db=Database(str(path));self.assertEqual(db.conn.execute('SELECT ecn_number FROM skus WHERE id=2').fetchone()[0],'ECN-001');db.close()
 def test_export_matrix_histories_literal_text_and_formats(self):
  another=self.s.create_sku(self.s.create_material(dict(base_code='OTHER',version='100',name='另一产品',unit='pcs')))
  extra=self.s.copy_sku_bom(self.other)
  self.s.update_sku_ecn(self.sid,'=ECN001','名称','内容一')
  self.s.update_sku_ecn(self.other,'=ECN001','名称','内容二\n'+'长内容'*35)
  self.s.update_sku_ecn(another,'=ECN001','名称','另一个SKU内容')
  self.s.update_sku_ecn(extra,'=ECN002','另一个ECN','内容三')
  for export,name in [(self.s.export_sku_list,'list.xlsx'),(self.s.export_database,'all.xlsx')]:
   export(self.path/name);book=load_workbook(self.path/name)
   try:
    self.assertEqual(book.sheetnames[:2],['SKU清单','ECN']);sheet=book['ECN']
    self.assertEqual(list(next(sheet.values)),['序号','ECN编号','ECN名称','SKU100 产品','OTHER100 另一产品'])
    self.assertEqual(sheet['B2'].value,'=ECN001');self.assertEqual(sheet['B2'].data_type,'s')
    self.assertEqual(sheet['D2'].value,'【100】\n内容一\n\n【101】\n内容二\n'+'长内容'*35)
    self.assertEqual(sheet['E2'].value,'【100】\n另一个SKU内容');self.assertEqual(sheet['D3'].value,'【102】\n内容三')
    for dim in sheet.column_dimensions.values():self.assertLessEqual(dim.width,30)
    for row in sheet:
     for cell in row:self.assertEqual(cell.border.left.style,'thin');self.assertTrue(cell.alignment.wrap_text)
    self.assertTrue(all(c.font.bold for c in sheet[1]));self.assertGreater(sheet.row_dimensions[2].height,22)
    self.assertEqual(book['SKU清单']['E1'].value,'历史版本号');self.assertEqual(book['SKU清单']['F1'].value,'ECN')
    self.assertEqual(book['SKU清单']['F2'].data_type,'s')
   finally:book.close()
 def test_export_empty_project_and_defaults_have_no_spurious_ecn(self):
  self.s.export_sku_list(self.path/'empty.xlsx');book=load_workbook(self.path/'empty.xlsx')
  self.assertEqual(book['ECN'].max_row,1);book.close()
  self.s.update_sku_ecn(self.other,'','','没有编号的内容');self.s.export_sku_list(self.path/'blank.xlsx');book=load_workbook(self.path/'blank.xlsx')
  self.assertEqual(book['ECN']['D2'].value,'【101】\n没有编号的内容');book.close()
