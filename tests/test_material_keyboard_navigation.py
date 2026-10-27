import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication,QComboBox,QDialog
from PyQt5.QtCore import Qt,QModelIndex
from PyQt5.QtTest import QTest
from database.database import Database
from services.services import Services
from ui.main_window import MaterialSelectionDialog,NewSkuDialog

class MaterialKeyboardNavigationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_filtered_down_up_from_editor_popup_and_viewport_then_confirm(self):
  for source in ('editor','combo','popup','viewport'):
   with self.subTest(source=source):
    def exercise(dialog):
     dialog.show();combo=dialog.findChild(QComboBox);edit=combo.lineEdit();edit.setFocus();self.app.processEvents();QTest.keyClicks(edit,'part');self.app.processEvents()
     popup=combo.completer().popup();popup.setCurrentIndex(QModelIndex())
     target={'editor':edit,'combo':combo,'popup':popup,'viewport':popup.viewport()}[source]
     for expected in (0,1,2,2):
      QTest.keyClick(target,Qt.Key_Down);self.app.processEvents();self.assertEqual(popup.currentIndex().row(),expected)
      self.assertEqual(edit.text(),'part');self.assertEqual(popup.model().rowCount(),3)
     QTest.keyClick(target,Qt.Key_Up);self.assertEqual(popup.currentIndex().row(),1)
     QTest.keyClick(target,Qt.Key_Return);self.assertEqual(dialog.result(),QDialog.Accepted);return dialog.result()
    with patch.object(MaterialSelectionDialog,'exec_',exercise):
     self.assertEqual(MaterialSelectionDialog.getItem(None,'选择物料','物料',['OTHER','PART1 one','PART2 two','PART3 three']),('PART2 two',True))
 def test_sku_navigation_skips_disabled_and_retyping_refilters(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids=[s.create_material(dict(base_code=x,version='100',name='match',unit='pcs')) for x in 'ABCD']
   s.create_sku(ids[0]);s.create_sku(ids[2]);d=NewSkuDialog(s);d.show()
   try:
    e=d.combo.lineEdit();e.setFocus();self.app.processEvents();QTest.keyClicks(e,'match');self.app.processEvents();popup=d.completer.popup();popup.setCurrentIndex(QModelIndex())
    QTest.keyClick(e,Qt.Key_Down);self.assertTrue(popup.currentIndex().data().startswith('B100'))
    QTest.keyClick(e,Qt.Key_Down);self.assertTrue(popup.currentIndex().data().startswith('D100'))
    QTest.keyClick(popup,Qt.Key_Up);self.assertTrue(popup.currentIndex().data().startswith('B100'))
    e.selectAll();QTest.keyClicks(e,'missing');self.app.processEvents();QTest.keyClick(e,Qt.Key_Down);self.assertEqual(e.text(),'missing');self.assertNotEqual(d.result(),QDialog.Accepted)
    e.selectAll();QTest.keyClicks(e,'D100');self.app.processEvents();QTest.keyClick(e,Qt.Key_Down);QTest.keyClick(e,Qt.Key_Return)
    self.assertEqual(d.material_id,ids[3]);self.assertEqual(d.result(),QDialog.Accepted)
   finally:d.close();d.deleteLater();db.close()
