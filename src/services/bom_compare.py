"""Read-only, parent-local comparison of saved SKU/mirror graphs."""
from difflib import SequenceMatcher
from dataclasses import dataclass

FIELDS = [('level','层级'),('serial','序号'),('parent_code','父项物料编码'),('base_code','物料编码'),('version','版本号'),('name','物料名称'),
          ('description','规格'),('quantity','用量'),('unit','单位'),('grade','物料等级'),
          ('manufacturer','制造商'),('mpn','MPN'),('mp_flag','M/P'),
          ('position','物料位置'),('remark','备注'),('alternates','替代料')]

@dataclass
class Difference:
    left: object
    right: object
    depth: int
    status: str
    changed: tuple = ()

def snapshot(service, sku):
    scoped = service.for_sku(sku['id'])
    root = dict(scoped.material_snapshot(sku['material_id']))
    root.update(material_id=sku['material_id'], quantity=1, children=[], alternates='', alternate_ids=frozenset(), level=0, serial='1', parent_code='ROOT')
    nodes = {None: root}
    alternate_cache = {}
    for source in scoped.bom(sku['material_id']):
        row = dict(source)
        if row['id'] not in alternate_cache:
            alternatives=[dict(x) for x in scoped.alternates(row['id'])]
            alternate_cache[row['id']] = ('\n'.join(sorted(
                ' | '.join(str(a.get(k) or '') for k in
                           ('base_code','version','name','description','manufacturer','mpn'))
                for a in alternatives)),frozenset(a['material_id'] for a in alternatives))
        row.update(children=[], alternates=alternate_cache[row['id']][0], alternate_ids=alternate_cache[row['id']][1])
        parent = nodes[row['parent_node_id']]
        row.update(serial=parent['serial']+'.'+str(len(parent['children'])+1), level=parent['level']+1, parent_code=str(parent['base_code'])+str(parent['version']))
        parent['children'].append(row)
        nodes[row['node_id']] = row
    return root

def value(node, field):
    raw = node.get(field)
    return f'{float(raw or 0):.1f}' if field == 'quantity' else str(raw if raw is not None else '')

def is_exchange(left,right):
    """A reciprocal main/alternate change, not merely an alternate addition."""
    return (left['material_id']!=right['material_id']
            and right['material_id'] in left.get('alternate_ids',())
            and left['material_id'] in right.get('alternate_ids',()))

def align_children(left, right):
    """Keep identity anchors; align replacements inside the intervening sibling gaps.

    Matching never crosses a parent boundary. Existing identities still match after
    reordering; positional replacement is only used for otherwise unmatched rows.
    """
    pairs = {}; unused = set(range(len(right)))
    for i,node in enumerate(left):
        j = next((j for j in sorted(unused) if right[j]['material_id']==node['material_id']),None)
        if j is not None:pairs[i]=j;unused.remove(j)
    # Explicit reciprocal main/alternate identities outrank names or positions.
    for i,node in enumerate(left):
        if i in pairs:continue
        matches=[j for j in unused if is_exchange(node,right[j])]
        if matches:
            j=min(matches,key=lambda j:(abs(i-j),j));pairs[i]=j;unused.remove(j)
    # Exact versions have already matched. Pair remaining versions by base code,
    # even when several versions of the same material occur under one parent.
    for i,node in enumerate(left):
        if i in pairs:continue
        matches=[j for j in unused if right[j]['base_code']==node['base_code']]
        if matches:
            j=min(matches,key=lambda j:(abs(i-j),j))
            pairs[i]=j;unused.remove(j)
    # Similar names align for inspection, but never establish material identity.
    candidates=[]
    for i,node in enumerate(left):
        if i in pairs:continue
        name=''.join(str(node.get('name','')).casefold().split())
        if not name:continue
        for j in unused:
            other=''.join(str(right[j].get('name','')).casefold().split())
            score=SequenceMatcher(None,name,other,autojunk=False).ratio()
            if score>=0.6:candidates.append((-score,abs(i-j),i,j))
    for _,_,i,j in sorted(candidates):
        if i not in pairs and j in unused:pairs[i]=j;unused.remove(j)
    reverse={j:i for i,j in pairs.items()}
    # Unique tokens prevent incidental identical text from pairing different branches.
    blocks=SequenceMatcher(None,list(range(len(left))),
                           [reverse.get(j,('new',j)) for j in range(len(right))],
                           autojunk=False).get_matching_blocks()
    li=ri=0
    for block in blocks:
        missing_left=[i for i in range(li,block.a) if i not in pairs]
        missing_right=[j for j in range(ri,block.b) if j in unused]
        for i,j in zip(missing_left,missing_right):pairs[i]=j;unused.remove(j)
        li=block.a+block.size;ri=block.b+block.size
    pending=sorted(unused);cursor=0
    for i,node in enumerate(left):
        j=pairs.get(i)
        if j is not None:
            while cursor<len(pending) and pending[cursor]<j:
                yield None,right[pending[cursor]];cursor+=1
        yield node,right[j] if j is not None else None
    for j in pending[cursor:]:yield None,right[j]

def compare_boms(service, left_id, right_id):
    skus = {s['id']: dict(s) for s in service.skus()}
    if left_id not in skus or right_id not in skus:
        raise ValueError('所选SKU或镜像已不存在，请重新选择。')
    result = []
    def visit(left, right, depth, serial):
        # Number aligned display slots, not original BOM positions. Only detached
        # snapshot dictionaries are changed; no database or editor state is written.
        if left is not None:left['serial']=serial
        if right is not None:right['serial']=serial
        changed = tuple(key for key, _ in FIELDS if key not in ('parent_code','serial') and left and right and value(left,key) != value(right,key))
        status = 'added' if left is None else 'deleted' if right is None else 'exchanged' if is_exchange(left,right) else 'replaced' if left['base_code']!=right['base_code'] else 'modified' if changed else 'same'
        result.append(Difference(left,right,depth,status,changed))
        ls = left['children'] if left else []
        rs = right['children'] if right else []
        for index,(l,r) in enumerate(align_children(ls,rs),1):
            visit(l,r,depth+1,serial+'.'+str(index))
    visit(snapshot(service,skus[left_id]),snapshot(service,skus[right_id]),0,'1')
    return result
