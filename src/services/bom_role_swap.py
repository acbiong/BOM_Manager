"""Recognize main/alternate role exchanges from saved and proposed relations."""

def is_swap(before,after):
    old=before['material_id'];new=after['material_id']
    aa=set(before.get('alternate_material_ids',[]));bb=set(after.get('alternate_material_ids',[]))
    return old!=new and new in aa and old in bb and aa|{old}==bb|{new}


def is_exchange(before,after):
    """Retain a confirmed draft exchange after subsequent alternate edits.

    The origin is anchored to the saved relationship, so refreshes, different
    parents and arbitrary replacements cannot inherit an unrelated exemption.
    Relationship fields are still compared separately by attribute_conflicts.
    """
    if is_swap(before,after):return True
    origin=after.get('_role_swap_origin')
    if not isinstance(origin,dict):return False
    if any(origin.get(k)!=before.get(k) for k in ('material_id','parent_material_id')):return False
    if (origin.get('position') or '')!=(before.get('position') or ''):return False
    alternatives=set(before.get('alternate_material_ids',[]))
    return (set(origin.get('alternate_material_ids',[]))==alternatives
            and after['material_id']!=before['material_id']
            and after['material_id'] in alternatives
            and origin.get('target_material_id')==after['material_id'])


def pair_rows(before,after):
    """Match each occurrence once, preserving position identity when possible."""
    from collections import defaultdict,deque
    remaining=set(range(len(before)));paired={}
    exact=defaultdict(deque)
    for j,row in enumerate(before):exact[row['material_id'],row.get('position') or ''].append(j)
    for i,row in enumerate(after):
        candidates=exact[row['material_id'],row.get('position') or '']
        if candidates:j=candidates.popleft();paired[i]=j;remaining.remove(j)
    for match in (lambda a,b:is_exchange(a,b) and (a.get('position') or '')==(b.get('position') or ''),
                  lambda a,b:a['material_id']==b['material_id'],is_exchange):
        for i,row in enumerate(after):
            if i in paired:continue
            j=next((j for j in sorted(remaining) if match(before[j],row)),None)
            if j is not None:paired[i]=j;remaining.remove(j)
    return paired


def draft_groups(root,items):
    result={root:[]};by_id={r.get('id'):r for r in items if r.get('id') is not None};seen=set()
    for row in items:
        parent=row.get('parent_material_id')
        if parent is None:
            ancestor=by_id.get(row.get('parent_item_id'))
            if ancestor is None and isinstance(row.get('parent_item_id'),int) and 1<=row['parent_item_id']<=len(items):ancestor=items[row['parent_item_id']-1]
            parent=ancestor['material_id'] if ancestor else root
        key=(parent,row['material_id'],row.get('position') or '')
        if key not in seen:result.setdefault(parent,[]).append(row);seen.add(key)
        if row.get('replace_children'):result.setdefault(row['material_id'],[])
    return result


def accepted(service,mid,codes):
    return service.db.conn.execute('SELECT 1 FROM bom_revision_role_definitions WHERE material_id=? AND child_codes=?',(mid,codes)).fetchone() is not None


def definitions(service,root,items):
    from services.current_catalog import groups
    from services.snapshot_bom import signature
    old=groups(service);result={};codes={}
    def code(mid):
        if mid not in codes:codes[mid]=service.material_snapshot(mid)['base_code']
        return codes[mid]
    for mid,after in draft_groups(root,items).items():
        before=old.get(mid,[])
        if not before or len(before)!=len(after):continue
        if {r['material_id'] for r in before}=={r['material_id'] for r in after}:continue
        pairs=pair_rows(before,after)
        if len(pairs)!=len(after) or not any(is_exchange(before[j],after[i]) for i,j in pairs.items()):continue
        original=signature(code(r['material_id']) for r in before)
        known=service.db.conn.execute('SELECT child_codes FROM bom_revision_definitions WHERE material_id=?',(mid,)).fetchone()
        if known and (known[0]==original or accepted(service,mid,original)):
            result[mid]=signature(code(r['material_id']) for r in after)
    return result
