#!/usr/bin/env python3
"""Compare project opening and layout on isolated synthetic data, never user DBs."""
import argparse,io,json,os,statistics,subprocess,sys,tarfile,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def measure(source):
    sys.path.insert(0,str(Path(source)/'src'))
    from PyQt5.QtWidgets import QApplication,QTableWidgetItem
    from ui.main_window import MainWindow
    from ui.frozen_table import FrozenMaterialTable
    from ui.table_layout import fit_columns
    from ui.operation_progress import OperationProgress
    from infrastructure.operation_progress import _current
    from database.database import Database
    from services.services import Services
    from services.snapshot_bom import migrate
    from services.current_catalog import initialize
    from services.material_history import initialize as histories
    from config.config_service import ConfigService
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);results={}
    def settle():
        for _ in range(6):app.processEvents()
    with tempfile.TemporaryDirectory(prefix='bom-refresh-benchmark-') as folder:
        folder=Path(folder);target=folder/'target.db';db=Database(str(target));svc=Services(db)
        with db.transaction():
            children=[svc.create_material(dict(base_code=f'PART-{i:04}',version='100',name='测试物料'+str(i),unit='pcs',description='规格描述'*5)) for i in range(250)]
            for i in range(60):
                root=svc.create_material(dict(base_code=f'SKU-{i:03}',version='100',name='测试SKU'+str(i),unit='pcs'))
                svc.create_sku(root);svc.save_bom(root,[dict(material_id=mid,quantity=1,unit='pcs') for mid in children[i:i+8]])
        migrate(db);initialize(db);histories(db);db.close()
        main=MainWindow(Services(None,ConfigService(folder)));main.show();settle()
        try:
            start=time.perf_counter();assert main.switch_project(target);settle();results['open_project_ms']=(time.perf_counter()-start)*1000
            start=time.perf_counter();main.show_materials();settle();results['open_material_library_ms']=(time.perf_counter()-start)*1000
            start=time.perf_counter();main.refresh();main._materials.refresh();settle();results['repeat_refresh_ms']=(time.perf_counter()-start)*1000
        finally:
            main.close();main.svc.db.close()
    table=FrozenMaterialTable();table.setColumnCount(18);table.setRowCount(400)
    for row in range(400):
        for col in range(18):table.setItem(row,col,QTableWidgetItem('物料描述'+str(row)+'\n'+str(col)))
    table.show();app.processEvents();counts={'checkpoints':0,'row_calls':0}
    class Controller:
        def update(self,*args):counts['checkpoints']+=1
    resize=table.resizeRowToContents
    def size(row):counts['row_calls']+=1;resize(row)
    table.resizeRowToContents=size;token=_current.set(Controller())
    try:
        start=time.perf_counter();fit_columns(table);results['layout_ms']=(time.perf_counter()-start)*1000
        start=time.perf_counter();fit_columns(table);results['unchanged_layout_ms']=(time.perf_counter()-start)*1000
        results.update(counts)
    finally:_current.reset(token);table.close()
    from PyQt5 import sip
    for w in app.topLevelWidgets():
        if w.parent() is None:w.deleteLater()
    app.processEvents();sip.delete(app)
    return results


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source');parser.add_argument('--baseline',default='c44aa3b');parser.add_argument('--report',required=True);args=parser.parse_args()
    if args.source:
        Path(args.report).write_text(json.dumps(measure(args.source)),encoding='utf-8');return
    report={'baseline':args.baseline,'fixture':{'skus':60,'parts':250,'layout_rows':400,'layout_columns':18},'samples':{}}
    with tempfile.TemporaryDirectory(prefix='refresh-baseline-',dir=ROOT/'.tmp') as folder:
        archive=subprocess.check_output(['git','archive',args.baseline,'src'],cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(folder,filter='data')
        for label,source in [('before',folder),('after',str(ROOT))]:
            report['samples'][label]=[]
            for n in range(3):
                output=Path(folder)/(label+str(n)+'.json')
                subprocess.run([sys.executable,__file__,'--source',source,'--report',str(output)],check=True,timeout=120)
                report['samples'][label].append(json.loads(output.read_text()))
    report['medians']={label:{key:statistics.median(sample[key] for sample in samples) for key in samples[0]} for label,samples in report['samples'].items()}
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report['medians'],indent=2))


if __name__=='__main__':main()
