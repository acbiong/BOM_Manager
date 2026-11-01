"""Explicit, transactional edits across selected SKU BOM histories."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from services import material_history as history
from services.current_catalog import groups, rows_for


@dataclass(frozen=True)
class Selection:
    material_id: int
    sku_ids: frozenset
    token: tuple
    impact_mid: int | None = None


def references(service, mid):
    conn=history.connection(service);primary=getattr(service,'primary',service)
    versions=dict(conn.execute('SELECT sku_id,history_version FROM material_history_bindings WHERE material_id=?',(mid,)))
    current=getattr(service,'sku_id',None)
    return sorted((dict(s,material_history_version=versions[s['id']]) for s in primary.skus()
                   if s['id'] in versions and s['id']!=current),
                  key=lambda s:(s['base_code'],s['version'],s['mirror_version'],s['id']))


def token(service, mid):
    return tuple((s['id'],s['material_history_version'],s['updated_at'],s['locked']) for s in references(service,mid))


def select(service, mid, ids=(), impact_mid=None):
    return Selection(mid,frozenset(ids),token(service,mid),impact_mid)


def selections(mode):
    return [mode] if isinstance(mode,Selection) else [v for v in mode.values() if isinstance(v,Selection)] if isinstance(mode,dict) else []


def signature(rows):
    return [(r['material_id'],float(r['quantity']),r.get('unit'),r.get('position') or '',r.get('remark') or '',
             tuple(r.get('alternate_material_ids',[]))) for r in rows]


def plans(service, root, rows, edits, mode):
    """Apply only the approved change, preserving target-specific quantities etc."""
    primary=getattr(service,'primary',service);sid=service.sku_id
    skus={s['id']:s for s in primary.skus()}
    before=groups(service);desired={root:[]}
    old_by_id={r['id']:r for values in before.values() for r in values}
    for raw in rows:
        row=dict(raw);parent=row.get('parent_material_id',root)
        row['alternate_material_ids']=list(row.get('alternate_material_ids',old_by_id.get(row.get('id'),{}).get('alternate_material_ids',[])))
        bucket=desired.setdefault(parent,[])
        if not any(r['material_id']==row['material_id'] and r.get('position','')==row.get('position','') for r in bucket):bucket.append(row)
        desired.setdefault(row['material_id'],[])
    result={sid:dict(service=service,sku=skus[sid],graph=desired,edits=dict(edits))}
    fork_mids=set()
    for choice in selections(mode):
        if choice.token!=token(service,choice.material_id):raise ValueError('引用BOM或锁定状态已变化，请重新选择变更范围')
        available={s['id'] for s in references(service,choice.material_id)}
        if not choice.sku_ids<=available:raise ValueError('所选BOM已不再引用此物料，请重新选择')
        mid=choice.material_id
        partial=bool(available-choice.sku_ids)
        if partial:fork_mids.add(mid)
        for target_id in choice.sku_ids:
            if target_id not in result:
                target=primary.for_sku(target_id)
                result[target_id]=dict(service=target,sku=skus[target_id],graph=deepcopy(groups(target)),edits={})
            target_plan=result[target_id];target=target_plan['service'];graph=target_plan['graph']
            if choice.impact_mid is not None:
                # Alternative lists belong to incoming relationships. Propagate
                # additions/removals to every main occurrence, across parents.
                added=[];removed=set()
                for parent,children in desired.items():
                    for row in children:
                        if row['material_id']!=mid:continue
                        old=next((r for r in before.get(parent,[]) if r['material_id']==mid and r.get('position','')==row.get('position','')),None)
                        if old is None:continue
                        added.extend(a for a in row['alternate_material_ids'] if a not in old['alternate_material_ids'] and a not in added)
                        removed.update(set(old['alternate_material_ids'])-set(row['alternate_material_ids']))
                for parent,children in graph.items():
                    for row in children:
                        if row['material_id']==mid:
                            row['alternate_material_ids']=[a for a in row['alternate_material_ids'] if a not in removed]
                            row['alternate_material_ids']+= [a for a in added if a not in row['alternate_material_ids']]
                            if partial:fork_mids.add(parent)
            else:
                if mid in edits:
                    original=service.material_snapshot(mid)
                    delta={k:v for k,v in edits[mid].items() if k in history.FIELDS and v!=original.get(k)}
                    target_plan['edits'][mid]={**target.material_snapshot(mid),**delta}
                if signature(desired.get(mid,[]))!=signature(before.get(mid,[])):
                    graph[mid]=deepcopy(desired.get(mid,[]))
                    pending=[r['material_id'] for r in graph[mid]];seen=set()
                    while pending:
                        child=pending.pop()
                        if child in seen:continue
                        seen.add(child)
                        if child not in graph:
                            graph[child]=deepcopy(desired.get(child,[]));pending.extend(r['material_id'] for r in graph[child])
        if partial and choice.impact_mid is not None:
            fork_mids.update(parent for parent,children in desired.items() if any(r['material_id']==mid for r in children))
    for entry in result.values():
        for children in entry['graph'].values():
            for row in children:
                if row['material_id'] in entry['edits']:row['unit']=entry['edits'][row['material_id']].get('unit',row['unit'])
        entry['rows']=rows_for(entry['graph'],entry['sku']['material_id'])
    return result,fork_mids


def conflicts(service, root, rows, edits, mode):
    from services.snapshot_bom import revision_conflicts
    result={}
    for entry in plans(service,root,rows,edits,mode)[0].values():
        target=entry['service'];previous=getattr(target,'_history_edits',None)
        target._history_edits=entry['edits']
        try:
            for conflict in revision_conflicts(target,entry['sku']['material_id'],entry['rows']):
                # Exclusive material changes must not introduce another prompt.
                if not references(target,conflict['material_id']):continue
                result.setdefault(conflict['material_id'],conflict)
        finally:
            if previous is None:del target._history_edits
            else:target._history_edits=previous
    return list(result.values())


def compact_new_revisions(conn, original_keys, original_bindings, fork_mids, original_current):
    """Reuse an old number only when every BOM using it moved together.

    Child-number substitutions can make ancestor snapshots identical again;
    iterate to a fixed point without modifying any unselected BOM's content.
    """
    old_owners={}
    for sid,mid,version in original_bindings:old_owners.setdefault((mid,version),set()).add(sid)
    bound_mids={mid for _,mid,_ in original_bindings}
    for mid,v in original_current.items():
        if mid not in bound_mids:old_owners.setdefault((mid,v),set())
    while True:
        records={(r['material_id'],r['history_version']):dict(r) for r in conn.execute('SELECT * FROM material_histories')}
        bindings={(sid,mid):v for sid,mid,v in conn.execute('SELECT * FROM material_history_bindings')}
        created=set(records)-original_keys;mapping={};overwrite={}
        for new in sorted(created):
            row=records[new]
            same=next((old for old in sorted(original_keys & records.keys()) if old[0]==new[0] and
                       all(records[old][f]==row[f] for f in ('attributes','children'))),None)
            if same is not None:mapping[new]=same;continue
            if new[0] in fork_mids:continue
            for old,owners in sorted(old_owners.items()):
                if old not in records or old[0]!=new[0]:continue
                versions={bindings.get((sid,old[0])) for sid in owners}
                # Removed references are not permission to rewrite their archive.
                if (versions=={new[1]} or not owners) and old not in overwrite:
                    mapping[new]=old;overwrite[old]=row;break
        if not mapping:break
        for old,row in overwrite.items():
            conn.execute('UPDATE material_histories SET attributes=?,children=? WHERE material_id=? AND history_version=?',
                         (row['attributes'],row['children'],*old))
        for new,old in mapping.items():
            conn.execute('UPDATE material_history_bindings SET history_version=? WHERE material_id=? AND history_version=?',(old[1],*new))
            conn.execute('UPDATE material_history_current SET history_version=? WHERE material_id=? AND history_version=?',(old[1],*new))
            conn.execute('DELETE FROM material_histories WHERE material_id=? AND history_version=?',new)
        import json
        for row in conn.execute('SELECT material_id,history_version,children FROM material_histories').fetchall():
            children=json.loads(row['children']);changed=False
            for edge in children:
                for ref in [edge,*edge.get('alternates',[])]:
                    old=mapping.get((ref['material_id'],ref['history_version']))
                    if old:ref['history_version']=old[1];changed=True
            if changed:conn.execute('UPDATE material_histories SET children=? WHERE material_id=? AND history_version=?',(history.encode(children),row['material_id'],row['history_version']))


def save(service, root, rows, edits, mode, versions_map):
    from services.snapshot_bom import save_with_revisions,ParentRevisionRequired,revision_conflicts
    from services.sku_lock import assert_sku_unlocked
    from services.current_catalog import write_public
    conn=history.connection(service);primary=getattr(service,'primary',service)
    with service.db.transaction():
        entries,fork_mids=plans(service,root,rows,edits,mode)
        required=conflicts(service,root,rows,edits,mode)
        if {c['material_id'] for c in required}!=set(versions_map):
            if required:raise ParentRevisionRequired(required)
            raise ValueError('父项升版清单已变化，请重新检查')
        for sid in entries:assert_sku_unlocked(service,sid)
        original_keys={tuple(r) for r in conn.execute('SELECT material_id,history_version FROM material_histories')}
        original_bindings=[tuple(r) for r in conn.execute('SELECT * FROM material_history_bindings')]
        original_current=dict(conn.execute('SELECT * FROM material_history_current'))
        source_mapping={};changed_ids=set();catalog={};metadata_logs=[]
        for sid,entry in entries.items():
            target=entry['service'];target_root=entry['sku']['material_id'];values=entry['edits']
            before={mid:target.material_snapshot(mid) for mid in values}
            old_graph=groups(target)
            changed_parents={mid for mid in set(old_graph)|set(entry['graph']) if signature(old_graph.get(mid,[]))!=signature(entry['graph'].get(mid,[]))}
            if not changed_parents and not any(any(v.get(k,old.get(k))!=old.get(k) for k in history.FIELDS) for mid,v in values.items() for old in [before[mid]]):continue
            target._history_defer=True;target._history_edits=values
            try:
                local=conflicts_for_entry(entry)
                needed={c['material_id'] for c in local}
                target._history_revision_approved={c['material_id'] for c in revision_conflicts(target,target_root,entry['rows'])}-needed
                mapping=save_with_revisions(target,target_root,entry['rows'],{mid:versions_map[mid] for mid in needed},required=local) if local else {}
                if not local:target.save_bom(target_root,entry['rows'])
                adjusted={mapping.get(mid,mid):dict(v) for mid,v in values.items()}
                for old,new in mapping.items():
                    if new in adjusted:
                        identity=conn.execute('SELECT base_code,version FROM materials WHERE id=?',(new,)).fetchone();adjusted[new].update(base_code=identity[0],version=identity[1])
                history.capture(target,adjusted)
                for old,attrs in before.items():metadata_logs.append((target,mapping.get(old,old),attrs))
                changed_ids.update(adjusted);changed_ids.update(mapping.values());changed_ids.update(changed_parents)
                graph=groups(target)
                catalog.update({mapping.get(mid,mid):graph.get(mapping.get(mid,mid),[]) for mid in changed_parents})
                if sid==service.sku_id:source_mapping=mapping
                conn.execute('UPDATE skus SET updated_at=? WHERE id=?',(datetime.now().isoformat(sep=' ',timespec='microseconds'),sid))
                target.publish(dict(type='bom_changed',root=target_root))
            finally:
                for name in ('_history_defer','_history_edits','_history_revision_approved'):
                    if hasattr(target,name):delattr(target,name)
        compact_new_revisions(conn,original_keys,original_bindings,fork_mids,original_current)
        for target,mid,attrs in metadata_logs:
            detail=history.log_metadata_edit(target,mid,attrs)
            if detail and target is service:primary.log('material',mid,'update',detail,snapshot=target.material_snapshot(mid))
        # Public selection follows the source's saved state, while each SKU's
        # own namespace and binding retain its explicitly selected result.
        source=groups(service)
        catalog.update({mid:source[mid] for mid in catalog if mid in source})
        if catalog:write_public(primary,catalog)
        for mid in changed_ids:
            v=history.current_version(conn,mid)
            if v is None:continue
            attrs=history.read(service,mid,v)['attributes'];keys=[k for k in history.FIELDS if k not in ('base_code','version')]
            conn.execute('UPDATE materials SET '+','.join(k+'=?' for k in keys)+' WHERE id=?',tuple(attrs[k] for k in keys)+(mid,))
        if changed_ids:
            service.publish(dict(type='material_history_changed',ids=list(changed_ids)))
            service.publish(dict(type='sku_changed',ids=list(entries)))
        return source_mapping


def conflicts_for_entry(entry):
    from services.snapshot_bom import revision_conflicts
    target=entry['service']
    return [c for c in revision_conflicts(target,entry['sku']['material_id'],entry['rows']) if references(target,c['material_id'])]
