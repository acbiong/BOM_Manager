import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QMenu,QMessageBox,QDialog,QTableWidget
from ui.interactive_windows import QDialog,QMessageBox
from PyQt5.QtCore import Qt,QPoint,QCoreApplication,QEvent
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate
from services.current_catalog import initialize
from services.sku_lock import LockedBomError
from infrastructure.events import WindowRefreshBus
from ui.main_window import MainWindow
from ui.sku_lock import show_operation_error

class SkuLockTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';self.db=Database(str(self.path));self.s=Services(self.db);self.main=None
  self.r,self.t,self.p,self.c,self.a,self.other=[self.s.create_material(dict(base_code=code,version='100',name=code+'名称',unit='pcs')) for code in ('R','T','P','C','A','OTHER')]
  self.s.save_bom(self.p,[dict(material_id=self.c,quantity=2,unit='pcs',alternate_material_ids=[self.a])])
  self.s.save_bom(self.r,[dict(material_id=self.p,quantity=1,unit='pcs')]);self.s.save_bom(self.t,[dict(material_id=self.p,quantity=1,unit='pcs')])
  self.sid=self.s.create_sku(self.r);self.tid=self.s.create_sku(self.t);migrate(self.db);initialize(self.db)
 def tearDown(self):
  if self.main:
   for w in list(self.main._bom_windows.values()):w.dirty=False;w.close()
   self.main.close();self.main.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
  self.db.close();self.tmp.cleanup()
 def state(self):return '\n'.join(self.db.conn.iterdump())
 def test_persistence_and_unlock(self):
  self.s.set_sku_locked(self.sid,True);self.db.close();self.db=Database(str(self.path));self.s=Services(self.db)
  self.assertEqual(next(s for s in self.s.skus() if s['id']==self.sid)['locked'],1)
  self.s.set_sku_locked(self.sid,False);self.assertEqual(next(s for s in self.s.skus() if s['id']==self.sid)['locked'],0)
 def test_material_edit_reports_all_locked_skus_and_parents_and_rolls_back(self):
  self.s.set_sku_locked(self.sid,True);self.s.set_sku_locked(self.tid,True);before=self.state();events=[];WindowRefreshBus.subscribe(events.append)
  try:
   with self.assertRaises(LockedBomError) as error:self.s.update_material(self.c,dict(self.s.material_snapshot(self.c),name='修改'))
  finally:WindowRefreshBus.unsubscribe(events.append)
  self.assertEqual(self.state(),before);self.assertEqual(events,[])
  self.assertEqual({x['sku_id'] for x in error.exception.details},{self.sid,self.tid})
  self.assertTrue(all('C100' in x['material'] and 'P100' in x['parent'] for x in error.exception.details))
 def test_alternate_metadata_root_and_version_updates_are_protected(self):
  self.s.set_sku_locked(self.sid,True)
  for mid in (self.a,self.r):
   before=self.state()
   with self.assertRaises(LockedBomError):self.s.update_material(mid,dict(self.s.material_snapshot(mid),name='修改'))
   self.assertEqual(self.state(),before)
  with self.assertRaises(LockedBomError):self.s.change_sku_version(self.sid,'101')
  with self.assertRaises(LockedBomError):self.s.change_mirror_version(self.sid,102)
  with self.assertRaises(LockedBomError):self.s.update_sku_change_description(self.sid,'修改描述')
  with self.assertRaises(LockedBomError):self.s.delete_sku(self.sid)
 def test_shared_bom_sync_is_atomic_and_reports_locked_target(self):
  self.s.set_sku_locked(self.tid,True);source=self.s.for_sku(self.sid);rows=source.bom(self.r)
  for row in rows:
   if row['material_id']==self.c:row['quantity']=9
  before=self.state()
  with self.assertRaises(LockedBomError) as error:source.save_bom(self.r,rows)
  self.assertEqual(self.state(),before);self.assertEqual({d['sku_id'] for d in error.exception.details},{self.tid})
  self.s.set_sku_locked(self.tid,False);source.save_bom(self.r,rows)
  self.assertEqual(self.s.for_sku(self.tid).bom(self.p)[0]['quantity'],9)
 def test_unrelated_change_and_copy_to_new_unlocked_history_remain_available(self):
  self.s.set_sku_locked(self.sid,True)
  self.s.update_material(self.other,dict(self.s.material_snapshot(self.other),name='允许修改'))
  copy=self.s.copy_sku_bom(self.sid);self.assertFalse(next(s for s in self.s.skus() if s['id']==copy)['locked'])
  self.assertTrue(next(s for s in self.s.skus() if s['id']==self.sid)['locked'])
 def test_historical_locked_structure_is_independent(self):
  copy=self.s.copy_sku_bom(self.sid);self.s.set_sku_locked(self.sid,True)
  source=self.s.for_sku(copy);rows=source.bom(self.r)
  for row in rows:
   if row['material_id']==self.c:row['quantity']=7
  source.save_bom(self.r,rows)
  self.assertEqual(self.s.for_sku(self.sid).bom(self.p)[0]['quantity'],2)
  self.assertEqual(source.bom(self.p)[0]['quantity'],7)
 def test_direct_locked_save_and_alternate_changes_rejected(self):
  self.s.set_sku_locked(self.sid,True);service=self.s.for_sku(self.sid);rows=service.bom(self.r)
  with self.assertRaises(LockedBomError):service.save_bom(self.r,rows)
  relation=next(row for row in rows if row['material_id']==self.c)
  with self.assertRaises(LockedBomError):service.add_alternate(relation['id'],self.other)
  alternate=service.alternates(relation['id'])[0]
  with self.assertRaises(LockedBomError):service.remove_alternate(alternate['id'])
 def test_ui_column_menu_browse_and_live_unlock(self):
  self.main=MainWindow(self.s);self.main.show();window=self.main.open_bom_id(self.sid)
  self.main.toggle_sku_lock(self.sid)
  column=7;row=next(i for i in range(self.main.table.rowCount()) if self.main.table.item(i,6).text()==str(self.sid))
  self.assertEqual(self.main.table.horizontalHeader().visualIndex(column),1);self.assertFalse(self.main.table.item(row,column).icon().isNull())
  self.assertIn('BOM浏览',window.windowTitle());item=window.root_item.child(0);window.show_item_info(item)
  self.assertFalse(window.save_action.isEnabled());self.assertTrue(window.export_action.isEnabled())
  for key in ('quantity','position','remark'):self.assertFalse(window.fields[key].isEnabled())
  before=window.capture_tree();window.remove_relation(item);self.assertEqual(window.capture_tree(),before);self.assertFalse(window.dirty)
  captured=[]
  def choose(menu,pos):captured.append([a.text() for a in menu.actions()]);return None
  with patch.object(window.tree,'itemAt',return_value=item),patch.object(QMenu,'exec_',choose):window.context_menu(QPoint())
  self.assertEqual(captured[-1],['物料反查','复制物料','','导出BOM结构'])
  def sku_menu(menu,pos):
   actions={a.text():a for a in menu.actions()};self.assertFalse(actions['删除SKU'].isEnabled());return actions['取消锁定']
  with patch.object(self.main.table,'rowAt',return_value=row),patch.object(QMenu,'exec_',sku_menu):self.main.sku_context_menu(QPoint())
  self.assertNotIn('BOM浏览',window.windowTitle());self.assertTrue(window.fields['quantity'].isEnabled())
 def test_lock_dirty_window_requires_handling_draft(self):
  self.main=MainWindow(self.s);window=self.main.open_bom_id(self.sid);window.mark_dirty()
  with patch.object(QMessageBox,'warning') as warning:self.main.toggle_sku_lock(self.sid);warning.assert_called_once()
  self.assertFalse(window.is_locked());self.assertTrue(window.dirty)
 def test_locked_error_dialog_has_sku_material_parent_table(self):
  error=LockedBomError([dict(sku_id=1,sku='SKU100 名称 历史版本100',material='C100 子项',parent='P100 父项')])
  def inspect(dialog):
   table=dialog.findChild(QTableWidget);self.assertEqual(table.columnCount(),3);self.assertEqual(table.item(0,2).text(),'P100 父项');return QDialog.Accepted
  with patch.object(QDialog,'exec_',inspect):show_operation_error(None,'保存失败',error)

 def test_import_overwrite_of_locked_material_fails_without_changing_attributes(self):
  from openpyxl import Workbook
  from services.services import MATERIAL_IMPORT_HEADERS
  self.s.set_sku_locked(self.sid,True);path=Path(self.tmp.name)/'import.xlsx';wb=Workbook();sheet=wb.active;sheet.append(MATERIAL_IMPORT_HEADERS)
  values={'物料基础编码':'C','物料版本号':'100','物料名称':'新名称','物料规格描述':'规格','单位':'pcs','物料等级':'A','M/P':'P','物料制造商':'厂家','物料MPN':'MPN'}
  sheet.append([values.get(key,'') for key in MATERIAL_IMPORT_HEADERS]);wb.save(path);wb.close();before=self.state()
  with self.assertRaises(LockedBomError):self.s.import_materials(path,conflict_resolver=lambda *args:'overwrite')
  self.assertEqual(self.state(),before)
 def test_multiple_nested_sync_changes_and_prior_edits_all_rollback(self):
  self.s.set_sku_locked(self.sid,True);self.s.set_sku_locked(self.tid,True);before=self.state();source=self.s.for_sku(self.sid);rows=source.bom(self.r)
  for row in rows:
   if row['material_id']==self.c:row['quantity']=11
  with self.assertRaises(LockedBomError) as error:
   with self.db.transaction():
    self.s.update_material(self.other,dict(self.s.material_snapshot(self.other),name='不可部分保存'))
    source.save_bom(self.r,rows)
  self.assertEqual({d['sku_id'] for d in error.exception.details},{self.sid,self.tid});self.assertEqual(self.state(),before)
 def test_open_prelocked_bom_is_readonly_and_unlock_allows_changes(self):
  self.s.set_sku_locked(self.sid,True);self.main=MainWindow(self.s);window=self.main.open_bom_id(self.sid)
  self.assertIn('BOM浏览',window.windowTitle());self.assertFalse(window.save_action.isEnabled())
  self.assertFalse(window.save());self.s.set_sku_locked(self.sid,False)
  window.remove_relation(window.root_item.child(0));self.assertTrue(window.dirty);self.assertTrue(window.save_action.isEnabled())

 def test_legacy_public_bom_is_protected_without_private_namespace(self):
  db=Database(str(Path(self.tmp.name)/'legacy.db'));service=Services(db)
  try:
   root=service.create_material(dict(base_code='ROOT',version='1',name='旧SKU',unit='pcs'));child=service.create_material(dict(base_code='CHILD',version='1',name='旧子料',unit='pcs'))
   service.save_bom(root,[dict(material_id=child,quantity=1,unit='pcs')]);sid=service.create_sku(root);service.set_sku_locked(sid,True)
   self.assertEqual(service.skus()[0]['scope_id'],0)
   with self.assertRaises(LockedBomError):service.save_bom(root,[dict(material_id=child,quantity=8,unit='pcs')])
   self.assertEqual(service.bom(root)[0]['quantity'],1)
  finally:db.close()

 def test_lock_column_fixed_after_resize_refresh_and_centered_icon(self):
  from PyQt5.QtWidgets import QHeaderView,QStyleOptionViewItem,QStyle
  from PyQt5.QtGui import QPixmap,QPainter,QPalette
  from PyQt5.QtCore import QRect,QSize
  from ui.table_layout import fit_columns
  self.s.set_sku_locked(self.sid,True);self.main=MainWindow(self.s)
  table=self.main.table;header=table.horizontalHeader();width=table._fixed_column_widths[7]
  self.main.show();self.main.resize(1800,900);self.app.processEvents();self.main.refresh();fit_columns(table)
  self.assertEqual(header.sectionResizeMode(7),QHeaderView.Fixed);self.assertEqual(header.sectionSize(7),width)
  row=next(i for i in range(table.rowCount()) if table.item(i,7).data(Qt.UserRole))
  image=QPixmap(100,40);image.fill(Qt.white);p=QPainter(image)
  opt=QStyleOptionViewItem();opt.state=QStyle.State_Enabled;opt.rect=QRect(0,0,100,40);opt.decorationSize=QSize(20,20);opt.palette=QPalette(Qt.white)
  table.itemDelegateForColumn(7).paint(p,opt,table.model().index(row,7));p.end()
  pixels=image.toImage();points=[(x,y) for x in range(100) for y in range(40) if pixels.pixelColor(x,y).red()>100 and pixels.pixelColor(x,y).green()<200 and pixels.pixelColor(x,y).blue()<100]
  self.assertTrue(points);self.assertLess(abs((min(x for x,y in points)+max(x for x,y in points))/2-50),3)
