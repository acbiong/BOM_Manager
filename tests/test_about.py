"""关于窗口与冻结构建元数据回归。"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from infrastructure.build_info import load_build_info, collect_build_info, REPOSITORY_URL
from ui.about_dialog import AboutDialog
from ui.main_window import MainWindow
from database.database import Database
from services.services import Services

class AboutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_frozen_reads_bundled_info_without_git_and_handles_missing(self):
  with tempfile.TemporaryDirectory() as tmp:
   data={'repository':REPOSITORY_URL,'commit':'a'*40,'author':'作者','date':'2026-10-10T12:00:00+08:00','message':'修复\n\n详细信息'}
   Path(tmp,'build_info.json').write_text(json.dumps(data),encoding='utf-8')
   with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',tmp,create=True),patch('infrastructure.build_info.subprocess.check_output') as git:
    self.assertEqual(load_build_info(),data);git.assert_not_called()
    Path(tmp,'build_info.json').write_text('bad',encoding='utf-8')
    self.assertEqual(load_build_info()['repository'],REPOSITORY_URL)
 def test_menu_opens_dialog_and_displays_version_commit_copyright(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));w=MainWindow(Services(db),'1.2.3')
   try:
    action=next(a for a in w.menuBar().actions() if a.text()=='关于')
    with patch('ui.main_window.AboutDialog') as dialog:
     action.trigger();dialog.assert_called_once_with('1.2.3',w);dialog.return_value.exec_.assert_called_once()
    info={'repository':REPOSITORY_URL,'commit':'b'*40,'author':'Biong','date':'2026-10-10','message':'说明\n第二行'}
    with patch('ui.about_dialog.load_build_info',return_value=info):d=AboutDialog('1.2.3',w)
    try:
     self.assertEqual(d.labels['name'].text(),'BOM管理系统');self.assertEqual(d.labels['version'].text(),'1.2.3');self.assertEqual(d.labels['commit'].text(),info['commit']);self.assertEqual(d.labels['message'].text(),info['message']);self.assertIn('Biong & BrainCo Inc.',d.labels['copyright'].text());self.assertTrue(d.labels['repository'].openExternalLinks())
    finally:d.close()
   finally:w.close();db.close()
 def test_source_repository_information(self):
  info=collect_build_info(Path(__file__).parents[1]);self.assertEqual(info['repository'],REPOSITORY_URL);self.assertEqual(len(info['commit']),40);self.assertTrue(info['message'])
