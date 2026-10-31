import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QTableWidget,QTableWidgetItem
from database.database import Database
from services.services import Services
from config.config_service import ConfigService
from ui.main_window import MainWindow,MaterialWindow
from ui.table_layout import fit_columns
from infrastructure.operation_progress import _current
from infrastructure.events import WindowRefreshBus


class RefreshEfficiencyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_layout_no_progress_repeated_fit_and_content_invalidation(self):
  t=QTableWidget(100,3);t.setHorizontalHeaderLabels(['编码','名称','规格'])
  for row in range(100):
   for col in range(3):t.setItem(row,col,QTableWidgetItem('物料'+str(row)))
  class Controller:
   def update(self,*args):raise AssertionError('Layout must not pump progress events')
  token=_current.set(Controller())
  try:
   with patch.object(t,'sizeHintForColumn',wraps=t.sizeHintForColumn) as width,patch.object(t,'resizeRowsToContents',wraps=t.resizeRowsToContents) as height:
    fit_columns(t);self.assertEqual(width.call_count,3);self.assertEqual(height.call_count,1)
    fit_columns(t);self.assertEqual(width.call_count,3);self.assertEqual(height.call_count,1)
    from PyQt5.QtCore import Qt
    t.item(0,1).setData(Qt.UserRole,123);fit_columns(t)
    self.assertEqual(width.call_count,3);self.assertEqual(height.call_count,1)
    t.item(0,1).setText('多行\n文字\n必须显示');fit_columns(t)
    self.assertEqual(height.call_count,2);self.assertGreater(t.rowHeight(0),t.rowHeight(1))
  finally:_current.reset(token);t.close()
 def test_project_scoped_events_and_one_refresh_per_transaction(self):
  with tempfile.TemporaryDirectory() as temp:
   dbs=[Database(str(Path(temp)/str(i))) for i in range(2)]
   services=[Services(db,ConfigService(Path(temp)/('config'+str(i)))) for i,db in enumerate(dbs)]
   windows=[MainWindow(svc) for svc in services];library=MaterialWindow(services[0],windows[0])
   try:
    with patch.object(windows[0],'refresh',wraps=windows[0].refresh) as first,patch.object(windows[1],'refresh',wraps=windows[1].refresh) as other,patch.object(library,'refresh',wraps=library.refresh) as materials:
     with services[0].db.transaction():
      for i in range(10):services[0].create_material(dict(base_code=str(i),version='1',name='物料',unit='pcs'))
     self.assertEqual(first.call_count,1);self.assertEqual(other.call_count,0);self.assertEqual(materials.call_count,1)
    root=services[0].create_material(dict(base_code='SKU',version='1',name='SKU',unit='pcs'));services[0].create_sku(root)
    button=windows[0].table.cellWidget(0,0)
    services[0].create_material(dict(base_code='unrelated',version='1',name='无关物料',unit='pcs'))
    self.assertIs(windows[0].table.cellWidget(0,0),button)
    with patch.object(services[0],'sku_material_quantities',wraps=services[0].sku_material_quantities) as quantities:
     with patch.object(library.t,'setUpdatesEnabled',wraps=library.t.setUpdatesEnabled) as painting:
      library.refresh();self.assertEqual(quantities.call_count,0);painting.assert_not_called()
     # A commit by another SQLite connection invalidates the read cache too.
     import sqlite3
     connection=sqlite3.connect(dbs[0].path)
     connection.execute("UPDATE materials SET name='外部提交' WHERE base_code='unrelated'");connection.commit();connection.close()
     library.refresh();self.assertEqual(quantities.call_count,1)
     self.assertTrue(any(library.t.item(row,2).text()=='外部提交' for row in range(library.t.rowCount())))
   finally:
    library.close()
    for w in windows:w.close()
    for db in dbs:db.close()
 def test_quantity_aggregation_reuses_catalogue_across_histories(self):
  db=Database(':memory:');svc=Services(db)
  try:
   root,child=[svc.create_material(dict(base_code=code,version='1',name=code,unit='pcs')) for code in ('R','C')]
   sid=svc.create_sku(root);svc.save_bom(root,[dict(material_id=child,quantity=2,unit='pcs')])
   for _ in range(5):svc.copy_sku_bom(sid)
   catalogue=svc.skus()
   with patch.object(Services,'skus',side_effect=AssertionError('重复读取全SKU清单')):
    quantities=svc.sku_material_quantities(catalogue)
   self.assertEqual(len(quantities),6)
   self.assertTrue(all(values[root]==1 and values[child]==2 for values in quantities.values()))
  finally:db.close()


if __name__=='__main__':unittest.main()


