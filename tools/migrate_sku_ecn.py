"""Preview legacy SKU-note migration; --apply backs up and migrates exclusively."""
import argparse,hashlib,json,sqlite3,sys,tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from services.sku_ecn import migrate,parse_legacy,values,FIELDS
from infrastructure.project_lock import ProjectLock


def table_hashes(conn):
    return {name:hashlib.sha256(repr([tuple(r) for r in conn.execute('SELECT * FROM "'+name.replace('"','""')+'" ORDER BY rowid')]).encode('utf-8')).hexdigest()
            for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name<>'skus' ORDER BY name")}


def run(source,report,apply=False):
    source=Path(source).resolve();report=Path(report).resolve()
    if source==report:raise ValueError('报告路径不能覆盖数据库')
    if not source.is_file():raise ValueError('数据库不存在')
    lock=ProjectLock(source);working=None
    with tempfile.TemporaryDirectory(prefix='bom-ecn-') as temp:
        try:
            if apply:lock.require()
            original=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
            try:
                columns={r[1] for r in original.execute('PRAGMA table_info(skus)')}
                if not {'change_description','mirror_version','locked'}<=columns:raise ValueError('请先用软件完成旧版数据库结构升级')
                already=set(FIELDS)<=columns
                if apply and not already:
                    backup=Path(str(source)+'.pre-ecn-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
                    copy=sqlite3.connect(backup)
                    try:original.backup(copy)
                    finally:copy.close()
                else:backup=None
                target=source if apply else Path(temp)/'preview.db'
                if not apply:
                    copy=sqlite3.connect(target)
                    try:original.backup(copy)
                    finally:copy.close()
            finally:original.close()
            working=sqlite3.connect(target);working.row_factory=sqlite3.Row;working.execute('BEGIN IMMEDIATE')
            before=[dict(r) for r in working.execute('SELECT * FROM skus ORDER BY id')];other=table_hashes(working)
            migrate(working)
            after=[dict(r) for r in working.execute('SELECT * FROM skus ORDER BY id')]
            assert len(before)==len(after)
            moved=0
            for old,new in zip(before,after):
                for field in columns-{'change_description',*FIELDS}:assert old[field]==new[field],(old['id'],field)
                if not already and (old['change_description'] or '').strip():
                    assert values(new)==parse_legacy(old['change_description']) and new['change_description']=='';moved+=1
                elif already:assert old==new
                else:assert values(new)==('/' if old['mirror_version']==100 else '','','')
            assert table_hashes(working)==other,'其他业务表发生变化'
            assert working.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not working.execute('PRAGMA foreign_key_check').fetchall()
            working.commit()
            result=dict(passed=True,applied=apply,source=str(source),backup=str(backup) if backup else None,already_migrated=already,sku_histories=len(before),notes_migrated=moved,other_tables_unchanged=True,integrity_check='ok')
            report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return result
        finally:
            if working is not None:working.close()
            lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('database');parser.add_argument('--report',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.database,args.report,args.apply),ensure_ascii=False))
