import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QDialog
from PyQt5.QtCore import QEvent
from database.database import Database
from services.services import Services
from ui.main_window import MaterialWindow,CreateMaterialDialog

class DuplicateFeedbackTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.s.create_material(dict(base_code='PART',version='100',name='已有',unit='pcs'))
  self.owner=MaterialWindow(self.s);self.d=CreateMaterialDialog(self.owner);self.d.show();self.app.processEvents()
 def tearDown(self):
  self.d.close();self.owner.close();self.d.deleteLater();self.owner.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.db.close();self.tmp.cleanup()
 def test_immediate_feedback_for_both_fields_and_clear(self):
  d=self.d;self.assertEqual(d.duplicate_notice.text(),'')
  d.e['base_code'].setText(' PART ');self.assertEqual(d.duplicate_notice.text(),'')
  d.e['version'].setText('100 ')
  self.assertIn('已经存在',d.duplicate_notice.text())
  for key in ('base_code','version'):self.assertIn('background-color:#f8d7da',d.e[key].styleSheet())
  d.e['version'].setText('101');self.assertEqual(d.duplicate_notice.text(),'')
  for key in ('base_code','version'):self.assertEqual(d.e[key].styleSheet(),d._identity_styles[key])
  d.e['version'].setText('100');self.assertTrue(d.check_duplicate_code())
  d.e['base_code'].clear();self.assertFalse(d.check_duplicate_code());self.assertEqual(d.duplicate_notice.text(),'')
 def test_save_rechecks_and_allows_new_identity(self):
  d=self.d;d.e['base_code'].setText('NEW');d.e['version'].setText('100');d.e['name'].setText('新物料')
  self.s.create_material(dict(base_code='NEW',version='100',name='其他窗口已建',unit='pcs'))
  d.accept();self.assertNotEqual(d.result(),QDialog.Accepted);self.assertTrue(d.isVisible());self.assertTrue(d.check_duplicate_code())
  d.e['version'].setText('101');self.assertEqual(d.duplicate_notice.text(),'');d.accept();self.assertEqual(d.result(),QDialog.Accepted)
  self.assertEqual(self.db.conn.execute("SELECT count(*) FROM materials WHERE base_code='NEW'").fetchone()[0],2)
