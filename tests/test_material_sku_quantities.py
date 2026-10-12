import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow,MaterialWindow

class MaterialSkuQuantityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_quantity_order_filters_and_live_changes(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids={x:s.create_material(dict(base_code=x,version='1',name=x,unit='pcs')) for x in ('Z','A','P','Q','C','X')}
   z=s.create_sku(ids['Z']);a=s.create_sku(ids['A'])
   s.save_bom(ids['P'],[dict(material_id=ids['C'],quantity=1.5,unit='pcs')])
   s.save_bom(ids['Q'],[dict(material_id=ids['C'],quantity=2,unit='pcs')])
   s.save_bom(ids['Z'],[dict(material_id=ids['P'],quantity=2,unit='pcs'),dict(material_id=ids['Q'],quantity=3,unit='pcs')])
   s.add_alternate(s.bom(ids['Z'])[0]['id'],ids['X'])
   main=MainWindow(s);main.show_materials();w=main._materials;standalone=MaterialWindow(s)
   def value(code,sid):
    row=next(i for i in range(w.t.rowCount()) if w.t.item(i,0).text()==code)
    return w.t.item(row,11+w._sku_column_ids.index(sid)).text()
   try:
    self.assertEqual(w.t.columnCount(),13);self.assertEqual(value('C',z),'9.0');self.assertEqual(value('Z',z),'1.0');self.assertEqual(value('C',a),'NA');self.assertEqual(value('X',z),'NA')
    w._filters[11]=('',{'9.0'});w.apply_filters()
    main.sort_skus(1);self.assertEqual(w._sku_column_ids,[a,z]);self.assertEqual(standalone._sku_column_ids,[a,z]);self.assertIn(12,w._filters);self.assertEqual(value('C',z),'9.0')
    self.assertEqual(w._column_labels[11],'A1 A');main.refresh();self.assertEqual(w._sku_column_ids,[a,z])
    s.save_bom(ids['P'],[dict(material_id=ids['C'],quantity=2,unit='pcs')]);self.assertEqual(value('C',z),'10.0')
    s.delete_sku(z);self.assertEqual(w._sku_column_ids,[a]);self.assertEqual(w._filters,{})
    new=s.create_sku(ids['X']);self.assertIn(new,w._sku_column_ids);self.assertEqual(value('X',new),'1.0')
   finally:standalone.close();w.close();main.close();db.close()
 def test_decimal_shared_subtree_and_zero_skus(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db);r,p,q,c=[s.create_material(dict(base_code=x,version='1',name=x,unit='pcs')) for x in ('R','P','Q','C')]
   w=MaterialWindow(s)
   try:
    self.assertEqual(w.t.columnCount(),11)
    sid=s.create_sku(r)
    for parent in (p,q):s.save_bom(parent,[dict(material_id=c,quantity=.5,unit='pcs')])
    s.save_bom(r,[dict(material_id=mid,quantity=.5,unit='pcs') for mid in (p,q)])
    self.assertEqual(str(s.sku_material_quantities()[sid][c]),'0.50')
    row=next(i for i in range(w.t.rowCount()) if w.t.item(i,0).text()=='C');self.assertEqual(w.t.item(row,11).text(),'0.5')
   finally:w.close();db.close()
