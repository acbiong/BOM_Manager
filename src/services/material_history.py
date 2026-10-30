"""Immutable material metadata/sub-BOM revisions and explicit SKU bindings.

SKU namespaces remain the editable relationship store. Historical definitions
reference other immutable revisions, so neither catalog edits nor garbage
collection can silently change an already recorded material subtree.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

FIELDS = ('base_code', 'version', 'name', 'description', 'unit', 'grade',
          'manufacturer', 'mpn', 'mp_flag')
MARKER = 'material_history_v1'


def connection(service):
    db = getattr(service, 'db', service)
    return getattr(db.conn, 'raw', db.conn)


def next_material_id(service):
    if not enabled(service):return None
    # Deleted identities may still occur in immutable child history references.
    return connection(service).execute('SELECT MAX(value)+1 FROM (SELECT COALESCE(MAX(id),0) value FROM materials UNION ALL SELECT COALESCE(MAX(material_id),0) FROM material_histories)').fetchone()[0]


def enabled(service):
    return bool(connection(service).execute(
        'SELECT 1 FROM app_metadata WHERE key=?', (MARKER,)).fetchone())


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def definitions(service, material_ids=None):
    if not enabled(service):
        return {}
    sid = getattr(service, 'sku_id', None)
    if sid is None:
        return {}
    sql='SELECT h.* FROM material_history_bindings b JOIN material_histories h ON h.material_id=b.material_id AND h.history_version=b.history_version WHERE b.sku_id=?'
    if material_ids is None:batches=[None]
    else:
        ids=list(set(material_ids));batches=[ids[i:i+500] for i in range(0,len(ids),500)]
    result={}
    for batch in batches:
        statement=sql if batch is None else sql+' AND b.material_id IN ('+','.join('?' for _ in batch)+')'
        parameters=(sid,) if batch is None else (sid,*batch)
        for row in connection(service).execute(statement,parameters):result[row['material_id']]=dict(json.loads(row['attributes']),history_version=row['history_version'])
    return result


def versions(service, mid):
    if not enabled(service):
        return []
    return [dict(row) for row in connection(service).execute(
        'SELECT history_version,created_at,source_sku_id FROM material_histories WHERE material_id=? ORDER BY history_version DESC', (mid,))]


def read(service, mid, version):
    row = connection(service).execute(
        'SELECT * FROM material_histories WHERE material_id=? AND history_version=?', (mid, version)).fetchone()
    if row is None:
        raise ValueError('物料历史版本不存在')
    return dict(row, attributes=json.loads(row['attributes']), children=json.loads(row['children']))


def record(conn, mid, attributes, children, sid=None, previous=None):
    values={k: attributes.get(k, '') for k in FIELDS}
    values['alternate_contexts']=attributes.get('alternate_contexts',{})
    attrs, edges = encode(values), encode(children)
    # Saving an unchanged historical definition must not create another revision.
    if previous is not None:
        old = conn.execute('SELECT attributes,children FROM material_histories WHERE material_id=? AND history_version=?', (mid, previous)).fetchone()
        if old and tuple(old) == (attrs, edges):
            return previous
    latest = conn.execute('SELECT * FROM material_histories WHERE material_id=? ORDER BY history_version DESC LIMIT 1', (mid,)).fetchone()
    if latest and (latest['attributes'], latest['children']) == (attrs, edges):
        return latest['history_version']
    version = latest['history_version'] + 1 if latest else 100
    conn.execute('INSERT INTO material_histories VALUES(?,?,?,?,?,?)',
                 (mid, version, attrs, edges, datetime.now().isoformat(sep=' ', timespec='microseconds'), sid))
    return version


def capture(service, edits=None):
    """Bottom-up immutable snapshots; one revision per changed definition/save."""
    from services.current_catalog import groups, reachable
    conn = connection(service)
    sid = getattr(service, 'sku_id', None)
    graph = groups(service)
    materials = {r['id']: dict(r) for r in conn.execute('SELECT * FROM materials')}
    bound = definitions(service)
    edits = edits or {}
    if sid:
        root = conn.execute('SELECT material_id FROM skus WHERE id=?', (sid,)).fetchone()[0]
        used = reachable(graph, root)
    else:
        used = set(materials)
    main_used=set(used)
    used.update(a for mid in list(used) for r in graph.get(mid, []) for a in r['alternate_material_ids'])
    done, active = {}, set()

    def visit(mid):
        if mid in done:
            return done[mid]
        if mid in active:
            raise ValueError('物料历史结构存在循环引用')
        active.add(mid)
        attributes = dict(materials[mid]); attributes.update(bound.get(mid, {})); attributes.update(edits.get(mid, {}))
        if mid in main_used:
            attributes['alternate_contexts']={str(parent):[{k:({**materials[aid],**bound.get(aid,{}),**edits.get(aid,{})}).get(k,'') for k in FIELDS} for aid in row['alternate_material_ids']]
                for parent in main_used for row in graph.get(parent,[]) if row['material_id']==mid and row['alternate_material_ids']}
        if mid not in main_used:
            previous=bound.get(mid,{}).get('history_version')
            if previous is None:previous=conn.execute('SELECT MAX(history_version) FROM material_histories WHERE material_id=?',(mid,)).fetchone()[0]
            children=read(service,mid,previous)['children'] if previous is not None else []
            done[mid]=record(conn,mid,attributes,children,sid,previous);active.remove(mid);return done[mid]
        children = []
        for row in graph.get(mid, []):
            child = row['material_id']
            # Alternates are identities, not edges in the main BOM. Their own
            # subtrees need not be recursively traversed (A may replace B).
            alternates = []
            for aid in row['alternate_material_ids']:
                alt_attrs = dict(materials[aid]); alt_attrs.update(bound.get(aid, {})); alt_attrs.update(edits.get(aid, {}))
                av = bound.get(aid, {}).get('history_version')
                if aid not in main_used:av=visit(aid)
                elif av is None:
                    latest = conn.execute('SELECT MAX(history_version) FROM material_histories WHERE material_id=?', (aid,)).fetchone()[0]
                    av = latest if latest is not None else record(conn, aid, alt_attrs, [], sid)
                if aid in edits:
                    av=record(conn,aid,alt_attrs,read(service,aid,av)['children'],sid,av)
                alternates.append(dict(material_id=aid, history_version=av))
            children.append(dict(material_id=child, history_version=visit(child), quantity=float(row['quantity']),
                                 unit=row['unit'], position=row.get('position') or '', remark=row.get('remark') or '', alternates=alternates))
        previous = bound.get(mid, {}).get('history_version')
        done[mid] = record(conn, mid, attributes, children, sid, previous)
        active.remove(mid)
        return done[mid]

    for mid in sorted(used):
        visit(mid)
    if sid:
        conn.execute('DELETE FROM material_history_bindings WHERE sku_id=?', (sid,))
        conn.executemany('INSERT INTO material_history_bindings VALUES(?,?,?)', [(sid, mid, version) for mid, version in done.items()])
    return {mid: version for mid, version in done.items() if bound.get(mid, {}).get('history_version') != version}


def initialize(db):
    if enabled(db):
        return
    from services.services import Services
    conn = db.conn
    if db.path != ':memory:' and conn.execute('SELECT 1 FROM materials LIMIT 1').fetchone():
        path = Path(str(db.path) + '.pre-material-history-' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.db')
        backup = sqlite3.connect(str(path))
        try:
            conn.backup(backup)
        finally:
            backup.close()
    with db.transaction():
        conn.execute('CREATE TABLE IF NOT EXISTS material_histories(material_id INTEGER NOT NULL,history_version INTEGER NOT NULL,attributes TEXT NOT NULL,children TEXT NOT NULL,created_at TEXT NOT NULL,source_sku_id INTEGER,PRIMARY KEY(material_id,history_version))')
        conn.execute('CREATE TABLE IF NOT EXISTS material_history_bindings(sku_id INTEGER NOT NULL,material_id INTEGER NOT NULL,history_version INTEGER NOT NULL,PRIMARY KEY(sku_id,material_id))')
        conn.execute('CREATE INDEX IF NOT EXISTS material_history_usage ON material_history_bindings(material_id,history_version,sku_id)')
        conn.execute('INSERT INTO app_metadata VALUES(?,?)', (MARKER, '1'))
        service = Services(db)
        # Existing differing historical structures are retained, never collapsed.
        for sku in sorted(service.skus(), key=lambda s: (s['mirror_version'], s['updated_at'] or '', s['id'])):
            capture(service.for_sku(sku['id']))
        # Unreferenced materials also start at 100; do not overwrite old subtrees.
        for material in conn.execute('SELECT * FROM materials').fetchall():
            if not versions(service, material['id']):
                record(conn, material['id'], dict(material), [])


def copy_bindings(source, sid):
    if not enabled(source):
        return
    conn = connection(source)
    source_id = getattr(source, 'sku_id', None)
    if source_id:
        conn.execute('INSERT INTO material_history_bindings SELECT ?,material_id,history_version FROM material_history_bindings WHERE sku_id=?', (sid, source_id))


def affected(service, mids):
    from services.current_catalog import latest_skus
    primary = getattr(service, 'primary', service)
    conn = connection(service)
    mids = set(mids)
    owners = {}
    for sku in latest_skus(primary):
        if sku['id'] == getattr(service, 'sku_id', None):
            continue
        used = {r[0] for r in conn.execute('SELECT material_id FROM material_history_bindings WHERE sku_id=?', (sku['id'],))}
        shared = mids & used
        if shared:
            owners[sku['id']] = (dict(sku), shared)
    return owners


def finish_save(service, changed_parents, edits=None, mode='sync', mapping=None,versions_map=None):
    """Called inside the outer save transaction, before notifications escape."""
    from services.current_catalog import groups, rows_for, latest_skus, write_public
    conn = connection(service); primary = getattr(service, 'primary', service)
    mapping = mapping or {}; edits = edits or {}
    changed = capture(service, edits)
    bound = definitions(service)
    changed.update({mid: bound[mid]['history_version'] for mid in set(changed_parents)|set(edits) if mid in bound})
    sid = getattr(service, 'sku_id', None)
    latest_ids = {s['id'] for s in latest_skus(primary)}
    if sid and sid not in latest_ids:
        mode='fork'  # An old SKU history never updates another SKU snapshot.
    source = groups(service)
    candidates = set(changed_parents) | set(edits) | set(mapping)
    sync_ids = {mid for mid in candidates if (mode.get(mid, 'fork') if isinstance(mode, dict) else mode) == 'sync'}
    if sync_ids:
        for target_id, (sku, shared) in affected(service, sync_ids).items():
            target = primary.for_sku(target_id); graph = groups(target)
            target_bound=set(definitions(target))
            for rows in graph.values():
                for row in rows:
                    row['material_id'] = mapping.get(row['material_id'], row['material_id']) if row['material_id'] in sync_ids else row['material_id']
                    row['alternate_material_ids'] = [mapping.get(a, a) if a in sync_ids else a for a in row['alternate_material_ids']]
            pending = [mapping.get(mid, mid) for mid in shared if mid in changed_parents or mid in mapping]
            visited = set()
            while pending:
                mid = pending.pop()
                if mid in visited:
                    continue
                visited.add(mid); graph[mid] = source.get(mid, [])
                pending.extend(r['material_id'] for r in graph[mid] if r['material_id'] in sync_ids or r['material_id'] not in target_bound)
            target._catalog_sync = True; target._history_defer = True
            target_edits={mid: value for mid, value in edits.items() if mid in shared}
            target._history_edits=target_edits;target._history_revision_approved=set(mapping.values())
            target_rows=rows_for(graph,sku['material_id'])
            for row in target_rows:
                if row['material_id'] in target_edits:row['unit']=target_edits[row['material_id']].get('unit',row['unit'])
            conflicts=attribute_conflicts(target,sku['material_id'],target_rows)
            target_mapping={}
            if conflicts:
                from services.snapshot_bom import save_with_revisions,ParentRevisionRequired
                required={c['material_id'] for c in conflicts}
                if not required<=set(versions_map or {}):raise ParentRevisionRequired(conflicts)
                target_mapping=save_with_revisions(target,sku['material_id'],target_rows,{mid:versions_map[mid] for mid in required},required=conflicts)
            else:target.save_bom(sku['material_id'],target_rows)
            capture(target,target_edits)
            if target_mapping:
                target_graph=groups(target)
                write_public(primary,{mid:target_graph.get(mid,[]) for mid in target_mapping.values()})
            conn.execute('UPDATE skus SET updated_at=? WHERE id=?', (datetime.now().isoformat(sep=' '), target_id))
            target.publish({'type': 'bom_changed', 'root': sku['material_id']})
    # The library presents the newest recorded state; never rewrite history rows.
    for mid in changed:
        attrs = read(service, mid, max(v['history_version'] for v in versions(service, mid)))['attributes']
        keys = [k for k in FIELDS if k not in ('base_code', 'version')]
        conn.execute('UPDATE materials SET ' + ','.join(k+'=?' for k in keys) + ',updated_at=? WHERE id=?',
                     tuple(attrs[k] for k in keys) + (datetime.now().isoformat(sep=' '), mid))
    write_public(primary, {mid: source.get(mid, []) for mid in changed if mid in source or mid in changed_parents})
    if changed:
        service.publish({'type': 'material_history_changed', 'ids': list(changed)})
        service.publish({'type': 'sku_changed'})
    return changed


def save(service, root, rows, edits, mode, versions_map=None):
    from services.snapshot_bom import save_with_revisions
    if not isinstance(mode, dict) and mode not in ('sync', 'fork'):
        raise ValueError('请选择同步最新BOM或升级物料历史版本')
    versions_map = versions_map or {}
    edits=dict(edits)
    for mid,data in edits.items():
        original=service.material_snapshot(mid)
        if not original:raise ValueError('待修改物料已不存在')
        if any(data.get(k,original[k])!=original[k] for k in ('base_code','version')):raise ValueError('物料基础编码及编码版本请通过版本变更功能修改')
        if not str(data.get('name',original['name'])).strip():raise ValueError('物料名称为必填项')
        if data.get('unit',original['unit']) not in service.UNITS:raise ValueError('单位不合规')
    rows=[dict(row) for row in rows]
    for row in rows:
        if row['material_id'] in edits:row['unit']=edits[row['material_id']].get('unit',row['unit'])
    from services.snapshot_bom import ParentRevisionRequired,revision_conflicts
    required=collect_conflicts(service,root,rows,edits,mode)
    if {c['material_id'] for c in required}!=set(versions_map):
        if required:raise ParentRevisionRequired(required)
        raise ValueError('父项升版清单已变化，请重新检查')
    service._history_edits = edits; service._history_defer = True
    try:
        with service.db.transaction():
            from services.current_catalog import groups
            old_graph = groups(service)
            before = {mid: version['history_version'] for mid, version in definitions(service).items()}
            source_required={c['material_id'] for c in revision_conflicts(service,root,rows)}
            mapping = save_with_revisions(service, root, rows, {mid:versions_map[mid] for mid in source_required}) if source_required else {}
            if not source_required:
                service.save_bom(root, rows)
            remapped_edits = {mapping.get(mid, mid): dict(value) for mid, value in edits.items()}
            for old,new in mapping.items():
                if new in remapped_edits:
                    identity=connection(service).execute('SELECT base_code,version FROM materials WHERE id=?',(new,)).fetchone()
                    remapped_edits[new].update(base_code=identity[0],version=identity[1])
            changes = capture(service, remapped_edits)
            # capture above establishes the final bindings; include all genuinely
            # changed descendants/ancestors when propagating the saved definition.
            new_graph = groups(service)
            def signature(rows):
                return [(r['material_id'], float(r['quantity']), r.get('unit'), r.get('position') or '', r.get('remark') or '', r['alternate_material_ids']) for r in rows]
            direct = {mid for mid in set(old_graph)|set(new_graph) if signature(old_graph.get(mid, [])) != signature(new_graph.get(mid, []))}
            changed = {mid for mid, value in definitions(service).items() if before.get(mid) != value['history_version']}
            if isinstance(mode, dict):
                mode = dict(mode)
                for old, new in mapping.items():mode[new] = mode.get(old, 'fork')
            finish_save(service, direct | set(mapping), remapped_edits, mode, mapping,versions_map)
            for mid in changes:
                service.log('material', mid, 'history_version', '物料历史版本：'+str(before.get(mid, '新建'))+' → '+str(changes[mid]))
            if changes and getattr(service,'sku_id',None):
                connection(service).execute('UPDATE skus SET updated_at=? WHERE id=?',(datetime.now().isoformat(sep=' '),service.sku_id))
                service.publish({'type':'bom_changed','root':root})
                service.publish({'type':'sku_changed','id':service.sku_id})
            service.publish({'type': 'material_history_changed', 'ids': list(changed)})
            return mapping
    finally:
        del service._history_edits
        del service._history_defer


def catalog_source(service,mid):
    from services.current_catalog import latest_skus
    primary=getattr(service,'primary',service)
    for sku in latest_skus(primary):
        if connection(service).execute('SELECT 1 FROM material_history_bindings WHERE sku_id=? AND material_id=?',(sku['id'],mid)).fetchone():
            return primary.for_sku(sku['id']),sku['material_id']
    return primary,None


def decision_token(service,mid):
    return tuple((sid,tuple(sorted(shared)),sku['mirror_version'],sku['updated_at'],sku['locked'])
                 for sid,(sku,shared) in affected(service,[mid]).items())


def collect_conflicts(service,root,rows,edits,mode='fork'):
    from services.snapshot_bom import revision_conflicts
    service._history_edits=edits
    try:result={c['material_id']:c for c in revision_conflicts(service,root,rows)}
    finally:del service._history_edits
    ids={mid for mid in edits if (mode.get(mid,'fork') if isinstance(mode,dict) else mode)=='sync'}
    primary=getattr(service,'primary',service)
    for sid,(sku,shared) in affected(service,ids).items():
        target=primary.for_sku(sid);target._history_edits={mid:edits[mid] for mid in shared}
        for conflict in attribute_conflicts(target,sku['material_id'],target.bom(sku['material_id'])):
            result.setdefault(conflict['material_id'],conflict)
    return list(result.values())


def update_catalog_material(service,mid,data):
    primary=getattr(service,'primary',service)
    source,root=catalog_source(primary,mid)
    if root is not None:
        return save(source,root,source.bom(root),{mid:data},'sync')
    conn=connection(service)
    with service.db.transaction():
        before=primary.material_snapshot(mid)
        if not before:raise ValueError('物料不存在')
        latest=versions(service,mid)
        children=read(service,mid,latest[0]['history_version'])['children'] if latest else []
        attrs={**before,**data}
        if attrs['unit'] not in service.UNITS:raise ValueError('单位不合规')
        record(conn,mid,attrs,children)
        keys=[k for k in FIELDS if k not in ('base_code','version')]
        conn.execute('UPDATE materials SET '+','.join(k+'=?' for k in keys)+',updated_at=? WHERE id=?',tuple(attrs.get(k,'') for k in keys)+(datetime.now().isoformat(sep=' '),mid))
        primary.log('material',mid,'update',primary.material_detail(before,attrs))
        primary.publish({'type':'material_changed','id':mid})


def selection_tree(service,root):
    """Always import the newest immutable catalog definition into a draft."""
    latest=versions(service,root)
    if not latest:return None
    number=[0]
    def expand(mid,version,path):
        record=read(service,mid,version);nodes=[]
        if (mid,version) in path:raise ValueError('物料历史结构存在循环引用')
        for edge in record['children']:
            child=edge['material_id'];revision=edge['history_version'];attrs=read(service,child,revision)['attributes']
            number[0]-=1
            data=dict(attrs,id=number[0],material_id=child,parent_material_id=mid,history_version=revision,
                      quantity=edge['quantity'],position=edge['position'],remark=edge['remark'],
                      _db_alternates=[a['material_id'] for a in edge['alternates']],
                      alternate_material_ids=[a['material_id'] for a in edge['alternates']])
            nodes.append(dict(data=data,children=expand(child,revision,path|{(mid,version)})))
        return nodes
    return expand(root,latest[0]['history_version'],set())


def attribute_conflicts(service, root, items):
    """Code revision rules are separate from material history revisions.

    Adding alternatives is exempt; removing one or editing relationship/child
    metadata requires the non-SKU parent's code revision. Pure order is ignored.
    """
    if not enabled(service):return []
    from services.current_catalog import groups
    from services.snapshot_bom import other_sku_usages
    old = groups(service); desired = {}
    by_id = {r.get('id'): r for r in items if r.get('id') is not None}
    edits = getattr(service, '_history_edits', {})
    details = {}
    for row in items:
        parent = row.get('parent_material_id')
        if parent is None:parent = by_id.get(row.get('parent_item_id'), {}).get('material_id', root)
        desired.setdefault(parent, []).append(row)
        previous = next((r for r in old.get(parent, []) if r['material_id']==row['material_id']), None)
        reasons = []
        material = service.material_snapshot(row['material_id'])
        label = material['base_code']+material['version']+' '+material['name']
        if row['material_id'] in edits:
            change = service.material_detail(material, {**material, **edits[row['material_id']]})
            if change:reasons.append(change)
        if previous:
            for key, title in [('quantity','数量'),('unit','单位'),('position','位置'),('remark','备注')]:
                a, b = previous.get(key) or '', row.get(key) or ''
                if a != b:reasons.append(f'{title}：{a or "（空）"} → {b or "（空）"}')
            if 'alternate_material_ids' in row and set(previous['alternate_material_ids'])-set(row['alternate_material_ids']):reasons.append('删除替代料')
        if reasons:details.setdefault(parent, []).append(label+'：'+'；'.join(reasons))
    result = []
    for mid, detail in details.items():
        if mid in getattr(service,'_history_revision_approved',set()):continue
        if service.db.conn.execute('SELECT 1 FROM skus WHERE material_id=?', (mid,)).fetchone():continue
        material = service.material_snapshot(mid)
        result.append(dict(material_id=mid, label=material['base_code']+material['version']+' '+material['name'],
                           before=[service.material_snapshot(r['material_id'])['base_code'] for r in old.get(mid, [])],
                           after=[service.material_snapshot(r['material_id'])['base_code'] for r in desired.get(mid, [])],
                           detail='\n'.join(detail), other_skus=other_sku_usages(service, mid)))
    return result
