import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate
from services.current_catalog import initialize
from services.bom_compare import snapshot
from PyQt5.QtWidgets import QApplication
from ui.main_window import BomWindow
from unittest.mock import patch

class BatchedReadTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_shared_paths_cycles_freshness_and_alternates(self):
  with tempfile.TemporaryDirectory() as folder:
   db=Database(str(Path(folder)/'db'));s=Services(db)
   ids={x:s.create_material(dict(base_code=x,version='1',name=x,unit='pcs')) for x in 'RPQCA'}
   row=lambda p,c:dict(parent_material_id=ids[p],material_id=ids[c],quantity=1,unit='pcs',alternate_material_ids=[ids['A']] if c=='C' else [])
   s.save_bom(ids['R'],[row('R','P'),row('R','Q'),row('P','C'),row('Q','P')]);sid=s.create_sku(ids['R']);migrate(db);initialize(db);svc=s.for_sku(sid)
   try:
    queries=[];db.conn.set_trace_callback(queries.append);rows=svc.bom(ids['R']);db.conn.set_trace_callback(None)
    self.assertEqual([r['base_code'] for r in rows],['P','C','Q','P','C']);self.assertLessEqual(len(queries),4)
    self.assertEqual(len({r['node_id'] for r in rows}),5)
    alts=svc.alternate_groups(r['id'] for r in rows)
    for r in rows:self.assertEqual([dict(a) for a in alts[r['id']]],[dict(a) for a in svc.alternates(r['id'])])
    s.update_material(ids['C'],{**s.material_snapshot(ids['C']),'name':'updated'})
    self.assertEqual([r['name'] for r in svc.bom(ids['R']) if r['material_id']==ids['C']],['updated','updated'])
    w=BomWindow(svc,ids['R'])
    try:
     with patch.object(svc,'materials',side_effect=AssertionError('must not read entire library')):w.show_item_info(w.root_item.child(0).child(0))
     self.assertEqual(w.alt_table.item(0,2).text(),'A')
    finally:w.dirty=False;w.close()
    # Legacy/corrupt cycles terminate while preserving the old path guard.
    svc.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit) VALUES(?,?,1,?)',(ids['C'],ids['R'],'pcs'))
    self.assertEqual(len(svc.bom(ids['R'])),5)
    db.conn.rollback()
   finally:db.close()
