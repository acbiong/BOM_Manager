import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate, ParentRevisionRequired, revision_conflicts
from services.current_catalog import initialize as catalog
from services import material_history as h
from services.sku_lock import LockedBomError
from PyQt5.QtWidgets import QApplication,QDialog
from PyQt5.QtCore import Qt


class MaterialHistoryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.temp.name)/'db'));self.s=Services(self.db)
  self.r,self.t,self.p,self.c,self.a=[self.s.create_material(dict(base_code=x,version='100',name=x,unit='pcs')) for x in ('R','T','P','C','A')]
  self.s.save_bom(self.p,[dict(material_id=self.c,quantity=2,unit='pcs')])
  for root in (self.r,self.t):self.s.save_bom(root,[dict(material_id=self.p,quantity=1,unit='pcs')])
  self.sid=self.s.create_sku(self.r);self.tid=self.s.create_sku(self.t)
  migrate(self.db);catalog(self.db);h.initialize(self.db)
  self.old=self.s.for_sku(self.sid);self.newid=self.s.copy_sku_bom(self.sid);self.new=self.s.for_sku(self.newid);self.other=self.s.for_sku(self.tid)
 def tearDown(self):self.db.close();self.temp.cleanup()
 def rows(self,service=None):
  service=service or self.new
  return [dict(r,alternate_material_ids=[a['material_id'] for a in service.alternates(r['id'])],replace_children=True) for r in service.bom(self.r)]
 def test_reuse_older_identical_content_and_current_pointer(self):
  conn=self.db.conn
  original=h.read(self.s,self.c,100)['attributes']
  with self.db.transaction():
   self.assertEqual(h.record(conn,self.c,{**original,'name':'changed'},[],previous=100),101)
   self.assertEqual(h.record(conn,self.c,original,[],previous=100),100)
   self.assertEqual(h.current_version(conn,self.c),101)
   self.assertEqual(h.record(conn,self.c,original,[],previous=101),100)
  self.assertEqual(h.current_version(conn,self.c),100)
  self.assertEqual(next(m for m in self.s.materials() if m['id']==self.c)['history_version'],100)
  self.assertEqual(len(h.versions(self.s,self.c)),2)
 def test_repair_duplicate_contexts_and_recursive_references(self):
  from services.history_identity import plan,apply
  conn=self.db.conn
  before=[tuple(r) for r in conn.execute('SELECT * FROM material_bom_items')]
  c=h.read(self.s,self.c,100);p=h.read(self.s,self.p,100)
  with self.db.transaction():
   attrs={**c['attributes'],'alternate_contexts':{'123':[{'name':'context only'}]}}
   conn.execute('INSERT INTO material_histories VALUES(?,?,?,?,?,?)',(self.c,101,h.encode(attrs),h.encode(c['children']),c['created_at'],self.tid))
   edges=p['children'];edges[0]['history_version']=101
   conn.execute('INSERT INTO material_histories VALUES(?,?,?,?,?,?)',(self.p,101,h.encode(p['attributes']),h.encode(edges),p['created_at'],self.tid))
   conn.execute('UPDATE material_history_bindings SET history_version=101 WHERE material_id IN (?,?)',(self.p,self.c))
   conn.execute('UPDATE material_history_current SET history_version=101 WHERE material_id IN (?,?)',(self.p,self.c))
   result=plan(conn);self.assertEqual(result['mapping'][(self.c,101)],(self.c,100));self.assertEqual(result['mapping'][(self.p,101)],(self.p,100))
   apply(conn,result)
  self.assertEqual(before,[tuple(r) for r in conn.execute('SELECT * FROM material_bom_items')])
  self.assertTrue(all(a==b for a,b in plan(conn)['mapping'].items()))
  self.assertEqual(h.current_version(conn,self.p),100)
  self.assertEqual(h.read(self.s,self.p,100)['children'][0]['history_version'],100)
 def test_repair_preserves_real_edge_differences_and_current(self):
  from services.history_identity import plan,apply
  import copy
  conn=self.db.conn;record=h.read(self.s,self.p,100)
  with self.db.transaction():
   for index,field in enumerate(('quantity','position','remark','alternates'),101):
    children=copy.deepcopy(record['children'])
    children[0][field]={'quantity':3.5,'position':'other','remark':'note','alternates':[dict(material_id=self.a,history_version=100)]}[field]
    self.assertEqual(h.record(conn,self.p,record['attributes'],children),index)
   result=plan(conn)
   self.assertTrue(all(a==b for a,b in result['mapping'].items()))
   apply(conn,result)
  self.assertEqual(h.current_version(conn,self.p),104)
  self.assertEqual(len(h.versions(self.s,self.p)),5)
 def test_repair_rejects_missing_reference_without_writes(self):
  from services.history_identity import plan
  with self.db.transaction():
   conn=self.db.conn
   conn.execute('UPDATE material_histories SET children=? WHERE material_id=?',(h.encode([dict(material_id=9999,history_version=100)]),self.p))
   before=list(conn.execute('SELECT * FROM material_histories'))
   with self.assertRaises(ValueError):plan(conn)
   self.assertEqual(before,list(conn.execute('SELECT * FROM material_histories')))
 def test_migration_initial_copy_and_noop(self):
  self.assertTrue(list(Path(self.temp.name).glob('*.pre-material-history-*')))
  self.assertEqual(h.versions(self.s,self.c)[0]['history_version'],100)
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  h.save(self.new,self.r,self.rows(),{},'fork')
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
  h.initialize(self.db);self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
 def test_metadata_fork_parent_code_rule_and_old_export(self):
  attrs={**self.new.material_snapshot(self.c),'name':'new child'}
  with self.assertRaises(ParentRevisionRequired):h.save(self.new,self.r,self.rows(),{self.c:attrs},'fork')
  mapping=h.save(self.new,self.r,self.rows(),{self.c:attrs},'fork',{self.p:'101'})
  self.assertNotEqual(mapping[self.p],self.p)
  self.assertEqual(self.new.material_snapshot(self.c)['name'],'new child')
  self.assertEqual(self.old.material_snapshot(self.c)['name'],'C')
  self.assertEqual(self.other.material_snapshot(self.c)['name'],'C')
  self.assertEqual(self.s.material_snapshot(self.c)['name'],'new child')
  self.assertEqual(h.versions(self.s,self.c)[0]['history_version'],101)
  from openpyxl import Workbook
  wb=Workbook();self.old.write_bom_sheet(wb.active,self.r)
  self.assertEqual(wb.active.cell(4,7).value,'C');wb.close()
 def test_sync_latest_only_with_new_parent_code(self):
  attrs={**self.new.material_snapshot(self.c),'name':'shared new'}
  mapping=h.save(self.new,self.r,self.rows(),{self.c:attrs},'sync',{self.p:'101'})
  self.assertEqual(self.other.material_snapshot(self.c)['name'],'shared new')
  self.assertEqual(self.other.bom(self.t)[0]['material_id'],mapping[self.p])
  self.assertEqual(self.old.bom(self.r)[0]['material_id'],self.p)
  self.assertEqual(self.old.material_snapshot(self.c)['name'],'C')
 def test_alternate_add_exempt_delete_requires_code(self):
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  self.assertFalse(revision_conflicts(self.new,self.r,rows))
  h.save(self.new,self.r,rows,{},'fork')
  self.assertEqual(self.new.bom(self.r)[0]['material_id'],self.p)
  self.assertEqual(h.versions(self.s,self.p)[0]['history_version'],101)
  self.assertEqual(h.versions(self.s,self.c)[0]['history_version'],100)
  self.assertFalse(self.other.alternates(self.other.bom(self.t)[-1]['id']))
  rows=self.rows();rows[-1]['alternate_material_ids']=[]
  self.assertEqual(revision_conflicts(self.new,self.r,rows)[0]['material_id'],self.p)
  with self.assertRaises(ParentRevisionRequired):h.save(self.new,self.r,rows,{},'fork')
 def test_locked_target_rolls_back_and_fork_is_allowed(self):
  self.s.set_sku_locked(self.tid,True)
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a]
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  with self.assertRaises(LockedBomError):h.save(self.new,self.r,rows,{},'sync')
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
  self.assertFalse(self.new.alternates(self.new.bom(self.r)[-1]['id']))
  h.save(self.new,self.r,rows,{},'fork')
  self.assertFalse(self.other.alternates(self.other.bom(self.t)[-1]['id']))
 def test_history_view_and_library_column(self):
  from ui.main_window import MaterialWindow
  from ui.material_history import MaterialHistoryDialog
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a];h.save(self.new,self.r,rows,{},'fork')
  window=MaterialWindow(self.s);viewer=MaterialHistoryDialog(self.s,self.p,100,window)
  try:
   index=window._base_column_labels.index('物料历史版本')
   row=next(i for i in range(window.t.rowCount()) if window.t.item(i,0).data(Qt.UserRole)==self.p)
   self.assertEqual(window.t.item(row,index).text(),'101');self.assertTrue(window.t.item(row,index).font().bold())
   self.assertEqual(viewer.tree.topLevelItem(0).child(0).text(7),'')
   self.assertEqual(viewer.windowModality(),Qt.NonModal)
  finally:viewer.close();window.close()
 def test_immediate_decision_cancel_draft_undo_and_save(self):
  from ui.main_window import BomWindow,MaterialDialog,MaterialSelectionDialog
  from ui.material_history import MaterialHistoryChoiceDialog
  from ui.parent_revision import ParentRevisionDialog
  w=BomWindow(self.new,self.r);item=w.root_item.child(0).child(0);w.tree.setCurrentItem(item)
  try:
   with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=QDialog.Rejected),patch.object(MaterialDialog,'exec_') as edit:
    w.edit_tree_material(item);edit.assert_not_called()
   def edit(dialog):dialog.e['name'].setText('draft name');return QDialog.Accepted
   with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=QDialog.Accepted),patch.object(MaterialDialog,'exec_',edit),patch.object(ParentRevisionDialog,'exec_',return_value=QDialog.Accepted),patch.object(ParentRevisionDialog,'versions',return_value={self.p:'101'}):
    w.edit_tree_material(item)
   self.assertTrue(w.dirty);self.assertEqual(self.s.material_snapshot(self.c)['name'],'C')
   self.assertIn('draft name',w.fields['name'].text());w.history.undo();self.assertFalse(w._material_edits);w.history.redo();self.assertEqual(w._material_edits[self.c]['name'],'draft name')
  finally:w.dirty=False;w.close()

 def test_add_alternate_prompts_before_picker_and_cancel_is_noop(self):
  from ui.main_window import BomWindow,MaterialSelectionDialog
  from ui.material_history import MaterialHistoryChoiceDialog
  w=BomWindow(self.new,self.r);w.tree.setCurrentItem(w.root_item.child(0).child(0))
  try:
   with patch.object(MaterialHistoryChoiceDialog,'exec_',return_value=QDialog.Rejected),patch.object(MaterialSelectionDialog,'getItem') as picker:
    w.add_alternate();picker.assert_not_called()
   self.assertFalse(w.dirty);self.assertFalse(w._alternate_edits);self.assertFalse(w.history.undo_stack)
  finally:w.dirty=False;w.close()
 def test_parent_metadata_and_child_metadata_keep_new_code(self):
  edits={mid:{**self.new.material_snapshot(mid),'name':'new '+str(mid)} for mid in (self.p,self.c)}
  mapping=h.save(self.new,self.r,self.rows(),edits,'fork',{self.p:'101'})
  self.assertEqual(self.new.material_snapshot(mapping[self.p])['version'],'101')
  self.assertEqual(self.new.material_snapshot(mapping[self.p])['name'],'new '+str(self.p))
 def test_latest_catalog_state_and_new_selection_are_immutable(self):
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a];h.save(self.new,self.r,rows,{},'fork')
  from services.current_catalog import selection_tree
  nodes=selection_tree(self.old,self.p)
  self.assertEqual(nodes[0]['data']['alternate_material_ids'],[self.a])
  self.assertFalse(self.old.alternates(self.old.bom(self.r)[-1]['id']))
  record=h.read(self.s,self.p,100)
  self.s.copy_sku_bom(self.sid)
  self.assertEqual(h.read(self.s,self.p,100),record)
 def test_invalid_edit_and_deleted_identity_do_not_corrupt_history(self):
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  with self.assertRaises(ValueError):h.save(self.new,self.r,self.rows(),{self.c:{'name':'','unit':'pcs'}},'fork')
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
  last=self.s.create_material(dict(base_code='OLD',version='1',name='old',unit='pcs'))
  self.s.delete_material(last)
  new=self.s.create_material(dict(base_code='NEW',version='1',name='new',unit='pcs'))
  self.assertGreater(new,last);self.assertEqual(h.read(self.s,last,100)['attributes']['name'],'old')
 def test_sync_checks_different_parents_in_other_latest_skus(self):
  q=self.s.create_material(dict(base_code='Q',version='100',name='other parent',unit='pcs'))
  u=self.s.create_material(dict(base_code='U',version='100',name='third SKU',unit='pcs'))
  uid=self.s.create_sku(u);target=self.s.for_sku(uid)
  target.save_bom(u,[dict(material_id=q,quantity=1,unit='pcs'),dict(parent_material_id=q,material_id=self.c,quantity=1,unit='pcs')])
  latest=self.s.copy_sku_bom(uid);target=self.s.for_sku(latest)
  edits={self.c:{**self.new.material_snapshot(self.c),'name':'all latest','unit':'米'}}
  required=h.collect_conflicts(self.new,self.r,self.rows(),edits,'sync')
  self.assertEqual({c['material_id'] for c in required},{self.p,q})
  with self.assertRaises(ParentRevisionRequired):h.save(self.new,self.r,self.rows(),edits,'sync',{self.p:'101'})
  h.save(self.new,self.r,self.rows(),edits,'sync',{self.p:'101',q:'101'})
  self.assertEqual(target.bom(u)[0]['version'],'101')
  self.assertEqual(target.material_snapshot(self.c)['name'],'all latest')
  self.assertEqual(self.s.for_sku(uid).material_snapshot(self.c)['name'],'C')
  self.assertEqual(self.s.for_sku(uid).bom(u)[0]['version'],'100')
  before=list(self.db.conn.execute('SELECT * FROM material_histories'))
  h.save(self.new,self.r,self.rows(),{},'fork')
  self.assertEqual(before,list(self.db.conn.execute('SELECT * FROM material_histories')))
 def test_logs_describe_metadata_once_without_ancestor_bookkeeping(self):
  before=self.new.db.conn.execute('SELECT COALESCE(MAX(id),0) FROM change_logs').fetchone()[0]
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a];h.save(self.new,self.r,rows,{},'fork')
  logs=list(self.new.db.conn.execute('SELECT * FROM change_logs WHERE id>?',(before,)))
  self.assertEqual(len(logs),1);self.assertIn('新增替代料',logs[0]['detail'])
  edits={self.c:{**self.new.material_snapshot(self.c),'name':'记录详细变化'}}
  h.save(self.new,self.r,self.rows(),edits,'sync',{self.p:'101'})
  for service in (self.s,self.new,self.other):
   logs=[dict(r) for r in service.db.conn.execute("SELECT * FROM change_logs WHERE object_type='material' AND object_id=? AND action='update'",(self.c,))]
   self.assertEqual(len(logs),1);self.assertIn('物料名称：C → 记录详细变化',logs[0]['detail']);self.assertIn('父项：P101 P',logs[0]['detail'])
 def test_viewer_switches_structure_and_exact_history_references(self):
  from ui.material_history import MaterialHistoryDialog
  rows=self.rows();rows[-1]['alternate_material_ids']=[self.a];h.save(self.new,self.r,rows,{},'fork')
  self.assertEqual({s['id'] for s in h.sku_references(self.s,self.p,100)},{self.sid,self.tid})
  self.assertEqual({s['id'] for s in h.sku_references(self.s,self.p,101)},{self.newid})
  self.assertEqual({s['id'] for s in h.sku_references(self.s,self.a,100)},{self.newid})
  before=self.db.conn.total_changes;viewer=MaterialHistoryDialog(self.s,self.p,100)
  try:
   self.assertEqual(viewer.version_combo.currentData(),100)
   self.assertEqual(viewer.references.rowCount(),2)
   self.assertEqual(viewer.tree.topLevelItem(0).child(0).text(7),'')
   for _ in range(3):
    viewer.version_combo.setCurrentIndex(viewer.version_combo.findData(101))
    self.assertEqual(viewer.references.rowCount(),1)
    self.assertEqual(viewer.references.item(0,2).text(),'101')
    self.assertEqual(viewer.references.item(0,0).data(Qt.UserRole),self.newid)
    self.assertEqual(viewer.attribute_values['history_version'].text(),'101')
    self.assertIn('A100 A',viewer.tree.topLevelItem(0).child(0).text(7))
    viewer.version_combo.setCurrentIndex(viewer.version_combo.findData(100))
    self.assertEqual(viewer.references.rowCount(),2);self.assertEqual(viewer.tree.topLevelItemCount(),1)
   for key,_ in viewer.FIELDS:
    self.assertTrue(viewer.attribute_labels[key].alignment() & Qt.AlignRight)
    self.assertTrue(viewer.attribute_values[key].alignment() & Qt.AlignLeft)
    self.assertTrue(viewer.attribute_values[key].textInteractionFlags() & Qt.TextSelectableByMouse)
   self.assertEqual(self.db.conn.total_changes,before)
  finally:viewer.close()
 def test_viewer_switches_metadata_and_shows_unreferenced_state(self):
  from ui.material_history import MaterialHistoryDialog
  h.save(self.new,self.r,self.rows(),{self.c:{**self.new.material_snapshot(self.c),'name':'new child','description':'long description '*80}},'fork',{self.p:'101'})
  viewer=MaterialHistoryDialog(self.s,self.c,101)
  try:
   self.assertEqual(viewer.attribute_values['name'].text(),'new child')
   viewer.version_combo.setCurrentIndex(viewer.version_combo.findData(100))
   self.assertEqual(viewer.attribute_values['name'].text(),'C');self.assertEqual(viewer.attribute_values['description'].text(),'（空）')
   self.assertNotIn('new child',viewer.windowTitle())
  finally:viewer.close()
  standalone=self.s.create_material(dict(base_code='FREE',version='1',name='unused',unit='pcs'))
  viewer=MaterialHistoryDialog(self.s,standalone,100)
  try:
   self.assertEqual(viewer.references.rowCount(),0);self.assertIn('未被任何SKU BOM引用',viewer.reference_label.text())
   self.assertEqual(viewer.version_combo.count(),1)
  finally:viewer.close()


if __name__=='__main__':unittest.main()
