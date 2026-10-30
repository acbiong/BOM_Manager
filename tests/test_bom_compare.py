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
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare();a,b=dialog.tables
   self.assertEqual(a.rowCount(),5);self.assertTrue(a.item(1,1).font().strikeOut())
   self.assertEqual(a.item(2,1).background().color().name(),dialog.ROW_COLOR)
   self.assertEqual(b.item(4,1).background().color().name(),dialog.ROW_COLOR)
   self.assertEqual(a.item(4,1).text(),'');self.assertEqual(b.item(1,1).text(),'')
   self.assertEqual(a.rowHeight(1),b.rowHeight(1))
   dialog.right.setCurrentIndex(1);self.assertEqual(a.rowCount(),0)
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
  from ui.bom_compare import DISPLAY_FIELDS
  self.put(self.s,self.r,[(self.p,2,dict(remark='相同前缀甲相同后缀'))])
  copy=self.s.copy_sku_bom(self.sid)
  self.put(self.s.for_sku(copy),self.r,[(self.p,2,dict(remark='相同前缀乙相同后缀'))])
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare();left,right=dialog.tables
   self.assertEqual([left.horizontalHeaderItem(c).text() for c in range(5)],['状态','层级','序号','父项物料编码','物料编码'])
   self.assertEqual(left.item(0,1).text(),'0');self.assertEqual(left.item(0,3).text(),'ROOT')
   self.assertEqual(left.item(1,1).text(),'1');self.assertEqual(left.item(1,3).text(),'R100')
   remark=1+[k for k,_ in DISPLAY_FIELDS].index('remark')
   for table,letter in ((left,'甲'),(right,'乙')):
    for c in range(table.columnCount()):
     item=table.item(1,c)
     if c==remark:
      self.assertEqual(item.background().color().name(),dialog.ROW_COLOR)
      self.assertEqual(item.data(RICH_TEXT_ROLE),'相同前缀<span style="background-color: '+dialog.COLORS['modified']+'; color: #202020;"><b>'+letter+'</b></span>相同后缀')
      self.assertFalse(item.font().bold())
     else:
      self.assertEqual(item.background().color().name(),dialog.ROW_COLOR)
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
  self.assertEqual([d.status for d in rows],['same','replaced','same','modified'])
  self.assertEqual(rows[1].left['material_id'],self.p);self.assertEqual(rows[1].right['material_id'],self.n)
  self.assertEqual(rows[3].changed,('quantity',))
  from PyQt5.QtCore import Qt
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare()
   for table in dialog.tables:
    self.assertEqual(table.item(2,3).background().style(),Qt.NoBrush)
    self.assertEqual(table.item(3,3).background().color().name(),dialog.ROW_COLOR)
   self.assertNotEqual(dialog.tables[0].item(2,3).text(),dialog.tables[1].item(2,3).text())
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
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
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
 def test_merged_code_version_and_character_highlight(self):
  from ui.bom_compare import RICH_TEXT_ROLE
  self.put(self.s,self.r,[(self.c,1,{})]);copy=self.s.copy_sku_bom(self.sid)
  new=self.s.create_material(dict(base_code='C',version='101',name='C',unit='pcs'))
  self.put(self.s.for_sku(copy),self.r,[(new,1,{})])
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare();left,right=dialog.tables
   self.assertNotIn('版本号',[left.horizontalHeaderItem(c).text() for c in range(left.columnCount())])
   self.assertEqual(left.item(1,4).text(),'C100');self.assertEqual(right.item(1,4).text(),'C101')
   self.assertEqual(left.item(1,4).data(RICH_TEXT_ROLE),'<span style="background-color: '+dialog.COLORS['modified']+'; color: #202020;"><b>C100</b></span>')
   self.assertEqual(right.item(1,4).data(RICH_TEXT_ROLE),'<span style="background-color: '+dialog.COLORS['modified']+'; color: #202020;"><b>C101</b></span>')
   self.assertEqual(left.item(1,4).background().color().name(),dialog.ROW_COLOR)
  finally:dialog.close()
 def test_click_keyboard_and_blank_partner_row_selection(self):
  from PyQt5.QtCore import Qt
  from PyQt5.QtTest import QTest
  self.put(self.s,self.r,[(self.p,1,{}),(self.c,1,{})]);copy=self.s.copy_sku_bom(self.sid)
  self.put(self.s.for_sku(copy),self.r,[(self.c,1,{})])
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare();dialog.show();self.app.processEvents();left,right=dialog.tables
   def assert_row(row):
    for table in dialog.tables:
     self.assertEqual({i.row() for i in table.selectedIndexes()},{row})
     self.assertEqual(len(table.selectedIndexes()),table.columnCount())
   QTest.mouseClick(left.viewport(),Qt.LeftButton,pos=left.visualItemRect(left.item(1,4)).center());assert_row(1)
   self.assertEqual(right.item(1,4).text(),'')
   QTest.mouseClick(right.viewport(),Qt.LeftButton,pos=right.visualItemRect(right.item(2,3)).center());assert_row(2)
   self.assertTrue(right.hasFocus())
   QTest.keyClick(right,Qt.Key_Up);assert_row(1)
   self.assertEqual(left.verticalScrollBar().value(),right.verticalScrollBar().value())
   dialog.compare()
   self.assertFalse(left.selectedIndexes());self.assertFalse(right.selectedIndexes())
  finally:dialog.close();self.app.processEvents()
 def test_serial_reordering_width_limit_wrapping_and_centering(self):
  from PyQt5.QtCore import Qt
  from ui.bom_compare import DISPLAY_FIELDS
  self.put(self.s,self.r,[(self.p,1,{}),(self.c,2,dict(remark='很长的备注'*70))]);self.put(self.s,self.p,[(self.a,1,{})])
  copy=self.s.copy_sku_bom(self.sid);self.put(self.s.for_sku(copy),self.r,[(self.c,2,dict(remark='很长的备注'*70)),(self.p,1,{})]);self.put(self.s.for_sku(copy),self.p,[(self.a,1,{})])
  rows=compare_boms(self.s,self.sid,copy)
  self.assertTrue(all(d.status=='same' for d in rows))
  self.assertEqual([d.left['serial'] for d in rows],['1','1.1','1.1.1','1.2'])
  self.assertEqual([d.right['serial'] for d in rows],['1','1.1','1.1.1','1.2'])
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare()
   for table in dialog.tables:
    self.assertTrue(all(table.columnWidth(c)<=dialog.max_column_width for c in range(table.columnCount())))
    for c,key in enumerate(['status']+[k for k,_ in DISPLAY_FIELDS]):
     if key in ('status','level','unit','quantity','mp_flag'):
      self.assertEqual(table.item(0,c).textAlignment(),Qt.AlignCenter)
    self.assertEqual(table.item(1,2).background().style(),Qt.NoBrush)
    self.assertGreater(table.rowHeight(3),table.rowHeight(0))
    self.assertGreater(table.columnWidth(1+[k for k,_ in DISPLAY_FIELDS].index('remark')),table.columnWidth(1))
  finally:dialog.close()
 def test_similar_names_pair_across_order_but_are_delete_add(self):
  def create(code,name):return self.s.create_material(dict(base_code=code,version='100',name=name,unit='pcs'))
  bolt=create('B1','固定螺钉M3');wire=create('W1','电源连接线');new_bolt=create('B2','固定螺钉M4');new_wire=create('W2','电源连接线新版')
  self.put(self.s,self.r,[(bolt,1,{}),(wire,1,{})]);copy=self.s.copy_sku_bom(self.sid)
  self.put(self.s.for_sku(copy),self.r,[(new_wire,1,{}),(new_bolt,1,{})])
  rows=compare_boms(self.s,self.sid,copy)
  self.assertEqual([(d.left['material_id'],d.right['material_id'],d.status) for d in rows[1:]],[(bolt,new_bolt,'replaced'),(wire,new_wire,'replaced')])
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare();left,right=dialog.tables
   self.assertEqual(left.item(1,0).text(),'换料');self.assertEqual(right.item(1,0).text(),'换料')
   self.assertEqual(left.item(1,4).background().color().name(),dialog.ROW_COLOR)
   self.assertFalse(left.item(1,4).font().strikeOut())
   self.assertEqual(right.item(1,4).background().color().name(),dialog.ROW_COLOR)
   self.assertIn('换料：2',dialog.summary.text());self.assertIn('新增：0',dialog.summary.text());self.assertIn('删除：0',dialog.summary.text())
  finally:dialog.close()
 def test_aligned_serials_are_display_only_and_preserve_database_order(self):
  self.put(self.s,self.r,[(self.p,1,{}),(self.c,1,{})]);self.put(self.s,self.p,[(self.a,1,{})])
  copied=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copied)
  self.put(mirror,self.r,[(self.c,1,{}),(self.p,1,{})]);self.put(mirror,self.p,[(self.a,1,{})])
  def state():return ([dict(r) for r in self.s.bom(self.r)],[dict(r) for r in mirror.bom(self.r)],[dict(r) for r in self.s.skus()])
  before=state();changes=self.db.conn.total_changes
  first=compare_boms(self.s,self.sid,copied);second=compare_boms(self.s,self.sid,copied)
  self.assertEqual(before,state());self.assertEqual(changes,self.db.conn.total_changes)
  self.assertEqual(first,second)
  self.assertEqual([(d.left['serial'],d.right['serial']) for d in first],[('1','1'),('1.1','1.1'),('1.1.1','1.1.1'),('1.2','1.2')])
  self.assertTrue(all(d.status=='same' for d in first))
 def test_similar_name_alignment_numbering_and_single_side_slots(self):
  def new(code,name):return self.s.create_material(dict(base_code=code,version='100',name=name,unit='pcs'))
  old=new('OLD','连接器白色');replacement=new('NEW','连接器黑色')
  self.put(self.s,self.r,[(old,1,{}),(self.p,1,{})]);copied=self.s.copy_sku_bom(self.sid)
  self.put(self.s.for_sku(copied),self.r,[(self.p,1,{}),(replacement,1,{}),(self.c,1,{})])
  rows=compare_boms(self.s,self.sid,copied)
  self.assertEqual([(d.left and d.left['serial'],d.right and d.right['serial']) for d in rows],[('1','1'),('1.1','1.1'),('1.2','1.2'),(None,'1.3')])
  self.assertEqual(rows[1].status,'replaced');self.assertEqual(rows[1].right['material_id'],replacement)
 def test_multiple_versions_pair_by_code_before_similar_names(self):
  from services.bom_compare import align_children
  left=[dict(material_id=i,base_code='SAME',name='旧名称') for i in (1,2)]
  right=[dict(material_id=i,base_code='SAME',name='新名称') for i in (4,3)]
  right.insert(0,dict(material_id=5,base_code='OTHER',name='旧名称'))
  pairs=list(align_children(left,right))
  matched=[(a,b) for a,b in pairs if a is not None]
  self.assertTrue(all(a['base_code']==b['base_code']=='SAME' for a,b in matched))
  self.assertEqual(len(matched),2)
 def test_sticky_columns_threshold_selection_and_scroll(self):
  from PyQt5.QtCore import Qt
  from PyQt5.QtTest import QTest
  from PyQt5.QtGui import QFontMetrics,QFont
  children=[(self.s.create_material(dict(base_code=f'X{i}',version='100',name='物料'+str(i),unit='pcs')),1,{}) for i in range(40)]
  self.put(self.s,self.r,children);self.s.copy_sku_bom(self.sid)
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare();dialog.show();self.app.processEvents();left,right=dialog.tables
   font=QFont(dialog.font());font.setBold(True)
   self.assertEqual(dialog.max_column_width,QFontMetrics(font).horizontalAdvance('中')*20)
   threshold=left.columnWidth(0)+left.columnWidth(1)
   left.horizontalScrollBar().setValue(threshold-1);self.assertFalse(left.frozen.isVisible())
   left.horizontalScrollBar().setValue(threshold);self.app.processEvents()
   for table in dialog.tables:
    self.assertTrue(table.frozen.isVisible())
    self.assertEqual([c for c in range(table.columnCount()) if not table.frozen.isColumnHidden(c)],[2,3,4,5])
   index=left.model().index(2,4)
   QTest.mouseClick(left.frozen.viewport(),Qt.LeftButton,pos=left.frozen.visualRect(index).center())
   for table in dialog.tables:self.assertEqual({i.row() for i in table.selectedIndexes()},{2})
   left.verticalScrollBar().setValue(200);self.app.processEvents()
   self.assertEqual(left.frozen.rowAt(0),left.rowAt(0));self.assertEqual(right.frozen.rowAt(0),right.rowAt(0))
   left.horizontalScrollBar().setValue(0);self.assertFalse(left.frozen.isVisible());self.assertFalse(right.frozen.isVisible())
  finally:dialog.close();self.app.processEvents()
 def test_character_background_only_changes_and_row_hint(self):
  from ui.bom_compare import character_diff,RICH_TEXT_ROLE
  from PyQt5.QtGui import QTextDocument,QTextCursor,QColor
  html=character_diff('前甲后','前乙后','#ffc35c');doc=QTextDocument();doc.setHtml(html)
  for pos in range(3):
   cursor=QTextCursor(doc);cursor.setPosition(pos);cursor.movePosition(QTextCursor.Right,QTextCursor.KeepAnchor)
   fmt=cursor.charFormat()
   if pos==1:self.assertEqual(fmt.background().color(),QColor('#ffc35c'));self.assertGreater(fmt.fontWeight(),50)
   else:self.assertEqual(fmt.background().style(),0);self.assertEqual(fmt.fontWeight(),50)
 def test_main_alternate_exchange_identity_overrides_names_and_order(self):
  from ui.bom_compare import RICH_TEXT_ROLE
  self.put(self.s,self.r,[(self.p,2,{}),(self.c,3,{})])
  self.s.add_alternate(self.s.bom(self.r)[0]['id'],self.a)
  self.s.add_alternate(self.s.bom(self.r)[0]['id'],self.n)
  copied=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copied)
  self.put(mirror,self.r,[(self.c,3,{}),(self.a,2,{})])
  relation=next(r for r in mirror.bom(self.r) if r['material_id']==self.a)
  mirror.add_alternate(relation['id'],self.p);mirror.add_alternate(relation['id'],self.n)
  rows=compare_boms(self.s,self.sid,copied)
  self.assertEqual([d.status for d in rows],['same','exchanged','same'])
  self.assertEqual(rows[1].right['material_id'],self.a)
  self.assertEqual(compare_boms(self.s,copied,self.sid)[2].status,'exchanged')
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare()
   for table in dialog.tables:
    self.assertEqual(table.item(1,0).text(),'交换')
    self.assertFalse(table.item(1,4).font().strikeOut())
    self.assertIn('<b>'+table.item(1,4).text()+'</b>',table.item(1,4).data(RICH_TEXT_ROLE))
   self.assertIn('交换：1',dialog.summary.text());self.assertIn('换料：0',dialog.summary.text())
  finally:dialog.close()
 def test_one_way_alternate_reference_is_not_exchange(self):
  self.put(self.s,self.r,[(self.p,1,{})]);self.s.add_alternate(self.s.bom(self.r)[0]['id'],self.a)
  copied=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copied)
  self.put(mirror,self.r,[(self.a,1,{})])
  self.assertEqual(compare_boms(self.s,self.sid,copied)[1].status,'replaced')
  self.put(mirror,self.r,[(self.p,1,{})]);mirror.add_alternate(mirror.bom(self.r)[0]['id'],self.c)
  self.assertEqual(compare_boms(self.s,self.sid,copied)[1].status,'modified')
 def test_click_has_no_delayed_scroll_or_layout_and_compact_fullscreen(self):
  from PyQt5.QtCore import Qt
  from PyQt5.QtTest import QTest
  from unittest.mock import patch
  children=[(self.s.create_material(dict(base_code=f'J{i}',version='100',name='很长的物料名称'*12,unit='pcs')),1,dict(remark='多行备注'*20)) for i in range(35)]
  self.put(self.s,self.r,children);self.s.copy_sku_bom(self.sid)
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2 if dialog.right.count()>2 else 1)
  try:
   dialog.compare();dialog.show();dialog.resize(1100,650);self.app.processEvents()
   layout=dialog.layout().itemAt(0).layout()
   self.assertIs(layout.itemAt(1).widget(),dialog.fullscreen_button)
   self.assertLess(dialog.fullscreen_button.width(),dialog.width()//3)
   left,right=dialog.tables
   left.horizontalScrollBar().setValue(left.columnWidth(0)+left.columnWidth(1)+60)
   self.app.processEvents();self.app.processEvents()
   left.verticalScrollBar().setValue(100);self.app.processEvents()
   def state():return [(t.horizontalScrollBar().value(),t.verticalScrollBar().value(),tuple(t.rowHeight(r) for r in range(t.rowCount())),t.frozen.isVisible()) for t in dialog.tables]
   before=state()
   # The frozen view shares a current index with the main table; selecting it
   # must not schedule a later ensureVisible/auto-scroll on either side.
   point=left.frozen.viewport().rect().center()
   row=left.frozen.rowAt(point.y())
   with patch.object(dialog,'align_rows',wraps=dialog.align_rows) as align:
    QTest.mouseClick(left.frozen.viewport(),Qt.LeftButton,pos=point)
    self.assertEqual(state(),before)
    for t in dialog.tables:self.assertEqual({i.row() for i in t.selectedIndexes()},{row})
    QTest.qWait(1200)
    self.assertEqual(state(),before);align.assert_not_called()
   # Clicking the right-hand scrolling properties also keeps both viewports stable.
   point=right.viewport().rect().topRight();point.setX(point.x()-8);point.setY(35)
   before=state();QTest.mouseClick(right.viewport(),Qt.LeftButton,pos=point)
   self.assertEqual(state(),before);QTest.qWait(1200);self.assertEqual(state(),before)
  finally:dialog.close();self.app.processEvents()
 def test_nonmodal_empty_choices_live_drafts_and_exact_editor_location(self):
  from ui.main_window import MainWindow
  from PyQt5.QtCore import Qt
  self.put(self.s,self.r,[(self.p,1,{}),(self.c,1,{})]);self.put(self.s,self.p,[(self.a,1,{})]);self.put(self.s,self.c,[(self.a,1,{})])
  copied=self.s.copy_sku_bom(self.sid);main=MainWindow(self.s)
  try:
   main.compare_boms();dialog=main._compare_dialog
   self.assertFalse(dialog.isModal())
   self.assertIsNone(dialog.left.currentData());self.assertIsNone(dialog.right.currentData())
   self.assertEqual(dialog.left.currentText(),'请显示对比的BOM')
   dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2);dialog.compare()
   dialog.open_editor(0,4);window=main._bom_windows[self.sid]
   self.assertEqual(window.tree.currentItem().data(0,Qt.UserRole)['material_id'],self.a)
   self.assertEqual(window.tree.currentItem().parent().data(0,Qt.UserRole)['material_id'],self.c)
   item=window.tree.currentItem();data=dict(item.data(0,Qt.UserRole));data['quantity']=9;item.setData(0,Qt.UserRole,data);window.mark_dirty()
   from PyQt5.QtTest import QTest
   QTest.qWait(250)
   self.assertEqual(dialog._rows[4].left['quantity'],9)
   self.assertEqual(dialog._rows[4].right['quantity'],1)
   self.assertEqual(dialog._rows[4].status,'modified')
   dialog.open_editor(0,4);self.assertIs(main._bom_windows[self.sid],window)
   self.assertIs(window.tree.currentItem(),item)
   window.dirty=False;window.close();QTest.qWait(250)
   self.assertTrue(all(d.status=='same' for d in dialog._rows))
  finally:
   if getattr(main,'_compare_dialog',None):main._compare_dialog.close()
   for w in list(main._bom_windows.values()):w.dirty=False;w.close()
   main.close();self.app.processEvents()
 def test_compare_direct_material_edit_updates_both_sides_and_cancel(self):
  from unittest.mock import patch
  from ui.main_window import MaterialDialog
  from PyQt5.QtWidgets import QDialog,QLabel
  self.put(self.s,self.r,[(self.p,2,{})]);self.s.copy_sku_bom(self.sid)
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2)
  try:
   dialog.compare();dialog.show();self.app.processEvents()
   def edit(form):
    self.assertIsInstance(form.e['base_code'],QLabel);self.assertIsInstance(form.e['version'],QLabel)
    form.e['name'].setText('对比中编辑名称');return QDialog.Accepted
   with patch.object(MaterialDialog,'exec_',edit):dialog.edit_material(1,1)
   self.app.processEvents();self.app.processEvents()
   self.assertEqual(self.s.material_snapshot(self.p)['name'],'对比中编辑名称')
   self.assertEqual(dialog._rows[1].left['name'],'对比中编辑名称');self.assertEqual(dialog._rows[1].right['name'],'对比中编辑名称')
   with patch.object(MaterialDialog,'exec_',return_value=QDialog.Rejected),patch.object(self.s,'update_material') as update:
    dialog.edit_material(0,1);update.assert_not_called()
   with patch.object(MaterialDialog,'exec_',edit),patch.object(self.s,'update_material',side_effect=ValueError('invalid')),patch('ui.bom_compare.QMessageBox.warning') as warning:
    dialog.edit_material(0,1);warning.assert_called_once()
  finally:dialog.close();self.app.processEvents()
 def test_difference_only_filter_restore_frozen_and_live_refresh(self):
  self.put(self.s,self.r,[(self.p,1,{}),(self.c,1,{})]);copied=self.s.copy_sku_bom(self.sid)
  self.put(self.s.for_sku(copied),self.r,[(self.p,2,{}),(self.c,1,{})])
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(2)
  try:
   self.assertFalse(dialog.differences_only.isChecked());dialog.compare();dialog.show();self.app.processEvents()
   original=[d.left['serial'] for d in dialog._rows]
   dialog.differences_only.setChecked(True)
   for table in dialog.tables:
    self.assertEqual([table.isRowHidden(r) for r in range(3)],[True,False,True])
    self.assertEqual([table.frozen.isRowHidden(r) for r in range(3)],[True,False,True])
   dialog.compare()
   self.assertTrue(dialog.tables[0].isRowHidden(0));self.assertEqual([d.left['serial'] for d in dialog._rows],original)
   self.put(self.s.for_sku(copied),self.r,[(self.p,1,{}),(self.c,1,{})]);self.app.processEvents();self.app.processEvents()
   self.assertTrue(all(dialog.tables[0].isRowHidden(r) for r in range(3)))
   dialog.differences_only.setChecked(False)
   for table in dialog.tables:
    self.assertTrue(all(not table.isRowHidden(r) and not table.frozen.isRowHidden(r) for r in range(3)))
   self.assertEqual([d.left['serial'] for d in dialog._rows],original)
  finally:dialog.close();self.app.processEvents()
 def test_sku_context_compare_uses_exact_mirror_and_reuses_window(self):
  from unittest.mock import patch
  from PyQt5.QtCore import QPoint
  from PyQt5.QtWidgets import QMenu
  from ui.main_window import MainWindow
  self.put(self.s,self.r,[(self.p,2,{})]);copy=self.s.copy_sku_bom(self.sid)
  self.put(self.s.for_sku(copy),self.r,[(self.p,5,{})]);main=MainWindow(self.s)
  try:
   main.sort_skus(4);main.sort_skus(4)
   row=next(r for r in range(main.table.rowCount()) if int(main.table.item(r,6).text())==copy)
   def choose(menu,*args):return next(a for a in menu.actions() if a.text()=='BOM对比')
   with patch.object(main.table,'rowAt',return_value=row),patch.object(QMenu,'exec_',choose):main.sku_context_menu(QPoint())
   dialog=main._compare_dialog;self.assertTrue(dialog.isVisible());self.assertEqual(dialog.left.currentData(),copy);self.assertIsNone(dialog.right.currentData());self.assertFalse(dialog._compared)
   dialog.right.setCurrentIndex(dialog.right.findData(self.sid));dialog.compare();self.assertEqual(dialog._rows[1].status,'modified')
   dialog.close();main.compare_sku_bom(self.sid)
   self.assertIs(main._compare_dialog,dialog);self.assertTrue(dialog.isVisible());self.assertEqual(dialog.left.currentData(),self.sid);self.assertEqual(dialog.right.currentData(),self.sid);self.assertFalse(dialog._compared);self.assertEqual(dialog._rows,[]);dialog.button.click();self.assertTrue(all(r.status=='same' for r in dialog._rows))
   main.compare_sku_bom(copy);self.assertEqual(dialog.left.currentData(),copy);self.assertEqual(dialog._rows,[]);self.app.processEvents();self.assertFalse(dialog._compared);dialog.button.click();self.assertEqual(dialog._rows[1].status,'modified')
   main.compare_boms();self.assertEqual(dialog.left.currentData(),copy);self.assertEqual(dialog.right.currentData(),self.sid);self.assertFalse(dialog._compared);self.assertEqual(dialog._rows,[])
  finally:main.close()
 def test_typing_debounces_live_compare_without_progress_and_reuses_unchanged_rows(self):
  from unittest.mock import patch
  from PyQt5.QtTest import QTest
  from ui.main_window import MainWindow
  from ui.operation_progress import OperationProgress
  self.put(self.s,self.r,[(self.p,1,{}),(self.c,1,{})]);copied=self.s.copy_sku_bom(self.sid);main=MainWindow(self.s)
  try:
   main.compare_boms();dialog=main._compare_dialog
   dialog.left.setCurrentIndex(dialog.left.findData(self.sid));dialog.right.setCurrentIndex(dialog.right.findData(copied));dialog.compare()
   editor=main.open_bom_id(self.sid);editor.show_item_info(editor.root_item.child(0));untouched=dialog.tables[0].item(2,0)
   with patch.object(OperationProgress,'threshold',0),patch.object(OperationProgress,'update',wraps=OperationProgress.update) as progress,patch.object(dialog,'compare',wraps=dialog.compare) as compare:
    for i in range(20):editor.update_tree_field('remark',f'连续输入{i}')
    compare.assert_not_called();QTest.qWait(300)
    self.assertEqual(compare.call_count,1);progress.assert_not_called()
   self.assertEqual(dialog._rows[1].left['remark'],'连续输入19')
   self.assertIs(dialog.tables[0].item(2,0),untouched)
   self.assertEqual(dialog._rows[1].status,'modified')
   with patch.object(dialog.tables[0],'resizeRowsToContents',wraps=dialog.tables[0].resizeRowsToContents) as resize:
    dialog.live_refresh();resize.assert_not_called()
  finally:
   for window in list(main._bom_windows.values()):window.dirty=False;window.close()
   main.close();self.app.processEvents()
 def test_live_snapshot_reuses_shared_material_reads_only_within_call(self):
  from unittest.mock import patch
  from ui.main_window import MainWindow
  self.put(self.s,self.r,[(self.p,1,{}),(self.c,1,{})]);self.put(self.s,self.p,[(self.a,1,{})]);self.put(self.s,self.c,[(self.a,1,{})]);main=MainWindow(self.s)
  try:
   editor=main.open_bom_id(self.sid);editor.dirty=True;dialog=BomCompareDialog(self.s,main);sku=dict(self.s.skus()[0])
   with patch.object(editor.svc,'material_snapshot',wraps=editor.svc.material_snapshot) as read:
    dialog.live_snapshot(sku);self.assertEqual(read.call_count,4)
    dialog.live_snapshot(sku);self.assertEqual(read.call_count,8)
   dialog.close()
  finally:
   for window in list(main._bom_windows.values()):window.dirty=False;window.close()
   main.close();self.app.processEvents()
 def test_exact_identity_alignment_is_linear_even_for_reversed_siblings(self):
  from services.bom_compare import align_children
  class Counted(dict):
   reads=0
   def __getitem__(self,key):
    if key=='base_code':Counted.reads+=1
    return super().__getitem__(key)
  nodes=[Counted(base_code=str(i),version='100',material_id=i) for i in range(2000)]
  pairs=list(align_children(nodes,list(reversed(nodes))))
  self.assertEqual(len(pairs),2000);self.assertTrue(all(a is b for a,b in pairs));self.assertLessEqual(Counted.reads,8000)
 def test_live_compare_failure_stays_inline_and_restores_progress_context(self):
  from unittest.mock import patch
  from infrastructure.operation_progress import _silent,_current
  dialog=BomCompareDialog(self.s);dialog.left.setCurrentIndex(1);dialog.right.setCurrentIndex(1);dialog.compare()
  try:
   with patch('ui.bom_compare.compare_trees',side_effect=ValueError('测试外部文件失效')),patch('ui.bom_compare.QMessageBox.warning') as warning:
    dialog.live_refresh();warning.assert_not_called()
   self.assertIn('测试外部文件失效',dialog.summary.text());self.assertFalse(_silent.get());self.assertIsNone(_current.get())
  finally:dialog.close()
