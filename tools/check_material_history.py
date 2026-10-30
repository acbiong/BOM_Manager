#!/usr/bin/env python3
"""Read-only source backup, migration isolation, real-data save and window checks."""
import argparse,hashlib,json,sqlite3,sys,tempfile,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);parser.add_argument('--native',action='store_true');args=parser.parse_args()
if not args.native:os.environ['QT_QPA_PLATFORM']='offscreen'
from PyQt5.QtWidgets import QApplication
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate
from services.current_catalog import initialize as catalog
from services import material_history as h
from ui.main_window import MaterialWindow
from ui.material_history import MaterialHistoryDialog,MaterialHistoryChoiceDialog

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def logical(service):
 result={}
 for sku in service.skus():
  scoped=service.for_sku(sku['id']);rows=scoped.bom(sku['material_id'])
  result[sku['id']]=[(r['parent_material_id'],r['material_id'],r['quantity'],r['unit'],r['position'],r['remark'],tuple(scoped.material_snapshot(r['material_id'])[k] for k in h.FIELDS),tuple(a['material_id'] for a in scoped.alternates(r['id']))) for r in rows]
 return result

source=Path(args.database);before=digest(source);report={'source':str(source),'source_sha256':before}
app=QApplication.instance() or QApplication([])
from ui.theme import apply_theme
apply_theme(False)
with tempfile.TemporaryDirectory(prefix='bom-history-check-') as temp:
 path=Path(temp)/'copy.db';reader=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True);writer=sqlite3.connect(path)
 try:reader.backup(writer)
 finally:writer.close();reader.close()
 db=Database(str(path));svc=Services(db);migrate(db);catalog(db);original=logical(svc)
 started=time.perf_counter();h.initialize(db);report['migration_ms']=round((time.perf_counter()-started)*1000,2)
 assert original==logical(svc),'Migration changed existing BOMs'
 sku=next(s for s in svc.skus() if svc.for_sku(s['id']).bom(s['material_id']))
 sid=svc.copy_sku_bom(sku['id']);scoped=svc.for_sku(sid);rows=[dict(r,alternate_material_ids=[a['material_id'] for a in scoped.alternates(r['id'])]) for r in scoped.bom(sku['material_id'])]
 alternate=svc.create_material(dict(base_code='HISTORY_TEST_ONLY',version='100',name='副本验证替代料',unit='pcs'))
 selected=rows[-1]['material_id'];parent=rows[-1]['parent_material_id']
 for r in rows:
  if r['parent_material_id']==parent and r['material_id']==selected:r['alternate_material_ids'].append(alternate)
 started=time.perf_counter();h.save(scoped,sku['material_id'],rows,{},'fork');report['save_ms']=round((time.perf_counter()-started)*1000,2)
 after=logical(svc)
 assert all(after[sid]==value for sid,value in original.items()),'Independent save modified an existing BOM'
 assert db.conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 count=db.conn.execute('SELECT COUNT(*) FROM material_histories').fetchone()[0];h.initialize(db)
 assert db.conn.execute('SELECT COUNT(*) FROM material_histories').fetchone()[0]==count
 library=MaterialWindow(svc);library.show();app.processEvents()
 viewer=MaterialHistoryDialog(svc,parent,h.versions(svc,parent)[0]['history_version'],library);viewer.show();app.processEvents()
 choice=MaterialHistoryChoiceDialog(scoped,selected,'新增替代料',library,impact_mid=parent);choice.show();app.processEvents()
 out=ROOT/'test_reports';out.mkdir(exist_ok=True)
 for name,window in [('library',library),('viewer',viewer),('choice',choice)]:
  window.raise_();app.processEvents();window.grab().save(str(out/('material_history_'+name+'.png')))
  assert window.windowModality()==0
 choice.close();viewer.close();library.close();db.close()
 report.update(passed=True,original_boms=len(original),history_records=count,integrity='ok',qt_platform=app.platformName())
assert digest(source)==before,'Original database was modified'
report['source_unchanged']=True
(ROOT/'test_reports/material_history_real.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
