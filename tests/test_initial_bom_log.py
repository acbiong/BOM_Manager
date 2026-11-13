import os,sys,tempfile,unittest
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate
from services.current_catalog import initialize
from openpyxl import load_workbook

class InitialBomLogTests(unittest.TestCase):
 def test_first_population_summary_then_deletions_and_reimport_are_detailed(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'test.db'));s=Services(db)
   root,a,b=[s.create_material(dict(base_code=x,version='100',name=x,unit='pcs')) for x in ('ROOT','A','B')]
   sid=s.create_sku(root);migrate(db);initialize(db);sc=s.for_sku(sid)
   rows=[dict(material_id=x,quantity=1,unit='pcs') for x in (a,b)]
   sc.save_bom(root,rows)
   logs=list(sc.db.conn.execute("SELECT * FROM change_logs WHERE object_type='bom'"))
   self.assertEqual(len(logs),1);self.assertEqual(logs[0]['detail'],'新创建BOM，包含2个物料')
   sc.save_bom(root,[])
   path=Path(tmp)/'out.xlsx';sc.export_sku(sid,path);w=load_workbook(path)
   changes=list(w['变更记录'].values)[1:];w.close()
   self.assertEqual(sum(r[5]=='新建BOM' for r in changes),1)
   self.assertEqual({r[3] for r in changes if r[5]=='删除物料'},{'A100','B100'})
   sc.save_bom(root,rows)
   self.assertEqual(sc.db.conn.execute("SELECT COUNT(*) FROM change_logs WHERE object_type='bom' AND action='create'").fetchone()[0],1)
   self.assertTrue(any('新增物料' in r[0] for r in sc.db.conn.execute("SELECT detail FROM change_logs WHERE object_type='bom' AND action='update'")))
   db.close()
