"""Root-only SKU namespaces backed by one public graph for all child materials."""
import json
from pathlib import Path
from datetime import datetime
from services.mirrors import table_name


def is_shared(conn):
    return bool(conn.execute("SELECT 1 FROM app_metadata WHERE key='shared_child_bom_v1'").fetchone())


def migration_candidates(db):
    """Read only. Empty captured definitions are candidates too."""
    conn=db.conn;sku_materials={r[0] for r in conn.execute('SELECT material_id FROM skus')}
    sources=[(0,'公共结构',conn.execute('SELECT DISTINCT parent_material_id FROM material_bom_items').fetchall())]
    for sku in conn.execute('SELECT s.*,m.base_code,m.version,m.name FROM skus s JOIN materials m ON m.id=s.material_id WHERE s.scope_id<>0'):
        mids=conn.execute('SELECT material_id FROM mirror_captured_materials WHERE sku_id=?',(sku['id'],)).fetchall()
        sources.append((sku['id'],f"{sku['base_code']}{sku['version']} {sku['name']} 镜像{sku['mirror_version']}",mids))
    parents={r[0] for _,_,rows in sources for r in rows}-sku_materials
    result={}
    for mid in sorted(parents):
        variants=[]
        for sid,label,mids in sources:
            if sid and mid not in {r[0] for r in mids}:continue
            table=table_name(sid,'material_bom_items') if sid else 'material_bom_items'
            alt=table_name(sid,'alternates') if sid else 'alternates'
            rows=[]
            for row in conn.execute(f'SELECT * FROM {table} WHERE parent_material_id=? ORDER BY sort_no,id',(mid,)):
                data={key:row[key] for key in ('child_material_id','quantity','unit','position','remark')}
                data['alternates']=[r[0] for r in conn.execute(f'SELECT material_id FROM {alt} WHERE bom_item_id=? ORDER BY sort_no,id',(row['id'],))];rows.append(data)
            variants.append(dict(scope=sid,label=label,rows=rows))
        result[mid]=variants
    return result


def conflicts(candidates):
    return {mid:variants for mid,variants in candidates.items() if len({json.dumps(v['rows'],sort_keys=True) for v in variants})>1}


def install_overlay(conn,sid):
    root=conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone()[0]
    table=table_name(sid,'material_bom_items');alt=table_name(sid,'alternates')
    conn.execute(f'ALTER TABLE {table} RENAME TO {table}_local')
    conn.execute(f'ALTER TABLE {alt} RENAME TO {alt}_local')
    conn.execute(f'DELETE FROM {alt}_local WHERE bom_item_id NOT IN (SELECT id FROM {table}_local WHERE parent_material_id=?)',(root,))
    conn.execute(f'DELETE FROM {table}_local WHERE parent_material_id<>?',(root,))
    offset=10**12+sid*10**8
    relation_ids=[r[0] for r in conn.execute(f'SELECT id FROM {table}_local ORDER BY id')]
    for number,old_id in enumerate(relation_ids,1):
        conn.execute(f'UPDATE {alt}_local SET bom_item_id=? WHERE bom_item_id=?',(-number,old_id))
        conn.execute(f'UPDATE {table}_local SET id=? WHERE id=?',(-number,old_id))
    for number in range(1,len(relation_ids)+1):
        conn.execute(f'UPDATE {alt}_local SET bom_item_id=? WHERE bom_item_id=?',(offset+number,-number))
        conn.execute(f'UPDATE {table}_local SET id=? WHERE id=?',(offset+number,-number))
    conn.execute(f'CREATE VIEW {table} AS SELECT * FROM {table}_local UNION ALL SELECT * FROM material_bom_items WHERE parent_material_id<>{root}')
    conn.execute(f'CREATE VIEW {alt} AS SELECT * FROM {alt}_local UNION ALL SELECT * FROM alternates WHERE bom_item_id IN (SELECT id FROM material_bom_items WHERE parent_material_id<>{root})')
    for view,public,condition in [(table,'material_bom_items',f'OLD.parent_material_id={root}'),(alt,'alternates',f'OLD.bom_item_id>={offset} AND OLD.bom_item_id<{offset+10**8}')]:
        cols=[r[1] for r in conn.execute(f'PRAGMA table_info({public})')]
        assignments=','.join(f'{c}=NEW.{c}' for c in cols if c!='id')
        conn.execute(f'CREATE TRIGGER {view}_delete INSTEAD OF DELETE ON {view} BEGIN DELETE FROM {view}_local WHERE id=OLD.id AND {condition}; DELETE FROM {public} WHERE id=OLD.id AND NOT ({condition}); END')
        conn.execute(f'CREATE TRIGGER {view}_update INSTEAD OF UPDATE ON {view} BEGIN UPDATE {view}_local SET {assignments} WHERE id=OLD.id AND {condition}; UPDATE {public} SET {assignments} WHERE id=OLD.id AND NOT ({condition}); END')
    # INSERTs are routed directly by MirrorConnection (preserving lastrowid/upsert).


