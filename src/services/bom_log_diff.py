"""Pair persisted edges across unambiguous material code revision migrations."""
def pair_edges(old, after, material, revisions=None):
    mapping=dict(revisions or {})
    def identity(mid):
        value=material(mid)
        return value.get('base_code'),value.get('version')
    # Discover explicit same-base replacements under the same logical parent.
    # Never merge two ambiguous occurrences or unrelated branches by name.
    changed=True
    while changed:
        changed=False
        for key in old:
            parent,child,position=key
            parent=mapping.get(parent,parent)
            if child in mapping or (parent,child,position) in after:continue
            base,version=identity(child)
            candidates=[k for k in after if k[0]==parent and k[2]==position
                        and identity(k[1])[0]==base and identity(k[1])[1]!=version
                        and k[1] not in mapping.values()
                        and not any((mapping.get(p,p),c,pos)==k for p,c,pos in old)]
            sources=[k for k in old if mapping.get(k[0],k[0])==parent and k[2]==position
                     and identity(k[1])[0]==base and (parent,k[1],position) not in after]
            if len(candidates)==len(sources)==1:
                mapping[child]=candidates[0][1];changed=True
    remaining=set(after);pairs=[]
    # A physical migration may retain the old public subtree for another owner.
    # Prefer exact matches so its retained edges are not paired away.
    for key,before in old.items():
        normalized=(mapping.get(key[0],key[0]),mapping.get(key[1],key[1]),key[2])
        target=key if key in remaining else normalized if normalized in remaining else None
        if target is None:
            candidates=[k for k in remaining if k[:2]==normalized[:2] and k not in old]
            sources=[k for k in old if (mapping.get(k[0],k[0]),mapping.get(k[1],k[1]))==normalized[:2] and k not in after]
            if len(candidates)==len(sources)==1:target=candidates[0]
        if target is not None:remaining.remove(target)
        pairs.append((key,before,target,after.get(target)))
    pairs.extend((key,None,key,after[key]) for key in after if key in remaining)
    return pairs
