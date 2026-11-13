"""Export the reported SKU histories read-only and verify deletion records."""
import sys,sqlite3,json,hashlib
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from services.services import Services
from openpyxl import load_workbook
source=Path('/home/biong/Documents/BOM/数据库/mobius_foot_MFH1_bom.db')
before=hashlib.sha256(source.read_bytes()).hexdigest()
c=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
s=Services(SimpleNamespace(conn=c,path=str(source)))
out=Path('test_reports/foot_export_logs');out.mkdir(parents=True,exist_ok=True);report=[]
for code in ('BC3-0000647100','BC3-0000648100'):
 sku=next(r for r in s.skus() if r['base_code']+r['version']==code and r['mirror_version']==100)
 path=out/(code+' 历史版本100.xlsx');s.export_sku(sku['id'],path)
 w=load_workbook(path);changes=list(w['变更记录'].values)[1:];bom=list(w.worksheets[1].values)[2:]
 for mid in ('BC2-0200349100','BC2-0200353100'):
  found=[r for r in changes if r[3]==mid and r[1]=='2026-11-13' and '删除物料' in str(r[5])]
  assert len(found)==1,(code,mid,found)
  assert not any(str(r[4])+str(r[5])==mid for r in bom)
  report.append(dict(sku=code,material=mid,export_row=found[0][0],date=found[0][1],time=found[0][2],detail=found[0][6]))
 w.close()
c.close();assert before==hashlib.sha256(source.read_bytes()).hexdigest()
(out/'summary.json').write_text(json.dumps(dict(passed=True,database_unchanged=True,records=report),ensure_ascii=False,indent=2))
print('FOOT_EXPORT_LOGS_OK',len(report))