def migrate(db,choices=None):
    conn=db.conn
    if is_shared(conn):return
    candidates=migration_candidates(db);choices=choices or {};ambiguous=conflicts(candidates)
    if set(ambiguous)-set(choices):raise ValueError('请逐项选择非SKU子BOM的公共结构')
    selected={mid:next(v for v in variants if v['scope']==choices.get(mid,variants[0]['scope'])) for mid,variants in candidates.items()}
    # Check all effective graphs before changing any rows, including every SKU root.
    graph={}
    for row in conn.execute('SELECT parent_material_id,child_material_id FROM material_bom_items'):graph.setdefault(row[0],set()).add(row[1])
    for mid,v in selected.items():graph[mid]={r['child_material_id'] for r in v['rows']}
    def validate(g):
        done=set();active=set()
        def visit(mid):
            if mid in active:raise ValueError('所选公共结构会形成循环引用，请重新选择')
            if mid in done:return
            active.add(mid)
            for child in g.get(mid,()):visit(child)
            active.remove(mid);done.add(mid)
        for mid in g:visit(mid)
    validate(graph)
    for sku in conn.execute('SELECT id,material_id FROM skus WHERE scope_id<>0'):
        g=dict(graph);g[sku['material_id']]={r[0] for r in conn.execute(f'SELECT child_material_id FROM {table_name(sku["id"],"material_bom_items")} WHERE parent_material_id=?',(sku['material_id'],))};validate(g)
    if db.path!=':memory:' and conn.execute('SELECT 1 FROM skus WHERE scope_id<>0').fetchone():
        import sqlite3
        backup=Path(str(db.path)+'.pre-shared-bom-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
        target=sqlite3.connect(str(backup))
        try:conn.backup(target)
        finally:target.close()
    with db.transaction():
        for mid,v in selected.items():
            conn.execute('DELETE FROM alternates WHERE bom_item_id IN (SELECT id FROM material_bom_items WHERE parent_material_id=?)',(mid,))
            conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=?',(mid,))
            for order,row in enumerate(v['rows']):
                rid=conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit,position,remark,sort_no) VALUES(?,?,?,?,?,?,?)',(mid,row['child_material_id'],row['quantity'],row['unit'],row['position'],row['remark'],order)).lastrowid
                for n,alt in enumerate(row['alternates']):conn.execute('INSERT INTO alternates(bom_item_id,material_id,sort_no) VALUES(?,?,?)',(rid,alt,n))
        conn.execute('CREATE TABLE IF NOT EXISTS shared_bom_migration_archive(material_id INTEGER,variants TEXT,selected_scope INTEGER)')
        for mid,variants in candidates.items():conn.execute('INSERT INTO shared_bom_migration_archive VALUES(?,?,?)',(mid,json.dumps(variants,ensure_ascii=False),selected[mid]['scope']))
        for sku in conn.execute('SELECT id FROM skus WHERE scope_id<>0').fetchall():install_overlay(conn,sku[0])
        conn.execute("INSERT INTO app_metadata VALUES('shared_child_bom_v1','1')")
