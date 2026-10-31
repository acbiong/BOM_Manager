#!/usr/bin/env python3
"""Finite two-process UI regression using only disposable projects."""
import argparse,json,os,signal,subprocess,sys,tempfile,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PyQt5.QtWidgets import QApplication,QMessageBox
from PyQt5.QtCore import QTimer,Qt
from PyQt5.QtTest import QTest
from database.database import Database
from services.services import Services
from config.config_service import ConfigService
from config.project_registry import ProjectRegistry
from ui.main_window import MainWindow


def fixture(folder,name):
    folder=Path(folder);folder.mkdir(exist_ok=True)
    db=Database(str(folder/(name+'.db')));svc=Services(db,ConfigService(folder/(name+'-config')))
    svc.update_project(dict(project_code=name,project_name=name+'测试项目'))
    root,child=[svc.create_material(dict(base_code=code,version='100',name=code,unit='pcs')) for code in ('ROOT','PART')]
    sid=svc.create_sku(root);svc.save_bom(root,[dict(material_id=child,quantity=2,unit='pcs')])
    return db,svc,sid


def wait(app,predicate,timeout=6):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        QTest.qWait(25)
    raise AssertionError('等待跨进程窗口更新超时')


def worker(folder):
    folder=Path(folder);app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    db,svc,sid=fixture(folder,'source');main=MainWindow(svc);main.show();bom=main.open_bom_id(sid)
    state={'seq':0,'stop':False};started=time.monotonic()
    def messages():
        for w in app.topLevelWidgets():
            if not isinstance(w,QMessageBox) or not w.isVisible():continue
            discard=next((b for b in w.buttons() if '不保存' in b.text()),None)
            if discard:discard.click();continue
            for b in w.buttons():
                if w.buttonRole(b)==QMessageBox.AcceptRole:b.click();break
    timer=QTimer();timer.timeout.connect(messages);timer.start(30)
    main._live_project.flush();(folder/'ready').write_text(str(os.getpid()))
    try:
        while not state['stop'] and time.monotonic()-started<90:
            app.processEvents();QTest.qWait(20)
            path=folder/'command.json'
            if not path.exists():continue
            command=json.loads(path.read_text());seq=command['seq']
            if seq==state['seq']:continue
            state['seq']=seq
            try:
                action=command['action']
                if action=='edit':
                    bom.show_item_info(bom.root_item.child(0));field=bom.fields['quantity']
                    field.setFocus();QTest.keyClick(field,Qt.Key_A,Qt.ControlModifier);QTest.keyClicks(field,str(command['value']))
                elif action=='undo':bom.history.undo()
                elif action=='redo':bom.history.redo()
                elif action=='save':assert bom.save()
                elif action=='discard':assert bom.close();bom=main.open_bom_id(sid)
                elif action=='stop':state['stop']=True
                main._live_project.flush()
                result=dict(seq=seq,dirty=bom.dirty,saved=svc.bom(1)[0]['quantity'])
            except Exception:result=dict(seq=seq,error=traceback.format_exc())
            temporary=folder/'ack.tmp';temporary.write_text(json.dumps(result));os.replace(temporary,folder/'ack.json')
            if command['action']=='crash':os._exit(0)
    finally:
        timer.stop()
        for w in list(main._bom_windows.values()):w.dirty=False
        main.close();db.close()


def run(report_path):
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    report_path=Path(report_path).resolve();report_path.parent.mkdir(parents=True,exist_ok=True)
    report=dict(passed=False,platform=app.platformName(),checks=[],screenshots=[])
    try:
        with tempfile.TemporaryDirectory(prefix='bom-two-process-') as folder:
            folder=Path(folder);log=(folder/'worker.log').open('w',encoding='utf-8')
            proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker',str(folder)],stdout=log,stderr=log,env=dict(os.environ,PYTHONUTF8='1'))
            main=db=None;seq=0
            try:
                wait(app,lambda:(folder/'ready').exists(),12)
                db,svc,sid=fixture(folder,'local');main=MainWindow(svc);main.show();main.compare_boms();dialog=main._compare_dialog
                source=folder/'source.db';ProjectRegistry(svc.config_service).remember(source,dict(project_code='source',project_name='来源项目'))
                dialog.left.setCurrentIndex(dialog.left.findData(sid))
                def capture(w,n):
                    path=report_path.with_name(report_path.stem+f'_selector{n}.png');w.grab().save(str(path));report['screenshots'].append(str(path))
                from infrastructure.project_compare_smoke import select_project
                select_project(dialog,capture=capture)
                assert dialog._rows[1].right['quantity']==2
                original=source.read_bytes();report['checks'].append('native_project_then_sku_selection')
                def command(action,**values):
                    nonlocal seq
                    seq+=1;temporary=folder/'command.tmp';temporary.write_text(json.dumps(dict(seq=seq,action=action,**values)))
                    os.replace(temporary,folder/'command.json')
                    wait(app,lambda:(folder/'ack.json').exists() and json.loads((folder/'ack.json').read_text())['seq']==seq)
                    ack=json.loads((folder/'ack.json').read_text());assert 'error' not in ack,ack
                    return ack
                def quantity(value):wait(app,lambda:bool(dialog._rows) and dialog._rows[1].right['quantity']==value)
                ack=command('edit',value=8.5);quantity(8.5)
                assert ack['dirty'] and ack['saved']==2 and source.read_bytes()==original
                assert '未保存草稿' in dialog.summary.text();report['checks'].append('cross_process_unsaved_without_database_write')
                command('undo');quantity(2);command('redo');quantity(8.5);report['checks'].append('cross_process_undo_redo')
                screenshot=report_path.with_suffix('.png');dialog.grab().save(str(screenshot));report['screenshots'].append(str(screenshot))
                command('discard');quantity(2);assert source.read_bytes()==original;report['checks'].append('cross_process_discard')
                command('edit',value=7.25);quantity(7.25);ack=command('save');assert ack['saved']==7.25 and not ack['dirty']
                wait(app,lambda:'已保存BOM' in dialog.summary.text());report['checks'].append('cross_process_save')
                command('edit',value=9);quantity(9)
                # Abrupt process exit releases the owner lock; stale temporary
                # snapshots must immediately stop masking the saved database.
                command('crash');proc.wait(timeout=5);quantity(7.25)
                report['checks'].append('dead_process_cache_ignored')
                report['passed']=True
            finally:
                if main:main.close()
                if db:db.close()
                if proc.poll() is None:
                    # Windows venv launchers may have a separate Python child.
                    if (folder/'ready').exists():
                        try:os.kill(int((folder/'ready').read_text()),signal.SIGTERM)
                        except ProcessLookupError:pass
                    proc.wait(timeout=5)
                log.close();report['worker_log']=(folder/'worker.log').read_text(encoding='utf-8')
                from infrastructure.live_project_cache import cache_identity
                cache,_=cache_identity(folder/'source.db');cache.unlink(missing_ok=True)
    except Exception:report['error']=traceback.format_exc()
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report');parser.add_argument('--worker');args=parser.parse_args()
    if args.worker:worker(args.worker)
    else:raise SystemExit(run(args.report))
