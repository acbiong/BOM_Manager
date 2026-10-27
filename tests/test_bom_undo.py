import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from unittest.mock import patch
from PyQt5.QtCore import Qt,QEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication,QToolBar
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow

class BomUndoTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db)
  self.ids={x:self.s.create_material(dict(base_code=x,version='100',name=x,unit='pcs')) for x in ('R','A','B','C')}
  self.s.create_sku(self.ids['R']);self.s.save_bom(self.ids['R'],[dict(material_id=self.ids[x],quantity=1,unit='pcs') for x in ('A','B')])
  self.w=BomWindow(self.s,self.ids['R']);self.w.show();self.app.processEvents()
 def tearDown(self):
  self.w.dirty=False;self.w.close();self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.db.close();self.tmp.cleanup()
 def select(self,index=0):
  item=self.w.root_item.child(index);self.w.tree.setCurrentItem(item);self.w.show_item_info(item);return item
 def test_shortcuts_buttons_draft_and_branch(self):
  w=self.w;self.assertEqual([a.text() for a in w.findChild(QToolBar).actions()][:4],['保存','撤销','恢复','刷新'])
  self.assertFalse(w.undo_action.isEnabled());self.assertFalse(w.redo_action.isEnabled())
  self.select();w.fields['remark'].setFocus();self.app.processEvents();QTest.keyClicks(w.fields['remark'],'abc')
  self.assertEqual(len(w.history.undo_stack),1)
  QTest.keyClick(w.fields['remark'],Qt.Key_Z,Qt.ControlModifier)
  self.assertEqual(w.fields['remark'].text(),'');self.assertFalse(w.dirty);self.assertFalse(w.save_action.isEnabled());self.assertTrue(w.redo_action.isEnabled())
  QTest.keyClick(w.fields['remark'],Qt.Key_Y,Qt.ControlModifier)
  self.assertEqual(w.fields['remark'].text(),'abc');self.assertTrue(w.save_action.isEnabled())
  w.history.undo();w.fields['position'].setText('X');self.assertFalse(w.redo_action.isEnabled())
  self.assertEqual(self.s.bom(w.root)[0]['position'],'')
 def test_nested_batch_and_restore_structure_metadata(self):
  w=self.w;self.select();w.root_item.child(1).setSelected(True)
  w.cut_material(w.root_item.child(0));self.assertEqual(len(w.history.undo_stack),1)
  self.assertTrue(all(w.root_item.child(i).data(0,Qt.UserRole).get('_deleted') for i in range(2)))
  w.history.undo();self.assertFalse(w._deleted_relations);self.assertFalse(w.root_item.child(0).data(0,Qt.UserRole).get('_deleted'))
  w.history.redo();self.assertTrue(w._deleted_relations)
  w.history.undo();item=self.select();w.set_row_color([item],'#123456');w.history.undo();self.assertNotEqual(w.root_item.child(0).data(0,Qt.UserRole).get('row_color'),'#123456')
  w.history.redo();self.assertEqual(w.root_item.child(0).data(0,Qt.UserRole)['row_color'],'#123456')
  w.move_item(w.root_item.child(0),1);w.history.undo();self.assertEqual(w.root_item.child(0).data(0,Qt.UserRole)['material_id'],self.ids['A'])
  w.insert_material(w.root_item,self.s.material_snapshot(self.ids['C']));self.assertEqual(w.root_item.childCount(),3)
  w.history.undo();self.assertEqual(w.root_item.childCount(),2);w.history.redo();self.assertEqual(w.root_item.childCount(),3)
 def test_save_refresh_failure_and_external_notice(self):
  w=self.w;self.select();w.fields['remark'].setText('draft')
  self.s.update_material(self.ids['A'],{**self.s.material_snapshot(self.ids['A']),'name':'changed'})
  w.history.undo();self.assertTrue(w.refresh_action.isEnabled());self.assertFalse(w.export_action.isEnabled())
  w.history.redo();w.refresh_external();self.assertFalse(w.undo_action.isEnabled());self.assertFalse(w.redo_action.isEnabled());self.select();self.assertEqual(w.fields['remark'].text(),'draft')
  w.fields['position'].setText('new')
  with patch.object(w.svc,'save_bom',side_effect=ValueError('failure')),patch('ui.main_window.show_operation_error'):
   self.assertFalse(w.save())
  self.assertTrue(w.undo_action.isEnabled())
  with patch('ui.main_window.QMessageBox.information'):self.assertTrue(w.save())
  self.assertFalse(w.undo_action.isEnabled());self.assertFalse(w.redo_action.isEnabled());self.assertFalse(w.dirty)
 def test_replacement_alternates_import_and_lock(self):
  from copy import deepcopy
  w=self.w;item=self.select();before=w.capture_tree()
  # Switching the alternate to the main item must restore both identities and roles.
  w._alternate_edits[w.alternate_key(item)]=[self.ids['C']]
  w.promote_alternate(item,self.ids['C'])
  self.assertEqual(len(w.history.undo_stack),1)
  w.history.undo();self.assertEqual(w.capture_tree(),before);self.assertEqual(w.alternate_ids(w.root_item.child(0)),[self.ids['C']])
  w.history.redo();self.assertTrue(any(w.root_item.child(i).data(0,Qt.UserRole)['material_id']==self.ids['C'] for i in range(w.root_item.childCount())))
  previous=deepcopy(w.capture_tree());nodes=w.database_tree();nodes[0]['data']['quantity']=7
  w.stage_import(nodes);w.history.undo();self.assertEqual(w.capture_tree(),previous)
  w.history.redo();self.assertEqual(w.root_item.child(0).text(1),'7')
  sid=self.s.skus()[0]['id'];self.s.set_sku_locked(sid,True)
  self.assertFalse(w.undo_action.isEnabled());self.assertFalse(w.redo_action.isEnabled());snapshot=w.capture_tree();w.history.undo();self.assertEqual(w.capture_tree(),snapshot)
  self.s.set_sku_locked(sid,False);self.assertTrue(w.undo_action.isEnabled())
