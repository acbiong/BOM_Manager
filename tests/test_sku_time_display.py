import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from ui.time_display import sku_timestamp
from ui.main_window import MainWindow
from database.database import Database
from services.services import Services
from PyQt5.QtWidgets import QApplication

class SkuTimeDisplayTests(unittest.TestCase):
 def test_integer_seconds_and_legacy_fraction(self):
  prefix='2026-10-14 16:45:59'
  for suffix,expected in [('', ''),('.1',''),('.12',''),('.123456',''),('.999999','')]:
   self.assertEqual(sku_timestamp(prefix+suffix),prefix+expected)
  self.assertEqual(sku_timestamp(prefix.replace(' ','T')+'.123'),prefix)
  self.assertEqual(sku_timestamp(None),'');self.assertEqual(sku_timestamp(''), '')
 def test_sku_window_formats_public_and_mirror_without_rewriting_history(self):
  app=QApplication.instance() or QApplication([])
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   root=s.create_material(dict(base_code='R',version='100',name='时间显示',unit='pcs'))
   sid=s.create_sku(root);copy=s.copy_sku_bom(sid)
   db.conn.execute('UPDATE materials SET updated_at=? WHERE id=?',('2026-10-14 16:45:59.123456',root))
   db.conn.execute('UPDATE skus SET updated_at=? WHERE id=?',('2026-10-14 16:45:59',copy));db.conn.commit()
   w=MainWindow(s)
   try:
    self.assertEqual([w.table.item(i,5).text() for i in range(2)],['2026-10-14 16:45:59','2026-10-14 16:45:59'])
    self.assertEqual(s.material_snapshot(root)['updated_at'],'2026-10-14 16:45:59.123456')
    w.sort_skus(5);self.assertEqual(w.table.item(0,5).text(),'2026-10-14 16:45:59')
   finally:w.close();db.close()
