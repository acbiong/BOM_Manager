"""业务服务层：物料、SKU、BOM、日志和Excel；UI不得直接访问数据库。编辑时间：2026-09-24。"""
from pathlib import Path
from datetime import datetime
from openpyxl import Workbook,load_workbook
class BomImportError(ValueError):
 def __init__(self,issues):
  self.issues=issues
  super().__init__(f'BOM扫描完成，共发现{len(issues)}个问题，未导入：\n'+'\n'.join(issues))

class MaterialHeaderError(ValueError):
 def __init__(self,headers,missing):
  self.headers=headers; self.missing=missing
  super().__init__('缺少表头：'+ '、'.join(missing))
from config.config_service import DEFAULT_MATERIAL_UNITS

class Services:
 UNITS=list(DEFAULT_MATERIAL_UNITS); MP=['M','P']
 def __init__(self,db,config_service=None):
  self.db=db; self.config_service=config_service; self.UNITS=config_service.material_units() if config_service else list(DEFAULT_MATERIAL_UNITS)
 MATERIAL_FIELDS=[('base_code','基础编码'),('version','版本号'),('name','物料名称'),('description','规格描述'),('unit','单位'),('manufacturer','制造商'),('mpn','MPN'),('mp_flag','M/P')]
 def material_snapshot(self,i):
  row=self.db.conn.execute('SELECT * FROM materials WHERE id=?',(i,)).fetchone()
  return dict(row) if row else {}
 def material_detail(self,before,after):
  def text(value):return '（空）' if value is None or value=='' else str(value)
  return '；'.join(f'{label}：{text(before.get(key))} → {text(after.get(key))}' for key,label in self.MATERIAL_FIELDS if before.get(key)!=after.get(key))
 def log(self,typ,obj,act,detail,snapshot=None):
  if snapshot is None and typ=='material':snapshot=self.material_snapshot(obj)
  snapshot=snapshot or {}
  code=f"{snapshot['base_code']}{snapshot['version']}" if snapshot else None
  self.db.conn.execute('INSERT INTO change_logs(object_type,object_id,action,detail,material_code,material_name) VALUES(?,?,?,?,?,?)',(typ,obj,act,detail,code,snapshot.get('name')))
 def materials(self,query=''):
  # 自身有下阶仅决定has_bom；idle只检查是否为SKU或被其他BOM作为子项引用。
  q=f'%{query}%'; return self.db.conn.execute('SELECT m.id,m.base_code,m.version,m.name,m.description,m.unit,m.manufacturer,m.mpn,m.mp_flag,m.has_bom AS stored_has_bom,m.created_at,m.updated_at,CASE WHEN EXISTS(SELECT 1 FROM material_bom_items b WHERE b.parent_material_id=m.id) THEN "Y" ELSE "N" END AS has_bom,CASE WHEN EXISTS(SELECT 1 FROM material_bom_items b WHERE b.child_material_id=m.id) OR EXISTS(SELECT 1 FROM skus s WHERE s.material_id=m.id) THEN "N" ELSE "Y" END AS idle FROM materials m WHERE base_code LIKE ? OR name LIKE ? ORDER BY base_code,version',(q,q)).fetchall()
 def create_material(self,d):
  if not all(d.get(k) for k in ('base_code','version','name')): raise ValueError('基础编码、版本号、名称为必填')
  if d.get('unit','pcs') not in self.UNITS: raise ValueError('单位不合规')
  with self.db.transaction():
   c=self.db.conn.execute('INSERT INTO materials(base_code,version,name,description,unit,manufacturer,mpn,mp_flag) VALUES(?,?,?,?,?,?,?,?)',(d['base_code'],d['version'],d['name'],d.get('description',''),d.get('unit','pcs'),d.get('manufacturer',''),d.get('mpn',''),d.get('mp_flag','M'))); i=c.lastrowid; self.log('material',i,'create','新建物料；'+self.material_detail({},self.material_snapshot(i)))
  try:
   from infrastructure.events import WindowRefreshBus; WindowRefreshBus.publish({'type':'material_changed','id':i})
  except Exception: pass
  return i
 def update_material(self,i,d):
  if d.get('unit') not in self.UNITS:raise ValueError('单位不合规，允许：'+ '、'.join(self.UNITS))
  before=self.material_snapshot(i)
  if not before:raise ValueError('物料不存在')
  with self.db.transaction(): self.db.conn.execute('UPDATE materials SET name=?,description=?,unit=?,manufacturer=?,mpn=?,mp_flag=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(d['name'],d.get('description',''),d['unit'],d.get('manufacturer',''),d.get('mpn',''),d.get('mp_flag','M'),i)); self.log('material',i,'update','修改物料；'+(self.material_detail(before,self.material_snapshot(i)) or '物料属性未发生变化'))
  from infrastructure.events import WindowRefreshBus
  WindowRefreshBus.publish({'type':'material_changed','id':i})
 def delete_material(self,i):
  if self.db.conn.execute('SELECT 1 FROM skus WHERE material_id=?',(i,)).fetchone(): raise ValueError('物料是SKU，请先删除SKU引用')
  r=self.db.conn.execute('SELECT COUNT(*) n FROM material_bom_items WHERE parent_material_id=? OR child_material_id=?',(i,i)).fetchone();
  if r['n']: raise ValueError('物料仍被BOM引用，请先删除引用')
  before=self.material_snapshot(i)
  with self.db.transaction(): self.db.conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=? OR child_material_id=?',(i,i)); self.db.conn.execute('DELETE FROM materials WHERE id=?',(i,)); self.log('material',i,'delete','删除物料；删除前：'+self.material_detail({},before),before)
 def skus(self): return self.db.conn.execute('SELECT s.id,m.id AS material_id,m.base_code,m.version,m.name,m.description,m.unit,m.manufacturer,m.mpn,m.mp_flag,m.has_bom,m.updated_at FROM skus s JOIN materials m ON m.id=s.material_id ORDER BY s.id').fetchall()
 def create_sku(self,mid,require_empty_bom=False):
  if not self.material_snapshot(mid):raise ValueError('物料不存在')
  if require_empty_bom and self.db.conn.execute('SELECT 1 FROM material_bom_items WHERE parent_material_id=?',(mid,)).fetchone():raise ValueError('物料已有BOM结构，不可用于新建SKU')
  if self.db.conn.execute('SELECT 1 FROM skus WHERE material_id=?',(mid,)).fetchone(): raise ValueError('已是SKU')
  with self.db.transaction(): c=self.db.conn.execute('INSERT INTO skus(material_id) VALUES(?)',(mid,)); self.log('sku',c.lastrowid,'create','创建SKU'); sid=c.lastrowid
  from infrastructure.events import WindowRefreshBus
  WindowRefreshBus.publish({'type':'sku_changed','id':sid})
  return sid
 def delete_sku(self,sid):
  with self.db.transaction():
   r=self.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone()
   if r is None:raise ValueError('SKU不存在')
   root=r['material_id']
   self.db.conn.execute('DELETE FROM alternates WHERE bom_item_id IN (SELECT id FROM material_bom_items WHERE parent_material_id=?)',(root,))
   self.db.conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=?',(root,))
   self.db.conn.execute('DELETE FROM bom_items WHERE bom_root_id=?',(root,))
   self.db.conn.execute('UPDATE materials SET has_bom=0 WHERE id=?',(root,))
   self.db.conn.execute('DELETE FROM skus WHERE id=?',(sid,)); self.log('sku',sid,'delete','删除SKU及其根BOM结构、直属替代料；保留共享子BOM和物料库记录')
  from infrastructure.events import WindowRefreshBus
  WindowRefreshBus.publish({'type':'sku_changed','id':sid})
  WindowRefreshBus.publish({'type':'bom_changed','root':r['material_id']})
 def bom(self,root):
  """递归展开物料关系表，返回兼容BOM编辑器的扁平树行。"""
  result=[]
  def walk(parent_id,level,parent_item_id,parent_node_id,ancestors):
   if parent_id in ancestors:return
   ancestors=ancestors|{parent_id}
   rows=self.db.conn.execute('SELECT b.*,m.base_code,m.version,m.name,m.description,m.unit AS material_unit,m.manufacturer,m.mpn,m.mp_flag FROM material_bom_items b JOIN materials m ON m.id=b.child_material_id WHERE b.parent_material_id=? ORDER BY b.sort_no,b.id',(parent_id,)).fetchall()
   for r in rows:
    if r['child_material_id'] in ancestors:continue
    node_id=f"{parent_node_id or ''}/{r['id']}"
    d=dict(r); d.update(material_id=r['child_material_id'],unit=r['material_unit'],level_no=level,parent_item_id=parent_item_id,bom_root_id=root,node_id=node_id,parent_node_id=parent_node_id)
    result.append(d); walk(r['child_material_id'],level+1,r['id'],node_id,ancestors)
  walk(root,1,None,None,set()); return result
 def save_bom(self,root,items,preview=False):
  """把树中的重复子BOM归并为物料关系，在单个事务中保存。"""
  old_rows=self.bom(root)
  retained={root}|{row['material_id'] for row in items}
  parents={root}|{row['parent_material_id'] for row in old_rows if row['parent_material_id'] in retained}
  # 编辑器提供完整子树；新增父物料的全部子项被标删时也需要清空其原共享BOM。
  parents.update(row['material_id'] for row in items if row.get('replace_children'))
  by_id={row['id']:row for row in items if row.get('id') is not None}
  desired={}; alternate_updates={}
  old={ (row['parent_material_id'],row['child_material_id'],row['position'] or ''):dict(row)
        for row in self.db.conn.execute('SELECT * FROM material_bom_items') }
  def payload(row):
   return (round(float(row['quantity']),1),row['unit'],row.get('remark','') or '')
  for row in items:
   parent=row.get('parent_material_id')
   if parent is None:
    pid=row.get('parent_item_id'); parent_row=by_id.get(pid)
    if pid is not None and parent_row is None:
     if isinstance(pid,int) and 1<=pid<=len(items): parent_row=items[pid-1]
     else: raise ValueError('BOM结构存在无效的父级关系')
    parent=parent_row['material_id'] if parent_row else root
   key=(parent,row['material_id'],row.get('position','') or '')
   if 'alternate_material_ids' in row:
    alternates=list(dict.fromkeys(row['alternate_material_ids']))
    if key in alternate_updates and alternate_updates[key]!=alternates:raise ValueError('共享BOM的替代料修改不一致')
    if row['material_id'] in alternates:raise ValueError('物料不能作为自身的替代料')
    for mid in alternates:
     if not self.db.conn.execute('SELECT 1 FROM materials WHERE id=?',(mid,)).fetchone():raise ValueError('替代料不存在，请重新选择')
    alternate_updates[key]=alternates
   values=payload(row)
   if values[0]<=0: raise ValueError('物料数量必须至少为0.1')
   parents.add(parent)
   if key in desired and desired[key]!=values:
    baseline=payload(old[key]) if key in old else None
    if values==baseline: continue
    if desired[key]!=baseline:
     material=self.db.conn.execute('SELECT base_code,version,name FROM materials WHERE id=?',(row['material_id'],)).fetchone()
     raise ValueError(f'共享子BOM的同一关系存在不同修改：{material[0]}{material[1]} {material[2]}。请统一数量、位置和备注后保存。')
   desired[key]=values
  # 替代料属于父子关系。只通知真正改变的父级BOM，不能把整棵树都当成已更新。
  changed_parents=set()
  old_groups={}; new_groups={}
  for key,row in sorted(old.items(),key=lambda pair:(pair[1]['sort_no'],pair[1]['id'])):
   old_groups.setdefault(key[0],[]).append((key,payload(row)))
  for key,values in desired.items():new_groups.setdefault(key[0],[]).append((key,values))
  for parent in parents:
   if old_groups.get(parent,[])!=new_groups.get(parent,[]):changed_parents.add(parent)
  for key,alternates in alternate_updates.items():
   previous=[row['material_id'] for row in self.alternates(old[key]['id'])] if key in old else []
   if previous!=alternates:changed_parents.add(key[0])
  # 同一个物料关系可能在树的多条路径出现，但数据库只保存一份。
  graph={}
  for key in old:
   if key[0] not in parents: graph.setdefault(key[0],set()).add(key[1])
  for parent,child,_ in desired: graph.setdefault(parent,set()).add(child)
  visiting=set(); visited=set()
  def check(node):
   if node in visiting: raise ValueError('BOM包含循环引用，请检查父级和子级物料')
   if node in visited: return
   visiting.add(node)
   for child in graph.get(node,()): check(child)
   visiting.remove(node); visited.add(node)
  for parent in parents: check(parent)
  if preview:
   # 使用与正式保存完全相同的关系集合生成编辑树，不写库、不发送刷新通知。
   relations={key:payload(row) for key,row in old.items() if key[0] not in parents}
   relations.update(desired)
   groups={}; materials={r['id']:dict(r) for r in self.materials()}
   for number,(key,values) in enumerate(relations.items(),1):
    parent,child,position=key; quantity,unit,remark=values
    previous=old.get(key); relation_id=previous['id'] if previous else -number
    data=dict(materials[child]); data.update(id=relation_id,material_id=child,parent_material_id=parent,quantity=quantity,unit=unit,position=position,remark=remark)
    data['_db_alternates']=[r['material_id'] for r in self.alternates(relation_id)] if previous else []
    groups.setdefault(parent,[]).append(data)
   def expand(parent):
    return [{'data':dict(data),'children':expand(data['material_id'])} for data in groups.get(parent,[])]
   return expand(root)
  with self.db.transaction():
   for key,row in old.items():
    if key[0] in parents and key not in desired:
     self.db.conn.execute('DELETE FROM alternates WHERE bom_item_id=?',(row['id'],))
     self.db.conn.execute('DELETE FROM material_bom_items WHERE id=?',(row['id'],))
   for order,(key,values) in enumerate(desired.items()):
    parent,child,position=key; quantity,unit,remark=values
    self.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit,position,remark,sort_no) VALUES(?,?,?,?,?,?,?) ON CONFLICT(parent_material_id,child_material_id,position) DO UPDATE SET quantity=excluded.quantity,unit=excluded.unit,remark=excluded.remark,sort_no=excluded.sort_no,updated_at=CURRENT_TIMESTAMP',(parent,child,quantity,unit,position,remark,order))
   for key,alternates in alternate_updates.items():
    relation=self.db.conn.execute('SELECT id FROM material_bom_items WHERE parent_material_id=? AND child_material_id=? AND position=?',key).fetchone()[0]
    self.db.conn.execute('DELETE FROM alternates WHERE bom_item_id=?',(relation,))
    for order,mid in enumerate(alternates):self.db.conn.execute('INSERT INTO alternates(bom_item_id,material_id,sort_no) VALUES(?,?,?)',(relation,mid,order))
   self.db.conn.execute('UPDATE materials SET has_bom=CASE WHEN EXISTS(SELECT 1 FROM material_bom_items WHERE parent_material_id=materials.id) THEN 1 ELSE 0 END')
   self.log('bom',root,'update',f'{len(desired)}条物料关系')
  from infrastructure.events import WindowRefreshBus
  for parent in changed_parents: WindowRefreshBus.publish({'type':'bom_changed','root':parent})
 def validate_bom_rows(self,root,rows):
  """校验导入BOM与现有结构的子项、数量、位置一致性。"""
  old={(x['material_id'],str(x['position'])):float(x['quantity']) for x in self.bom(root)}; new={(x['material_id'],str(x.get('position',''))):float(x['quantity']) for x in rows}
  return old==new, {'missing':list(set(old)-set(new)),'extra':list(set(new)-set(old))}
 def change_sku_version(self,sid,new_version):
  r=self.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone()
  if not r: raise ValueError('SKU不存在')
  self.change_material_version(r['material_id'],new_version)
  self.log('sku',sid,'version',new_version)
 def delete_bom_item(self,bom_item_id,recursive=True):
  r=self.db.conn.execute('SELECT parent_material_id,child_material_id FROM material_bom_items WHERE id=?',(bom_item_id,)).fetchone()
  if not r:return
  with self.db.transaction():
   self.db.conn.execute('DELETE FROM material_bom_items WHERE id=?',(bom_item_id,))
   self.db.conn.execute('UPDATE materials SET has_bom=CASE WHEN EXISTS(SELECT 1 FROM material_bom_items WHERE parent_material_id=materials.id) THEN 1 ELSE 0 END')
   self.log('bom',r['parent_material_id'],'delete',f'删除下阶物料{r["child_material_id"]}')
  try:
   from infrastructure.events import WindowRefreshBus
   WindowRefreshBus.publish({'type':'bom_changed','root':r['parent_material_id']})
  except Exception: pass
 BOM_HEADERS=['父项物料编码','父项版本号','物料基础编码','物料版本号','物料数量','位置']
 def import_bom(self,path,root=None,sheet_name=None,header_mapping=None,persist=True):
  import math
  wb=load_workbook(path,read_only=True,data_only=True)
  try:
   if sheet_name is None:
    if len(wb.sheetnames)!=1:raise ValueError('文件包含多个工作表，请选择BOM所在工作表')
    sheet_name=wb.sheetnames[0]
   if sheet_name not in wb.sheetnames:raise ValueError('所选工作表不存在')
   ws=wb[sheet_name]; headers=[str(x if x is not None else '').strip() for x in next(ws.iter_rows(values_only=True),())]
   mapping=header_mapping or {field:field for field in self.BOM_HEADERS}
   missing=[field for field in self.BOM_HEADERS if not mapping.get(field) or not str(mapping[field]).strip() or mapping[field] not in headers]
   if missing:raise MaterialHeaderError(headers,missing)
   if len(set(mapping[field] for field in self.BOM_HEADERS))!=len(self.BOM_HEADERS):raise ValueError('表头映射重复')
   if any(headers.count(mapping[field])!=1 for field in self.BOM_HEADERS):raise ValueError('源表头名称重复，请修改文件表头后重试')
   index={field:headers.index(mapping[field]) for field in self.BOM_HEADERS}; rows=[]; pairs=set(); children={}; parents=set(); child_ids=set()
   materials={(r['base_code'],r['version']):r for r in self.materials()}
   issues=[]; records=[]; root_row=None
   current=self.material_snapshot(root) if root is not None else None
   if root is not None and not current:issues.append('当前BOM根物料不存在')
   for no,values in enumerate(ws.iter_rows(values_only=True),1):
    if no==1:continue
    data={field:str(values[i] if i<len(values) and values[i] is not None else '').strip() for field,i in index.items()}
    if not any(data.values()):continue
    is_root=[data[field].casefold()=='root' for field in ('父项物料编码','父项版本号')]
    if any(is_root):
     if not all(is_root):issues.append(f'第{no}行根节点标记不完整：父项物料编码和父项版本号必须同时为ROOT/root')
     if root_row is not None:issues.append(f'第{no}行存在重复根节点声明，BOM只能有一个ROOT根节点')
     root_row=no; key=(data['物料基础编码'],data['物料版本号'])
     if current:
      if key!=(current['base_code'],current['version']):
       issues.append(f"BOM选择错误：第{no}行ROOT物料为{key[0]}{key[1]}，当前BOM为{current['base_code']}{current['version']}，禁止导入")
     elif root is None:
      if key not in materials:issues.append(f'第{no}行ROOT物料不存在：{key[0]}{key[1]}')
      elif all(is_root):root=materials[key]['id'];current=materials[key]
     continue
    records.append((no,data))
   edge_lines={}
   for no,data in records:
    start_errors=len(issues)
    absent=[field for field in self.BOM_HEADERS[:-1] if not data[field]]
    if absent:issues.append(f'第{no}行必填项缺失：'+ '、'.join(absent))
    parent=materials.get((data['父项物料编码'],data['父项版本号'])); child=materials.get((data['物料基础编码'],data['物料版本号']))
    if parent is None and data['父项物料编码'] and data['父项版本号']:issues.append(f'第{no}行父项不存在：'+data['父项物料编码']+data['父项版本号'])
    if child is None and data['物料基础编码'] and data['物料版本号']:issues.append(f'第{no}行子物料不存在：'+data['物料基础编码']+data['物料版本号'])
    quantity=None
    if data['物料数量']:
     try:
      quantity=float(data['物料数量'])
      if not math.isfinite(quantity) or round(quantity,1)<=0:issues.append(f'第{no}行数量必须至少为0.1且为有限数字')
     except ValueError:issues.append(f'第{no}行数量不是有效数字')
    if parent is None or child is None:continue
    pid=parent['id']; mid=child['id']
    if (pid,mid) in pairs:issues.append(f'第{no}行同一父级重复包含相同物料（首次出现于第{edge_lines[pid,mid]}行）')
    if pid==mid:issues.append(f'第{no}行物料不能包含自身')
    pairs.add((pid,mid));edge_lines.setdefault((pid,mid),no);parents.add(pid);child_ids.add(mid)
    if mid not in children.setdefault(pid,[]):children[pid].append(mid)
    if len(issues)==start_errors:rows.append(dict(parent_material_id=pid,material_id=mid,quantity=round(quantity,1),unit=child['unit'],position=data['位置']))
   if not rows and root_row is None and not issues:issues.append('所选工作表没有可导入的BOM数据')
   if root is None:
    roots=parents-child_ids
    if len(roots)!=1:issues.append('BOM必须具有唯一根物料，或结构存在循环')
    else:root=next(iter(roots))
   visited=set();active=set()
   def walk(mid):
    if mid in visited:return
    active.add(mid)
    for child in children.get(mid,[]):
     if child in active:issues.append(f'第{edge_lines[mid,child]}行关系使BOM结构存在循环包含')
     else:walk(child)
    active.remove(mid);visited.add(mid)
   if root is not None:
    walk(root)
    unreachable=(parents|child_ids)-visited
    if unreachable:
     lines=sorted({no for (parent,child),no in edge_lines.items() if parent in unreachable or child in unreachable})
     issues.append('第'+ '、'.join(map(str,lines))+'行存在不属于当前根物料的孤立分支，请检查父项编码和版本号')
   for mid in sorted(parents|child_ids):walk(mid)
   if root is not None:
    try:preview_tree=self.save_bom(root,rows,preview=True)
    except ValueError as error:issues.append('与数据库共享BOM结构校验失败：'+str(error))
   if issues:raise BomImportError(issues)
   if not persist:return preview_tree
   self.save_bom(root,rows)
   return len(rows)
  finally:wb.close()
 def update_project(self,d):
  with self.db.transaction(): self.db.conn.execute('UPDATE project SET project_name=?,project_code=?,product_name=?,product_model=? WHERE id=1',(d.get('project_name',''),d.get('project_code',''),d.get('product_name',''),d.get('product_model',''))); self.log('project',1,'update',d.get('project_name',''))
 def project(self): return self.db.conn.execute('SELECT * FROM project WHERE id=1').fetchone()
 def material_version_references(self,i):
  """以实际共享父级BOM为选择单位，列出所有受影响SKU。"""
  parents=self.db.conn.execute('SELECT DISTINCT m.* FROM material_bom_items b JOIN materials m ON m.id=b.parent_material_id WHERE b.child_material_id=? ORDER BY m.base_code,m.version',(i,)).fetchall()
  result=[]
  for parent in parents:
   usages=[]; sku_ids=[]
   for sku in self.skus():
    if any(row['material_id']==i and row['parent_material_id']==parent['id'] for row in self.bom(sku['material_id'])):
     usages.append(f"{sku['base_code']}{sku['version']} {sku['name']}"); sku_ids.append(sku['id'])
   parent_label=f"{parent['base_code']}{parent['version']} {parent['name']}"
   result.append({'parent_id':parent['id'],'sku_ids':sku_ids or [None],'sku_labels':usages or ['未包含在SKU中'],'parent_label':parent_label,'labels':[f'{label}/{parent_label}' for label in (usages or ['未包含在SKU中'])]})
  return result
 def material_usage(self,i):
  result=[{'sku_id':sid,'sku':sku,'parent':reference['parent_label']} for reference in self.material_version_references(i) for sid,sku in zip(reference['sku_ids'],reference['sku_labels'])]
  for sku in self.skus():
   if sku['material_id']==i: result.append({'sku_id':sku['id'],'sku':f"{sku['base_code']}{sku['version']} {sku['name']}",'parent':'SKU根节点（无父级）'})
  return result
 def change_material_version(self,i,new_version,selected_parents=None,expected_parents=None):
  new_version=new_version.strip()
  if not new_version: raise ValueError('版本号不能为空')
  with self.db.transaction():
   old=self.db.conn.execute('SELECT * FROM materials WHERE id=?',(i,)).fetchone()
   if old is None: raise ValueError('物料不存在')
   if self.db.conn.execute('SELECT 1 FROM materials WHERE base_code=? AND version=?',(old['base_code'],new_version)).fetchone(): raise ValueError('目标版本已存在')
   parents={r[0] for r in self.db.conn.execute('SELECT DISTINCT parent_material_id FROM material_bom_items WHERE child_material_id=?',(i,))}
   if expected_parents is not None and parents!=set(expected_parents): raise ValueError('物料的BOM引用已变化，请重新打开版本变更窗口')
   selected=parents if selected_parents is None else set(selected_parents)
   if not selected<=parents: raise ValueError('所选BOM引用已变化，请重新选择')
   if selected==parents:
    new_id=i
    self.db.conn.execute('UPDATE materials SET version=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(new_version,i))
   else:
    columns=['base_code','name','description','unit','manufacturer','mpn','mp_flag','has_bom']
    values=[old[k] for k in columns]
    new_id=self.db.conn.execute('INSERT INTO materials('+','.join(columns)+',version) VALUES('+','.join('?' for _ in range(len(columns)+1))+')',values+[new_version]).lastrowid
    # 新版本继承原物料自己的下阶结构和替代料，新旧版本后续可独立维护。
    for child in self.db.conn.execute('SELECT * FROM material_bom_items WHERE parent_material_id=?',(i,)).fetchall():
     relation=self.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit,position,remark,sort_no) VALUES(?,?,?,?,?,?,?)',(new_id,child['child_material_id'],child['quantity'],child['unit'],child['position'],child['remark'],child['sort_no'])).lastrowid
     self.db.conn.execute('INSERT INTO alternates(bom_item_id,material_id,sort_no) SELECT ?,material_id,sort_no FROM alternates WHERE bom_item_id=?',(relation,child['id']))
    for parent in selected:
     self.db.conn.execute('UPDATE material_bom_items SET child_material_id=?,updated_at=CURRENT_TIMESTAMP WHERE parent_material_id=? AND child_material_id=?',(new_id,parent,i))
   self.log('material',new_id,'version',f'{old["base_code"]}: {old["version"]}->{new_version}; 原物料={i}; 更新父级BOM={[str(self.material_snapshot(parent).get('base_code',''))+str(self.material_snapshot(parent).get('version',''))+' '+str(self.material_snapshot(parent).get('name','')) for parent in sorted(selected)]}; '+('原位更新' if new_id==i else '保留旧版本并创建新物料'))
  from infrastructure.events import WindowRefreshBus
  WindowRefreshBus.publish({'type':'material_changed','id':new_id})
  for parent in selected: WindowRefreshBus.publish({'type':'bom_changed','root':parent})
  return new_id
 def add_alternate(self,bom_item_id,material_id):
  with self.db.transaction(): self.db.conn.execute('INSERT INTO alternates(bom_item_id,material_id,sort_no) VALUES(?,?,COALESCE((SELECT MAX(sort_no)+1 FROM alternates WHERE bom_item_id=?),0))',(bom_item_id,material_id,bom_item_id))
 def alternates(self,bom_item_id): return self.db.conn.execute('SELECT a.*,m.base_code,m.version,m.name,m.description,m.manufacturer,m.mpn FROM alternates a JOIN materials m ON m.id=a.material_id WHERE a.bom_item_id=? ORDER BY a.sort_no',(bom_item_id,)).fetchall()
 def remove_alternate(self,aid):
  with self.db.transaction(): self.db.conn.execute('DELETE FROM alternates WHERE id=?',(aid,))
 def import_materials(self,path,conflict_resolver=None,header_mapping=None,progress_callback=None,sheet_name=None):
  required=['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN']
  wb=load_workbook(path,read_only=True,data_only=True)
  try:
   if sheet_name is None:
    if len(wb.sheetnames)!=1:raise ValueError('文件包含多个工作表，请先选择物料库所在的工作表')
    sheet_name=wb.sheetnames[0]
   if sheet_name not in wb.sheetnames:raise ValueError('所选工作表不存在：'+sheet_name)
   ws=wb[sheet_name]; headers=[str(x if x is not None else '').strip() for x in next(ws.iter_rows(values_only=True),())]
   if header_mapping is None:
    missing=[x for x in required if x not in headers]
    if missing: raise MaterialHeaderError(headers,missing)
    header_mapping={x:x for x in required}
   missing=[x for x in required if not header_mapping.get(x) or header_mapping[x] not in headers]
   if missing: raise MaterialHeaderError(headers,missing)
   idx={x:headers.index(header_mapping[x]) for x in required}; ok=[]; fail=[]; total=max((ws.max_row or 1)-1,0)
   if progress_callback: progress_callback(0,total)
   for no,row in enumerate(ws.iter_rows(min_row=2,values_only=True),2):
    d={k:str(row[i] if row[i] is not None else '').strip() for k,i in idx.items()};
    if progress_callback: progress_callback(no-1,total)
    if not d['物料基础编码'] and not d['物料名称']:continue
    display_code=(d['物料基础编码'] or '（空基础编码）')+(d['物料版本号'] or '（空版本号）')
    missing_fields=[field for field in ('物料基础编码','物料版本号','物料名称','单位','物料制造商') if not d[field]]
    if missing_fields:
     fail.append((no,display_code,d.get('物料名称',''),'必填项缺失：'+ '、'.join(missing_fields))); continue
    if d['单位'] not in self.UNITS: fail.append((no,display_code,d['物料名称'],'单位不合规')); continue
    old=self.db.conn.execute('SELECT * FROM materials WHERE base_code=? AND version=?',(d['物料基础编码'],d['物料版本号'])).fetchone()
    if old:
     same=all(str(old[k] or '')==str(d[key] or '') for k,key in [('name','物料名称'),('description','物料规格描述'),('unit','单位'),('manufacturer','物料制造商'),('mpn','物料MPN')])
     if same:
      fail.append((no,display_code,d['物料名称'],'重复物料信息相同，自动跳过')); continue
     choice=conflict_resolver(d,old) if conflict_resolver else 'skip'
     if choice=='cancel': return ok,fail+[(no,display_code,d['物料名称'],'用户取消')]
     if choice=='overwrite':
      self.update_material(old['id'],{'name':d['物料名称'],'description':d['物料规格描述'],'unit':d['单位'],'manufacturer':d['物料制造商'],'mpn':d['物料MPN']}); ok.append(d['物料基础编码']); continue
     fail.append((no,display_code,d['物料名称'],'跳过重复物料')); continue
    try: self.create_material({'base_code':d['物料基础编码'],'version':d['物料版本号'],'name':d['物料名称'],'description':d['物料规格描述'],'unit':d['单位'],'manufacturer':d['物料制造商'],'mpn':d['物料MPN']}); ok.append(d['物料基础编码'])
    except Exception as e: fail.append((no,display_code,d['物料名称'],str(e)))
   if progress_callback: progress_callback(total,total)
   return ok,fail
  finally:wb.close()
 def export_database(self,path):
  wb=Workbook(); ws=wb.active; ws.title='SKU清单'; ws.append(['序号','SKU编码','SKU名称','SKU描述','修改日期时间'])
  for n,r in enumerate(self.skus(),1): ws.append([n,r['base_code']+r['version'],r['name'],r['description'],r['updated_at']])
  w=wb.create_sheet('物料库'); w.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN','M/P','是否存在BOM结构','是否为呆滞料'])
  for r in self.materials(): w.append([r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag'],r['has_bom'],r['idle']])
  c=wb.create_sheet('变更记录'); c.append(['序号','变更时间','变更详细内容','变更日期','变更时间'])
  for n,r in enumerate(self.db.conn.execute('SELECT * FROM change_logs ORDER BY id'),1): c.append([n,r['changed_at'],r['detail'],r['changed_at'][:10],r['changed_at'][11:]])
  for r in self.skus():
   b=wb.create_sheet((r['base_code']+r['version'])[:31]); b.append(['序号','层级','父项编码','父项版本','物料基础编码','物料版本号','物料名称','物料规格描述','用量','单位','M/P','制造商','MPN'])
   for n,x in enumerate(self.bom(r['material_id']),1): b.append([n,x['level_no'],r['base_code'],r['version'],x['base_code'],x['version'],x['name'],x['description'],x['quantity'],x['unit'],x['mp_flag'],x['manufacturer'],x['mpn']])
  for sheet in wb:
   headers=[cell.value for cell in sheet[1]]
   if '用量' in headers:
    for row in sheet.iter_rows(min_row=2): row[headers.index('用量')].number_format='0.0'
  wb.save(path)
 def export_materials(self,path):
  from openpyxl.styles import Alignment
  wb=Workbook(); ws=wb.active; ws.title='变更记录'; ws.append(['序号','变更日期','变更时间','变更物料编码','变更物料名称','变更详细内容'])
  ws2=wb.create_sheet('物料库'); ws2.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN','M/P','是否存在BOM结构','是否为呆滞料'])
  for r in self.materials():ws2.append([r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag'],r['has_bom'],r['idle']])
  for n,r in enumerate(self.db.conn.execute("SELECT * FROM change_logs WHERE object_type='material' ORDER BY id"),1):
   code=r['material_code']; name=r['material_name']; detail=r['detail'] or ''
   if code is None:
    # 老日志无历史快照，不能用可能已复用的ID推断历史物料，也不能伪造变更前值。
    code='历史记录未保存'; name='历史记录未保存'; detail='历史日志（未记录字段前后值及物料快照）：'+detail
   changed=r['changed_at'] or ''; ws.append([n,changed[:10],changed[11:],code,name,detail])
  ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
  for column,width in [('A',8),('B',14),('C',14),('D',28),('E',32),('F',90)]:ws.column_dimensions[column].width=width
  for row in ws.iter_rows(min_row=2):
   for cell in row:cell.alignment=Alignment(wrap_text=True,vertical='top')
  wb.save(path)
 def export_sku(self,sid,path):
  s=self.db.conn.execute('SELECT s.*,m.* FROM skus s JOIN materials m ON m.id=s.material_id WHERE s.id=?',(sid,)).fetchone(); wb=Workbook(); w=wb.active; w.title='变更记录'; w.append(['序号','变更时间','变更详细内容','变更日期','变更时间']); b=wb.create_sheet('SKU对应的BOM'); b.append(['序号','层级','父项编码','父项版本','物料基础编码','物料版本号','物料名称','物料规格描述','用量','单位','M/P','制造商','MPN']);
  for n,r in enumerate(self.bom(s['material_id']),1): b.append([n,r['level_no'],s['base_code'],s['version'],r['base_code'],r['version'],r['name'],r['description'],r['quantity'],r['unit'],r['mp_flag'],r['manufacturer'],r['mpn']])
  for sheet in wb:
   headers=[cell.value for cell in sheet[1]]
   if '用量' in headers:
    for row in sheet.iter_rows(min_row=2): row[headers.index('用量')].number_format='0.0'
  wb.save(path)
