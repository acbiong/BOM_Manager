"""Public material BOM catalog shared by latest SKU mirrors; history stays private."""
from datetime import datetime
from pathlib import Path
import sqlite3
from services.snapshot_bom import enabled as snapshots_enabled

MARKER='latest_mirror_catalog_v1'

def enabled(service):
    return bool(service.db.conn.execute('SELECT 1 FROM app_metadata WHERE key=?',(MARKER,)).fetchone())

def latest_skus(primary):
    latest={}
    for sku in primary.skus():
        key=sku['material_id']
        if key not in latest or sku['mirror_version']>latest[key]['mirror_version']:latest[key]=sku
    return list(latest.values())

def groups(service):
    result={};alternates={}
    for alt in service.db.conn.execute('SELECT bom_item_id,material_id FROM alternates ORDER BY sort_no,id'):
        alternates.setdefault(alt[0],[]).append(alt[1])
    for row in service.db.conn.execute('SELECT * FROM material_bom_items ORDER BY sort_no,id'):
        data=dict(row);data['material_id']=data['child_material_id']
        data['alternate_material_ids']=alternates.get(data['id'],[])
        result.setdefault(data['parent_material_id'],[]).append(data)
    return result

def reachable(graph,root):
    seen=set();pending=[root]
    while pending:
        mid=pending.pop()
        if mid in seen:continue
        seen.add(mid);pending.extend(r['material_id'] for r in graph.get(mid,[]))
    return seen

def rows_for(graph,root):
    rows=[]
    def walk(mid,path):
        if mid in path:raise ValueError('公共子BOM同步将导致循环引用，请检查物料结构')
        for source in graph.get(mid,[]):
            row={k:v for k,v in source.items() if k not in ('id','parent_item_id','node_id','parent_node_id')}
            row.update(parent_material_id=mid,replace_children=True)
            rows.append(row);walk(row['material_id'],path|{mid})
    walk(root,set());return rows

def write_public(primary,updates):
    conn=primary.db.conn
    for mid,rows in updates.items():
        conn.execute('DELETE FROM alternates WHERE bom_item_id IN (SELECT id FROM material_bom_items WHERE parent_material_id=?)',(mid,))
        conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=?',(mid,))
        for order,row in enumerate(rows):
            rid=conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit,position,remark,sort_no) VALUES(?,?,?,?,?,?,?)',(mid,row['material_id'],row['quantity'],row['unit'],row.get('position',''),row.get('remark',''),order)).lastrowid
            conn.executemany('INSERT INTO alternates(bom_item_id,material_id,sort_no) VALUES(?,?,?)',[(rid,aid,n) for n,aid in enumerate(row['alternate_material_ids'])])
    conn.execute('UPDATE materials SET has_bom=EXISTS(SELECT 1 FROM material_bom_items WHERE parent_material_id=materials.id)')

def apply_to_latest(primary,updates,exclude=None):
    for sku in latest_skus(primary):
        if sku['id']==exclude:continue
        target=primary.for_sku(sku['id']);graph=groups(target)
        used=reachable(graph,sku['material_id'])
        if not used.intersection(updates):continue
        graph.update(updates)
        target._catalog_sync=True
        target.save_bom(sku['material_id'],rows_for(graph,sku['material_id']))

def synchronize(service,changed_parents):
    if not enabled(service) or getattr(service,'_catalog_sync',False):return
    primary=getattr(service,'primary',service)
    current=next((s for s in latest_skus(primary) if s['id']==getattr(service,'sku_id',None)),None)
    if current is None and getattr(service,'scope_id',0):return
    graph=groups(service)
    # Deleted/unreachable branches must not overwrite definitions still used elsewhere.
    used=reachable(graph,current['material_id']) if current else set(graph)|set(changed_parents)
    updates={mid:graph.get(mid,[]) for mid in set(changed_parents)&used}
    if not updates:return
    pending=[r['material_id'] for rows in updates.values() for r in rows]
    while pending:
        mid=pending.pop()
        if mid in updates:continue
        updates[mid]=graph.get(mid,[])
        pending.extend(r['material_id'] for r in updates[mid])
    write_public(primary,updates)
    apply_to_latest(primary,updates,getattr(service,'sku_id',None))
    if current:prune_public(primary)

