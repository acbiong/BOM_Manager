import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from config.config_service import ConfigService
from config.project_registry import ProjectRegistry
import shutil
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from ui.help_dialog import HelpDialog

class HelpDialogTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db,ConfigService(self.tmp.name));self.w=MainWindow(self.s);self.w.show();self.app.processEvents()
 def tearDown(self):
  if getattr(self.w,'_help_dialog',None):self.w._help_dialog.close()
  self.w.close();self.db.close();self.tmp.cleanup()
 def test_help_menu_is_before_about_and_opens_five_sections(self):
  labels=[a.text() for a in self.w.menuBar().actions()];self.assertLess(labels.index('帮助'),labels.index('关于'))
  self.w.show_help();self.app.processEvents();dialog=self.w._help_dialog
  self.assertTrue(dialog.isVisible())
  from PyQt5.QtWidgets import QTabWidget
  tabs=dialog.findChildren(QTabWidget)[0]
  self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],['快捷键','页面与功能','操作指引','操作技巧','Q&A'])
  self.assertEqual(dialog.windowModality(),0)
  # 页面说明、10步操作指引和6项技巧均应包含截图框。
  self.assertGreaterEqual(len(dialog.findChildren(__import__('PyQt5.QtWidgets',fromlist=['QLabel']).QLabel)),20)

 def test_empty_current_project_uses_config_database_for_real_screenshots(self):
  self.w.close();self.db.close()
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp); source=Path('/home/biong/Documents/BOM/数据库/mobius_lite_bom.db');shutil.copy2(source,base/'db')
   config=ConfigService(base); db=Database(str(base/'db'));svc=Services(db,config);metadata=dict(svc.project());db.close();ProjectRegistry(config).remember(base/'db',metadata)
   empty=MainWindow(Services(None,config));empty.show();self.app.processEvents();help_window=HelpDialog(empty);self.app.processEvents()
   self.assertIsNotNone(help_window._demo_main);self.assertEqual(help_window._demo_main.table.rowCount(),5);self.assertTrue(help_window._demo_main._materials.isVisible());self.assertTrue(bool(help_window._demo_main._bom_windows))
   help_window.close();empty.close();empty.deleteLater()
