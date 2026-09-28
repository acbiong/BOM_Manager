"""业务服务层：物料、SKU、BOM、日志和Excel；UI不得直接访问数据库。编辑时间：2026-09-24。"""
from pathlib import Path
from datetime import datetime
from openpyxl import Workbook,load_workbook
class Services:
 UNITS=['pcs','套','ml','L','mm','cm','m']; MP=['M','P']
 def __init__(self,db): self.db=db
 def log(self,typ,obj,act,detail): self.db.conn.execute('INSERT INTO change_logs(object_type,object_id,action,detail) VALUES(?,?,?,?)',(typ,obj,act,detail))
 def materials(self,query=''):
  q=f'%{query}%'; return self.db.conn.execute('SELECT m.id,m.base_code,m.version,m.name,m.description,m.unit,m.manufacturer,m.mpn,m.mp_flag,m.has_bom AS stored_has_bom,m.created_at,m.updated_at,CASE WHEN EXISTS(SELECT 1 FROM material_bom_items b WHERE b.parent_material_id=m.id) THEN "Y" ELSE "N" END AS has_bom,CASE WHEN EXISTS(SELECT 1 FROM material_bom_items b WHERE b.parent_material_id=m.id) THEN "Y" ELSE "N" END AS idle FROM materials m WHERE base_code LIKE ? OR name LIKE ? ORDER BY base_code,version',(q,q)).fetchall()
 def create_material(self,d):
  if not all(d.get(k) for k in ('base_code','version','name')): raise ValueError('基础编码、版本号、名称为必填')
  if d.get('unit','pcs') not in self.UNITS: raise ValueError('单位不合规')
  with self.db.transaction():
   c=self.db.conn.execute('INSERT INTO materials(base_code,version,name,description,unit,manufacturer,mpn,mp_flag) VALUES(?,?,?,?,?,?,?,?)',(d['base_code'],d['version'],d['name'],d.get('description',''),d.get('unit','pcs'),d.get('manufacturer',''),d.get('mpn',''),d.get('mp_flag','M'))); i=c.lastrowid; self.log('material',i,'create',d['name'])
  try:
   from infrastructure.events import WindowRefreshBus; WindowRefreshBus.publish({'type':'material_changed','id':i})
  except Exception: pass
  return i
 def update_material(self,i,d):
  with self.db.transaction(): self.db.conn.execute('UPDATE materials SET name=?,description=?,unit=?,manufacturer=?,mpn=?,mp_flag=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(d['name'],d.get('description',''),d['unit'],d.get('manufacturer',''),d.get('mpn',''),d.get('mp_flag','M'),i)); self.log('material',i,'update',d['name'])
  from infrastructure.events import WindowRefreshBus
  WindowRefreshBus.publish({'type':'material_changed','id':i})
 def delete_material(self,i):
  r=self.db.conn.execute('SELECT COUNT(*) n FROM material_bom_items WHERE parent_material_id=? OR child_material_id=?',(i,i)).fetchone();
  if r['n']: raise ValueError('物料仍被BOM引用，请先删除引用')
  with self.db.transaction(): self.db.conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=? OR child_material_id=?',(i,i)); self.db.conn.execute('DELETE FROM materials WHERE id=?',(i,)); self.log('material',i,'delete','删除物料')
 def skus(self): return self.db.conn.execute('SELECT s.id,m.id AS material_id,m.base_code,m.version,m.name,m.description,m.unit,m.manufacturer,m.mpn,m.mp_flag,m.has_bom,m.updated_at FROM skus s JOIN materials m ON m.id=s.material_id ORDER BY s.id').fetchall()
 def create_sku(self,mid):
  if self.db.conn.execute('SELECT 1 FROM skus WHERE material_id=?',(mid,)).fetchone(): raise ValueError('已是SKU')
  with self.db.transaction(): c=self.db.conn.execute('INSERT INTO skus(material_id) VALUES(?)',(mid,)); self.log('sku',c.lastrowid,'create','创建SKU'); return c.lastrowid
 def delete_sku(self,sid):
  with self.db.transaction(): r=self.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone(); self.db.conn.execute('DELETE FROM material_bom_items WHERE parent_material_id=?',(r['material_id'],)); self.db.conn.execute('DELETE FROM skus WHERE id=?',(sid,)); self.log('sku',sid,'delete','删除SKU')
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
 def save_bom(self,root,items):
  """把树中的重复子BOM归并为物料关系，在单个事务中保存。"""
  old_rows=self.bom(root)
  retained={root}|{row['material_id'] for row in items}
  parents={root}|{row['parent_material_id'] for row in old_rows if row['parent_material_id'] in retained}
  by_id={row['id']:row for row in items if row.get('id') is not None}
  desired={}
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
   values=payload(row)
   if values[0]<=0: raise ValueError('物料数量必须至少为0.1')
   parents.add(parent)
   if key in desired and desired[key]!=values:
    baseline=payload(old[key]) if key in old else None
    if values==baseline: continue
    if desired[key]!=baseline:
     material=self.db.conn.execute('SELECT base_code,version,name FROM materials WHERE id=?',(row['material_id'],)).fetchone()
     raise ValueError(f'共享子BOM的同一关系存在不同修改：{material[0]}-{material[1]} {material[2]}。请统一数量、位置和备注后保存。')
   desired[key]=values
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
  with self.db.transaction():
   for key,row in old.items():
    if key[0] in parents and key not in desired:
     self.db.conn.execute('DELETE FROM alternates WHERE bom_item_id=?',(row['id'],))
     self.db.conn.execute('DELETE FROM material_bom_items WHERE id=?',(row['id'],))
   for order,(key,values) in enumerate(desired.items()):
    parent,child,position=key; quantity,unit,remark=values
    self.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit,position,remark,sort_no) VALUES(?,?,?,?,?,?,?) ON CONFLICT(parent_material_id,child_material_id,position) DO UPDATE SET quantity=excluded.quantity,unit=excluded.unit,remark=excluded.remark,sort_no=excluded.sort_no,updated_at=CURRENT_TIMESTAMP',(parent,child,quantity,unit,position,remark,order))
   self.db.conn.execute('UPDATE materials SET has_bom=CASE WHEN EXISTS(SELECT 1 FROM material_bom_items WHERE parent_material_id=materials.id) THEN 1 ELSE 0 END')
   self.log('bom',root,'update',f'{len(desired)}条物料关系')
  from infrastructure.events import WindowRefreshBus
  for parent in parents: WindowRefreshBus.publish({'type':'bom_changed','root':parent})
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
 def import_bom(self,path,root=None):
  required=['父项物料编码','父项版本号','物料基础编码','物料版本号','物料数量','位置']
  wb=load_workbook(path,read_only=True,data_only=True); ws=wb.active; hs=[str(x or '').strip() for x in next(ws.iter_rows(values_only=True))]; miss=[x for x in required if x not in hs]
  if miss: raise ValueError('缺少表头：'+ '、'.join(miss))
  ix={h:i for i,h in enumerate(hs)}; rows=[]
  for no,row in enumerate(ws.iter_rows(min_row=2,values_only=True),2):
   d={k:str(row[i] or '').strip() for k,i in ix.items()}; p=self.db.conn.execute('SELECT id FROM materials WHERE base_code=? AND version=?',(d['父项物料编码'],d['父项版本号'])).fetchone(); m=self.db.conn.execute('SELECT id,unit FROM materials WHERE base_code=? AND version=?',(d['物料基础编码'],d['物料版本号'])).fetchone()
   if not p or not m: raise ValueError(f'第{no}行父项或物料不存在')
   try:q=float(d['物料数量'])
   except: raise ValueError(f'第{no}行数量不合法')
   rows.append({'parent_item_id':None,'material_id':m['id'],'quantity':q,'unit':m['unit'],'position':d['位置'],'level_no':1})
  if root is None and rows: root=p['id']
  if root and rows:self.save_bom(root,rows)
  return len(rows)
 def update_project(self,d):
  with self.db.transaction(): self.db.conn.execute('UPDATE project SET project_name=?,project_code=?,product_name=?,product_model=? WHERE id=1',(d.get('project_name',''),d.get('project_code',''),d.get('product_name',''),d.get('product_model',''))); self.log('project',1,'update',d.get('project_name',''))
 def project(self): return self.db.conn.execute('SELECT * FROM project WHERE id=1').fetchone()
 def change_material_version(self,i,new_version):
  if not new_version: raise ValueError('版本号不能为空')
  old=self.db.conn.execute('SELECT * FROM materials WHERE id=?',(i,)).fetchone()
  if self.db.conn.execute('SELECT 1 FROM materials WHERE base_code=? AND version=?',(old['base_code'],new_version)).fetchone(): raise ValueError('目标版本已存在')
  with self.db.transaction(): self.db.conn.execute('UPDATE materials SET version=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(new_version,i)); self.log('material',i,'version',f'{old["version"]}->{new_version}')
  from infrastructure.events import WindowRefreshBus
  WindowRefreshBus.publish({'type':'material_changed','id':i})
 def add_alternate(self,bom_item_id,material_id):
  with self.db.transaction(): self.db.conn.execute('INSERT INTO alternates(bom_item_id,material_id,sort_no) VALUES(?,?,COALESCE((SELECT MAX(sort_no)+1 FROM alternates WHERE bom_item_id=?),0))',(bom_item_id,material_id,bom_item_id))
 def alternates(self,bom_item_id): return self.db.conn.execute('SELECT a.*,m.base_code,m.version,m.name,m.description,m.manufacturer,m.mpn FROM alternates a JOIN materials m ON m.id=a.material_id WHERE a.bom_item_id=? ORDER BY a.sort_no',(bom_item_id,)).fetchall()
 def remove_alternate(self,aid):
  with self.db.transaction(): self.db.conn.execute('DELETE FROM alternates WHERE id=?',(aid,))
 def import_materials(self,path,conflict_resolver=None):
  required=['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN']
  wb=load_workbook(path,read_only=True,data_only=True); ws=wb.active; headers=[str(x or '').strip() for x in next(ws.iter_rows(values_only=True))]
  missing=[x for x in required if x not in headers]
  if missing: raise ValueError('缺少表头：'+ '、'.join(missing))
  idx={h:i for i,h in enumerate(headers)}; ok=[]; fail=[]
  for no,row in enumerate(ws.iter_rows(min_row=2,values_only=True),2):
   d={k:str(row[i] or '').strip() for k,i in idx.items()};
   if not d['物料基础编码'] or not d['物料版本号'] or not d['物料名称'] or not d['单位'] or not d['物料制造商']: fail.append((no,d.get('物料基础编码',''),d.get('物料名称',''),'必填项缺失')); continue
   if d['单位'] not in self.UNITS: fail.append((no,d['物料基础编码'],d['物料名称'],'单位不合规')); continue
   old=self.db.conn.execute('SELECT * FROM materials WHERE base_code=? AND version=?',(d['物料基础编码'],d['物料版本号'])).fetchone()
   if old:
    same=all(str(old[k] or '')==str(d[key] or '') for k,key in [('name','物料名称'),('description','物料规格描述'),('unit','单位'),('manufacturer','物料制造商'),('mpn','物料MPN')])
    if same:
     fail.append((no,d['物料基础编码'],d['物料名称'],'重复物料信息相同，自动跳过')); continue
    choice=conflict_resolver(d,old) if conflict_resolver else 'skip'
    if choice=='cancel': return ok,fail+[(no,d['物料基础编码'],d['物料名称'],'用户取消')]
    if choice=='overwrite':
     self.update_material(old['id'],{'name':d['物料名称'],'description':d['物料规格描述'],'unit':d['单位'],'manufacturer':d['物料制造商'],'mpn':d['物料MPN']}); ok.append(d['物料基础编码']); continue
    fail.append((no,d['物料基础编码'],d['物料名称'],'跳过重复物料')); continue
   try: self.create_material({'base_code':d['物料基础编码'],'version':d['物料版本号'],'name':d['物料名称'],'description':d['物料规格描述'],'unit':d['单位'],'manufacturer':d['物料制造商'],'mpn':d['物料MPN']}); ok.append(d['物料基础编码'])
   except Exception as e: fail.append((no,d['物料基础编码'],d['物料名称'],str(e)))
  return ok,fail
 def export_database(self,path):
  wb=Workbook(); ws=wb.active; ws.title='SKU清单'; ws.append(['序号','SKU编码','SKU名称','SKU描述','修改日期时间'])
  for n,r in enumerate(self.skus(),1): ws.append([n,r['base_code']+'-'+r['version'],r['name'],r['description'],r['updated_at']])
  w=wb.create_sheet('物料库'); w.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN','M/P','是否存在BOM结构'])
  for r in self.materials(): w.append([r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag'],r['has_bom']])
  c=wb.create_sheet('变更记录'); c.append(['序号','变更时间','变更详细内容','变更日期','变更时间'])
  for n,r in enumerate(self.db.conn.execute('SELECT * FROM change_logs ORDER BY id'),1): c.append([n,r['changed_at'],r['detail'],r['changed_at'][:10],r['changed_at'][11:]])
  for r in self.skus():
   b=wb.create_sheet((r['base_code']+'-'+r['version'])[:31]); b.append(['序号','层级','父项编码','父项版本','物料基础编码','物料版本号','物料名称','物料规格描述','用量','单位','M/P','制造商','MPN'])
   for n,x in enumerate(self.bom(r['material_id']),1): b.append([n,x['level_no'],r['base_code'],r['version'],x['base_code'],x['version'],x['name'],x['description'],x['quantity'],x['unit'],x['mp_flag'],x['manufacturer'],x['mpn']])
  for sheet in wb:
   headers=[cell.value for cell in sheet[1]]
   if '用量' in headers:
    for row in sheet.iter_rows(min_row=2): row[headers.index('用量')].number_format='0.0'
  wb.save(path)
 def export_materials(self,path):
  wb=Workbook(); ws=wb.active; ws.title='变更记录'; ws.append(['序号','变更时间','变更详细内容','变更日期','变更时间']); ws2=wb.create_sheet('物料库'); ws2.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN','M/P','是否存在BOM结构']);
  for r in self.materials(): ws2.append([r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag'],r['has_bom']])
  for n,r in enumerate(self.db.conn.execute('SELECT * FROM change_logs ORDER BY id'),1): ws.append([n,r['changed_at'],r['detail'],r['changed_at'][:10],r['changed_at'][11:]])
  for sheet in wb:
   headers=[cell.value for cell in sheet[1]]
   if '用量' in headers:
    for row in sheet.iter_rows(min_row=2): row[headers.index('用量')].number_format='0.0'
  wb.save(path)
 def export_sku(self,sid,path):
  s=self.db.conn.execute('SELECT s.*,m.* FROM skus s JOIN materials m ON m.id=s.material_id WHERE s.id=?',(sid,)).fetchone(); wb=Workbook(); w=wb.active; w.title='变更记录'; w.append(['序号','变更时间','变更详细内容','变更日期','变更时间']); b=wb.create_sheet('SKU对应的BOM'); b.append(['序号','层级','父项编码','父项版本','物料基础编码','物料版本号','物料名称','物料规格描述','用量','单位','M/P','制造商','MPN']);
  for n,r in enumerate(self.bom(s['material_id']),1): b.append([n,r['level_no'],s['base_code'],s['version'],r['base_code'],r['version'],r['name'],r['description'],r['quantity'],r['unit'],r['mp_flag'],r['manufacturer'],r['mpn']])
  for sheet in wb:
   headers=[cell.value for cell in sheet[1]]
   if '用量' in headers:
    for row in sheet.iter_rows(min_row=2): row[headers.index('用量')].number_format='0.0'
  wb.save(path)
