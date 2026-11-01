import unittest
from unittest.mock import patch
import test_material_history as fixture
from PyQt5.QtCore import Qt
from ui.main_window import BomWindow,QMessageBox
from ui.material_history import MaterialHistoryChoiceDialog

class BomSaveViewTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MaterialHistoryTests.setUpClass.__func__)
 def setUp(self):
  fixture.MaterialHistoryTests.setUp(self);self.w=BomWindow(self.new,self.r)
 def tearDown(self):
  self.w.dirty=False;self.w.close();fixture.MaterialHistoryTests.tearDown(self)
 def save(self):
  with patch.object(QMessageBox,'information'),patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=1):self.assertTrue(self.w.save())
 def current(self):return self.w.tree.currentItem().data(0,Qt.UserRole)
 def test_selected_descendant_and_multi_selection_survive_save(self):
  parent=self.w.root_item.child(0);leaf=parent.child(0);parent.setExpanded(True)
  self.w.tree.setCurrentItem(leaf);parent.setSelected(True);leaf.setSelected(True)
  self.save();self.app.processEvents()
  self.assertEqual(self.current()['material_id'],self.c)
  self.assertEqual({n.data(0,Qt.UserRole)['material_id'] for n in self.w.tree.selectedItems()},{self.c,self.p})
  self.assertIs(self.w.current_item,self.w.tree.currentItem())
  self.assertEqual(self.w.fields['base_code'].text(),'C')
 def test_new_node_survives_save_and_deleted_sibling_index_shift(self):
  parent=self.w.root_item.child(0);leaf=parent.child(0)
  # Root changes keep the newly inserted node despite fresh relationship IDs.
  self.w.insert_material(self.w.root_item,self.s.material_snapshot(self.a))
  selected=self.w.tree.currentItem();self.assertEqual(selected.data(0,Qt.UserRole)['material_id'],self.a)
  self.save();self.assertEqual(self.current()['material_id'],self.a)
  self.w.remove_relation(self.w.root_item.child(0));self.w.tree.setCurrentItem(self.w.root_item.child(1))
  self.save();self.assertEqual(self.current()['material_id'],self.a)
 def test_deleted_current_falls_back_to_surviving_parent(self):
  parent=self.w.root_item.child(0);self.w.remove_relation(parent);self.w.tree.setCurrentItem(parent)
  self.save();self.assertIs(self.w.tree.currentItem(),self.w.root_item)
 def test_parent_revision_mapping_keeps_selected_descendant(self):
  from test_parent_revision_draft import ParentRevisionDraftTests
  ParentRevisionDraftTests.edit(self)
  leaf=self.w.root_item.child(0).child(0);self.w.tree.setCurrentItem(leaf)
  self.save();self.assertEqual(self.current()['material_id'],self.c)
  self.assertEqual(self.w.tree.currentItem().parent().data(0,Qt.UserRole)['version'],'101')
 def test_failed_save_does_not_reset_selection(self):
  leaf=self.w.root_item.child(0).child(0);self.w.tree.setCurrentItem(leaf)
  with patch.object(self.w,'save_material_history',side_effect=ValueError('failure')),patch('ui.main_window.show_operation_error'):
   self.assertFalse(self.w.save())
  self.assertIs(self.w.tree.currentItem(),leaf)
 def test_deleted_source_preserves_unsaved_cache_without_reading_dropped_tables(self):
  node=self.w.insert_material(self.w.root_item,self.s.material_snapshot(self.a));before=self.w.capture_tree()
  self.s.delete_sku(self.newid)
  self.assertEqual(self.w.capture_tree(),before);self.assertTrue(self.w.dirty)
  self.assertIs(self.w.tree.currentItem(),node);self.assertTrue(self.w.is_locked())
  self.assertFalse(self.w.save_action.isEnabled());self.assertFalse(self.w.save())
 def test_scroll_anchor_and_collapsed_branches_survive_save(self):
  for i in range(45):
   mid=self.s.create_material(dict(base_code=f'SCROLL{i:02d}',version='100',name='scroll item',unit='pcs'))
   self.w.insert_material(self.w.root_item,self.s.material_snapshot(mid))
  self.w.show();self.w.resize(850,450);self.app.processEvents()
  self.w.root_item.child(0).setExpanded(False)
  leaf=self.w.root_item.child(30);self.w.tree.setCurrentItem(leaf);self.w.tree.scrollToItem(leaf);self.app.processEvents()
  mid=leaf.data(0,Qt.UserRole)['material_id'];vertical=self.w.tree.verticalScrollBar().value()
  self.save();self.app.processEvents()
  self.assertEqual(self.current()['material_id'],mid)
  self.assertFalse(self.w.root_item.child(0).isExpanded())
  self.assertEqual(self.w.tree.verticalScrollBar().value(),vertical)
