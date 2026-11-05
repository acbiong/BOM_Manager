"""Read-only import gate against current catalog definitions, not SKU caches."""
from collections import defaultdict
from infrastructure.operation_progress import checkpoint
from domain.quantity import format_quantity


def validate(service,root,rows,source_lines=None):
    from services.services import BomImportError
    from services.current_catalog import groups
    from services import material_history as history
    source_lines=source_lines or {}
    primary=getattr(service,'primary',service)
    system=groups(primary)
    materials={r['id']:dict(r) for r in primary.db.conn.execute('SELECT * FROM materials')}
    # A newly created SKU namespace often has no captured sub-BOM. The catalog's
    # current immutable definition remains authoritative even if its edge cache
    # is empty/outdated. Do not compare to MAX(history_version).
    if history.enabled(primary):
        import json
        for record in history.connection(primary).execute('SELECT h.* FROM material_histories h JOIN material_history_current c ON c.material_id=h.material_id AND c.history_version=h.history_version'):
            mid=record['material_id'];materials.setdefault(mid,json.loads(record['attributes']))
            system[mid]=[dict(edge,alternate_material_ids=[a['material_id'] for a in edge.get('alternates',[])]) for edge in json.loads(record['children'])]
    # Existing leaf definitions referenced by another main BOM are definitions
    # too; adding children to them cannot bypass the identity check.
    if history.enabled(primary):
        defined={r['material_id'] for r in history.main_bindings(primary)}
    else:
        defined={r['material_id'] for values in system.values() for r in values}
    incoming={root:[]}
    for row in rows:
        incoming.setdefault(row['parent_material_id'],[]).append(row)
        incoming.setdefault(row['material_id'],[])  # Explicit leaf, not "reuse system subtree".
    def label(mid):
        material=materials.get(mid,{})
        return material.get('base_code',str(mid))+material.get('version','')+' '+material.get('name','')
    def signature(row):
        return (float(row['quantity']),row.get('unit') or '',row.get('position') or '',row.get('remark') or '',tuple(sorted(row.get('alternate_material_ids',[]))))
    def display(row,field):
        value=signature(row)[field]
        if field==0:return format_quantity(value)
        if field==4:return '、'.join(label(mid) for mid in value) or '无'
        return value or '（空）'
    def description(row):
        return '存在；'+'；'.join(title+'：'+display(row,i) for i,title in enumerate(('数量','单位','位置','备注','替代料')))
    differences=[]
    for parent,new_rows in incoming.items():
        checkpoint()
        old_rows=system.get(parent,[])
        # An undefined/new material may acquire its first sub-BOM through import.
        if not old_rows and (parent not in defined or parent==root):continue
        old_by=defaultdict(list);new_by=defaultdict(list)
        for row in old_rows:old_by[row['material_id']].append(row)
        for row in new_rows:new_by[row['material_id']].append(row)
        def add(mid,field,left,right):
            differences.append(dict(comparison_kind='system_import',parent=label(parent),material=label(mid),field=field,
                left_path='系统物料库当前子BOM / '+label(parent),right_path='待导入子BOM / '+label(parent),
                left_line=None,right_line=source_lines.get((parent,mid)),left=left,right=right,left_note='数据库记录'))
        for mid in sorted(old_by.keys()|new_by.keys()):
            old=sorted(old_by[mid],key=signature);new=sorted(new_by[mid],key=signature)
            # Remove exact matches before pairing changed occurrences.
            for row in list(new):
                match=next((r for r in old if signature(r)==signature(row)),None)
                if match is not None:old.remove(match);new.remove(row)
            for left,right in zip(old,new):
                for index,title in enumerate(('数量','单位','位置','备注','替代料')):
                    if signature(left)[index]!=signature(right)[index]:add(mid,title,display(left,index),display(right,index))
            for row in old[len(new):]:add(mid,'子物料存在性',description(row),'不存在')
            for row in new[len(old):]:add(mid,'子物料存在性','不存在',description(row))
    if differences:
        raise BomImportError(['相同物料编码及版本号的子BOM不一致，禁止导入。请修正文件或使用新的物料版本，不允许覆盖系统结构。']+
            [f"{d['parent']} / {d['material']}：{d['field']}；系统：{d['left']}；导入：{d['right']}" for d in differences],differences)
    return rows
