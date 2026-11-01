"""Read-only content comparison of proposed materials and incoming alternates.

Node pairs are compared with a visited set, including alternate cycles. History
numbers, owner IDs and ordering do not establish content differences.
"""
import json
from services import material_history as history


class Reader:
    def __init__(self,service):
        self.service=service;self.records={};self.bindings={}

    def bound(self,service):
        sid=getattr(service,'sku_id',None)
        if sid not in self.bindings:
            self.bindings[sid]={r['material_id']:r['history_version'] for r in history.connection(service).execute(
                'SELECT material_id,history_version FROM material_history_bindings WHERE sku_id=?',(sid,))}
        return self.bindings[sid]

    def record(self,mid,version):
        key=(mid,version)
        if key not in self.records:self.records[key]=history.read(self.service,mid,version)
        return self.records[key]

    def state(self,service,mid,rows=None,edits=None):
        bound=self.bound(service);graph=None;edits=edits or {};nodes=[];indices={}
        if rows is not None:
            from services.bom_role_swap import draft_groups
            root=service.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(service.sku_id,)).fetchone()[0]
            graph=draft_groups(root,rows)
            incoming=[r for children in graph.values() for r in children if r['material_id']==mid]
        else:
            # Captured but detached subtrees are not usages in this SKU.
            incoming=[dict(r) for r in service.db.conn.execute(
                'SELECT id FROM material_bom_items WHERE child_material_id=? AND '
                '(parent_material_id=(SELECT material_id FROM skus WHERE id=?) OR EXISTS '
                '(SELECT 1 FROM mirror_material_usage u WHERE u.sku_id=? AND u.role="main" '
                'AND u.material_id=material_bom_items.parent_material_id))',
                (mid,service.sku_id,service.sku_id))]
            alternatives=service.alternate_groups([r['id'] for r in incoming])
            for r in incoming:r['alternate_material_ids']=[a['material_id'] for a in alternatives[r['id']]]

        def version(material):
            value=bound.get(material)
            return value if value is not None else history.current_version(history.connection(service),material)

        def visit(material,revision=None,draft=False):
            key=(material,revision,draft)
            if key in indices:return indices[key]
            index=len(nodes);indices[key]=index;nodes.append(None)
            record=self.record(material,revision) if revision is not None else None
            attrs=dict(record['attributes']) if record else service.material_snapshot(material)
            if draft:attrs.update(edits.get(material,{}))
            use_draft=draft is True and graph is not None and material in graph
            children=graph[material] if use_draft else record['children'] if record else []
            edges=[]
            for row in children:
                child=row['material_id']
                child_version=version(child) if use_draft else row['history_version']
                child_ref=visit(child,child_version,use_draft)
                alts=row.get('alternate_material_ids',[]) if use_draft else row.get('alternates',[])
                alternate_refs=[]
                for alt in sorted(alts,key=lambda a:a if use_draft else a['material_id']):
                    aid=alt if use_draft else alt['material_id']
                    av=version(aid) if use_draft else alt['history_version']
                    # An alternate's own structure remains its bound historical
                    # structure; edits to its attributes still apply in drafts.
                    alternate_refs.append(visit(aid,av,'attributes' if use_draft and aid in edits else False))
                edges.append([child,float(row['quantity']),edits.get(child,{}).get('unit',row['unit']) if use_draft else row['unit'],
                              row.get('position') or '',row.get('remark') or '',child_ref,alternate_refs])
            edges.sort(key=lambda e:(e[0],e[3],e[1],e[2],e[4]))
            nodes[index]=[material,[attrs.get(k,'') or '' for k in history.FIELDS],edges]
            return index

        main=visit(mid,version(mid),graph is not None)
        occurrences=[]
        for row in incoming:
            refs=[visit(a,version(a),'attributes' if a in edits else False) for a in row['alternate_material_ids']]
            occurrences.append([main,sorted(refs,key=lambda i:nodes[i][0])])
        # SKU roots have no incoming relationship or incoming alternates.
        if not occurrences:occurrences=[[main,[]]]
        return json.dumps([nodes,occurrences],ensure_ascii=False,separators=(',',':'))


def matches(proposed,existing):
    """Every target occurrence must already match a proposed occurrence."""
    left,expected=json.loads(proposed);right,actual=json.loads(existing)
    def same_node(a,b,seen):
        if (a,b) in seen:return True
        seen.add((a,b));x,y=left[a],right[b]
        if x[:2]!=y[:2] or len(x[2])!=len(y[2]):return False
        for u,v in zip(x[2],y[2]):
            if u[:5]!=v[:5] or len(u[6])!=len(v[6]):return False
            if not same_node(u[5],v[5],seen):return False
            if not all(same_node(i,j,seen) for i,j in zip(u[6],v[6])):return False
        return True
    def same(a,b):
        seen=set()
        return len(a[1])==len(b[1]) and same_node(a[0],b[0],seen) and all(same_node(i,j,seen) for i,j in zip(a[1],b[1]))
    return all(any(same(a,b) for a in expected) for b in actual)


def equivalent(a,b):return matches(a,b) and matches(b,a)


def pending(service,mid,rows,edits=None):return Reader(service).state(service,mid,rows,edits)


def matching_skus(service,mid,comparison,refs):
    if comparison is None:return frozenset()
    reader=Reader(service);primary=getattr(service,'primary',service)
    return frozenset(s['id'] for s in refs if matches(comparison,reader.state(primary.for_sku(s['id']),mid)))
