#!/usr/bin/env python3
"""Audit duplicate definitions on a copy; optionally repair under project lock."""
import argparse,hashlib,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from services.history_identity import plan,apply,backup
from infrastructure.project_lock import ProjectLock


def untouched(conn):
    excluded={'material_histories','material_history_bindings','material_history_current','app_metadata'}
    result={}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        if name in excluded:continue
        rows=conn.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall()
        data=json.dumps(sorted([tuple(r) for r in rows],key=repr),ensure_ascii=False,default=str)
        result[name]=hashlib.sha256(data.encode()).hexdigest()
    return result


def verify(conn,result,before,bindings):
    assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert untouched(conn)==before,'BOM/material/alternate/log data changed'
    expected=sorted((sid,mid,result['mapping'][(mid,v)][1]) for sid,mid,v in bindings)
    assert sorted(tuple(r) for r in conn.execute('SELECT * FROM material_history_bindings'))==expected
    after=plan(conn)
    assert all(a==b for a,b in after['mapping'].items()),'Not idempotent'
    assert after['records']==result['records'],'Definition content changed'
    assert after['current']==result['current']


def run(path,write=False):
    lock=ProjectLock(path)
    if write:lock.require()
    conn=sqlite3.connect(str(path) if write else Path(path).resolve().as_uri()+'?mode=ro',uri=not write)
    conn.row_factory=sqlite3.Row
    try:
        saved=str(backup(conn,path)) if write else None
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        result=plan(conn);before=untouched(conn);bindings=[tuple(r) for r in conn.execute('SELECT * FROM material_history_bindings')]
        # Validate the exact transaction snapshot on an independent database first.
        trial=sqlite3.connect(':memory:');trial.row_factory=sqlite3.Row
        trial.executescript('\n'.join(conn.iterdump()))
        apply(trial,result);verify(trial,result,before,bindings);trial.close()
        if write:apply(conn,result);verify(conn,result,before,bindings);conn.commit()
        else:conn.rollback()
        changed=[dict(material_id=a[0],old=a[1],canonical=b[1]) for a,b in sorted(result['mapping'].items()) if a!=b]
        target=conn.execute("SELECT id FROM materials WHERE base_code||version='BC2-3000001100'").fetchone()
        return dict(applied=write,backup=saved,histories_before=len(result['mapping']),histories_after=len(result['records']),merged=len(changed),mapping=changed,table_hashes=before,bindings_checked=len(bindings),target_material_id=target[0] if target else None,target_remaining=[k[1] for k in result['records'] if target and k[0]==target[0]],integrity='ok',content_preserved=True)
    finally:
        conn.close();lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('database');parser.add_argument('--apply',action='store_true');parser.add_argument('--report',required=True);args=parser.parse_args()
    result=run(args.database,args.apply)
    Path(args.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('mapping','table_hashes')},ensure_ascii=False,indent=2))
