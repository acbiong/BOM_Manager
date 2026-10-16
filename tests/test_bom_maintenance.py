import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate
from services.current_catalog import initialize
from services.bom_maintenance import cleanup_orphan_boms

class BomMaintenanceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db'
  self.db=Database(str(self.path));self.s=Services(self.db)
  self.r,self.p,self.c,self.a,self.x,self.y=[self.s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('R','P','C','A','X','Y')]
  self.s.save_bom(self.p,[dict(material_id=self.c,quantity=2,unit='pcs',alternate_material_ids=[self.a])])
  self.s.save_bom(self.r,[dict(material_id=self.p,quantity=1,unit='pcs')])
  self.sid=self.s.create_sku(self.r);migrate(self.db);initialize(self.db)
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def orphan(self,service):
  with self.db.transaction():
   rid=service.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit,remark) VALUES(?,?,1,?,?)',(self.x,self.y,'pcs','orphan'*10000)).lastrowid
   service.db.conn.execute('INSERT INTO alternates(bom_item_id,material_id) VALUES(?,?)',(rid,self.a))
  return rid
 def test_reverse_ignores_catalog_cache_and_includes_real_mirrors_and_alternates(self):
  copy=self.s.copy_sku_bom(self.sid)
  for mid in (self.p,self.c,self.a):
   usages=self.s.material_usage(mid)
   self.assertEqual({r['sku_id'] for r in usages},{self.sid,copy})
   self.assertFalse(any('未包含' in r['sku'] for r in usages))
  refs=self.s.material_version_references(self.c)
  self.assertEqual(len(refs),2);self.assertTrue(all(r['parent_id'].startswith('mirror:') for r in refs))
  alt=self.s.material_usage(self.a)[0]
  self.assertEqual(alt['focus_material_id'],self.c);self.assertIn('替代料',alt['parent'])
 def test_orphan_cleanup_preserves_history_master_and_logs_and_compacts(self):
  copy=self.s.copy_sku_bom(self.sid);self.s.for_sku(copy).save_bom(self.r,[])
  current=self.s.for_sku(copy);self.orphan(current);self.orphan(self.s)
  with self.db.transaction():
   self.db.conn.execute('INSERT OR IGNORE INTO mirror_captured_materials VALUES(?,?)',(copy,self.x))
   current.db.conn.execute('INSERT INTO alternates(bom_item_id,material_id) VALUES(999999,?)',(self.a,))
  history=[dict(r) for r in self.s.for_sku(self.sid).bom(self.r)]
  logs=self.s.for_sku(self.sid).db.conn.execute('SELECT COUNT(*) FROM change_logs').fetchone()[0]
  report=cleanup_orphan_boms(self.s,backup=True,compact=True)
  self.assertEqual(report['relations'],2);self.assertEqual(report['alternates'],3)
  self.assertTrue(report['compacted']);self.assertLess(report['bytes_after'],report['bytes_before'])
  self.assertTrue(Path(report['backup']).exists())
  self.assertEqual(self.s.for_sku(self.sid).bom(self.r),history)
  self.assertEqual(self.s.for_sku(self.sid).db.conn.execute('SELECT COUNT(*) FROM change_logs').fetchone()[0],logs)
  self.assertTrue(self.s.material_snapshot(self.x));self.assertTrue(self.s.material_snapshot(self.y))
  self.assertEqual(self.s.material_usage(self.y),[])
  self.assertEqual(self.db.conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
  self.assertEqual(cleanup_orphan_boms(self.s,backup=True,compact=True)['relations'],0)
  self.assertEqual(len(list(self.path.parent.glob('*.pre-orphan-cleanup-*.db'))),1)
 def test_orphan_reverse_does_not_claim_fake_sku(self):
  self.orphan(self.s);self.orphan(self.s.for_sku(self.sid))
  self.assertEqual(self.s.material_usage(self.y),[])
  cleanup_orphan_boms(self.s)
  self.assertEqual(self.s.bom(self.x),[])
  self.assertEqual(self.s.for_sku(self.sid).db.conn.execute('SELECT COUNT(*) FROM material_bom_items WHERE parent_material_id=?',(self.x,)).fetchone()[0],0)
 def test_startup_cleans_and_reopen_keeps_real_reverse_usage(self):
  from ui.snapshot_migration import prepare_snapshot_bom
  self.orphan(self.s)
  self.assertTrue(prepare_snapshot_bom(self.db))
  self.assertEqual(self.s.bom(self.x),[])
  self.db.close();self.db=Database(str(self.path));self.s=Services(self.db)
  self.assertEqual(self.s.material_usage(self.c)[0]['sku_id'],self.sid)
 def test_backup_failure_does_not_remove_orphan(self):
  self.orphan(self.s)
  with patch('services.bom_maintenance.sqlite3.connect',side_effect=OSError('backup failed')):
   with self.assertRaises(OSError):cleanup_orphan_boms(self.s,backup=True)
  self.assertEqual(len(self.s.bom(self.x)),1)

 def test_reachable_alternate_subtree_is_preserved_and_reverse_is_available(self):
  scoped=self.s.for_sku(self.sid)
  with self.db.transaction():
   scoped.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit) VALUES(?,?,1,?)',(self.a,self.x,'pcs'))
  self.orphan(self.s)
  cleanup_orphan_boms(self.s)
  self.assertTrue(scoped.db.conn.execute('SELECT 1 FROM material_bom_items WHERE parent_material_id=? AND child_material_id=?',(self.a,self.x)).fetchone())
  self.assertEqual(self.s.material_usage(self.x)[0]['sku_id'],self.sid)
