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
  self.put(self.s,self.r,[(self.p,1,{})]);self.put(self.s,self.p,[(self.c,1,{})])
  copy=self.s.copy_sku_bom(self.sid);mirror=self.s.for_sku(copy)
  self.put(mirror,self.r,[(self.n,1,{})])
  rows=compare_boms(self.s,self.sid,copy)
  self.assertEqual([d.status for d in rows],['same','deleted','deleted','added'])
  dialog=BomCompareDialog(self.s)
  try:
   dialog.compare();a,b=dialog.tables
   self.assertEqual(a.rowCount(),4);self.assertTrue(a.item(1,1).font().strikeOut())
   self.assertEqual(a.item(2,1).background().color().name(),dialog.COLORS['deleted'])
   self.assertEqual(b.item(3,1).background().color().name(),dialog.COLORS['added'])
   self.assertEqual(a.item(3,1).text(),'');self.assertEqual(b.item(1,1).text(),'')
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
