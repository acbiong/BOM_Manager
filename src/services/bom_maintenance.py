"""Reachability-based BOM audit and cleanup; never delete material master/history."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from services.mirrors import table_name


def actual_material_usage(service,material_id):
    primary=getattr(service,'primary',service);result=[];seen=set()
    def label(mid):
        material=primary.material_snapshot(mid)
        return material.get('base_code','')+material.get('version','')+' '+material.get('name','')
    for sku in primary.skus():
        scoped=primary.for_sku(sku['id'])
        sku_label=f"{sku['base_code']}{sku['version']} {sku['name']} 镜像{sku['mirror_version']}"
        if sku['material_id']==material_id:
            result.append(dict(sku_id=sku['id'],sku=sku_label,parent='SKU根节点（无父级）'))
        alternatives={r[0] for r in scoped.db.conn.execute('SELECT bom_item_id FROM alternates WHERE material_id=?',(material_id,))}
        _,reachable_ids=reachable_relations(scoped.db.conn,'material_bom_items','alternates',[sku['material_id']])
        for row in scoped.db.conn.execute('SELECT id,parent_material_id,child_material_id AS material_id FROM material_bom_items ORDER BY sort_no,id'):
            if row['id'] not in reachable_ids:continue
            alternate=row['id'] in alternatives
            if row['material_id']!=material_id and not alternate:continue
            key=(sku['id'],row['parent_material_id'],row['material_id'] if alternate else None)
            if key in seen:continue
            seen.add(key)
            parent_label=label(row['parent_material_id'])
            if alternate:parent_label+='（作为 '+label(row['material_id'])+' 的替代料）'
            result.append(dict(sku_id=sku['id'],sku=sku_label,parent=parent_label,parent_id=row['parent_material_id'],focus_material_id=row['material_id']))
    return result


def reachable_relations(conn,relations_table,alternates_table,roots):
    graph={};alternates={}
    for row in conn.execute(f'SELECT id,parent_material_id,child_material_id FROM {relations_table}'):
        graph.setdefault(row[1],[]).append((row[0],row[2]))
    for row in conn.execute(f'SELECT bom_item_id,material_id FROM {alternates_table}'):
        alternates.setdefault(row[0],[]).append(row[1])
    seen=set();relations=set();pending=list(roots)
    while pending:
        mid=pending.pop()
        if mid in seen:continue
        seen.add(mid)
        for rid,child in graph.get(mid,[]):
            relations.add(rid);pending.append(child);pending.extend(alternates.get(rid,()))
    return seen,relations


def cleanup_orphan_boms(primary,backup=False,compact=False):
    """Remove only rows unreachable from any SKU mirror; compact outside transactions."""
    db=primary.db;conn=db.conn;scopes=[];public_roots=set()
    for sku in primary.skus():
        if not sku['scope_id']:
            public_roots.add(sku['material_id']);continue
        table=table_name(sku['id'],'material_bom_items');alts=table_name(sku['id'],'alternates')
        used,relations=reachable_relations(conn,table,alts,[sku['material_id']])
        scopes.append((sku['id'],table,alts,used,relations))
        public_roots.update(used)
    used,relations=reachable_relations(conn,'material_bom_items','alternates',public_roots)
    scopes.append((0,'material_bom_items','alternates',used,relations))
    removals=[]
    for sid,table,alts,used,relations in scopes:
        orphan_ids=[r[0] for r in conn.execute(f'SELECT id FROM {table}') if r[0] not in relations]
        orphan_alts=[r[0] for r in conn.execute(f'SELECT id,bom_item_id FROM {alts}') if r[1] not in relations]
        legacy=table_name(sid,'bom_items') if sid else 'bom_items'
        legacy_count=conn.execute(f'SELECT COUNT(*) FROM {legacy}').fetchone()[0]
        captured=[r[0] for r in conn.execute('SELECT material_id FROM mirror_captured_materials WHERE sku_id=?',(sid,)) if r[0] not in used] if sid else []
        if orphan_ids or orphan_alts or legacy_count or captured:removals.append((sid,table,alts,legacy,used,orphan_ids,orphan_alts,legacy_count,captured))
    report=dict(relations=0,alternates=0,legacy_rows=0,captured=0,compacted=False)
    if not removals:return report
    if backup and db.path!=':memory:':
        path=Path(str(db.path)+'.pre-orphan-cleanup-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
        destination=sqlite3.connect(str(path))
        try:conn.backup(destination)
        finally:destination.close()
        report['backup']=str(path)
    with db.transaction():
        for sid,table,alts,legacy,used,orphan_ids,orphan_alts,legacy_count,captured in removals:
            conn.executemany(f'DELETE FROM {alts} WHERE id=?',[(rid,) for rid in orphan_alts])
            conn.executemany(f'DELETE FROM {table} WHERE id=?',[(rid,) for rid in orphan_ids])
            conn.execute(f'DELETE FROM {legacy}')
            if sid:
                conn.executemany('DELETE FROM mirror_captured_materials WHERE sku_id=? AND material_id=?',[(sid,mid) for mid in captured])
                conn.execute('DELETE FROM bom_revision_legacy_conflicts WHERE sku_id=? AND material_id NOT IN (SELECT material_id FROM mirror_captured_materials WHERE sku_id=?)',(sid,sid))
                primary.for_sku(sid).refresh_usage()
            report['relations']+=len(orphan_ids);report['alternates']+=len(orphan_alts);report['legacy_rows']+=legacy_count;report['captured']+=len(captured)
        conn.execute('UPDATE materials SET has_bom=EXISTS(SELECT 1 FROM material_bom_items WHERE parent_material_id=materials.id)')
    if compact and (report['relations'] or report['alternates'] or report['legacy_rows']) and db.path!=':memory:' and not conn.in_transaction:
        report['bytes_before']=Path(db.path).stat().st_size
        try:
            conn.execute('VACUUM');conn.execute('PRAGMA optimize');report['compacted']=True
        except sqlite3.DatabaseError as error:report['compact_error']=str(error)
        report['bytes_after']=Path(db.path).stat().st_size
    with db.transaction():
        conn.execute('INSERT INTO app_metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('last_orphan_cleanup',json.dumps(report,ensure_ascii=False)))
    return report
