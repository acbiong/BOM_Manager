import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MaterialSelectionDialog

class BomReplaceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_replace_inherits_draft_properties_alternates_and_save(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids={c:s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('ROOT','OLD','NEW','LAST','ALT','CHILD','CYCLE')}
   s.save_bom(ids['NEW'],[dict(material_id=ids['CHILD'],quantity=2,unit='pcs')])
   s.save_bom(ids['ROOT'],[dict(material_id=ids[c],quantity=1,unit='pcs') for c in ('OLD','LAST')])
   s.save_bom(ids['CYCLE'],[dict(material_id=ids['ROOT'],quantity=1,unit='pcs')])
   w=BomWindow(s,ids['ROOT'])
   try:
    old=w.root_item.child(0);w.show_item_info(old)
    w.fields['quantity'].setValue(3.5);w.fields['position'].setText('位置A');w.fields['remark'].setText('备注\n第二行')
    w._alternate_edits[w.alternate_key(old)]=[ids['ALT']]
    with patch.object(MaterialSelectionDialog,'getItem',return_value=('',False)) as dialog:w.replace_material(old)
    options=dialog.call_args.args[3]
    for code in ('ROOT','OLD','LAST','ALT','CYCLE'):self.assertNotIn(code+'1 '+code,options)
    self.assertEqual(w.root_item.childCount(),2)
    with patch.object(MaterialSelectionDialog,'getItem',return_value=('NEW1 NEW',True)):new=w.replace_material(old)
    self.assertEqual([w.root_item.child(i).data(0,Qt.UserRole)['material_id'] for i in range(3)],[ids[c] for c in ('OLD','NEW','LAST')])
    self.assertTrue(old.data(0,Qt.UserRole)['_deleted']);self.assertTrue(old.font(0).strikeOut());self.assertTrue(new.data(0,Qt.UserRole)['_added'])
    self.assertEqual(new.text(1),'3.5');self.assertEqual(new.text(3),'位置A');self.assertEqual(new.text(4),'备注\n第二行');self.assertEqual(w.alternate_ids(new),[ids['ALT']]);self.assertEqual(w.alternate_ids(old),[ids['ALT']])
    self.assertIs(w.tree.currentItem(),new);self.assertEqual(new.child(0).data(0,Qt.UserRole)['material_id'],ids['CHILD'])
    self.assertEqual(s.bom(ids['ROOT'])[0]['material_id'],ids['OLD'])
    with patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning') as warning:self.assertTrue(w.save());warning.assert_not_called()
    new=w.root_item.child(0);self.assertEqual(new.data(0,Qt.UserRole)['material_id'],ids['NEW']);self.assertEqual(new.text(1),'3.5');self.assertEqual(w.alternate_ids(new),[ids['ALT']]);self.assertEqual(w.root_item.childCount(),2)
   finally:w.dirty=False;w.close();db.close()
 def test_shared_parent_occurrences_replace_consistently(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids={c:s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('R','A','B','P','O','N')}
   for parent,children in [('P',['O']),('A',['P']),('B',['P']),('R',['A','B'])]:s.save_bom(ids[parent],[dict(material_id=ids[c],quantity=1,unit='pcs') for c in children])
   w=BomWindow(s,ids['R'])
   try:
    old=w.root_item.child(0).child(0).child(0)
    with patch.object(MaterialSelectionDialog,'getItem',return_value=('N1 N',True)):w.replace_material(old)
    for branch in range(2):
     parent=w.root_item.child(branch).child(0)
     self.assertTrue(parent.child(0).data(0,Qt.UserRole)['_deleted'])
     self.assertEqual(parent.child(1).data(0,Qt.UserRole)['material_id'],ids['N'])
    with patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning') as warning:self.assertTrue(w.save());warning.assert_not_called()
    for branch in range(2):self.assertEqual(w.root_item.child(branch).child(0).child(0).data(0,Qt.UserRole)['material_id'],ids['N'])
   finally:w.dirty=False;w.close();db.close()
