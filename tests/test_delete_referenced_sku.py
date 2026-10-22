import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox
from ui.interactive_windows import QMessageBox
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from infrastructure.events import WindowRefreshBus

class DeleteReferencedSkuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_referenced_root_preserves_structure_alternates_history_and_no_bom_event(self):
  for alternate in (False,True):
   with self.subTest(alternate=alternate),tempfile.TemporaryDirectory() as tmp:
    db=Database(str(Path(tmp)/'db'));s=Services(db)
    root,parent,child,other,alt=[s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('R','P','C','O','X')]
    sid=s.create_sku(root)
    s.save_bom(child,[dict(material_id=alt,quantity=3,unit='pcs')])
    s.save_bom(root,[dict(material_id=child,quantity=2,unit='pcs',position='位置',remark='备注')])
    edge=s.bom(root)[0]['id'];s.add_alternate(edge,other)
    s.save_bom(parent,[dict(material_id=other if alternate else root,quantity=1,unit='pcs')])
    if alternate:s.add_alternate(s.bom(parent)[0]['id'],root)
    before=[tuple(r) for r in db.conn.execute('SELECT * FROM material_bom_items ORDER BY id')]
    before_alts=[tuple(r) for r in db.conn.execute('SELECT * FROM alternates ORDER BY id')]
    logs=[tuple(r) for r in db.conn.execute("SELECT * FROM change_logs WHERE object_type='bom'")]
    main=MainWindow(s);events=[];WindowRefreshBus.subscribe(events.append)
    try:
     with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes) as ask:main.delete_sku(sid)
     self.assertIn('仅移除SKU标记',ask.call_args.args[2]);self.assertEqual(s.skus(),[])
     self.assertEqual(before,[tuple(r) for r in db.conn.execute('SELECT * FROM material_bom_items ORDER BY id')])
     self.assertEqual(before_alts,[tuple(r) for r in db.conn.execute('SELECT * FROM alternates ORDER BY id')])
     self.assertEqual(logs,[tuple(r) for r in db.conn.execute("SELECT * FROM change_logs WHERE object_type='bom'")])
     self.assertEqual(s.material_snapshot(root)['has_bom'],1);self.assertTrue(s.material_snapshot(root))
     self.assertFalse(any(e['type']=='bom_changed' for e in events))
     self.assertTrue(any(e['type']=='sku_changed' for e in events))
    finally:WindowRefreshBus.unsubscribe(events.append);main.close();db.close()
    db=Database(str(Path(tmp)/'db'))
    try:self.assertEqual(len(Services(db).bom(root)),2)
    finally:db.close()
