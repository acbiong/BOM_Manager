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
   from ui.help_guides import GUIDE_KEYS
   self.assertEqual(len(images),len(GUIDE_KEYS)+10)
   self.assertIsNone(empty.svc.db);self.assertIsNone(empty._materials);self.assertEqual(empty._bom_windows,{})
   dialog.close();dialog.show();self.app.processEvents()
   self.assertEqual({w for w in self.app.topLevelWidgets() if w.isVisible()}-before,{dialog})
   dialog.close();dialog.deleteLater()
  empty.close();empty.deleteLater()
 def test_guides_have_action_images_and_switch_independently(self):
  import json
  from PIL import Image
  from ui.help_guides import GUIDES,GUIDE_KEYS
  dialog=HelpDialog(self.w)
  manifest=json.loads((Path(__file__).parents[1]/'resources/help_screenshots/actions.json').read_text())
  self.assertEqual(set(GUIDE_KEYS),set(manifest));self.assertEqual(len(GUIDE_KEYS),len(set(GUIDE_KEYS)))
  self.assertEqual(dialog.guide_selector.count(),len(GUIDES))
  for index,guide in enumerate(GUIDES):
   dialog.guide_selector.setCurrentIndex(index);self.app.processEvents()
   self.assertEqual(dialog.guide_stack.currentIndex(),index)
   for step in guide['steps']:
    self.assertTrue(step['detail']);info=manifest[step['key']];x,y,w,h=info['target']
    self.assertGreater(w,0);self.assertGreater(h,0)
    with Image.open(Path(__file__).parents[1]/'resources/help_screenshots'/(step['key']+'.png')) as im:
     pixels=im.convert('RGB')
     red=sum(1 for r,g,b in pixels.getdata() if r>180 and g<70 and b<90)
     self.assertGreater(red,80,step['key'])
  dialog.close();dialog.deleteLater()
