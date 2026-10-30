#!/usr/bin/env python3
"""Compare baseline/current live refresh on synthetic temporary data, without user DB writes."""
import os,sys,argparse,subprocess,types,time,tempfile,json,statistics,copy
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt,QEvent
from database.database import Database
from services.services import Services
from services.bom_compare import compare_trees
from ui.main_window import MainWindow
from ui.bom_compare import BomCompareDialog
from ui.operation_progress import OperationProgress

def load_baseline(revision,path,name):
 module=types.ModuleType(name);sys.modules[name]=module
 source=subprocess.check_output(['git','show',revision+':'+path],cwd=ROOT,text=True)
 exec(compile(source,path,'exec'),module.__dict__);return module

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--baseline',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
 old=load_baseline(args.baseline,'src/services/bom_compare.py','_old_compare')
 old_ui=load_baseline(args.baseline,'src/ui/bom_compare.py','_old_ui_compare');old_ui.compare_trees=old.compare_trees
 app=QApplication([]);OperationProgress.threshold=float('inf')
 def node(i):return dict(base_code=str(i),version='100',name=str(i),material_id=i,children=[],quantity=1)
 left=node(-1);left['children']=[node(i) for i in range(2000)];right=copy.deepcopy(left);right['children'].reverse()
 report={'baseline':args.baseline}
 outputs=[]
 for label,function in [('before',old.compare_trees),('after',compare_trees)]:
  times=[]
  for _ in range(3):
   a,b=copy.deepcopy(left),copy.deepcopy(right);start=time.perf_counter();rows=function(a,b);times.append((time.perf_counter()-start)*1000)
  outputs.append([(r.status,r.changed,r.left['material_id'] if r.left else None,r.right['material_id'] if r.right else None) for r in rows])
  report['algorithm_'+label+'_ms']=statistics.median(times)
 assert outputs[0]==outputs[1]
 with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as tmp:
  db=Database(str(Path(tmp)/'db'));svc=Services(db)
  root=svc.create_material(dict(base_code='ROOT',version='100',name='SKU',unit='pcs'));sid=svc.create_sku(root)
  children=[svc.create_material(dict(base_code=f'P{i:04}',version='100',name=f'测试物料{i}',unit='pcs')) for i in range(300)]
  svc.save_bom(root,[dict(material_id=mid,quantity=1,unit='pcs') for mid in children]);mirror=svc.copy_sku_bom(sid)
  main=MainWindow(svc);editor=main.open_bom_id(sid);editor.dirty=True;item=editor.root_item.child(0)
  try:
   for label,cls in [('before',old_ui.BomCompareDialog),('after',BomCompareDialog)]:
    dialog=cls(svc,main);dialog.left.setCurrentIndex(dialog.left.findData(sid));dialog.right.setCurrentIndex(dialog.right.findData(mirror));dialog.compare();times=[]
    for value in (2,3,4):
     data=dict(item.data(0,Qt.UserRole));data['quantity']=value;item.setData(0,Qt.UserRole,data)
     start=time.perf_counter();dialog.live_refresh();times.append((time.perf_counter()-start)*1000)
     assert dialog._rows[1].left['quantity']==value and dialog._rows[1].status=='modified'
    report['live_300_rows_'+label+'_ms']=statistics.median(times);dialog.close();dialog.deleteLater()
  finally:
   editor.dirty=False;editor.close();main.close()
   for widget in app.topLevelWidgets():widget.deleteLater()
   app.sendPostedEvents(None,QEvent.DeferredDelete);db.close()
 report['equivalent_results']=True
 Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
