import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import QTimer,QEvent,QObject
from PyQt5.QtWidgets import QApplication
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MaterialSelectionDialog

class PickerPerformanceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_large_library_replacement_and_alternate_popup_under_300ms(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   r=s.create_material(dict(base_code='ROOT',version='1',name='根',unit='pcs'));c=s.create_material(dict(base_code='CHILD',version='1',name='子',unit='pcs'))
   db.conn.executemany("INSERT INTO materials(base_code,version,name,unit) VALUES(?,'1',?,'pcs')",[(f'M{i:05}',f'性能测试物料{i}') for i in range(10000)]);db.conn.commit()
   s.save_bom(r,[dict(material_id=c,quantity=1,unit='pcs')]);w=BomWindow(s,r)
   class Probe(QObject):
    def eventFilter(self,obj,event):
     if isinstance(obj,MaterialSelectionDialog) and event.type()==QEvent.Paint and not measured:
      measured.append(time.perf_counter()-start);QTimer.singleShot(0,obj.reject)
     return False
   probe=Probe();self.app.installEventFilter(probe)
   try:
    for action in ('replace','alternate'):
     node=w.root_item.child(0);w.tree.setCurrentItem(node);w.show_item_info(node)
     measured=[];queries=[];db.conn.set_trace_callback(queries.append);start=time.perf_counter()
     if action=='replace':w.replace_material(node)
     else:w.add_alternate()
     db.conn.set_trace_callback(None)
     self.assertTrue(measured);print(f'{action}: 10000 materials, first paint {measured[0]*1000:.1f} ms, queries {len(queries)}')
     self.assertLess(measured[0],.3);self.assertLess(len(queries),10)
    node=w.root_item.child(0)
    expected={row['id'] for row in s.db.conn.execute('SELECT id FROM materials LIMIT 12') if w.paste_block_reason(node,False,row['id'])}
    actual=w.replacement_blocked_materials(node)
    for row in s.db.conn.execute('SELECT id FROM materials LIMIT 12'):self.assertEqual(row['id'] in actual,row['id'] in expected)
    self.assertFalse(w.dirty)
   finally:self.app.removeEventFilter(probe);w.close();db.close()
