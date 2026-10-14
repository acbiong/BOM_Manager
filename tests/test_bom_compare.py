import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from database.database import Database
from services.services import Services
from services.bom_compare import compare_boms
from ui.bom_compare import BomCompareDialog

class BomCompareTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'test.db'));self.s=Services(self.db)
  self.r,self.p,self.c,self.a,self.n=[self.s.create_material(dict(base_code=x,version='100',name=x,unit='pcs')) for x in ('R','P','C','A','N')]
  self.sid=self.s.create_sku(self.r)
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def put(self,s,parent,children):s.save_bom(parent,[dict(material_id=c,quantity=q,unit='pcs',**kw) for c,q,kw in children])
 def test_independent_mirror_fields_and_alternates(self):
  self.put(self.s,self.r,[(self.p,2,{})]);self.put(self.s,self.p,[(self.c,3,{})])
  copy=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copy)
  self.assertTrue(all(d.status=='same' for d in compare_boms(self.s,self.sid,copy)))
  self.put(mirror,self.p,[(self.c,4,dict(position='A1',remark='test'))]);mirror.add_alternate(mirror.bom(self.p)[0]['id'],self.a)
  rows=compare_boms(self.s,self.sid,copy)
  self.assertEqual([d.status for d in rows],['same','same','modified'])
  self.assertEqual(set(rows[-1].changed),{'quantity','position','remark','alternates'})
  self.assertEqual(self.s.bom(self.p)[0]['quantity'],3)
 def test_deleted_and_added_subtrees_and_ui(self):
  self.put(self.s,self.r,[(self.p,1,{}),(self.a,1,{})]);self.put(self.s,self.p,[(self.c,1,{})])
  copy=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copy)
  self.put(mirror,self.r,[(self.a,1,{}),(self.n,1,{})])
  rows=compare_boms(self.s,self.sid,copy)
  self.assertEqual([d.status for d in rows],['same','deleted','deleted','same','added'])
  dialog=BomCompareDialog(self.s)
  try:
   dialog.compare();a,b=dialog.tables
   self.assertEqual(a.rowCount(),5);self.assertTrue(a.item(1,1).font().strikeOut())
   self.assertEqual(a.item(2,1).background().color().name(),dialog.COLORS['deleted'])
   self.assertEqual(b.item(4,1).background().color().name(),dialog.COLORS['added'])
   self.assertEqual(a.item(4,1).text(),'');self.assertEqual(b.item(1,1).text(),'')
   self.assertEqual(a.rowHeight(1),b.rowHeight(1))
   dialog.right.setCurrentIndex(0);self.assertEqual(a.rowCount(),0)
   dialog.compare();self.assertIn('修改：0',dialog.summary.text())
  finally:dialog.close()
 def test_parent_local_match_and_version_change(self):
  self.put(self.s,self.r,[(self.p,1,{}),(self.n,1,{})]);self.put(self.s,self.p,[(self.c,2,{})]);self.put(self.s,self.n,[(self.c,3,{})])
  copy=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copy)
  new=self.s.create_material(dict(base_code='C',version='101',name='C',unit='pcs'))
  self.put(mirror,self.p,[(new,2,{})])
  rows=compare_boms(self.s,self.sid,copy)
  self.assertEqual([d.status for d in rows],['same','same','modified','same','same'])
  self.assertEqual(rows[2].changed,('version',))
 def test_empty_same_and_invalid_selection(self):
  rows=compare_boms(self.s,self.sid,self.sid);self.assertEqual(len(rows),1);self.assertEqual(rows[0].status,'same')
  with self.assertRaises(ValueError):compare_boms(self.s,self.sid,-1)
 def test_order_alone_is_not_change(self):
  self.put(self.s,self.r,[(self.p,1,{}),(self.c,1,{})]);copy=self.s.copy_sku_bom(self.sid)
  self.put(self.s.for_sku(copy),self.r,[(self.c,1,{}),(self.p,1,{})])
  self.assertTrue(all(d.status=='same' for d in compare_boms(self.s,self.sid,copy)))
 def test_cell_only_colors_character_emphasis_and_parent_columns(self):
  from PyQt5.QtCore import Qt
  from ui.bom_compare import RICH_TEXT_ROLE
  from services.bom_compare import FIELDS
  self.put(self.s,self.r,[(self.p,2,dict(remark='相同前缀甲相同后缀'))])
  copy=self.s.copy_sku_bom(self.sid)
  self.put(self.s.for_sku(copy),self.r,[(self.p,2,dict(remark='相同前缀乙相同后缀'))])
  dialog=BomCompareDialog(self.s)
  try:
   dialog.compare();left,right=dialog.tables
   self.assertEqual([left.horizontalHeaderItem(c).text() for c in range(4)],['状态','层级','父项物料编码','物料编码'])
   self.assertEqual(left.item(0,1).text(),'0');self.assertEqual(left.item(0,2).text(),'ROOT')
   self.assertEqual(left.item(1,1).text(),'1');self.assertEqual(left.item(1,2).text(),'R100')
   remark=1+[k for k,_ in FIELDS].index('remark')
   for table,letter in ((left,'甲'),(right,'乙')):
    for c in range(table.columnCount()):
     item=table.item(1,c)
     if c==remark:
      self.assertEqual(item.background().color().name(),dialog.COLORS['modified'])
      self.assertEqual(item.data(RICH_TEXT_ROLE),'相同前缀<b>'+letter+'</b>相同后缀')
      self.assertFalse(item.font().bold())
     else:
      self.assertEqual(item.background().style(),Qt.NoBrush)
      self.assertIsNone(item.data(RICH_TEXT_ROLE));self.assertFalse(item.font().bold())
   dialog.show();self.app.processEvents()
   self.assertFalse(dialog.grab().isNull())
   left.setColumnWidth(remark,70);self.app.processEvents()
   self.assertEqual(left.rowHeight(1),right.rowHeight(1))
  finally:dialog.close();self.app.processEvents()
 def test_character_diff_insert_delete_escape_multiline(self):
  from ui.bom_compare import character_diff
  self.assertEqual(character_diff('AB新CD','ABCD'),'AB<b>新</b>CD')
  self.assertEqual(character_diff('ABCD','AB新CD'),'ABCD')
  self.assertEqual(character_diff('<甲>\n&','<乙>\n&'),'&lt;<b>甲</b>&gt;<br>&amp;')
  self.assertEqual(character_diff('相同','相同'),'相同')
  self.assertEqual(character_diff('新增',''),'<b>新增</b>')
 def test_parent_replacement_compares_descendants_and_ignores_parent_code(self):
  self.put(self.s,self.r,[(self.p,1,{})]);self.put(self.s,self.p,[(self.c,2,{}),(self.a,3,{})])
  copy=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copy)
  self.put(mirror,self.n,[(self.c,2,{}),(self.a,4,{})]);self.put(mirror,self.r,[(self.n,1,{})])
  rows=compare_boms(self.s,self.sid,copy)
  self.assertEqual([d.status for d in rows],['same','modified','same','modified'])
  self.assertEqual(rows[1].left['material_id'],self.p);self.assertEqual(rows[1].right['material_id'],self.n)
  self.assertEqual(rows[3].changed,('quantity',))
  from PyQt5.QtCore import Qt
  dialog=BomCompareDialog(self.s)
  try:
   dialog.compare()
   for table in dialog.tables:
    self.assertEqual(table.item(2,2).background().style(),Qt.NoBrush)
    self.assertEqual(table.item(3,2).background().style(),Qt.NoBrush)
   self.assertNotEqual(dialog.tables[0].item(2,2).text(),dialog.tables[1].item(2,2).text())
  finally:dialog.close()
 def test_sequence_alignment_keeps_insertions_by_anchor_and_replacements_together(self):
  from services.bom_compare import align_children
  def nodes(*names):return [dict(material_id=n,base_code=n) for n in names]
  def names(pairs):return [(a['base_code'] if a else None,b['base_code'] if b else None) for a,b in pairs]
  self.assertEqual(names(align_children(nodes('A','B','C'),nodes('X','A','N','C','Z'))),[(None,'X'),('A','A'),('B','N'),('C','C'),(None,'Z')])
  self.assertEqual(names(align_children(nodes('A','B','C'),nodes('C','A','B'))),[('A','A'),('B','B'),('C','C')])
  self.assertEqual(names(align_children(nodes('A','B','C'),nodes('A','C'))),[('A','A'),('B',None),('C','C')])
 def test_window_modes_and_scroll_alignment_after_wrapped_rows(self):
  from PyQt5.QtCore import Qt
  from PyQt5.QtGui import QKeyEvent
  from PyQt5.QtCore import QEvent
  children=[(self.s.create_material(dict(base_code=f'T{i}',version='1',name=f'测试物料{i}',unit='pcs')),1,dict(remark='多行说明'*20)) for i in range(30)]
  self.put(self.s,self.r,children);copy=self.s.copy_sku_bom(self.sid)
  dialog=BomCompareDialog(self.s)
  try:
   self.assertTrue(dialog.windowFlags() & Qt.WindowMaximizeButtonHint)
   self.assertTrue(dialog.windowFlags() & Qt.WindowMinimizeButtonHint)
   dialog.compare();dialog.show();self.app.processEvents()
   dialog.showMaximized();self.app.processEvents();self.assertTrue(dialog.isMaximized())
   dialog.toggle_fullscreen();self.app.processEvents();self.assertTrue(dialog.isFullScreen())
   dialog.keyPressEvent(QKeyEvent(QEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier));self.app.processEvents();self.assertTrue(dialog.isMaximized())
   dialog.showNormal();dialog.resize(900,500);self.app.processEvents()
   left,right=dialog.tables
   for source,target in ((left,right),(right,left)):
    source.verticalScrollBar().setValue(source.verticalScrollBar().maximum()//2)
    self.assertGreater(source.verticalScrollBar().value(),0)
    self.assertEqual(source.rowAt(0),target.rowAt(0))
    row=source.rowAt(0);self.assertEqual(source.rowViewportPosition(row),target.rowViewportPosition(row))
   left.setColumnWidth(14,70);self.app.processEvents()
   self.assertEqual(left.verticalScrollBar().value(),right.verticalScrollBar().value())
   self.assertTrue(all(left.rowHeight(r)==right.rowHeight(r) for r in range(left.rowCount())))
  finally:dialog.close();self.app.processEvents()
