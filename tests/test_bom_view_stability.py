import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt,QPoint
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow

class BomViewStabilityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_copy_and_stable_insert_delete_replace_promote(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids=[s.create_material(dict(base_code=f'M{i:03}',version='1',name='物料'+str(i),description='详细规格',unit='pcs')) for i in range(85)]
   s.save_bom(ids[0],[dict(material_id=mid,quantity=1,unit='pcs') for mid in ids[1:81]])
   w=BomWindow(s,ids[0]);w.resize(850,500);w.show();self.app.processEvents()
   try:
    tree=w.tree;node=w.root_item.child(35);tree.setCurrentItem(node);w.show_item_info(node)
    field=w.fields['name'];self.assertTrue(field.textInteractionFlags() & Qt.TextSelectableByMouse)
    field.setSelection(0,len(field.text()));field.setFocus();QTest.keyClick(field,Qt.Key_C,Qt.ControlModifier);self.assertEqual(self.app.clipboard().text(),field.text())
    tree.verticalScrollBar().setValue(600);tree.horizontalScrollBar().setValue(20);self.app.processEvents()
    anchor=tree.itemAt(QPoint(1,1));before=tree.visualItemRect(anchor).top();horizontal=tree.horizontalScrollBar().value()
    def stable():
     self.app.processEvents();self.app.processEvents()
     self.assertEqual(tree.visualItemRect(anchor).top(),before);self.assertEqual(tree.horizontalScrollBar().value(),horizontal)
    material=lambda mid:dict(s.db.conn.execute('SELECT * FROM materials WHERE id=?',(mid,)).fetchone())
    added=w.insert_material(w.root_item,material(ids[81]),after=node);stable()
    w.remove_relation(added);stable()
    new=w.replace_nodes(node,[node],material(ids[82]));stable()
    w._alternate_edits[w.alternate_key(new)]=[ids[83]]
    promoted=w.promote_alternate(new,ids[83]);stable()
    self.assertIs(tree.currentItem(),promoted);self.assertEqual(w.fields['base_code'].text(),'M083')
   finally:w.dirty=False;w.close();db.close()
