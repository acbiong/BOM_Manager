import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QPoint
from PyQt5.QtWidgets import QApplication,QMessageBox,QMenu
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow

class PromoteAlternateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_context_swap_inherits_cache_preserves_other_alternates_and_save(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids={c:s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('R','OLD','NEW','ALT','EXTRA','CHILD')}
   s.save_bom(ids['R'],[dict(material_id=ids['OLD'],quantity=1,unit='pcs')])
   s.save_bom(ids['NEW'],[dict(material_id=ids['CHILD'],quantity=2,unit='pcs')])
   relation=s.bom(ids['R'])[0]['id']
   for code in ('ALT','NEW'):s.add_alternate(relation,ids[code])
   w=BomWindow(s,ids['R'])
   try:
    old=w.root_item.child(0);w.show_item_info(old)
    w.fields['quantity'].setValue(4.5);w.fields['position'].setText('P');w.fields['remark'].setText('备注\n第二行')
    w._alternate_edits[w.alternate_key(old)]=[ids[c] for c in ('ALT','NEW','EXTRA')];w.show_item_info(old)
    def choose(menu,*args):return next(a for a in menu.actions() if a.text()=='切换成主物料')
    with patch.object(w.alt_table,'rowAt',return_value=1),patch.object(QMenu,'exec_',choose):w.alternate_menu(QPoint())
    new=w.tree.currentItem();self.assertEqual(new.data(0,Qt.UserRole)['material_id'],ids['NEW'])
    self.assertTrue(old.data(0,Qt.UserRole)['_deleted']);self.assertEqual(new.text(1),'4.5');self.assertEqual(new.text(3),'P');self.assertEqual(new.text(4),'备注\n第二行')
    self.assertEqual(w.alternate_ids(new),[ids[c] for c in ('ALT','OLD','EXTRA')])
    self.assertEqual(new.child(0).data(0,Qt.UserRole)['material_id'],ids['CHILD'])
    self.assertEqual(s.bom(ids['R'])[0]['material_id'],ids['OLD'])
    with patch.object(QMessageBox,'information'):self.assertTrue(w.save())
    new=w.root_item.child(0);self.assertEqual(new.text(1),'4.5');self.assertEqual(w.alternate_ids(new),[ids[c] for c in ('ALT','OLD','EXTRA')]);self.assertEqual(w.root_item.childCount(),1)
   finally:w.dirty=False;w.close();db.close()
 def test_cycle_and_duplicate_promotions_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   r,a,b=[s.create_material(dict(base_code=c,version='1',name=c,unit='pcs')) for c in ('R','A','B')]
   s.save_bom(r,[dict(material_id=m,quantity=1,unit='pcs') for m in (a,b)])
   relation=s.bom(r)[0]['id'];s.add_alternate(relation,r);s.add_alternate(relation,b)
   w=BomWindow(s,r)
   try:
    node=w.root_item.child(0)
    for mid in (r,b):
     with patch.object(QMessageBox,'warning') as warning:self.assertIsNone(w.promote_alternate(node,mid));warning.assert_called_once()
    self.assertFalse(w.dirty);self.assertEqual(w.root_item.childCount(),2)
   finally:w.dirty=False;w.close();db.close()
