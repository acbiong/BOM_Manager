import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QDialog,QFileDialog,QMessageBox
from ui.interactive_windows import QFileDialog,QMessageBox
from PyQt5.QtCore import QCoreApplication,QEvent
from config.config_service import ConfigService
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow,ProjectDialog
import main

class FirstLaunchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.config=ConfigService(self.base);self.window=None
 def tearDown(self):
  if self.window:
   self.window.close();self.window.deleteLater()
   if self.window.svc.db is not None:self.window.svc.db.close()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.tmp.cleanup()
 def empty_window(self):
  with patch.object(main,'choose_database_recovery') as recovery,patch.object(main,'Database') as database:
   self.assertIsNone(main.startup_database(self.config,self.config.load()));recovery.assert_not_called();database.assert_not_called()
  self.window=MainWindow(Services(None,self.config));return self.window
 def actions(self,menu):
  result={}
  for action in menu.actions():
   if action.menu():result.update(self.actions(action.menu()))
   else:result[action.text()]=action
  return result
 def test_first_and_second_launch_only_config_no_phantom_project(self):
  w=self.empty_window();w.show();w.refresh();w.toggle_theme()
  self.assertEqual(list(self.base.iterdir()),[self.config.path]);self.assertEqual(w.projects.entries(),[])
  self.assertIsNone(w.svc.db);self.assertEqual(w.table.rowCount(),0);self.assertIn('未打开项目',w.count_label.text())
  actions=self.actions(w.menuBar())
  for title in ('物料库','新建SKU','导出资料库','修改项目信息','BOM对比','筛选','选择SQLite数据库'):self.assertFalse(actions[title].isEnabled())
  for title in ('新增项目','导入项目','导入项目数据库','关于'):self.assertTrue(actions[title].isEnabled())
  with patch.object(main,'choose_database_recovery') as recovery:self.assertIsNone(main.startup_database(self.config,self.config.load()));recovery.assert_not_called()
 def test_new_project_creates_only_selected_database_and_enables_actions(self):
  w=self.empty_window();target=self.base/'项目数据';target.mkdir();db=target/'项目A.sqlite'
  metadata=dict(project_code='A',project_name='项目A',product_name='',product_model='')
  with patch.object(ProjectDialog,'exec_',return_value=QDialog.Accepted),patch.object(ProjectDialog,'data',return_value=metadata),patch.object(QFileDialog,'exec_',return_value=QDialog.Accepted),patch.object(QFileDialog,'selectedFiles',return_value=[str(db)]):w.new_project()
  self.assertEqual(Path(w.svc.db.path),db);self.assertEqual(w.svc.project()['project_name'],'项目A')
  self.assertEqual(list(target.iterdir()),[db]);self.assertFalse((self.base/'bom.db').exists());self.assertEqual(len(w.projects.entries()),1)
  for title in ('物料库','新建SKU','修改项目信息','导出资料库'):self.assertTrue(self.actions(w.menuBar())[title].isEnabled())
  with patch.object(main,'choose_database_recovery') as recovery:
   reopened=main.startup_database(self.config,self.config.load());reopened.close();recovery.assert_not_called()
 def test_cancel_create_and_failed_import_stay_empty(self):
  w=self.empty_window();metadata=dict(project_code='A',project_name='项目A',product_name='',product_model='')
  with patch.object(ProjectDialog,'exec_',return_value=QDialog.Accepted),patch.object(ProjectDialog,'data',return_value=metadata),patch.object(QFileDialog,'exec_',return_value=QDialog.Rejected):w.new_project()
  with patch.object(QMessageBox,'critical'):self.assertFalse(w.switch_project(self.base/'missing.db'))
  self.assertIsNone(w.svc.db);self.assertEqual(w.projects.entries(),[]);self.assertEqual(self.config.load()['database']['path'],'');self.assertEqual(list(self.base.iterdir()),[self.config.path])
 def test_import_existing_database_from_empty_window(self):
  w=self.empty_window();path=self.base/'existing.db';db=Database(str(path));s=Services(db);s.update_project(dict(project_code='OLD',project_name='旧项目'));db.close()
  with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'')):w.import_project_database()
  self.assertEqual(Path(w.svc.db.path),path);self.assertIn('OLD 旧项目',w.windowTitle());self.assertEqual(len(w.projects.entries()),1)
 def test_main_enters_event_loop_without_database_or_recovery_prompt(self):
  def event_loop():
   w=next(w for w in self.app.topLevelWidgets() if isinstance(w,MainWindow) and w.isVisible());self.assertIsNone(w.svc.db);self.assertTrue(w.isVisible());w.close();w.deleteLater();return 0
  with patch.object(main,'QApplication',return_value=self.app),patch.object(main,'app_base',return_value=self.base),patch.object(main,'choose_database_recovery') as recovery,patch.object(self.app,'exec_',side_effect=event_loop),patch.object(main.QMessageBox,'critical') as error:
   self.assertEqual(main.main(),0);recovery.assert_not_called();error.assert_not_called()
  self.assertEqual(list(self.base.iterdir()),[self.config.path])
  manager=self.app._bom_save_shortcuts;del self.app._bom_save_shortcuts;manager.deleteLater()

 def test_saved_projects_visible_on_first_hover_and_open_correct_database(self):
  from config.project_registry import ProjectRegistry
  from PyQt5.QtCore import QPoint
  from PyQt5.QtTest import QTest
  registry=ProjectRegistry(self.config)
  for code in ('OLD1','OLD2'):
   path=self.base/(code+'.db');db=Database(str(path));svc=Services(db)
   svc.update_project(dict(project_code=code,project_name='历史项目'+code))
   svc.create_sku(svc.create_material(dict(base_code=code,version='100',name=code,unit='pcs')))
   registry.remember(path,dict(svc.project()),active=False);db.close()
  w=self.empty_window();w.show();self.app.processEvents()
  self.assertEqual(len(w.history_menu.actions()),2)
  menu=next(a.menu() for a in w.menuBar().actions() if a.text()=='项目')
  menu.popup(QPoint(50,50));QTest.qWait(50)
  QTest.mouseMove(menu,menu.actionGeometry(menu.actions()[0]).center());QTest.qWait(50)
  QTest.mouseMove(menu,menu.actionGeometry(w.history_menu.menuAction()).center());QTest.qWait(500)
  self.assertTrue(w.history_menu.isVisible())
  action=next(a for a in w.history_menu.actions() if a.text().startswith('OLD2 '))
  w.history_menu.close();menu.close();action.trigger()
  self.assertEqual(Path(w.svc.db.path),self.base/'OLD2.db')
  self.assertIn('OLD2 历史项目OLD2',w.windowTitle())
  self.assertEqual(w.table.item(0,1).text(),'OLD2100')
 def test_parent_menu_refreshes_history_created_after_startup(self):
  from PyQt5.QtCore import QPoint
  w=self.empty_window();w.show();self.app.processEvents()
  self.assertEqual(w.history_menu.actions()[0].text(),'暂无历史项目')
  self.assertFalse(w.history_menu.actions()[0].isEnabled())
  w.projects.remember(self.base/'external.db',dict(project_code='NEW',project_name='新增历史项目'),active=False)
  menu=next(a.menu() for a in w.menuBar().actions() if a.text()=='项目')
  menu.popup(QPoint(50,50));self.app.processEvents()
  self.assertEqual([a.text() for a in w.history_menu.actions()],['NEW 新增历史项目'])
  menu.close()
