import tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from openpyxl import load_workbook
class TestExports(unittest.TestCase):
 def test_database_export_sheets(self):
  f=tempfile.NamedTemporaryFile(suffix='.db'); s=Services(Database(f.name)); m=s.create_material({'base_code':'A','version':'1','name':'A','unit':'pcs'}); s.create_sku(m); out=f.name+'.xlsx'; s.export_database(out); self.assertEqual(load_workbook(out).sheetnames,['SKU清单','物料库','变更记录','A1'])
if __name__=='__main__': unittest.main()
