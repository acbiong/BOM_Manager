"""Whole-tree SKU snapshots and immutable base-code definitions per material revision."""
import json,re,sqlite3
from datetime import datetime
from pathlib import Path
from services.mirrors import TABLES,table_name

MARKER='whole_tree_snapshots_v2'

def enabled(db):
    conn=getattr(db.conn,'raw',db.conn)
    return bool(conn.execute('SELECT 1 FROM app_metadata WHERE key=?',(MARKER,)).fetchone())

def signature(codes):return json.dumps(sorted(set(codes)),ensure_ascii=False)

def create_tables(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS bom_revision_definitions(material_id INTEGER PRIMARY KEY,child_codes TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS bom_revision_legacy_conflicts(sku_id INTEGER,material_id INTEGER,child_codes TEXT,PRIMARY KEY(sku_id,material_id))')

def scope_definitions(conn,sid,root):
    table=table_name(sid,'material_bom_items') if sid else 'material_bom_items'
    groups={};graph={}
    for row in conn.execute(f'SELECT b.parent_material_id,b.child_material_id,m.base_code FROM {table} b JOIN materials m ON m.id=b.child_material_id'):
        groups.setdefault(row[0],set()).add(row[2]);graph.setdefault(row[0],set()).add(row[1])
    pending=[root];seen=set()
    while pending:
        mid=pending.pop()
        if mid in seen:continue
        seen.add(mid);pending.extend(graph.get(mid,()))
    return {mid:signature(groups.get(mid,())) for mid in seen}

def migrate(db):
    if enabled(db):return
    conn=db.conn
    skus=conn.execute('SELECT * FROM skus ORDER BY id').fetchall()
    if skus and db.path!=':memory:':
        backup=Path(str(db.path)+'.pre-whole-tree-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
        destination=sqlite3.connect(str(backup))
        try:conn.backup(destination)
        finally:destination.close()
    # Materialize each existing effective graph before removing shared views.
    datasets={}
    for sku in skus:
        datasets[sku['id']]={}
        for table in TABLES:
            source=table_name(sku['id'],table) if sku['scope_id'] else table
            datasets[sku['id']][table]=[dict(r) for r in conn.execute(f'SELECT * FROM {source}')]
    with db.transaction():
        create_tables(conn)
        for sku in skus:
            sid=sku['id'];root=sku['material_id'];data=datasets[sid]
            edges={}
            for row in data['material_bom_items']:edges.setdefault(row['parent_material_id'],[]).append(row)
            pending=[root];seen=set();relations=set()
            while pending:
                mid=pending.pop()
                if mid in seen:continue
                seen.add(mid)
                for row in edges.get(mid,[]):relations.add(row['id']);pending.append(row['child_material_id'])
            for table in TABLES:
                name=table_name(sid,table)
                kind=conn.execute('SELECT type FROM sqlite_master WHERE name=?',(name,)).fetchone()
                if kind:conn.execute(f'DROP {kind[0].upper()} {name}')
                conn.execute(f'DROP TABLE IF EXISTS {name}_local')
                sql=conn.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone()[0]
                sql=re.sub(r'(?i)CREATE TABLE(?: IF NOT EXISTS)?\s+["`]?'+table+r'["`]?',f'CREATE TABLE {name}',sql,count=1);conn.execute(sql)
                rows=data[table]
                if table=='material_bom_items':rows=[r for r in rows if r['id'] in relations]
                elif table=='alternates':rows=[r for r in rows if r['bom_item_id'] in relations]
                elif table=='bom_items':rows=[]
                if rows:
                    columns=[k for k in rows[0] if table!='alternates' or k!='id']
                    conn.executemany(f'INSERT INTO {name} ('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[[r[k] for k in columns] for r in rows])
            conn.execute('UPDATE skus SET scope_id=? WHERE id=?',(sid,sid))
            conn.execute('DELETE FROM mirror_captured_materials WHERE sku_id=?',(sid,))
            conn.executemany('INSERT INTO mirror_captured_materials VALUES(?,?)',[(sid,mid) for mid in seen])
            conn.execute(f'CREATE INDEX mirror_{sid}_parent ON {table_name(sid,"material_bom_items")}(parent_material_id)')
            conn.execute(f'CREATE INDEX mirror_{sid}_child ON {table_name(sid,"material_bom_items")}(child_material_id)')
            for mid,codes in scope_definitions(conn,sid,root).items():
                if conn.execute('SELECT 1 FROM skus WHERE material_id=?',(mid,)).fetchone():continue
                old=conn.execute('SELECT child_codes FROM bom_revision_definitions WHERE material_id=?',(mid,)).fetchone()
                if old and old[0]!=codes:conn.execute('INSERT OR REPLACE INTO bom_revision_legacy_conflicts VALUES(?,?,?)',(sid,mid,codes))
                else:conn.execute('INSERT OR IGNORE INTO bom_revision_definitions VALUES(?,?)',(mid,codes))
        conn.execute('INSERT INTO app_metadata VALUES(?,?)',(MARKER,'1'))
        conn.execute("DELETE FROM app_metadata WHERE key='shared_child_bom_v1'")
        from services.services import Services
        primary=Services(db)
        for sku in skus:primary.for_sku(sku['id']).refresh_usage()

class ParentRevisionRequired(ValueError):
    def __init__(self,conflicts):
        self.conflicts=conflicts
        super().__init__('以下父物料的直接子物料基础编码发生变化，需要升版：'+ '、'.join(v['label'] for v in conflicts))

def draft_definitions(service,root,items):
    groups={root:set()}
    retained={root}|{r['material_id'] for r in items}
    for row in service.bom(root):
        if row['parent_material_id'] in retained:groups.setdefault(row['parent_material_id'],set())
    by_id={r.get('id'):r for r in items if r.get('id') is not None}
    for row in items:
        parent=row.get('parent_material_id')
        if parent is None:
            ancestor=by_id.get(row.get('parent_item_id'))
            if ancestor is None and isinstance(row.get('parent_item_id'),int) and 1<=row['parent_item_id']<=len(items):ancestor=items[row['parent_item_id']-1]
            parent=ancestor['material_id'] if ancestor else root
        groups.setdefault(parent,set()).add(service.material_snapshot(row['material_id'])['base_code'])
        if row.get('replace_children'):groups.setdefault(row['material_id'],set())
    return {mid:signature(codes) for mid,codes in groups.items()}

def revision_conflicts(service,root,items):
    if not enabled(service.db):return []
    conflicts=[]
    for mid,codes in draft_definitions(service,root,items).items():
        if service.db.conn.execute('SELECT 1 FROM skus WHERE material_id=?',(mid,)).fetchone():continue
        known=service.db.conn.execute('SELECT child_codes FROM bom_revision_definitions WHERE material_id=?',(mid,)).fetchone()
        if known and known[0]!=codes:
            material=service.material_snapshot(mid)
            conflicts.append(dict(material_id=mid,label=material['base_code']+material['version']+' '+material['name'],before=json.loads(known[0]),after=json.loads(codes)))
    return conflicts

def record_definitions(service,root):
    conn=getattr(service.db.conn,'raw',service.db.conn)
    for mid,codes in scope_definitions(conn,getattr(service,'scope_id',0),root).items():
        if conn.execute('SELECT 1 FROM skus WHERE material_id=?',(mid,)).fetchone():continue
        conn.execute('INSERT OR IGNORE INTO bom_revision_definitions VALUES(?,?)',(mid,codes))
        if getattr(service,'scope_id',0):conn.execute('DELETE FROM bom_revision_legacy_conflicts WHERE sku_id=? AND material_id=?',(service.scope_id,mid))

def save_with_revisions(service,root,items,versions,progress=None):
    """Create/reuse explicitly chosen parent revisions and save atomically."""
    violations=revision_conflicts(service,root,items)
    if {v['material_id'] for v in violations}!=set(versions):raise ValueError('父项升版清单已变化，请重新检查')
    original=getattr(service.db,'original',service.db)
    mapping={}
    with original.transaction():
        for problem in violations:
            mid=problem['material_id'];old=service.material_snapshot(mid);version=str(versions[mid]).strip()
            if not version or version==old['version']:raise ValueError('请选择或输入不同的新版本号：'+problem['label'])
            if old['version'].isdigit() and version.isdigit() and int(version)<=int(old['version']):raise ValueError('父项新版本号必须大于原版本号：'+problem['label'])
            existing=service.db.conn.execute('SELECT id FROM materials WHERE base_code=? AND version=?',(old['base_code'],version)).fetchone()
            if existing:new_id=existing[0]
            else:
                fields=['base_code','version','name','description','unit','grade','manufacturer','mpn','mp_flag']
                values=[version if f=='version' else old[f] for f in fields]
                new_id=service.db.conn.execute('INSERT INTO materials('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',values).lastrowid
                getattr(service,'primary',service).log('material',new_id,'create','')
            known=service.db.conn.execute('SELECT child_codes FROM bom_revision_definitions WHERE material_id=?',(new_id,)).fetchone()
            if known and known[0]!=signature(problem['after']):raise ValueError('所选父物料版本已有不同的子料基础编码定义：'+old['base_code']+version)
            mapping[mid]=new_id
        rows=[]
        for original_row in items:
            row=dict(original_row)
            if 'alternate_material_ids' not in row and row.get('id') is not None:
                row['alternate_material_ids']=[a['material_id'] for a in service.alternates(row['id'])]
            row['material_id']=mapping.get(row['material_id'],row['material_id'])
            if row.get('parent_material_id') is not None:row['parent_material_id']=mapping.get(row['parent_material_id'],row['parent_material_id'])
            rows.append(row)
        service.save_bom(mapping.get(root,root),rows,progress=progress)
    service.publish({'type':'material_changed','ids':list(mapping.values())})
    return mapping


def latest_usage(service):
    primary=getattr(service,'primary',service);skus=list(primary.skus());latest={}
    for sku in skus:
        key=(sku['base_code'],sku['version'])
        if key not in latest or sku['mirror_version']>latest[key]['mirror_version']:latest[key]=sku
    used={sku['material_id'] for sku in latest.values()}
    for sku in latest.values():
        used.update(row[0] for row in primary.db.conn.execute('SELECT material_id FROM mirror_material_usage WHERE sku_id=?',(sku['id'],)))
    return used

def material_sources(service,mid):
    primary=getattr(service,'primary',service);latest={}
    for sku in primary.skus():
        key=(sku['base_code'],sku['version'])
        if key not in latest or sku['mirror_version']>latest[key]['mirror_version']:latest[key]=sku
    owners={row[0] for row in primary.db.conn.execute('SELECT DISTINCT sku_id FROM mirror_material_usage WHERE parent_id=? AND role="main"',(mid,))}
    result=[sku for sku in latest.values() if sku['id'] in owners]
    return sorted(result,key=lambda r:(r['updated_at'] or '',r['id']),reverse=True)

def template_service(primary,mid):
    sources=material_sources(primary,mid)
    return primary.for_sku(sources[0]['id']) if sources else primary
