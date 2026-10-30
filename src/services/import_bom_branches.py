"""Validate repeated *occurrences* before reducing an expanded tree to shared edges."""
from collections import defaultdict
from infrastructure.operation_progress import checkpoint
from domain.quantity import format_quantity


def normalize_branches(rows, root, materials, issues, hierarchical=False, root_level=None, comparisons=None):
    comparisons = comparisons if comparisons is not None else []
    repeated = len({(r['parent_material_id'], r['material_id']) for r in rows}) != len(rows)
    def clean(row):return {k:v for k,v in row.items() if not k.startswith('_import_')}
    if not hierarchical and not repeated:return [clean(r) for r in rows]
    def label(mid):
        material=materials[mid]
        return material['base_code']+material['version']+' '+material['name']
    base=root_level if root_level is not None else (rows[0].get('_import_level',1)-1 if rows else 0)
    origin=dict(mid=root,line=0,level=base,children=[],path=label(root))
    stack=[origin];occurrences=defaultdict(list)
    for row in rows:
        checkpoint()
        line=row['_import_line'];pid=row['parent_material_id'];mid=row['material_id']
        if hierarchical:
            depth=row['_import_level']
            while len(stack)>1 and stack[-1]['level']>=depth:stack.pop()
            parent=stack[-1]
            if parent['level']!=depth-1 or parent['mid']!=pid:
                issues.append(f'第{line}行层级与父项编码不匹配，不能确定祖先分支：{label(pid)} → {label(mid)}')
                continue
        else:
            while len(stack)>1 and stack[-1]['mid']!=pid:stack.pop()
            parent=stack[-1];depth=parent['level']+1
            if parent['mid']!=pid:
                issues.append(f'第{line}行重复子BOM无法确定所属祖先分支，请按树顺序排列并提供“层级”列')
                continue
        same=next((n for n in parent['children'] if n['mid']==mid),None)
        if same:
            issues.append(f"第{line}行同一父级重复包含相同物料（首次出现于第{same['line']}行）；分支：{parent['path']}")
        node=dict(mid=mid,line=line,level=depth,row=row,children=[],path=parent['path']+' / '+label(mid))
        parent['children'].append(node);occurrences[mid].append(node);stack.append(node)
    def signature(node):
        row=node['row']
        return (float(row['quantity']),row.get('position','') or '',row.get('remark','') or '',tuple(sorted(row.get('alternate_material_ids',[]))))
    def value(sig,index):
        if index==0:return format_quantity(sig[index])
        if index==3:return '、'.join(label(mid) for mid in sig[index]) or '无'
        return sig[index] or '（空）'
    # Compare every repeated parent's complete immediate definition. Doing this
    # for all descendants checks the full subtree without including the parent's
    # own quantity/position under different ancestors, which may legitimately differ.
    for mid,nodes in occurrences.items():
        if len(nodes)<2:continue
        first=nodes[0];old={n['mid']:n for n in first['children']}
        for other in nodes[1:]:
            checkpoint()
            new={n['mid']:n for n in other['children']}
            for child in sorted(set(old)|set(new)):
                a=old.get(child);b=new.get(child)
                prefix=(f"子BOM不一致，禁止导入：{label(mid)}；分支一（第{first['line']}行）：{first['path']}；"
                        f"分支二（第{other['line']}行）：{other['path']}；子物料：{label(child)}；")
                context=dict(parent=label(mid),material=label(child),left_path=first['path'],right_path=other['path'],
                             left_line=a['line'] if a else None,right_line=b['line'] if b else None)
                if a is None or b is None:
                    comparisons.append(dict(context,field='子物料存在性',left='不存在' if a is None else '存在',right='不存在' if b is None else '存在'))
                    issues.append(prefix+('分支一缺少子物料，分支二第'+str(b['line'])+'行存在' if a is None else '分支二缺少子物料，分支一第'+str(a['line'])+'行存在'))
                    continue
                sa,sb=signature(a),signature(b)
                for i,field in enumerate(('数量','位置','备注','替代料')):
                    if sa[i]!=sb[i]:comparisons.append(dict(context,field=field,left=value(sa,i),right=value(sb,i)))
                differences=[f'{field}：{value(sa,i)} → {value(sb,i)}' for i,field in enumerate(('数量','位置','备注','替代料')) if sa[i]!=sb[i]]
                if differences:issues.append(prefix+f"第{a['line']}行 / 第{b['line']}行："+'；'.join(differences))
    # Stable first occurrence order; store each shared definition once. Preview
    # expansion will still render the subtree beneath every ancestor branch.
    result=[];seen=set()
    for row in rows:
        key=(row['parent_material_id'],row['material_id'])
        if key not in seen:result.append(clean(row));seen.add(key)
    return result
