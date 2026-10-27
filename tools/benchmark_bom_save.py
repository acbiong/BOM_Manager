#!/usr/bin/env python3
"""Profile saving a new comparable BOM, strictly on a SQLite backup."""
import os,sys,sqlite3,tempfile,time,json,cProfile,pstats,hashlib,argparse
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PyQt5.QtWidgets import QApplication
from unittest.mock import patch
from database.database import Database
from services.services import Services
from config.config_service import ConfigService
from ui.main_window import MainWindow,BomWindow
from services.current_catalog import latest_skus,groups,rows_for

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--report',required=True);parser.add_argument('--profile',action='store_true');parser.add_argument('--max-ms',type=float);args=parser.parse_args()
 source=Path(args.source).resolve();before=hashlib.sha256(source.read_bytes()).hexdigest();app=QApplication([])
 with tempfile.TemporaryDirectory(dir=ROOT/'.tmp',prefix='bom_save_perf_') as folder:
  target=Path(folder)/'copy.db';reader=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);writer=sqlite3.connect(target)
  try:reader.backup(writer)
  finally:writer.close();reader.close()
  db=Database(str(target));s=Services(db,ConfigService(folder))
  candidates=[(len(s.for_sku(row['id']).bom(row['material_id'])),dict(row)) for row in latest_skus(s)]
  count,sku=max(candidates,key=lambda pair:pair[0]);original=s.for_sku(sku['id']);graph=groups(original)
  mid=s.create_material(dict(base_code='PERF-NEW',version='100',name='隔离副本性能验证',unit='pcs'));sid=s.create_sku(mid);service=s.for_sku(sid)
  rows=rows_for(graph,sku['material_id'])
  for row in rows:
   if row['parent_material_id']==sku['material_id']:row['parent_material_id']=mid
  main=MainWindow(s);main.show();main.show_materials();w=BomWindow(service,mid,main);w.show()
  nodes=service.save_bom(mid,rows,preview=True);w.stage_import(nodes);app.processEvents()
  original_times={row['id']:row['updated_at'] for row in s.skus() if row['id']!=sid}
  expected=rows_for(graph,sku['material_id'])
  profiler=cProfile.Profile();start=time.perf_counter()
  with patch('ui.main_window.QMessageBox.information'),patch('ui.main_window.show_operation_error',side_effect=lambda *a: (_ for _ in ()).throw(RuntimeError(str(a)))):
   if args.profile:profiler.enable()
   success=w.save()
   if args.profile:profiler.disable()
  elapsed=(time.perf_counter()-start)*1000
  assert success
  assert original_times=={row['id']:row['updated_at'] for row in s.skus() if row['id']!=sid},'Unchanged SKU timestamp modified'
  actual=rows_for(groups(service),mid)
  for row in actual:
   if row['parent_material_id']==mid:row['parent_material_id']=sku['material_id']
  fields=('parent_material_id','material_id','quantity','unit','position','remark','alternate_material_ids')
  assert [{k:r.get(k) for k in fields} for r in actual]==[{k:r.get(k) for k in fields} for r in expected], 'Saved structure differs'
  result={'source':str(source),'source_sha256_before':before,'rows':count,'source_sku':sku['base_code']+sku['version'],'save_ms':elapsed,'success':success,'materials':len(s.materials()),'skus':len(s.skus())}
  w.dirty=False;w.close();main._materials.close();main.close();db.close()
 after=hashlib.sha256(source.read_bytes()).hexdigest();result['source_sha256_after']=after;assert before==after,'Source database changed'
 report=Path(args.report);report.parent.mkdir(exist_ok=True,parents=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
 if args.max_ms is not None and elapsed>args.max_ms:raise SystemExit(f'Save {elapsed:.1f}ms exceeds {args.max_ms:.1f}ms')
 if args.profile:
  with report.with_suffix('.profile.txt').open('w') as out:pstats.Stats(profiler,stream=out).strip_dirs().sort_stats('cumulative').print_stats(65)
if __name__=='__main__':main()
