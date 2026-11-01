"""Pure comparison of two stored material subtrees; never changes bindings."""
from difflib import SequenceMatcher
from services import material_history as history

DIFF_FIELDS=('base_code','version','name','description','unit','grade','manufacturer','mpn','mp_flag')


def pair_children(current,previous):
    """Match stable identities/positions first, then position edits by identity."""
    paired={};remaining=set(range(len(previous)))
    for i,edge in enumerate(current):
        found=next((j for j in sorted(remaining) if previous[j]['material_id']==edge['material_id'] and previous[j].get('position','')==edge.get('position','')),None)
        if found is not None:paired[i]=found;remaining.remove(found)
    for i,edge in enumerate(current):
        if i in paired:continue
        found=next((j for j in sorted(remaining) if previous[j]['material_id']==edge['material_id']),None)
        if found is not None:paired[i]=found;remaining.remove(found)
    old_order=sorted(paired.values());new_order=[paired[i] for i in sorted(paired)]
    stable=set()
    for block in SequenceMatcher(None,old_order,new_order,autojunk=False).get_matching_blocks():
        stable.update(new_order[block.b:block.b+block.size])
    return paired,remaining,{i for i,j in paired.items() if j not in stable}


def compare(service,mid,version):
    previous_versions=[r['history_version'] for r in history.versions(service,mid) if r['history_version']<version]
    previous=max(previous_versions) if previous_versions else None
    cache={}
    def read(key):
        if key not in cache:cache[key]=history.read(service,*key)
        return cache[key]
    def alternatives(current,old,added,deleted):
        matches,missing,_=pair_children(current,old);result=[]
        for i,edge in enumerate(current):
            record=read((edge['material_id'],edge['history_version']))
            prior=read((old[matches[i]]['material_id'],old[matches[i]]['history_version'])) if i in matches else None
            state='deleted' if deleted else 'added' if added or prior is None else 'modified' if record['history_version']!=prior['history_version'] or any(record['attributes'].get(k)!=prior['attributes'].get(k) for k in DIFF_FIELDS) else ''
            result.append(dict(record=record,previous=prior,state=state))
        for j in sorted(missing):result.append(dict(record=read((old[j]['material_id'],old[j]['history_version'])),previous=None,state='deleted'))
        return result
    def node(key,old_key=None,edge=None,old_edge=None,added=False,deleted=False,moved=False,path=frozenset(),old_path=frozenset()):
        if key in path or old_key is not None and old_key in old_path:raise ValueError('物料历史数据存在循环引用')
        record=read(key);prior=read(old_key) if old_key is not None else None
        edge=edge or {};old_edge=old_edge or {}
        attrs=record['attributes'];before=prior['attributes'] if prior else {}
        fields={k for k in DIFF_FIELDS if prior and attrs.get(k,'')!=before.get(k,'')}
        changed={c for k,c in [('base_code',0),('version',0),('name',1),('unit',4)] if k in fields}
        if prior and record['history_version']!=prior['history_version']:changed.add(2)
        for key_name,column in [('quantity',3),('position',5),('remark',6),('unit',4)]:
            if prior and edge.get(key_name,'' if key_name!='quantity' else 1)!=old_edge.get(key_name,'' if key_name!='quantity' else 1):changed.add(column)
        alt=alternatives(edge.get('alternates',[]),old_edge.get('alternates',[]) if prior else [],added,deleted)
        if prior and (edge.get('alternates',[])!=old_edge.get('alternates',[]) or any(a['state'] for a in alt)):changed.add(7)
        children=[];current=record['children'];old=prior['children'] if prior else []
        paired,missing,reordered=pair_children(current,old)
        for i,child in enumerate(current):
            prev=old[paired[i]] if i in paired else None
            children.append(node((child['material_id'],child['history_version']),
                                 (prev['material_id'],prev['history_version']) if prev else None,child,prev,
                                 added or (prior is not None and prev is None),deleted,i in reordered,
                                 path|{key},old_path|({old_key} if old_key else set())))
        for j in sorted(missing):
            prev=old[j]
            children.append(node((prev['material_id'],prev['history_version']),edge=prev,deleted=True,path=old_path|{old_key}))
        return dict(record=record,previous=prior,edge=edge,old_edge=old_edge,added=added,deleted=deleted,moved=moved,
                    fields=fields,columns=changed,alternatives=alt,children=children,
                    old_alternatives=[read((a['material_id'],a['history_version'])) for a in old_edge.get('alternates',[])])
    root=node((mid,version),(mid,previous) if previous is not None else None)
    # The first available version is a baseline, not an entirely added BOM.
    if previous is None:
        def clear(n):
            for a in n['alternatives']:a['state']=''
            for child in n['children']:clear(child)
        clear(root)
    return root,previous
