import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from openpyxl import Workbook
from PyQt5.QtWidgets import QApplication,QDialog
from ui.interactive_windows import QFileDialog,QMessageBox
from database.database import Database
from services.services import Services,BomImportError
from ui.main_window import MainWindow,MaterialHeaderMappingDialog,BomImportIssuesDialog

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
   for w in list(self.main._material_bom_windows.values())+list(self.main._bom_windows.values()):w.dirty=False;w.close()
   self.main.close()
  self.db.close();self.tmp.cleanup()
 def item(self,c,q):return dict(material_id=self.ids[c],quantity=q,unit='pcs')
 def write(self,edges):
  wb=Workbook();wb.active.append(self.s.BOM_HEADERS)
  for p,c,q,pos in edges:wb.active.append([p,'1',c,'1',q,pos])
  wb.save(self.path);wb.close()
 def test_equal_structure_no_prompt_no_writes(self):
  self.write([('R','A',1,''),('A','B',2,''),('B','C',3,'')]);before=list(self.db.conn.iterdump());resolver=Mock()
  nodes=self.s.import_bom(self.path,self.ids['R'],persist=False,conflict_resolver=resolver)
  resolver.assert_not_called();self.assertEqual(nodes[0]['children'][0]['children'][0]['data']['material_id'],self.ids['C']);self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_conflicts_cannot_be_overridden_and_report_all_fields(self):
  self.write([('R','A',1,''),('A','B',4,'新位置'),('B','D',5,'')]);before=list(self.db.conn.iterdump())
  for persist in (False,True):
   for decision in ('incoming','system','stop'):
    resolver=Mock(return_value=decision)
    with self.assertRaises(BomImportError) as caught:self.s.import_bom(self.path,self.ids['R'],persist=persist,conflict_resolver=resolver)
    resolver.assert_not_called();error=caught.exception
    self.assertIn('禁止导入',str(error));self.assertEqual(len(error.comparisons),4)
    self.assertEqual({d['field'] for d in error.comparisons},{'数量','位置','子物料存在性'})
    self.assertEqual(before,list(self.db.conn.iterdump()))
 def test_omitted_existing_subtree_is_a_conflict(self):
  self.write([('R','A',1,'')])
  with self.assertRaises(BomImportError) as caught:self.s.import_bom(self.path,self.ids['R'],persist=False)
  self.assertIn('B1 B名称',str(caught.exception));self.assertIn('不存在',str(caught.exception))
 def test_new_sku_scope_compares_public_current_history_not_empty_cache(self):
  self.s.save_bom(self.ids['S'],[self.item('A',1)]);source=self.s.create_sku(self.ids['S']);sid=self.s.create_sku(self.ids['R'])
  from services.snapshot_bom import migrate
  from services.current_catalog import initialize
  from services import material_history as h
  migrate(self.db);initialize(self.db);h.initialize(self.db)
  sid=self.s.copy_sku_bom(sid);scope=self.s.for_sku(sid);self.assertFalse(scope.db.conn.execute('SELECT 1 FROM material_bom_items WHERE parent_material_id=?',(self.ids['A'],)).fetchone())
  # Even an empty public edge cache cannot hide immutable current definitions.
  with self.db.transaction():self.db.conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=?',(self.ids['A'],))
  before=list(self.db.conn.iterdump());self.write([('R','A',1,''),('A','B',9,''),('B','C',3,'')])
  with self.assertRaises(BomImportError) as caught:scope.import_bom(self.path,self.ids['R'],persist=False)
  self.assertTrue(any(d['field']=='数量' and d['left']=='2' and d['right']=='9' for d in caught.exception.comparisons))
  self.assertEqual(before,list(self.db.conn.iterdump()))
  self.write([('R','A',1,''),('A','B',2,''),('B','C',3,'')]);self.assertTrue(scope.import_bom(self.path,self.ids['R'],persist=False))
 def test_current_pointer_not_max_and_different_code_version_allowed(self):
  from services import material_history as h
  h.initialize(self.db)
  original=h.read(self.s,self.ids['A'],100)
  with self.db.transaction():
   edges=[dict(e,quantity=8) for e in original['children']]
   h.record(self.db.conn,self.ids['A'],original['attributes'],edges)
   self.db.conn.execute('UPDATE material_history_current SET history_version=100 WHERE material_id=?',(self.ids['A'],))
  self.write([('R','A',1,''),('A','B',2,''),('B','C',3,'')]);self.assertTrue(self.s.import_bom(self.path,self.ids['R'],persist=False))
  aid=self.s.create_material(dict(base_code='A',version='2',name='新版本A',unit='pcs'))
  wb=Workbook();wb.active.append(self.s.BOM_HEADERS);wb.active.append(['R','1','A','2',1,'']);wb.active.append(['A','2','D','1',8,'']);wb.save(self.path);wb.close()
  self.assertEqual(self.s.import_bom(self.path,self.ids['R'],persist=False)[0]['data']['material_id'],aid)
 def test_remark_alternative_differences(self):
  edge=self.s.bom(self.ids['A'])[0]['id'];self.s.add_alternate(edge,self.ids['X'])
  self.db.conn.execute("UPDATE material_bom_items SET remark='系统备注' WHERE id=?",(edge,));self.db.conn.commit()
  self.write([('R','A',1,''),('A','B',2,''),('B','C',3,'')])
  with self.assertRaises(BomImportError) as caught:self.s.import_bom(self.path,self.ids['R'],persist=False)
  self.assertEqual({d['field'] for d in caught.exception.comparisons},{'备注','替代料'})
 def test_existing_leaf_cannot_silently_acquire_children(self):
  self.write([('R','A',1,''),('A','B',2,''),('B','C',3,''),('C','D',1,'')])
  with self.assertRaises(BomImportError) as caught:self.s.import_bom(self.path,self.ids['R'],persist=False)
  self.assertTrue(any(d['parent'].startswith('C1 ') and d['right'].startswith('存在') for d in caught.exception.comparisons))
 def test_ui_displays_table_and_keeps_unsaved_draft(self):
  sid=self.s.create_sku(self.ids['R']);self.main=MainWindow(self.s);window=self.main.open_bom_id(sid)
  window.dirty=True;before=window.capture_tree();database=list(self.db.conn.iterdump());shown=[]
  self.write([('R','A',1,''),('A','B',9,''),('B','C',3,'')])
  def inspect(dialog):
   shown.append(dialog);self.assertGreater(dialog.table.rowCount(),0)
   self.assertIn('系统物料库',dialog.table.item(0,3).text());self.assertIn('导入文件',dialog.table.item(0,5).text())
   return QDialog.Rejected
  with patch.object(MaterialHeaderMappingDialog,'exec_',return_value=QDialog.Accepted),patch.object(BomImportIssuesDialog,'exec_',inspect),patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.path),'')),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(window,'stage_import') as stage:
   window.import_bom();stage.assert_not_called()
  self.assertEqual(len(shown),1);self.assertEqual(window.capture_tree(),before);self.assertTrue(window.dirty);self.assertEqual(database,list(self.db.conn.iterdump()))
