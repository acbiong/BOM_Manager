import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox
from openpyxl import load_workbook
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow

class BomStateHistoryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_expansion_save_refresh_reopen_and_export_history(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids=[s.create_material(dict(base_code=code,version='1',name=code,unit='pcs')) for code in ['R','P','C','OTHER']]
   root,parent,child,other=ids
   def rows(qty):return [dict(material_id=parent,quantity=1,unit='pcs'),dict(parent_material_id=parent,material_id=child,quantity=qty,unit='pcs',remark='备注')]
   s.save_bom(root,rows(1));sid=s.create_sku(root);s.save_bom(other,rows(1));other_sid=s.create_sku(other)
   window=BomWindow(s,root)
   try:
    window.root_item.child(0).setExpanded(True);window.root_item.setExpanded(False)
    window.show_item_info(window.root_item.child(0).child(0));window.fields['quantity'].setValue(3.5)
    with patch.object(QMessageBox,'information'):self.assertTrue(window.save())
    self.assertFalse(window.root_item.isExpanded());self.assertTrue(window.root_item.child(0).isExpanded())
    s.save_bom(root,rows(4.5));window.refresh_external()
    self.assertFalse(window.root_item.isExpanded());self.assertTrue(window.root_item.child(0).isExpanded())
    window.close();window=BomWindow(s,root)
    self.assertFalse(window.root_item.isExpanded());self.assertTrue(window.root_item.child(0).isExpanded())
    for current_sid in [sid,other_sid]:
     path=Path(tmp)/(str(current_sid)+'.xlsx');s.export_sku(current_sid,path);wb=load_workbook(path)
     details='\n'.join(str(row[-1] or '') for row in list(wb['变更记录'].values)[1:]);wb.close()
     self.assertIn('数量：1.0 → 3.5',details);self.assertIn('数量：3.5 → 4.5',details)
    count=db.conn.execute("SELECT COUNT(*) FROM change_logs WHERE object_type='bom'").fetchone()[0]
    s.save_bom(root,rows(4.5));self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM change_logs WHERE object_type='bom'").fetchone()[0],count)
   finally:window.dirty=False;window.close();db.close()
