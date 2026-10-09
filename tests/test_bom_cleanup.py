import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from openpyxl import load_workbook

class BomCleanupTests(unittest.TestCase):
 def test_recursive_cleanup_shared_protection_and_reopen(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'db';db=Database(str(path));s=Services(db)
   ids={code:s.create_material(dict(base_code=code,version='1',name=code,unit='pcs')) for code in ('R','P','C','D','ALT','OTHER')}
   def row(parent,child):return dict(parent_material_id=ids[parent],material_id=ids[child],quantity=1,unit='pcs',remark='备注',position='位置',alternate_material_ids=[ids['ALT']])
   s.save_bom(ids['R'],[row('R','P'),row('P','C'),row('C','D')]);sid=s.create_sku(ids['R'])
   s.save_bom(ids['OTHER'],[row('OTHER','C'),row('C','D')])
   s.save_bom(ids['R'],[])
   self.assertEqual(s.bom(ids['P']),[])
   self.assertEqual([r['material_id'] for r in s.bom(ids['OTHER'])],[ids['C'],ids['D']])
   self.assertEqual(db.conn.execute('SELECT COUNT(*) FROM alternates').fetchone()[0],2)
   s.save_bom(ids['OTHER'],[])
   self.assertEqual(db.conn.execute('SELECT COUNT(*) FROM material_bom_items').fetchone()[0],0)
   self.assertEqual(db.conn.execute('SELECT COUNT(*) FROM alternates').fetchone()[0],0)
   self.assertEqual(len(s.materials()),6)
   db.close();db=Database(str(path));s=Services(db)
   try:
    self.assertEqual(s.bom(ids['R']),[]);self.assertEqual(s.bom(ids['C']),[])
    out=Path(tmp)/'bom.xlsx';s.export_sku(sid,out);wb=load_workbook(out)
    logs=list(wb['变更记录'].values);wb.close()
    self.assertTrue(all(r[3]!='历史记录未保存' for r in logs[1:]))
    self.assertTrue(all(r[6] is None for r in logs[1:] if r[5]=='新建物料'))
   finally:db.close()
 def test_cleanup_failure_rolls_back_every_relation(self):
  db=Database(':memory:');s=Services(db)
  try:
   root=s.create_material(dict(base_code='R',version='1',name='R',unit='pcs'));child=s.create_material(dict(base_code='C',version='1',name='C',unit='pcs'));leaf=s.create_material(dict(base_code='L',version='1',name='L',unit='pcs'))
   s.save_bom(root,[dict(material_id=child,quantity=1,unit='pcs'),dict(parent_material_id=child,material_id=leaf,quantity=1,unit='pcs',alternate_material_ids=[root])])
   before=[tuple(r) for r in db.conn.execute('SELECT * FROM material_bom_items')]
   db.conn.execute("CREATE TEMP TRIGGER fail_cleanup BEFORE DELETE ON alternates BEGIN SELECT RAISE(ABORT,'模拟清理失败'); END")
   with self.assertRaises(Exception):s.save_bom(root,[])
   self.assertEqual([tuple(r) for r in db.conn.execute('SELECT * FROM material_bom_items')],before)
   self.assertEqual(db.conn.execute('SELECT COUNT(*) FROM alternates').fetchone()[0],1)
  finally:db.close()
