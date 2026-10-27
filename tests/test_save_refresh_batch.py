import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from unittest.mock import patch
from infrastructure.events import WindowRefreshBus as Bus
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow

class SaveRefreshBatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_batch_preserves_events_and_coalesces_nested_refresh_in_priority_order(self):
  calls=[];events=[]
  def material():calls.append('material')
  def sku():calls.append('sku');Bus.refresh(material)
  def handler(event):
   events.append(event);Bus.refresh(material);Bus.refresh(sku,priority=0)
  Bus.subscribe(handler)
  try:
   items=[{'type':'bom_changed','root':r} for r in (1,2,3)]
   Bus.publish_many(items);self.assertEqual(events,items);self.assertEqual(calls,['sku','material']);self.assertEqual(Bus._batch_depth,0)
  finally:Bus.unsubscribe(handler)
 def test_transaction_refresh_once_and_rollback_does_not_refresh(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db);mid=s.create_material(dict(base_code='A',version='1',name='A',unit='pcs'));w=MainWindow(s);w.show_materials();m=w._materials
   try:
    old=m.t.item(0,0)
    with patch.object(w,'refresh',wraps=w.refresh) as main_refresh,patch.object(m,'refresh',wraps=m.refresh) as library_refresh:
     with db.transaction():
      for i in range(4):s.publish({'type':'bom_changed','root':mid});s.publish({'type':'sku_changed'})
     self.assertEqual(main_refresh.call_count,1);self.assertEqual(library_refresh.call_count,1)
     self.assertIs(m.t.item(0,0),old)
     main_refresh.reset_mock();library_refresh.reset_mock()
     with self.assertRaises(ValueError):
      with db.transaction():s.publish({'type':'material_changed','id':mid});raise ValueError('rollback')
     main_refresh.assert_not_called();library_refresh.assert_not_called()
   finally:w.close();db.close()
