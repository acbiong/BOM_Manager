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
  self.assertEqual(dialog.windowModality(),0)
  # 页面说明、10步操作指引和6项技巧均应包含截图框。
  self.assertGreaterEqual(len(dialog.findChildren(__import__('PyQt5.QtWidgets',fromlist=['QLabel']).QLabel)),20)

 def test_static_help_without_project_opens_no_other_windows(self):
  from unittest.mock import patch
  from PyQt5.QtWidgets import QLabel
  empty=MainWindow(Services(None,ConfigService(self.tmp.name)));empty.show();self.app.processEvents()
  before={w for w in self.app.topLevelWidgets() if w.isVisible()}
  with patch.object(Database,'__init__',side_effect=AssertionError('运行时帮助不能打开数据库')),patch.object(MainWindow,'show_materials',side_effect=AssertionError('不能打开物料库')),patch.object(MainWindow,'open_bom_id',side_effect=AssertionError('不能打开BOM')):
   dialog=HelpDialog(empty);dialog.show();self.app.processEvents()
   self.assertEqual({w for w in self.app.topLevelWidgets() if w.isVisible()}-before,{dialog})
   images=[label for label in dialog.findChildren(QLabel) if label.pixmap() is not None and not label.pixmap().isNull()]
   self.assertEqual(len(images),20)
   self.assertIsNone(empty.svc.db);self.assertIsNone(empty._materials);self.assertEqual(empty._bom_windows,{})
   dialog.close();dialog.show();self.app.processEvents()
   self.assertEqual({w for w in self.app.topLevelWidgets() if w.isVisible()}-before,{dialog})
   dialog.close();dialog.deleteLater()
  empty.close();empty.deleteLater()
 def test_step_ten_uses_search_image(self):
  from unittest.mock import patch
  dialog=HelpDialog(self.w)
  with patch.object(dialog,'_image_widget') as render:
   dialog._guide_image('步骤10：查找和故障处理')
   self.assertEqual(render.call_args.args[0],'step10_search')
  dialog.close();dialog.deleteLater()
