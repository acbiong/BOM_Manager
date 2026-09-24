import tempfile,unittest,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
class TestServices(unittest.TestCase):
 def setUp(self): self.f=tempfile.NamedTemporaryFile(suffix='.db'); self.s=Services(Database(self.f.name))
 def test_material_unique_and_sku(self):
  i=self.s.create_material({'base_code':'A','version':'1','name':'A','unit':'pcs'})
  with self.assertRaises(Exception): self.s.create_material({'base_code':'A','version':'1','name':'dup','unit':'pcs'})
  self.s.create_sku(i); self.assertEqual(len(self.s.skus()),1)
 def test_bom_and_idle(self):
  a=self.s.create_material({'base_code':'A','version':'1','name':'A','unit':'pcs'}); b=self.s.create_material({'base_code':'B','version':'1','name':'B','unit':'pcs'}); self.s.save_bom(a,[{'material_id':b,'quantity':2,'unit':'pcs','level_no':1}]); self.assertEqual(len(self.s.bom(a)),1); self.assertEqual([r['idle'] for r in self.s.materials() if r['id']==b][0],'N')
 def test_import_export(self):
  from openpyxl import Workbook,load_workbook
  p=self.f.name+'.xlsx'; w=Workbook(); w.active.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN']); w.active.append(['X','1','测试','','pcs','厂商','M']); w.save(p); ok,fail=self.s.import_materials(p); self.assertEqual(ok,['X']); self.assertEqual(fail,[]); out=self.f.name+'-out.xlsx'; self.s.export_materials(out); self.assertEqual(load_workbook(out).sheetnames,['变更记录','物料库']); os.unlink(p); os.unlink(out)
 def test_delete_reference_blocked(self):
  a=self.s.create_material({'base_code':'A','version':'1','name':'A','unit':'pcs'}); b=self.s.create_material({'base_code':'B','version':'1','name':'B','unit':'pcs'}); self.s.save_bom(a,[{'material_id':b,'quantity':1,'unit':'pcs'}])
  with self.assertRaises(ValueError): self.s.delete_material(b)
 def test_bom_import_and_project(self):
     from openpyxl import Workbook
     p=self.f.name+'-bom.xlsx'; a=self.s.create_material({'base_code':'A','version':'1','name':'A','unit':'pcs'}); b=self.s.create_material({'base_code':'B','version':'1','name':'B','unit':'pcs'}); w=Workbook(); w.active.append(['父项物料编码','父项版本号','物料基础编码','物料版本号','物料数量','位置']); w.active.append(['A','1','B','1','3','P1']); w.save(p); self.assertEqual(self.s.import_bom(p,a),1); self.assertEqual(self.s.bom(a)[0]['quantity'],3); self.s.update_project({'project_name':'项目'}); self.assertEqual(self.s.project()['project_name'],'项目'); os.unlink(p)
if __name__=='__main__': unittest.main()
