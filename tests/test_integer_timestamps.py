import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from openpyxl import load_workbook

class IntegerTimestampTests(unittest.TestCase):
 def test_exports_seconds_without_changing_stored_precision(self):
  with tempfile.TemporaryDirectory() as folder:
   db=Database(str(Path(folder)/'db'));svc=Services(db)
   root=svc.create_material(dict(base_code='R',version='1',name='根',unit='pcs'));sid=svc.create_sku(root);mirror=svc.copy_sku_bom(sid)
   value='2026-10-28 10:01:02.987654'
   for table in ['materials','skus']:db.conn.execute(f'UPDATE {table} SET updated_at=?',(value,))
   for table in ['change_logs',f'mirror_{mirror}_change_logs']:db.conn.execute(f'UPDATE {table} SET changed_at=?',(value,))
   db.conn.commit()
   for label,export in [('library',svc.export_database),('materials',svc.export_materials),('skus',svc.export_sku_list),('bom',lambda p:svc.export_sku(mirror,p))]:
    out=Path(folder)/(label+'.xlsx');export(out);wb=load_workbook(out)
    if 'SKU清单' in wb:
     self.assertTrue(all(row[5].value=='2026-10-28 10:01:02' for row in list(wb['SKU清单'].rows)[1:]))
    if '变更记录' in wb:
     self.assertTrue(all(row[2].value=='10:01:02' for row in list(wb['变更记录'].rows)[1:]))
    wb.close()
   for table,column in [('materials','updated_at'),('skus','updated_at'),('change_logs','changed_at'),(f'mirror_{mirror}_change_logs','changed_at')]:
    self.assertTrue(all(row[0]==value for row in db.conn.execute(f'SELECT {column} FROM {table}')))
   self.assertEqual(db.conn.execute('PRAGMA integrity_check').fetchone()[0],'ok');db.close()
