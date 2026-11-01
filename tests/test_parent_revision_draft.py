import unittest
from unittest.mock import patch
import test_material_history as fixture
from services import history_selection as hs
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog
from ui.main_window import BomWindow,MaterialDialog,QMessageBox
from ui.parent_revision import ParentRevisionDialog
from ui.bom_snapshot import draft_snapshot


class ParentRevisionDraftTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MaterialHistoryTests.setUpClass.__func__)
 def setUp(self):
  fixture.MaterialHistoryTests.setUp(self)
  self.w=BomWindow(self.new,self.r)
 def tearDown(self):
  self.w.dirty=False;self.w.close()
  fixture.MaterialHistoryTests.tearDown(self)
 def edit(self,accepted=True):
  node=self.w.root_item.child(0).child(0)
  data={**self.new.material_snapshot(self.c),'name':'changed child'}
  with patch.object(self.w,'choose_material_history',return_value=hs.select(self.new,self.c)),patch.object(MaterialDialog,'exec_',return_value=QDialog.Accepted),patch.object(MaterialDialog,'data',return_value=data),patch.object(ParentRevisionDialog,'exec_',return_value=QDialog.Accepted if accepted else QDialog.Rejected),patch.object(ParentRevisionDialog,'versions',return_value={self.p:'101'}):
   self.w.edit_tree_material(node)
 def assert_pending(self):
  parent=self.w.root_item.child(0)
  self.assertIn('P101',parent.text(0))
  self.assertEqual(parent.data(0,Qt.UserRole)['version'],'101')
  self.w.show_item_info(parent)
  self.assertEqual(self.w.fields['version'].text(),'101')
  snapshot=draft_snapshot(self.w)
  self.assertEqual(snapshot['children'][0]['version'],'101')
  self.assertEqual(snapshot['children'][0]['children'][0]['parent_code'],'P101')
 def test_confirm_immediately_updates_draft_and_undo_redo_without_writing(self):
  before=list(self.db.conn.iterdump());self.edit();self.assert_pending()
  self.assertEqual(before,list(self.db.conn.iterdump()))
  self.w.history.undo();self.assertIn('P100',self.w.root_item.child(0).text(0))
  self.assertFalse(self.w._history_parent_versions)
  self.w.history.redo();self.assert_pending()
  self.w.refresh_styles();self.assert_pending()
 def test_save_maps_draft_to_real_new_parent(self):
  self.edit()
  with patch.object(QMessageBox,'information'),patch.object(ParentRevisionDialog,'exec_') as dialog:
   self.assertTrue(self.w.save());dialog.assert_not_called()
  parent=self.w.root_item.child(0).data(0,Qt.UserRole)
  self.assertNotEqual(parent['material_id'],self.p)
  self.assertEqual(parent['version'],'101')
  self.assertFalse(self.w._history_parent_versions)
  self.assertEqual(self.old.material_snapshot(self.p)['version'],'100')
 def test_cancel_leaves_old_draft_and_database(self):
  before=list(self.db.conn.iterdump());self.edit(False)
  self.assertFalse(self.w._history_parent_versions)
  self.assertIn('P100',self.w.root_item.child(0).text(0))
  self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_failed_save_retains_pending_version(self):
  self.edit();before=list(self.db.conn.iterdump())
  with patch('services.material_history.save',side_effect=ValueError('test rollback')),patch('ui.main_window.show_operation_error'):
   self.assertFalse(self.w.save())
  self.assert_pending();self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_external_refresh_keeps_parent_version_and_child_edit(self):
  self.edit();self.w.refresh_external();self.assert_pending()
  self.assertEqual(draft_snapshot(self.w)['children'][0]['children'][0]['name'],'changed child')
 def test_existing_version_attributes_shown_without_changing_relation_unit(self):
  self.s.create_material(dict(base_code='P',version='101',name='existing parent',unit='套'))
  self.edit();self.assert_pending()
  parent=self.w.root_item.child(0)
  self.assertIn('existing parent',parent.text(0));self.assertEqual(parent.text(2),'pcs')
  self.assertEqual(draft_snapshot(self.w)['children'][0]['unit'],'pcs')
  self.w.history.undo();self.assertIn('P100 P',self.w.root_item.child(0).text(0))
