import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox,QDialog
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MaterialSelectionDialog,ReplacementSelectionDialog

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
    with patch.object(MaterialSelectionDialog,'getItem',return_value=('N1 N',True)),patch.object(ReplacementSelectionDialog,'exec_',return_value=QDialog.Accepted):w.replace_material(old)
    for branch in range(2):
     parent=w.root_item.child(branch).child(0)
     self.assertTrue(parent.child(0).data(0,Qt.UserRole)['_deleted'])
     self.assertEqual(parent.child(1).data(0,Qt.UserRole)['material_id'],ids['N'])
    with patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning') as warning:self.assertTrue(w.save());warning.assert_not_called()
    for branch in range(2):self.assertEqual(w.root_item.child(branch).child(0).child(0).data(0,Qt.UserRole)['material_id'],ids['N'])
   finally:w.dirty=False;w.close();db.close()
 def test_choose_occurrences_cancel_partial_and_inherit_each_relation(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids={c:s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('R','A','B','C','D','O','N','ALT1','ALT2')}
   for number,parent in enumerate(('A','B','C','D'),1):
    children=[dict(material_id=ids['O'],quantity=number,unit='pcs',position=parent,remark='备注'+parent)]
    if parent=='D':children.append(dict(material_id=ids['N'],quantity=1,unit='pcs'))
    s.save_bom(ids[parent],children)
   for parent,alt in [('A','ALT1'),('B','ALT2')]:s.add_alternate(s.bom(ids[parent])[0]['id'],ids[alt])
   s.save_bom(ids['R'],[dict(material_id=ids[c],quantity=1,unit='pcs') for c in ('A','B','C','D')])
   w=BomWindow(s,ids['R'])
   try:
    old=w.root_item.child(0).child(0)
    with patch.object(MaterialSelectionDialog,'getItem',return_value=('N1 N',True)),patch.object(ReplacementSelectionDialog,'exec_',return_value=QDialog.Rejected):w.replace_material(old)
    self.assertFalse(w.dirty)
    def choose(dialog):
     self.assertEqual(len(dialog.groups),4)
     self.assertEqual(dialog.table.item(0,0).checkState(),Qt.Checked)
     self.assertEqual(dialog.table.item(1,0).checkState(),Qt.Unchecked)
     self.assertIn('已存在相同物料',dialog.groups[3]['reason'])
     self.assertFalse(dialog.table.item(3,0).flags() & Qt.ItemIsEnabled)
     dialog.table.item(1,0).setCheckState(Qt.Checked)
     return QDialog.Accepted
    with patch.object(MaterialSelectionDialog,'getItem',return_value=('N1 N',True)),patch.object(ReplacementSelectionDialog,'exec_',choose):w.replace_material(old)
    for index in (0,1):
     parent=w.root_item.child(index);new=parent.child(1)
     self.assertTrue(parent.child(0).data(0,Qt.UserRole)['_deleted']);self.assertEqual(new.text(1),f'{index+1}')
     self.assertEqual(new.text(3),('A','B')[index]);self.assertEqual(w.alternate_ids(new),[ids[('ALT1','ALT2')[index]]])
    for index in (2,3):self.assertFalse(w.root_item.child(index).child(0).data(0,Qt.UserRole).get('_deleted',False))
    with patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning') as warning:self.assertTrue(w.save());warning.assert_not_called()
    for parent in ('A','B'):self.assertEqual(s.bom(ids[parent])[0]['material_id'],ids['N'])
    for parent in ('C','D'):self.assertEqual(s.bom(ids[parent])[0]['material_id'],ids['O'])
   finally:w.dirty=False;w.close();db.close()
