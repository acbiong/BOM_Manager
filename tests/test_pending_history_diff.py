import unittest
from unittest.mock import patch
import test_material_history as fixture
from services import material_history as h, history_selection as hs
from services.pending_history_diff import compare
from ui.main_window import BomWindow, QMessageBox
from ui.material_history import MaterialHistoryChoiceDialog
from PyQt5.QtWidgets import QDialog
from PyQt5.QtCore import Qt


class PendingHistoryDiffTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MaterialHistoryTests.setUpClass.__func__)
 rows=fixture.MaterialHistoryTests.rows
 def setUp(self):
  fixture.MaterialHistoryTests.setUp(self)
  self.w=BomWindow(self.new,self.r)
 def tearDown(self):
  self.w.dirty=False;self.w.close();fixture.MaterialHistoryTests.tearDown(self)
 def diff(self,rows=None,edits=None,mid=None):
  return compare(self.new,mid or self.p,self.rows() if rows is None else rows,edits)
 def test_unchanged_and_reverted_edits_save_without_prompt_or_revision(self):
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  self.w._material_edits[self.c]=dict(self.new.material_snapshot(self.c))
  self.w._history_choices[self.c]=hs.select(self.new,self.c,[self.sid,self.tid])
  self.assertFalse(self.diff(edits=self.w._material_edits)['changes'])
  with patch.object(MaterialHistoryChoiceDialog,'exec_') as dialog,patch.object(QMessageBox,'information'):
   self.assertTrue(self.w.save());dialog.assert_not_called()
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
 def test_bound_history_not_latest_is_the_baseline(self):
  rec=h.read(self.new,self.p,100);rec['children'][0]['quantity']=9
  with self.db.transaction():h.record(self.db.conn,self.p,rec['attributes'],rec['children'])
  self.assertEqual(h.current_version(self.db.conn,self.p),101)
  self.assertEqual(self.diff(),dict(version=100,changes=[]))
  rows=self.rows();rows[-1]['quantity']=9
  change=self.diff(rows)['changes'][0]
  self.assertEqual((change['field'],change['before'],change['after']),('数量','2','9'))
 def test_all_relationship_fields_and_child_attributes_are_visible(self):
  rows=self.rows();rows[-1].update(quantity=2.5,unit='set',position='X1',remark='新备注',alternate_material_ids=[self.a])
  edits={self.c:{'description':'新规格','name':'新名称'}}
  result=self.diff(rows,edits)['changes']
  self.assertEqual({r['field'] for r in result},{'数量','单位','位置','备注','替代料','规格描述','名称'})
  self.assertTrue(all('C100' in r['path'] for r in result))
  self.assertEqual(next(r['after'] for r in result if r['field']=='数量'),'2.5')
 def test_added_and_deleted_children_include_relationship_details(self):
  rows=self.rows();rows[-1].update(material_id=self.a,quantity=3,position='Y',remark='装配')
  result=self.diff(rows)['changes']
  self.assertEqual({r['kind'] for r in result},{'新增','删除'})
  self.assertIn('数量：3',result[0]['after']);self.assertIn('装配',result[0]['after'])
  self.assertIn('C100',result[1]['before'])
 def test_history_numbers_alone_are_ignored(self):
  rec=h.read(self.new,self.c,100)
  with self.db.transaction():
   self.db.conn.execute('INSERT INTO material_histories VALUES(?,?,?,?,?,?)',(self.c,999,h.encode(rec['attributes']),h.encode(rec['children']),rec['created_at'],self.newid))
   self.db.conn.execute('UPDATE material_history_bindings SET history_version=999 WHERE sku_id=? AND material_id=?',(self.newid,self.c))
  self.assertFalse(self.diff()['changes'])
 def test_incoming_alternates_are_not_part_of_material_subbom(self):
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  self.assertFalse(self.diff(rows,mid=self.c)['changes'])
  self.assertEqual(self.diff(rows)['changes'][0]['field'],'替代料')
 def test_repeated_positions_and_order_do_not_confuse_comparison(self):
  rows=self.rows();rows.append(dict(rows[-1],position='other',quantity=7))
  h.save(self.new,self.r,rows,{},hs.select(self.new,self.p))
  rows=list(reversed(self.rows()))
  self.assertFalse(self.diff(rows)['changes'])
  next(r for r in rows if r.get('position')=='other')['quantity']=8
  result=self.diff(rows)['changes']
  self.assertEqual(len(result),1);self.assertEqual(result[0]['before'],'7')
  self.assertIn('other',result[0]['path'])
 def test_preview_and_cancel_keep_database_and_draft(self):
  item=self.w.root_item.child(0).child(0);item.setData(0,Qt.UserRole,dict(item.data(0,Qt.UserRole),quantity=3));item.setText(1,'3')
  rows=self.w.history_rows();before=list(self.db.conn.iterdump());seen=[]
  def cancel(dialog):
   seen.append(dialog.diff_table)
   self.assertEqual(dialog.diff_table.rowCount(),1)
   self.assertEqual([dialog.diff_table.item(0,c).text() for c in (2,3,4)],['数量','2','3'])
   return QDialog.Rejected
  with patch.object(MaterialHistoryChoiceDialog,'exec_',cancel):
   self.assertIsNone(self.w.save_material_history(self.r,rows))
  self.assertEqual(len(seen),1);self.assertEqual(before,list(self.db.conn.iterdump()))
  self.assertEqual(self.w.history_rows(),rows)
 def test_no_other_owner_saves_without_history_dialog(self):
  self.s.delete_sku(self.sid);self.s.delete_sku(self.tid)
  rows=self.rows();rows[-1]['quantity']=4
  with patch.object(MaterialHistoryChoiceDialog,'exec_') as dialog:
   self.w.save_material_history(self.r,rows);dialog.assert_not_called()
  self.assertEqual(self.new.bom(self.p)[0]['quantity'],4)
 def test_reverted_old_confirmation_does_not_synchronize_differing_target(self):
  rows=self.rows(self.old);rows[-1]['alternate_material_ids']=[self.a]
  h.save(self.old,self.r,rows,{},hs.select(self.old,self.p))
  old_rows=self.old.bom(self.r)
  self.w._history_choices[self.p]=hs.select(self.new,self.p,[self.sid])
  # Make the scope token stale as well: a no-op must discard it, not reconfirm.
  self.s.set_sku_locked(self.tid,True)
  with patch.object(MaterialHistoryChoiceDialog,'exec_') as dialog:
   self.w.save_material_history(self.r,self.rows());dialog.assert_not_called()
  self.assertEqual(self.old.bom(self.r),old_rows)
 def test_added_removed_subtrees_show_every_level(self):
  result=self.diff(rows=[dict(material_id=self.a,parent_material_id=self.r,quantity=1,unit='pcs',replace_children=True,alternate_material_ids=[])],mid=self.r)['changes']
  self.assertEqual(len(result),3)
  self.assertTrue(any('C100' in r['path'] and r['kind']=='删除' for r in result))
 def test_remaining_alternate_attributes_and_cycles(self):
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  h.save(self.new,self.r,rows,{},hs.select(self.new,self.c,impact_mid=self.p))
  with self.db.transaction():
   self.db.conn.execute('UPDATE material_histories SET children=? WHERE material_id=? AND history_version=100',
    (h.encode([dict(material_id=self.c,history_version=100,quantity=1,unit='pcs',position='',remark='',alternates=[dict(material_id=self.a,history_version=100)])]),self.a))
  self.assertFalse(self.diff()['changes'])
  result=self.diff(edits={self.a:{'name':'替代料新名称'}})['changes']
  self.assertEqual(len(result),1);self.assertEqual(result[0]['after'],'替代料新名称')
  self.assertIn('替代料',result[0]['path'])
