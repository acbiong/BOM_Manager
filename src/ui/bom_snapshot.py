"""Detached comparison snapshot of an unsaved editor, shared by local and remote views."""
from PyQt5.QtCore import Qt
from infrastructure.operation_progress import checkpoint

def draft_snapshot(window):
    material_cache={};alternate_cache={}
    def material(mid):
        if mid not in material_cache:material_cache[mid]={**window.svc.material_snapshot(mid),**getattr(window,'_material_edits',{}).get(mid,{})}
        return material_cache[mid]
    def node(item,parent=None,path=()):
        data=dict(item.data(0,Qt.UserRole) or {})
        mid=data.get('material_id',window.root)
        result=dict(data);result.update(material(mid))
        for key in ('quantity','position','remark'):
            checkpoint()
            if key in data:result[key]=data[key]
        if parent:
            key=window.alternate_key(item)
            if key not in alternate_cache:alternate_cache[key]=window.alternate_ids(item)
            ids=alternate_cache[key]
        else:ids=[]
        alternatives=[material(i) for i in ids]
        result.update(material_id=mid,children=[],alternate_ids=frozenset(ids),alternate_codes=frozenset((a['base_code'],a['version']) for a in alternatives),
            alternates='\n'.join(sorted(' | '.join(str(a.get(k) or '') for k in ('base_code','version','name','description','manufacturer','mpn')) for a in alternatives)),
            level=len(path),parent_code=(str(parent['base_code'])+str(parent['version'])) if parent else 'ROOT',_material_path=path)
        if parent is None:result['quantity']=1
        for i in range(item.childCount()):
            checkpoint()
            child=item.child(i);d=child.data(0,Qt.UserRole) or {}
            if not d.get('_deleted'):result['children'].append(node(child,result,path+(d['material_id'],)))
        return result
    return node(window.root_item)
