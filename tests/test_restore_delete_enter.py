import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication,QMessageBox,QComboBox,QDialog
from PyQt5.QtTest import QTest
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MaterialSelectionDialog,NewSkuDialog

class RestoreEnterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_nested_delete_restore_preserves_previous_delete_and_edits(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   r,p,c,a=[s.create_material(dict(base_code=x,version='1',name=x,unit='pcs')) for x in ('R','P','C','A')]
   s.save_bom(p,[dict(material_id=c,quantity=2,unit='pcs')]);s.save_bom(r,[dict(material_id=p,quantity=1,unit='pcs')]);w=BomWindow(s,r)
   try:
    parent=w.root_item.child(0);child=parent.child(0);w.show_item_info(parent);w.fields['remark'].setText('保留备注');w._alternate_edits[w.alternate_key(parent)]=[a]
    w.remove_relation(child);w.remove_relation(parent);w.restore_relation(parent)
    self.assertFalse(parent.data(0,Qt.UserRole)['_deleted']);self.assertTrue(child.data(0,Qt.UserRole)['_deleted'])
    w.restore_relation(child);self.assertFalse(child.font(0).strikeOut());self.assertEqual(parent.text(4),'保留备注');self.assertEqual(w.alternate_ids(parent),[a]);self.assertEqual(w._deleted_relations,set())
    w.remove_relation(parent);w.restore_relation(child);self.assertFalse(parent.data(0,Qt.UserRole)['_deleted'])
    with patch.object(QMessageBox,'information'):self.assertTrue(w.save())
    self.assertEqual(w.root_item.child(0).text(4),'保留备注');self.assertEqual(w.root_item.child(0).childCount(),1)
   finally:w.dirty=False;w.close();db.close()
 def test_enter_selects_first_match_without_accepting_and_skips_disabled(self):
  def exercise(dialog):
   combo=dialog.findChild(QComboBox);combo.lineEdit().setText('b')
   QTest.keyClick(combo.lineEdit(),Qt.Key_Return);self.assertEqual(combo.currentText(),'B1 Beta')
   self.assertNotEqual(dialog.result(),QDialog.Accepted)
   combo.lineEdit().setText('missing');QTest.keyClick(combo.lineEdit(),Qt.Key_Return);self.assertEqual(combo.currentText(),'missing')
   return QDialog.Rejected
  with patch.object(MaterialSelectionDialog,'exec_',exercise):MaterialSelectionDialog.getItem(None,'选择','物料',['A1 Alpha','B1 Beta','B2 Beta'])
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   a=s.create_material(dict(base_code='A',version='1',name='match',unit='pcs'));b=s.create_material(dict(base_code='B',version='1',name='match',unit='pcs'));s.create_sku(a)
   d=NewSkuDialog(s)
   try:
    d.combo.lineEdit().setText('match');QTest.keyClick(d.combo.lineEdit(),Qt.Key_Return);self.assertEqual(d.combo.currentText(),'B1 match');self.assertNotEqual(d.result(),QDialog.Accepted)
   finally:d.close();db.close()

 def test_enter_confirms_preselected_material_and_keypad_enter(self):
  for key in (Qt.Key_Return,Qt.Key_Enter):
   def exercise(dialog):
    combo=dialog.findChild(QComboBox);combo.setCurrentIndex(1)
    QTest.keyClick(combo.lineEdit(),key)
    self.assertEqual(dialog.result(),QDialog.Accepted)
    return dialog.result()
   with patch.object(MaterialSelectionDialog,'exec_',exercise):
    self.assertEqual(MaterialSelectionDialog.getItem(None,'选择','物料',['A1 Alpha','B1 Beta']),('B1 Beta',True))
 def test_sku_second_enter_confirms_first_filtered_candidate(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   mid=s.create_material(dict(base_code='B',version='1',name='match',unit='pcs'))
   d=NewSkuDialog(s)
   try:
    d.combo.lineEdit().setText('match');QTest.keyClick(d.combo.lineEdit(),Qt.Key_Return)
    self.assertNotEqual(d.result(),QDialog.Accepted)
    QTest.keyClick(d.combo.lineEdit(),Qt.Key_Return)
    self.assertEqual(d.result(),QDialog.Accepted);self.assertEqual(d.material_id,mid)
   finally:d.close();db.close()

 def test_enter_confirms_highlighted_completion_not_first_match(self):
  def exercise(dialog):
   dialog.show();combo=dialog.findChild(QComboBox);combo.lineEdit().setText('Beta')
   completer=combo.completer();completer.setCompletionPrefix('Beta');completer.complete()
   popup=completer.popup();popup.setCurrentIndex(completer.completionModel().index(1,0))
   QTest.keyClick(popup,Qt.Key_Return)
   self.assertEqual(dialog.result(),QDialog.Accepted)
   return dialog.result()
  with patch.object(MaterialSelectionDialog,'exec_',exercise):
   self.assertEqual(MaterialSelectionDialog.getItem(None,'选择','物料',['B1 Beta','B2 Beta']),('B2 Beta',True))
