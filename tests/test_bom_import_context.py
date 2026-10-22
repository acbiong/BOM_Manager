import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QFileDialog,QMessageBox,QDialog
from ui.interactive_windows import QFileDialog,QMessageBox
from openpyxl import Workbook
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MaterialHeaderMappingDialog,MainWindow

class BomContextImportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_context_import_child_root_and_toolbar_export_state(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   root,parent,child=[s.create_material(dict(base_code=x,version='1',name=x,unit='pcs')) for x in ['R','P','C']]
   s.save_bom(root,[dict(material_id=parent,quantity=1,unit='pcs')]);s.create_sku(root)
   file=Path(tmp)/'in.xlsx';wb=Workbook();ws=wb.active;ws.append(s.BOM_HEADERS);ws.append(['ROOT','ROOT','P','1',None,None]);ws.append(['P','1','C','1',2,'位置']);wb.save(file);wb.close()
   window=BomWindow(s,root);child_item=window.root_item.child(0)
   try:
    self.assertTrue(window.export_action.isEnabled())
    with patch.object(MaterialHeaderMappingDialog,'exec_',return_value=QDialog.Accepted),patch.object(QFileDialog,'getOpenFileName',return_value=(str(file),'')),patch.object(QMessageBox,'information'):
     window.import_bom(child_item)
    self.assertTrue(window.dirty);self.assertFalse(window.export_action.isEnabled());self.assertEqual(child_item.childCount(),1);self.assertEqual(child_item.child(0).text(3),'位置');self.assertEqual(s.bom(root)[0]['material_id'],parent)
    with patch.object(QMessageBox,'information'):self.assertTrue(window.save())
    self.assertTrue(window.export_action.isEnabled());self.assertEqual(s.bom(parent)[0]['material_id'],child)
   finally:window.dirty=False;window.close();db.close()
 def test_theme_footer_and_no_import_toolbar_action(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db);mid=s.create_material(dict(base_code='R',version='1',name='SKU',unit='pcs'));s.create_sku(mid);window=BomWindow(s,mid);main=MainWindow(s)
   try:
    self.assertEqual(main.version_label.text(),'版本 '+main.version)
    self.assertFalse(any(a.text()=='导入BOM' for a in window.findChildren(__import__('PyQt5.QtWidgets',fromlist=['QAction']).QAction)))
    self.assertEqual(window.export_action.text(),'导出BOM')
   finally:window.close();main.close();db.close()
