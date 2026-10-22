"""Atomic protection of locked SKU snapshots, including shared material metadata."""
from collections import defaultdict

class LockedBomError(ValueError):
 def __init__(self,details):
  self.details=details
  super().__init__('下列BOM已被锁定，请解除锁定后再进行编辑：\n'+'\n'.join(f"{d['sku']} | 物料：{d['material']} | 父项物料：{d['parent']}" for d in details))

def locked_snapshots(conn,ids=None):
 rows=conn.execute('SELECT * FROM skus WHERE locked=1').fetchall() if ids is None else conn.execute('SELECT * FROM skus WHERE id IN ('+','.join('?' for _ in ids)+')',tuple(ids)).fetchall()
 if not rows:return {}
 fields=('base_code','version','name','description','unit','grade','manufacturer','mpn','mp_flag')
 materials={r['id']:tuple(r[k] for k in fields) for r in conn.execute('SELECT * FROM materials')}
 result={}
 for sku in rows:
  prefix=f"mirror_{sku['scope_id']}_" if sku['scope_id'] else ''
  graph=defaultdict(list);alts=defaultdict(list)
  for a in conn.execute('SELECT * FROM '+prefix+'alternates ORDER BY sort_no,id'):alts[a['bom_item_id']].append((a['material_id'],a['sort_no']))
  for r in conn.execute('SELECT * FROM '+prefix+'material_bom_items'):graph[r['parent_material_id']].append(dict(r))
  seen=set();pending=[sku['material_id']];edges={};uses=set();used={}
  while pending:
   parent=pending.pop()
   if parent in seen:continue
   seen.add(parent);used[parent]=materials.get(parent)
   for rank,r in enumerate(sorted(graph[parent],key=lambda r:(r['sort_no'],r['id']))):
    child=r['child_material_id'];alternates=tuple((mid,index) for index,(mid,_) in enumerate(alts[r['id']]));key=(parent,child)
    edges.setdefault(key,[]).append((r['quantity'],r['unit'],r['position'],r['remark'],rank,alternates))
    uses.add((child,parent));pending.append(child)
    for alternate,_ in alternates:uses.add((alternate,parent));pending.append(alternate)
  colors={(r['parent_id'],r['material_id']):r['color'] for r in conn.execute('SELECT * FROM bom_row_colors WHERE scope_id=?',(sku['scope_id'],)) if (r['parent_id'],r['material_id']) in edges or (r['parent_id']==0 and r['material_id']==sku['material_id'])}
  result[sku['id']]=dict(colors=colors,sku=dict(sku),materials=used,edges={k:sorted(v,key=repr) for k,v in edges.items()},uses=uses)
 return result

def label(material):
 return (str(material[0])+str(material[1])+' '+str(material[2])) if material else '（物料已删除）'

def check_locked_changes(conn,before):
 if not before:return
 after=locked_snapshots(conn,before.keys());details=[]
 for sid,old in before.items():
  new=after.get(sid);sku=old['sku'];root=sku['material_id'];root_label=label(old['materials'].get(root));sku_label=root_label+' 历史版本'+str(sku['mirror_version'])
  impacts=set()
  if new is None or any(new['sku'][k]!=sku[k] for k in ('material_id','mirror_version','scope_id','change_description')):impacts.add((root,None))
  if new:
   for mid in set(old['materials'])|set(new['materials']):
    if old['materials'].get(mid)!=new['materials'].get(mid):
     impacts.update((m,p) for m,p in old['uses']|new['uses'] if m==mid)
     if mid==root:impacts.add((mid,None))
   for key in set(old['colors'])|set(new['colors']):
    if old['colors'].get(key)!=new['colors'].get(key):impacts.add((key[1],key[0] or None))
   for parent,child in set(old['edges'])|set(new['edges']):
    if old['edges'].get((parent,child))!=new['edges'].get((parent,child)):impacts.add((child,parent))
  for mid,parent in sorted(impacts,key=repr):
   materials=dict(new['materials']) if new else {};materials.update(old['materials'])
   details.append(dict(sku_id=sid,sku=sku_label,material=label(materials.get(mid)),parent=label(materials.get(parent)) if parent else 'SKU根节点（无父项）'))
 if details:raise LockedBomError(details)

def assert_sku_unlocked(service,sid):
 primary=getattr(service,'primary',service)
 row=primary.db.conn.execute('SELECT s.*,m.base_code,m.version,m.name FROM skus s JOIN materials m ON m.id=s.material_id WHERE s.id=?',(sid,)).fetchone()
 if row and row['locked']:
  text=row['base_code']+row['version']+' '+row['name']
  raise LockedBomError([dict(sku_id=sid,sku=text+' 历史版本'+str(row['mirror_version']),material=text,parent='SKU根节点（无父项）')])