def initialize(db):
    from services.services import Services
    primary=Services(db)
    if enabled(primary):
        ensure_indexes(db)
        return
    if not snapshots_enabled(db):raise ValueError('请先迁移整树镜像')
    if db.path!=':memory:':
        path=Path(str(db.path)+'.pre-latest-catalog-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
        backup=sqlite3.connect(str(path))
        try:db.conn.backup(backup)
        finally:backup.close()
    # Last saved latest mirror wins per parent, including explicitly empty leaves.
    updates={}
    for sku in sorted(latest_skus(primary),key=lambda s:(s['updated_at'] or '',s['id'])):
        graph=groups(primary.for_sku(sku['id']))
        for mid in reachable(graph,sku['material_id']):updates[mid]=graph.get(mid,[])
    with db.transaction():
        db.conn.execute('INSERT INTO app_metadata VALUES(?,?)',(MARKER,'1'))
        write_public(primary,updates)
        apply_to_latest(primary,updates)
        from services.snapshot_bom import signature
        for mid,rows in updates.items():
            if db.conn.execute('SELECT 1 FROM skus WHERE material_id=?',(mid,)).fetchone():continue
            codes=[primary.material_snapshot(r['material_id'])['base_code'] for r in rows]
            db.conn.execute('INSERT INTO bom_revision_definitions VALUES(?,?) ON CONFLICT(material_id) DO UPDATE SET child_codes=excluded.child_codes',(mid,signature(codes)))
        db.conn.execute('DELETE FROM bom_items')
    ensure_indexes(db)
    db.conn.execute('PRAGMA optimize')

def material_structure_sources(service):
    """Newest containing mirror per SKU, then most recently saved across SKUs.

    Read reachable relationships, not the public cache or a possibly stale usage index.
    An empty definition in a newer containing mirror is authoritative too.
    """
    primary=getattr(service,'primary',service);candidates={};graphs={}
    skus=sorted(primary.skus(),key=lambda row:row['mirror_version'],reverse=True)
    for sku in skus:
        source=primary.for_sku(sku['id']);scope=sku['scope_id']
        if scope not in graphs:
            graph={}
            for row in source.db.conn.execute('SELECT parent_material_id,child_material_id FROM material_bom_items'):
                graph.setdefault(row[0],set()).add(row[1])
            graphs[scope]=graph
        graph=graphs[scope];pending=[sku['material_id']];seen=set()
        while pending:
            mid=pending.pop()
            if mid in seen:continue
            seen.add(mid);pending.extend(graph.get(mid,()))
            owners=candidates.setdefault(mid,{})
            if sku['material_id'] not in owners:
                owners[sku['material_id']]=dict(sku=dict(sku),children=graph.get(mid,set()))
    return {mid:sorted(owners.values(),key=lambda value:(value['sku']['updated_at'] or '',value['sku']['id']),reverse=True)
            for mid,owners in candidates.items()}

def material_structure_source(service,mid):
    primary=getattr(service,'primary',service)
    sources=material_structure_sources(primary).get(mid,[])
    return primary.for_sku(sources[0]['sku']['id']) if sources else primary

def catalog_edges(service):
    primary=getattr(service,'primary',service);sources=material_structure_sources(primary)
    edges=[(mid,child) for mid,owners in sources.items() for child in owners[0]['children']]
    edges.extend(row for row in primary.bom_graph_edges() if row[0] not in sources)
    return edges

def selection_tree(service,root):
    """Read public metadata and descendants without mutating editor snapshots."""
    source=material_structure_source(service,root)
    from services.services import Services
    nodes={};roots=[]
    for row in Services.bom(source,root):
        node={'data':dict(row),'children':[]}
        node['data']['_db_alternates']=[a['material_id'] for a in source.alternates(row['id'])]
        nodes[row['node_id']]=node;parent=nodes.get(row['parent_node_id'])
        (parent['children'] if parent else roots).append(node)
    return roots

def prune_snapshot(service):
    if not getattr(service,'scope_id',0):return
    conn=service.db.conn
    row=conn.execute('SELECT material_id FROM skus WHERE id=?',(service.sku_id,)).fetchone()
    if row is None:return
    used=reachable(groups(service),row[0])
    parents={r[0] for r in conn.execute('SELECT DISTINCT parent_material_id FROM material_bom_items')}
    for mid in parents-used:
        conn.execute('DELETE FROM alternates WHERE bom_item_id IN (SELECT id FROM material_bom_items WHERE parent_material_id=?)',(mid,))
        conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=?',(mid,))
    conn.execute('DELETE FROM alternates WHERE NOT EXISTS(SELECT 1 FROM material_bom_items b WHERE b.id=alternates.bom_item_id)')
    conn.execute('DELETE FROM bom_items')
    conn.execute('DELETE FROM mirror_captured_materials WHERE sku_id=?',(service.sku_id,))
    conn.executemany('INSERT INTO mirror_captured_materials VALUES(?,?)',[(service.sku_id,mid) for mid in used])
    conn.execute('DELETE FROM bom_revision_legacy_conflicts WHERE sku_id=? AND material_id NOT IN (SELECT material_id FROM mirror_captured_materials WHERE sku_id=?)',(service.sku_id,service.sku_id))

def prune_public(primary):
    used=set()
    for sku in latest_skus(primary):
        used.update(reachable(groups(primary.for_sku(sku['id'])),sku['material_id']))
    conn=primary.db.conn
    for row in conn.execute('SELECT DISTINCT parent_material_id FROM material_bom_items').fetchall():
        if row[0] not in used:
            conn.execute('DELETE FROM alternates WHERE bom_item_id IN (SELECT id FROM material_bom_items WHERE parent_material_id=?)',(row[0],))
            conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=?',(row[0],))
    conn.execute('DELETE FROM alternates WHERE NOT EXISTS(SELECT 1 FROM material_bom_items b WHERE b.id=alternates.bom_item_id)')
    conn.execute('UPDATE materials SET has_bom=EXISTS(SELECT 1 FROM material_bom_items WHERE parent_material_id=materials.id)')

def refresh_latest_from_catalog(primary):
    if not enabled(primary):return
    graph=groups(primary)
    sku_materials={r[0] for r in primary.db.conn.execute('SELECT material_id FROM skus')}
    used=set()
    for sku in latest_skus(primary):used.update(reachable(groups(primary.for_sku(sku['id'])),sku['material_id']))
    apply_to_latest(primary,{mid:graph.get(mid,[]) for mid in used-sku_materials})

def ensure_indexes(db):
    from services.mirrors import table_name
    with db.transaction():
        db.conn.execute('CREATE INDEX IF NOT EXISTS mirror_usage_parent ON mirror_material_usage(parent_id,role,sku_id)')
        db.conn.execute('CREATE INDEX IF NOT EXISTS alternate_relation ON alternates(bom_item_id,sort_no)')
        for row in db.conn.execute('SELECT id FROM skus WHERE scope_id<>0').fetchall():
            table=table_name(row[0],'alternates')
            db.conn.execute(f'CREATE INDEX IF NOT EXISTS {table}_relation ON {table}(bom_item_id,sort_no)')

def synchronization_plan(service,root,items):
    """Describe changed shared parents and the latest mirrors affected by each."""
    if not enabled(service) or not getattr(service,'sku_id',None):return []
    primary=service.primary
    latest=latest_skus(primary)
    if service.sku_id not in {s['id'] for s in latest}:return []
    old=groups(service);public=groups(primary);existing=reachable(old,root)
    retained={root}|{r['material_id'] for r in items}
    touched={root}|{mid for mid in old if mid in retained}|{r['material_id'] for r in items if r.get('replace_children')}
    desired={mid:[] for mid in touched}
    by_id={r.get('id'):r for r in items if r.get('id') is not None}
    for original in items:
        row=dict(original);parent=row.get('parent_material_id')
        if parent is None:
            source=by_id.get(row.get('parent_item_id'))
            parent=source['material_id'] if source else root
        row['parent_material_id']=parent
        if 'alternate_material_ids' not in row:
            previous=next((r for r in old.get(parent,[]) if r['material_id']==row['material_id'] and (r.get('position') or '')==(row.get('position') or '')),None)
            row['alternate_material_ids']=previous['alternate_material_ids'] if previous else []
        values=desired.setdefault(parent,[])
        if not any(r['material_id']==row['material_id'] and r.get('position','')==row.get('position','') for r in values):values.append(row)
    def payload(row):return (row['material_id'],float(row['quantity']),row.get('position','') or '',row.get('remark','') or '',tuple(row.get('alternate_material_ids',[])))
    def label(mid):
        material=service.material_snapshot(mid)
        return material.get('base_code','')+material.get('version','')+' '+material.get('name','')
    def describe(before,after):
        details=[];old_by={r['material_id']:r for r in before};new_by={r['material_id']:r for r in after}
        for mid in old_by.keys()-new_by.keys():details.append('删除物料：'+label(mid))
        for mid in new_by.keys()-old_by.keys():details.append('新增物料：'+label(mid))
        for mid in old_by.keys()&new_by.keys():
            a,b=old_by[mid],new_by[mid]
            from domain.quantity import format_quantity
            for key,title in [('quantity','数量'),('position','位置'),('remark','备注')]:
                av,bv=a.get(key,''),b.get(key,'')
                if key=='quantity':av,bv=format_quantity(av),format_quantity(bv)
                if av!=bv:details.append(f'{label(mid)} {title}：{av or "（空）"} → {bv or "（空）"}')
            aa=a.get('alternate_material_ids',[]);bb=b.get('alternate_material_ids',[])
            for value in aa:
                if value not in bb:details.append(label(mid)+' 删除替代料：'+label(value))
            for value in bb:
                if value not in aa:details.append(label(mid)+' 新增替代料：'+label(value))
        if not details:details.append('物料或替代料排序发生变化')
        return '\n'.join(details)
    plan=[]
    for mid,after in desired.items():
        before=old.get(mid,[]) if mid in existing else public.get(mid,[])
        if [payload(r) for r in before]==[payload(r) for r in after]:continue
        owners={r[0] for r in primary.db.conn.execute('SELECT sku_id FROM mirror_material_usage WHERE material_id=?',(mid,))}
        affected=[s for s in latest if s['id']!=service.sku_id and (s['id'] in owners or s['material_id']==mid)]
        if not affected:continue
        plan.append(dict(material_id=mid,label=label(mid),detail=describe(before,after),other_skus=affected,
                         before=sorted({service.material_snapshot(r['material_id'])['base_code'] for r in before}),
                         after=sorted({service.material_snapshot(r['material_id'])['base_code'] for r in after})))
    return plan

def save_confirmed(service,root,items,plan,selections,versions,progress=None):
    """Apply confirmed synchronization and optional parent forks in one transaction."""
    from services.snapshot_bom import save_with_revisions,revision_conflicts
    fresh=synchronization_plan(service,root,items)
    if fresh!=plan:raise ValueError('受影响的BOM或变更内容已变化，请重新保存并确认')
    partial=[p for p in plan if set(selections.get(p['material_id'],()))!={s['id'] for s in p['other_skus']}]
    for p in plan:
        if not set(selections.get(p['material_id'],()))<={s['id'] for s in p['other_skus']}:raise ValueError('同步目标已变化')
    approved={p['material_id'] for p in plan if p not in partial}
    service._approved_catalog_parents=approved
    try:
        conflicts={c['material_id']:c for c in revision_conflicts(service,root,items)}
        conflicts.update({c['material_id']:c for c in partial})
        with service.primary.db.transaction():
            mapping=save_with_revisions(service,root,items,versions,progress,required=list(conflicts.values())) if conflicts else {}
            if not conflicts:service.save_bom(root,items,progress=progress)
            for problem in partial:
                old=problem['material_id'];new=mapping[old]
                source=groups(service)
                descendants=reachable(source,new)
                for sid in selections.get(old,[]):
                    target=service.primary.for_sku(sid);graph=groups(target)
                    for rows in graph.values():
                        for row in rows:
                            if row['material_id']==old:row['material_id']=new
                    for mid in descendants:graph[mid]=source.get(mid,[])
                    target._catalog_sync=True
                    sku=next(s for s in target.skus() if s['id']==sid)
                    target.save_bom(sku['material_id'],rows_for(graph,sku['material_id']))
            prune_public(service.primary)
        return mapping
    finally:del service._approved_catalog_parents
