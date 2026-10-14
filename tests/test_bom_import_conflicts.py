import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from openpyxl import Workbook
from PyQt5.QtWidgets import QApplication,QFileDialog,QMessageBox,QDialog
from database.database import Database
from services.services import Services,BomImportError
from ui.main_window import MainWindow,MaterialHeaderMappingDialog,BomImportConflictDialog,BomImportIssuesDialog

class BomImportConflictTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'in.xlsx';self.db=Database(str(Path(self.tmp.name)/'db'));self.s=Services(self.db);self.main=None
  self.ids={c:self.s.create_material(dict(base_code=c,version='1',name=c+'名称',unit='pcs')) for c in ('R','S','A','B','C','D','X')}
  self.s.save_bom(self.ids['B'],[self.item('C',3)])
  self.s.save_bom(self.ids['A'],[self.item('B',2)])
 def tearDown(self):
  if self.main:
   for w in list(self.main._material_bom_windows.values()):w.dirty=False;w.close()
   self.main.close()
  self.db.close();self.tmp.cleanup()
 def item(self,code,qty):return dict(material_id=self.ids[code],quantity=qty,unit='pcs')
 def write(self,edges):
  wb=Workbook();wb.active.append(self.s.BOM_HEADERS)
  for parent,child,qty,pos in edges:wb.active.append([parent,'1',child,'1',qty,pos])
  wb.save(self.path);wb.close()
 def snapshot(self):return list(self.db.conn.iterdump())
 def preview(self,choice=None):return self.s.import_bom(self.path,self.ids['R'],persist=False,conflict_resolver=choice)
 def test_equal_structure_no_prompt_and_no_writes(self):
  self.write([('R','A',1,''),('A','B',2,''),('B','C',3,'')]);before=self.snapshot();resolver=Mock()
  nodes=self.preview(resolver);resolver.assert_not_called();self.assertEqual(nodes[0]['children'][0]['children'][0]['data']['material_id'],self.ids['C']);self.assertEqual(before,self.snapshot())
 def test_stop_reports_all_differences_and_preserves_database(self):
  self.write([('R','A',1,''),('A','B',4,'新位置'),('B','D',5,'')]);before=self.snapshot();captured=[]
  def stop(conflicts):captured.extend(conflicts);return 'stop'
  with self.assertRaises(BomImportError):self.preview(stop)
  self.assertEqual(before,self.snapshot());self.assertEqual(len(captured),3)
  self.assertTrue(any(c['difference']=='数量、位置' for c in captured));self.assertTrue(any(c['material']=='C1 C名称' for c in captured))
  dialog=BomImportConflictDialog(captured)
  try:
   self.assertEqual(dialog.table.rowCount(),3);self.assertEqual(dialog.choice,'stop')
   self.assertIn('数量：2',dialog.table.item(0,3).text());dialog.reject();self.assertEqual(dialog.choice,'stop')
  finally:dialog.close()
 def test_system_keeps_entire_subtree_and_discards_disconnected_imports(self):
  self.write([('R','A',1,''),('A','B',4,''),('B','D',5,''),('D','X',6,'')]);before=self.snapshot()
  nodes=self.preview(lambda _: 'system');b=nodes[0]['children'][0]
  self.assertEqual(b['data']['quantity'],2);self.assertEqual(b['children'][0]['data']['material_id'],self.ids['C']);self.assertEqual(before,self.snapshot())
  self.s.import_bom(self.path,self.ids['R'],conflict_resolver=lambda _:'system')
  self.assertEqual(self.s.bom(self.ids['D']),[])
  self.assertEqual([r['material_id'] for r in self.s.bom(self.ids['R'])],[self.ids[c] for c in ('A','B','C')])
 def test_imported_cached_until_save_then_shared_window_notified(self):
  sid=self.s.create_sku(self.ids['R']);other=self.s.create_sku(self.ids['S']);self.s.save_bom(self.ids['S'],[self.item('A',1)])
  self.main=MainWindow(self.s);w=self.main.open_bom_id(sid);shared=self.main.open_bom_id(other)
  self.write([('R','A',1,''),('A','B',4,''),('B','D',5,'')]);before=self.snapshot()
  def decide(dialog):dialog.finish('incoming');return QDialog.Accepted
  with patch.object(MaterialHeaderMappingDialog,'exec_',return_value=QDialog.Accepted),patch.object(BomImportConflictDialog,'exec_',decide),patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.path),'')),patch.object(QMessageBox,'information'):
   w.import_bom()
  self.assertTrue(w.dirty);self.assertEqual(before,self.snapshot());self.assertFalse(shared.refresh_action.isEnabled())
  self.assertEqual(w.root_item.child(0).child(0).text(1),'4')
  with patch.object(QMessageBox,'information'):self.assertTrue(w.save())
  self.assertTrue(shared.refresh_action.isEnabled());self.assertEqual(self.s.bom(self.ids['B'])[0]['material_id'],self.ids['D'])
 def test_stop_ui_leaves_draft_unchanged(self):
  sid=self.s.create_sku(self.ids['R']);self.main=MainWindow(self.s);w=self.main.open_bom_id(sid)
  self.write([('R','A',1,''),('A','B',9,'')]);before=w.capture_tree()
  with patch.object(MaterialHeaderMappingDialog,'exec_',return_value=QDialog.Accepted),patch.object(BomImportConflictDialog,'exec_',return_value=QDialog.Rejected),patch.object(BomImportIssuesDialog,'exec_',return_value=QDialog.Rejected),patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.path),'')):
   w.import_bom()
  self.assertEqual(w.capture_tree(),before);self.assertFalse(w.dirty);self.assertEqual(self.s.bom(self.ids['R']),[])
 def test_system_choice_still_rejects_combined_cycle(self):
  # R -> A -> D is legal; retaining A -> B -> C -> R would form a cycle.
  self.s.save_bom(self.ids['C'],[self.item('R',1)])
  self.write([('R','A',1,''),('A','D',1,'')])
  before=self.snapshot()
  with self.assertRaisesRegex(BomImportError,'循环'):self.preview(lambda _:'system')
  self.assertEqual(self.snapshot(),before)
 def test_alternate_and_remark_differences_are_visible_and_preserved(self):
  edge=self.s.bom(self.ids['A'])[0]['id'];self.s.add_alternate(edge,self.ids['X'])
  self.db.conn.execute("UPDATE material_bom_items SET remark='系统备注' WHERE id=?",(edge,));self.db.conn.commit()
  self.write([('R','A',1,''),('A','B',2,'')]);captured=[]
  def resolver(conflicts):captured.extend(conflicts);return 'system'
  nodes=self.preview(resolver);self.assertIn('备注',captured[0]['difference']);self.assertIn('替代料',captured[0]['difference'])
  self.assertEqual(nodes[0]['children'][0]['data']['remark'],'系统备注')
  self.assertEqual(nodes[0]['children'][0]['data']['alternate_material_ids'],[self.ids['X']])

 def test_existing_import_root_also_requires_explicit_choice(self):
  self.s.save_bom(self.ids['R'],[self.item('A',1)])
  self.write([('R','D',7,'')]);before=self.snapshot()
  with self.assertRaises(BomImportError):self.preview()
  nodes=self.preview(lambda _: 'system')
  self.assertEqual(nodes[0]['data']['material_id'],self.ids['A'])
  self.assertEqual(nodes[0]['children'][0]['children'][0]['data']['material_id'],self.ids['C'])
  self.assertEqual(self.snapshot(),before)
  nodes=self.preview(lambda _: 'incoming');self.assertEqual(nodes[0]['data']['material_id'],self.ids['D'])
