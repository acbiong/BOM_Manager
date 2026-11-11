"""Read-only reproduction of stale public cache versus actual SKU history usage."""
import sys,sqlite3,json,hashlib
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from services.services import Services
p=Path('/home/biong/Documents/BOM/数据库/mobius_lite_bom.db')
before=hashlib.sha256(p.read_bytes()).hexdigest()
conn=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
conn.execute('PRAGMA query_only=ON')
s=Services(SimpleNamespace(path=str(p),conn=conn));results=[]
for base in ('BC2-0400202','BC2-0400215'):
 for material in s.materials(base):
  mid=material['id'];refs=s.material_usage(mid)
  keys=[(r['sku_id'],r.get('parent_id'),r.get('focus_material_id')) for r in refs]
  assert len(keys)==len(set(keys)),refs
  for ref in refs:
   sku=next(r for r in s.skus() if r['id']==ref['sku_id'])
   actual=s.for_sku(sku['id']).bom(sku['material_id'])
   assert any(r['material_id']==mid and r['parent_material_id']==ref['parent_id'] for r in actual),ref
  if material['version']=='060':assert not refs and material['idle']=='Y'
  if material['version']=='100':assert len(refs)==1 and material['idle']=='N'
  results.append(dict(code=base+material['version'],idle=material['idle'],references=refs))
conn.close();assert before==hashlib.sha256(p.read_bytes()).hexdigest()
Path('test_reports/lite_actual_usage.json').write_text(json.dumps(dict(passed=True,database_unchanged=True,results=results),ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False,indent=2))
