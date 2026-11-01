"""Read-only, content-based preview against this SKU's bound history.

Incoming relationships are not part of a material's sub-BOM. History numbers
and row order alone do not establish a content change. Alternate structures
are traversed with cycle protection, just as in history_state.
"""
import json
from services import material_history as history
from services.history_state import Reader
from domain.quantity import format_quantity

FIELDS = dict(zip(history.FIELDS, ('基础编码', '物料版本号', '名称', '规格描述',
                                  '单位', '物料等级', '制造商', 'MPN', 'M/P')))


def compare(service, mid, rows, edits=None):
    reader = Reader(service)
    old_nodes, old_roots = json.loads(reader.state(service, mid))
    new_nodes, new_roots = json.loads(reader.state(service, mid, rows, edits))
    changes = []

    def label(nodes, index):
        attrs = nodes[index][1]
        return attrs[0] + attrs[1] + ' ' + attrs[2]

    def add(path, field, before, after, kind='修改'):
        changes.append(dict(path=path, field=field, before=str(before),
                            after=str(after), kind=kind))

    def edge_text(nodes, edge):
        alts = '、'.join(label(nodes, i) for i in edge[6]) or '无'
        return (f'{label(nodes, edge[5])}\n数量：{format_quantity(edge[1])}；单位：{edge[2]}'
                f'\n位置：{edge[3] or "（空）"}；备注：{edge[4] or "（空）"}\n替代料：{alts}')

    def whole_edge(nodes, edge, path, added, active=frozenset()):
        value = edge_text(nodes, edge)
        add(path, '子物料', '' if added else value, value if added else '',
            '新增' if added else '删除')
        index = edge[5]
        if index in active:
            return
        for child in nodes[index][2]:
            whole_edge(nodes, child, path + ' / ' + label(nodes, child[5]),
                       added, active | {index})

    def walk(a, b, path, active):
        if (a, b) in active:
            return
        active = active | {(a, b)}
        old, new = old_nodes[a], new_nodes[b]
        for i, (key, title) in enumerate(FIELDS.items()):
            if old[1][i] != new[1][i]:
                add(path, title, old[1][i], new[1][i])
        # Match all exact positions first, then pair remaining occurrences of
        # the same material so moving a position shows both values clearly.
        remaining = set(range(len(old[2])))
        pairs = {}
        for exact in (True, False):
            for i, edge in enumerate(new[2]):
                if i in pairs:
                    continue
                j = next((j for j in sorted(remaining) if old[2][j][0] == edge[0]
                          and (not exact or old[2][j][3] == edge[3])), None)
                if j is not None:
                    pairs[i] = j
                    remaining.remove(j)
        for i, edge in enumerate(new[2]):
            child_path = path + ' / ' + label(new_nodes, edge[5])
            if edge[3]:
                child_path += '（位置：' + edge[3] + '）'
            if i not in pairs:
                whole_edge(new_nodes, edge, child_path, True)
                continue
            before = old[2][pairs[i]]
            for col, title in ((1, '数量'), (2, '单位'), (3, '位置'), (4, '备注')):
                if before[col] != edge[col]:
                    fmt = format_quantity if col == 1 else str
                    add(child_path, title, fmt(before[col]), fmt(edge[col]))
            old_alts = {old_nodes[x][0]: x for x in before[6]}
            new_alts = {new_nodes[x][0]: x for x in edge[6]}
            for aid in sorted(old_alts.keys() | new_alts.keys()):
                if aid not in old_alts:
                    add(child_path, '替代料', '', label(new_nodes, new_alts[aid]), '新增')
                elif aid not in new_alts:
                    add(child_path, '替代料', label(old_nodes, old_alts[aid]), '', '删除')
                else:
                    walk(old_alts[aid], new_alts[aid], child_path + ' / 替代料：' +
                         label(new_nodes, new_alts[aid]), active)
            walk(before[5], edge[5], child_path, active)
        for j in sorted(remaining):
            edge = old[2][j]
            whole_edge(old_nodes, edge, path + ' / ' + label(old_nodes, edge[5]), False)

    old_root, new_root = old_roots[0][0], new_roots[0][0]
    walk(old_root, new_root, label(new_nodes, new_root), set())
    return dict(version=reader.bound(service).get(mid), changes=changes)
