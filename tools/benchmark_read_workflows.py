#!/usr/bin/env python3
"""Measure repeated read workflows only on a disposable SQLite backup."""
import sys,sqlite3,tempfile,time,json,hashlib,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from database.database import Database
from services.services import Services

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--report',required=True);args=p.parse_args();source=Path(args.source).resolve();digest=hashlib.sha256(source.read_bytes()).hexdigest();results={}
 with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
  target=Path(folder)/'copy.db';a=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);b=sqlite3.connect(target)
  try:a.backup(b)
  finally:a.close();b.close()
  db=Database(str(target));s=Services(db);skus=list(s.skus());sku=max(skus,key=lambda r:len(s.for_sku(r['id']).bom(r['material_id'])));scoped=s.for_sku(sku['id'])
  from services.bom_compare import snapshot
  operations={'all_bom_reads':lambda:[s.for_sku(r['id']).bom(r['material_id']) for r in skus], 'materials':s.materials,'compare_tree':lambda:snapshot(s,sku), 'export_database':lambda:s.export_database(str(Path(folder)/'export.xlsx'))}
  for label,operation in operations.items():
   queries=[];db.conn.set_trace_callback(queries.append);start=time.perf_counter();operation();elapsed=(time.perf_counter()-start)*1000;db.conn.set_trace_callback(None);results[label]={'ms':elapsed,'sql_count':len(queries)}
  from openpyxl import load_workbook
  wb=load_workbook(Path(folder)/'export.xlsx');sheets=[]
  for ws in wb:
   sheets.append((ws.title,[[[cell.value,cell.number_format,str(cell.alignment),str(cell.border),str(cell.fill),str(cell.font)] for cell in row] for row in ws],[(k,v.width) for k,v in ws.column_dimensions.items()]))
  wb.close();results['export_content_sha256']=hashlib.sha256(json.dumps(sheets,ensure_ascii=False,default=str).encode()).hexdigest()
  assert db.conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
 assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
 Path(args.report).write_text(json.dumps({'source_sha256':digest,'skus':len(skus),'results':results},indent=2));print(results)
if __name__=='__main__':main()
