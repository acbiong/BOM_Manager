"""Read-only, parent-local comparison of saved SKU/mirror graphs."""
from collections import Counter
from dataclasses import dataclass

FIELDS = [('base_code','物料编码'),('version','版本号'),('name','物料名称'),
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
    root.update(material_id=sku['material_id'], quantity=1, children=[], alternates='')
    nodes = {None: root}
    alternate_cache = {}
    for source in scoped.bom(sku['material_id']):
        row = dict(source)
        if row['id'] not in alternate_cache:
            alternate_cache[row['id']] = '\n'.join(sorted(
                ' | '.join(str(a.get(k) or '') for k in
                           ('base_code','version','name','description','manufacturer','mpn'))
                for a in (dict(x) for x in scoped.alternates(row['id']))))
        row.update(children=[], alternates=alternate_cache[row['id']])
        nodes[row['parent_node_id']]['children'].append(row)
        nodes[row['node_id']] = row
    return root

def value(node, field):
    raw = node.get(field)
    return f'{float(raw or 0):.1f}' if field == 'quantity' else str(raw or '')

def compare_boms(service, left_id, right_id):
    skus = {s['id']: dict(s) for s in service.skus()}
    if left_id not in skus or right_id not in skus:
        raise ValueError('所选SKU或镜像已不存在，请重新选择。')
    result = []
    def visit(left, right, depth):
        changed = tuple(key for key, _ in FIELDS if left and right and value(left,key) != value(right,key))
        status = 'added' if left is None else 'deleted' if right is None else 'modified' if changed else 'same'
        result.append(Difference(left,right,depth,status,changed))
        ls = left['children'] if left else []
        rs = right['children'] if right else []
        # Exact identity first; only unambiguous version changes are paired by base code.
        pairs = {}; unused = set(range(len(rs)))
        for i,l in enumerate(ls):
            j = next((j for j in sorted(unused) if rs[j]['material_id']==l['material_id']),None)
            if j is not None:pairs[i]=j;unused.remove(j)
        lc = Counter(l['base_code'] for i,l in enumerate(ls) if i not in pairs)
        rc = Counter(rs[j]['base_code'] for j in unused)
        for i,l in enumerate(ls):
            if i not in pairs and lc[l['base_code']]==rc[l['base_code']]==1:
                j=next(j for j in unused if rs[j]['base_code']==l['base_code'])
                pairs[i]=j;unused.remove(j)
        for i,l in enumerate(ls):visit(l,rs[pairs[i]] if i in pairs else None,depth+1)
        for j in sorted(unused):visit(None,rs[j],depth+1)
    visit(snapshot(service,skus[left_id]),snapshot(service,skus[right_id]),0)
    return result
