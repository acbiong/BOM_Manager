import unittest,tempfile
from pathlib import Path
import test_material_history as fixture
from services import material_history as history
from openpyxl import load_workbook

class RevisionLogTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MaterialHistoryTests.setUpClass.__func__)
 setUp=fixture.MaterialHistoryTests.setUp
 tearDown=fixture.MaterialHistoryTests.tearDown
 rows=fixture.MaterialHistoryTests.rows
 def test_parent_revision_logs_only_revision_and_real_child_changes(self):
  rows=self.rows();rows[-1]['quantity']=3
  before=self.new.db.conn.execute('SELECT COALESCE(MAX(id),0) FROM change_logs').fetchone()[0]
  mapping=history.save(self.new,self.r,rows,{},'fork',{self.p:'101'})
  logs=list(self.new.db.conn.execute("SELECT * FROM change_logs WHERE id>? AND object_type='bom'",(before,)))
  self.assertEqual(len(logs),2)
  self.assertEqual(sum('物料版本更新：P100 P → P101 P' in r['detail'] for r in logs),1)
  self.assertTrue(any('数量：2.0 → 3' in r['detail'] for r in logs))
  self.assertFalse(any('删除物料' in r['detail'] or '新增物料' in r['detail'] for r in logs))
  path=Path(self.temp.name)/'out.xlsx';self.new.export_sku(self.newid,path)
  w=load_workbook(path);values=list(w['变更记录'].values);w.close()
  self.assertTrue(any(r[5]=='物料版本更新' and r[3]=='P101' for r in values[1:]))
 def test_parent_revision_keeps_deleted_child_details_and_alternates(self):
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  history.save(self.new,self.r,rows,{},'fork')
  before=self.new.db.conn.execute('SELECT COALESCE(MAX(id),0) FROM change_logs').fetchone()[0]
  rows=self.rows()[:1]
  history.save(self.new,self.r,rows,{},'fork',{self.p:'101'})
  logs=list(self.new.db.conn.execute("SELECT * FROM change_logs WHERE id>? AND object_type='bom'",(before,)))
  self.assertEqual(len(logs),2)
  deleted=next(r for r in logs if '删除物料' in r['detail'])
  self.assertEqual(deleted['material_code'],'C100');self.assertIn('删除替代料：A100',deleted['detail'])
  self.assertTrue(any('物料版本更新：P100 P → P101 P' in r['detail'] for r in logs))
