import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor
from openpyxl import load_workbook
from database.database import Database
from services.services import Services
from ui.main_window import MaterialWindow

class AlternateIdleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_alternate_only_usage_ui_export_and_last_reference(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids={code:s.create_material(dict(base_code=code,version='1',name=code,unit='pcs')) for code in ['SKU','P','C','ALT','OTHER']}
   s.create_sku(ids['SKU']);window=MaterialWindow(s)
   def row(parent,child,alts):return dict(parent_material_id=ids[parent],material_id=ids[child],quantity=1,unit='pcs',alternate_material_ids=[ids[a] for a in alts])
   def flag():return next(r['idle'] for r in s.materials() if r['id']==ids['ALT'])
   try:
    self.assertEqual(flag(),'Y')
    s.save_bom(ids['SKU'],[row('SKU','P',[]),row('P','C',['ALT'])]);self.assertEqual(flag(),'N')
    index=next(i for i in range(window.t.rowCount()) if window.t.item(i,0).text()=='ALT')
    self.assertEqual(window.t.item(index,10).text(),'N');self.assertNotEqual(window.t.item(index,0).background().color(),QColor('red'))
    with self.assertRaisesRegex(ValueError,'替代料'):s.delete_material(ids['ALT'])
    path=Path(tmp)/'out.xlsx';s.export_materials(path);wb=load_workbook(path)
    self.assertEqual(next(r[-1] for r in list(wb['物料库'].values)[1:] if r[1]=='ALT'),'N');wb.close()
    s.save_bom(ids['OTHER'],[row('OTHER','C',['ALT'])])
    s.save_bom(ids['SKU'],[row('SKU','P',[]),row('P','C',[])]);self.assertEqual(flag(),'N')
    s.save_bom(ids['OTHER'],[row('OTHER','C',[])]);self.assertEqual(flag(),'Y')
    self.assertEqual(window.t.item(index,0).background().color(),QColor('red'))
    # 失去父关系的历史孤儿引用不能让物料误判为非呆滞。
    db.conn.execute('INSERT INTO alternates(bom_item_id,material_id,sort_no) VALUES(99999,?,0)',(ids['ALT'],));db.conn.commit();self.assertEqual(flag(),'Y')
   finally:window.close();db.close()
