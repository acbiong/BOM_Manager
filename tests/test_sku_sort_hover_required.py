import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from openpyxl import Workbook
from database.database import Database
from services.services import Services,MATERIAL_IMPORT_HEADERS
from ui.main_window import MainWindow,MaterialHeaderMappingDialog
from ui.theme import apply_theme

class SortHoverRequiredTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_sku_sort_refresh_and_open_identity(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   for code,name,date in [('Z','Alpha','2026-01-01 01:00:00'),('A','Zulu','2026-03-01 01:00:00'),('B','Beta','2026-02-01 01:00:00')]:
    mid=s.create_material(dict(base_code=code,version='1',name=name,unit='pcs'));s.create_sku(mid);db.conn.execute('UPDATE materials SET updated_at=? WHERE id=?',(date,mid))
   db.conn.commit();w=MainWindow(s)
   try:
    for col in (1,2,4,5):
     w.table.horizontalHeader().sectionClicked.emit(col)
     values=[w.table.item(i,col).text() for i in range(3)];self.assertEqual(values,sorted(values))
     w.table.horizontalHeader().sectionClicked.emit(col);w.refresh()
     values=[w.table.item(i,col).text() for i in range(3)];self.assertEqual(values,sorted(values,reverse=True))
     for i in range(3):
      sid=int(w.table.item(i,6).text())
      with patch.object(w,'open_bom_id') as opened:w.table.cellWidget(i,0).click();opened.assert_called_once_with(sid)
    previous=w._sku_sort;w.sort_skus(0);self.assertEqual(w._sku_sort,previous)
   finally:w.close();db.close()
 def test_required_stars_do_not_change_mapping_keys(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'a.xlsx';wb=Workbook();wb.active.append(MATERIAL_IMPORT_HEADERS);wb.save(path);wb.close()
   for required in (None,Services.BOM_HEADERS):
    fields=required or MATERIAL_IMPORT_HEADERS;dialog=MaterialHeaderMappingDialog(path,fields,[],required=required)
    try:
     if required:dialog.add_alternate_mapping()
     for i,field in enumerate(dialog.required):
      self.assertEqual(dialog.mapping_table.item(0,i).text().endswith(' *'),field not in dialog.optional)
      self.assertIn(field,dialog.mapping())
    finally:dialog.close()
 def test_hover_changes_pixels_in_both_themes(self):
  for dark in (False,True):
   apply_theme(dark);button=QPushButton('可点击');button.resize(150,45);button.show();self.app.processEvents()
   try:
    QTest.mouseMove(button,button.rect().bottomRight()+__import__('PyQt5.QtCore',fromlist=['QPoint']).QPoint(20,20));self.app.processEvents();before=button.grab().toImage()
    QTest.mouseMove(button,button.rect().center());self.app.processEvents();after=button.grab().toImage()
    self.assertNotEqual(before,after)
    self.assertIn(':enabled:hover',self.app.styleSheet())
   finally:button.close()
  apply_theme(False)
