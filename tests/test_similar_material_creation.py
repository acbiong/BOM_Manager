import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMenu,QMessageBox
from PyQt5.QtCore import QPoint,QEvent,QCoreApplication
from database.database import Database
from services.services import Services
from ui.main_window import MaterialWindow,show_create_material

class SimilarMaterialCreationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.values=dict(base_code='PART',version='101',name='测试物料',description='规格\n第二行',unit='pcs',grade='工业级',manufacturer='厂商',mpn='MPN-01',mp_flag='P')
  self.source=self.s.create_material(self.values);self.library=MaterialWindow(self.s);self.library.show()
 def tearDown(self):
  self.library.close();self.library.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.db.close();self.tmp.cleanup()
 def open_similar(self):
  row=next(i for i,m in enumerate(self.s.materials()) if m['id']==self.source)
  def choose(menu,pos):return next(a for a in menu.actions() if a.text()=='类似新增物料')
  with patch.object(self.library.t,'rowAt',return_value=row),patch.object(QMenu,'exec_',choose):self.library.menu(QPoint())
  return self.library._create_material_dialog
 def test_prefill_validate_create_and_refresh_without_changing_source(self):
  before=self.s.material_snapshot(self.source);dialog=self.open_similar()
  self.assertFalse(dialog.isModal());self.assertEqual(dialog.data(),dict(self.values,base_code='',version=''))
  self.assertEqual(len(self.s.materials()),1)
  with patch.object(QMessageBox,'warning') as warning:dialog.accept();warning.assert_called_once()
  self.assertTrue(dialog.isVisible());dialog.e['base_code'].setText('NEW');dialog.e['version'].setText('100');dialog.accept()
  self.assertEqual(self.library.t.rowCount(),2);self.assertEqual(self.s.material_snapshot(self.source),before)
  created=next(m for m in self.s.materials() if m['base_code']=='NEW')
  self.assertEqual({k:created[k] for k in self.values},dict(self.values,base_code='NEW',version='100'))
  self.assertEqual(created['has_bom'],'N')
 def test_existing_draft_requires_confirmation_and_cancel_never_writes(self):
  draft=show_create_material(self.library);draft.e['name'].setText('正在编辑')
  with patch.object(QMessageBox,'question',return_value=QMessageBox.No):self.assertIs(self.open_similar(),draft)
  self.assertEqual(draft.e['name'].text(),'正在编辑')
  with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):new=self.open_similar()
  self.assertIsNot(new,draft);self.assertFalse(draft.isVisible());self.assertEqual(new.data()['name'],self.values['name'])
  new.reject();self.assertEqual(len(self.s.materials()),1);self.assertIsNone(self.library._create_material_dialog)
 def test_uses_latest_attributes_and_does_not_mutate_prefill_dictionary(self):
  self.s.update_material(self.source,dict(self.values,name='已更新名称'))
  dialog=self.open_similar();self.assertEqual(dialog.data()['name'],'已更新名称');dialog.reject()
  original=self.s.material_snapshot(self.source);show_create_material(self.library,data=original)
  self.assertEqual(original['base_code'],'PART');self.assertEqual(original['version'],'101')
