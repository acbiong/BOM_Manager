"""Deduplicate immutable definitions by content, never by owning SKU/context.

Partition refinement also handles alternate reference cycles without recursion.
Actual incoming alternate relationships remain in BOM relationship tables.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from services.material_history import FIELDS, encode

MARKER='material_history_content_identity_v2'


def plan(conn):
    rows={(r['material_id'],r['history_version']):dict(r) for r in conn.execute('SELECT * FROM material_histories')}
    attrs={k:encode({f:json.loads(r['attributes']).get(f,'') for f in FIELDS}) for k,r in rows.items()}
    children={k:json.loads(r['children']) for k,r in rows.items()}
    def rewritten(edges,mapping):
        result=json.loads(encode(edges))
        for edge in result:
            for ref in [edge,*edge.get('alternates',[])]:
                key=(ref['material_id'],ref['history_version'])
                if key not in mapping:raise ValueError('物料历史引用缺失：'+str(key))
                ref['history_version']=mapping[key][1]
        return result
    minimum={};maximum={}
    for mid,v in rows:
        minimum[mid]=min(minimum.get(mid,v),v)
        maximum[mid]=max(maximum.get(mid,v),v)
    mapping={k:(k[0],minimum[k[0]]) for k in rows}
    for _ in range(len(rows)+1):
        groups={};updated={}
        for k in sorted(rows):
            signature=(k[0],attrs[k],encode(rewritten(children[k],mapping)))
            updated[k]=groups.setdefault(signature,k)
        if updated==mapping:break
        mapping=updated
    else:raise ValueError('历史版本合并未收敛')
    for r in conn.execute('SELECT material_id,history_version FROM material_history_bindings'):
        if tuple(r) not in mapping:raise ValueError('SKU物料历史引用缺失：'+str(tuple(r)))
    has_current=conn.execute("SELECT 1 FROM sqlite_master WHERE name='material_history_current'").fetchone()
    current=dict(conn.execute('SELECT material_id,history_version FROM material_history_current')) if has_current else {}
    for mid,version in maximum.items():current.setdefault(mid,version)
    current={mid:mapping[(mid,v)][1] for mid,v in current.items()}
    return dict(mapping=mapping,records={k:(attrs[k],encode(rewritten(children[k],mapping))) for k in set(mapping.values())},current=current)


def apply(conn, result):
    conn.execute('CREATE TABLE IF NOT EXISTS material_history_current(material_id INTEGER PRIMARY KEY,history_version INTEGER NOT NULL)')
    for (mid,old),(_,new) in result['mapping'].items():
        if old!=new:
            conn.execute('UPDATE material_history_bindings SET history_version=? WHERE material_id=? AND history_version=?',(new,mid,old))
            conn.execute('DELETE FROM material_histories WHERE material_id=? AND history_version=?',(mid,old))
    for (mid,version),(attrs,children) in result['records'].items():
        conn.execute('UPDATE material_histories SET attributes=?,children=? WHERE material_id=? AND history_version=?',(attrs,children,mid,version))
    conn.executemany('INSERT OR REPLACE INTO material_history_current VALUES(?,?)',result['current'].items())
    conn.execute('INSERT OR REPLACE INTO app_metadata VALUES(?,?)',(MARKER,'1'))


def backup(conn,path):
    target=Path(str(path)+'.pre-history-dedup-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
    dest=sqlite3.connect(str(target))
    try:conn.backup(dest)
    finally:dest.close()
    return target


def upgrade(db):
    if db.conn.execute('SELECT 1 FROM app_metadata WHERE key=?',(MARKER,)).fetchone():return
    if str(db.path)!=':memory:':backup(db.conn,db.path)
    with db.transaction():apply(db.conn,plan(db.conn))
