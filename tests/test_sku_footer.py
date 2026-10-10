import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow

class SkuFooterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_footer_all_information_stays_visible_after_mouse_status_changes(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db);mid=s.create_material(dict(base_code='R',version='1',name='SKU',unit='pcs'));s.create_sku(mid);w=MainWindow(s)
   try:
    self.assertEqual(w.count_label.text(),'共计1个SKU');self.assertEqual(w.power_label.text(),'Powered by Biong & BrainCo Inc.');self.assertEqual(w.version_label.text(),'版本 '+w.version)
    footer=w.count_label.parentWidget();self.assertIs(footer,w.power_label.parentWidget());self.assertIs(footer,w.version_label.parentWidget());self.assertEqual(footer.layout().count(),5)
    w.statusBar().showMessage('鼠标移动后的临时提示');self.app.processEvents();self.assertEqual(w.count_label.text(),'共计1个SKU');self.assertEqual(w.power_label.text(),'Powered by Biong & BrainCo Inc.')
    s.create_material(dict(base_code='S',version='1',name='SKU2',unit='pcs'));s.create_sku(2);w.refresh();self.assertEqual(w.count_label.text(),'共计2个SKU')
   finally:w.close();db.close()
