"""业务服务层：物料、SKU、BOM、日志和Excel；UI不得直接访问数据库。编辑时间：2026-09-24。"""
from pathlib import Path
from datetime import datetime
from openpyxl import Workbook,load_workbook
class Services:
 UNITS=['pcs','套','ml','L','mm','cm','m']; MP=['M','P']
 def __init__(self,db): self.db=db
 def log(self,typ,obj,act,detail): self.db.conn.execute('INSERT INTO change_logs(object_type,object_id,action,detail) VALUES(?,?,?,?)',(typ,obj,act,detail))
 def materials(self,query=''):
  q=f'%{query}%'; return self.db.conn.execute('SELECT m.*,CASE WHEN EXISTS(SELECT 1 FROM bom_items b WHERE b.material_id=m.id) THEN "N" ELSE "Y" END idle FROM materials m WHERE base_code LIKE ? OR name LIKE ? ORDER BY base_code,version',(q,q)).fetchall()
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
 def delete_material(self,i):
  r=self.db.conn.execute('SELECT COUNT(*) n FROM bom_items WHERE material_id=?',(i,)).fetchone();
  if r['n']: raise ValueError('物料仍被BOM引用，请先删除引用')
  with self.db.transaction(): self.db.conn.execute('DELETE FROM materials WHERE id=?',(i,)); self.log('material',i,'delete','删除物料')
 def skus(self): return self.db.conn.execute('SELECT s.id,m.id AS material_id,m.base_code,m.version,m.name,m.description,m.unit,m.manufacturer,m.mpn,m.mp_flag,m.has_bom,m.updated_at FROM skus s JOIN materials m ON m.id=s.material_id ORDER BY s.id').fetchall()
 def create_sku(self,mid):
  if self.db.conn.execute('SELECT 1 FROM skus WHERE material_id=?',(mid,)).fetchone(): raise ValueError('已是SKU')
  with self.db.transaction(): c=self.db.conn.execute('INSERT INTO skus(material_id) VALUES(?)',(mid,)); self.log('sku',c.lastrowid,'create','创建SKU'); return c.lastrowid
 def delete_sku(self,sid):
  with self.db.transaction(): r=self.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone(); self.db.conn.execute('DELETE FROM bom_items WHERE bom_root_id=?',(r['material_id'],)); self.db.conn.execute('DELETE FROM skus WHERE id=?',(sid,)); self.log('sku',sid,'delete','删除SKU')
 def bom(self,root): return self.db.conn.execute('SELECT b.*,m.base_code,m.version,m.name,m.description,m.unit,m.manufacturer,m.mpn,m.mp_flag FROM bom_items b JOIN materials m ON m.id=b.material_id WHERE b.bom_root_id=? ORDER BY b.level_no,b.sort_no,b.id',(root,)).fetchall()
 def save_bom(self,root,items):
  with self.db.transaction():
   self.db.conn.execute('DELETE FROM bom_items WHERE bom_root_id=?',(root,))
   for n,x in enumerate(items): self.db.conn.execute('INSERT INTO bom_items(bom_root_id,parent_item_id,material_id,quantity,unit,position,level_no,remark,sort_no) VALUES(?,?,?,?,?,?,?,?,?)',(root,x.get('parent_item_id'),x['material_id'],x['quantity'],x['unit'],x.get('position',''),x.get('level_no',1),x.get('remark',''),n))
   self.db.conn.execute('UPDATE materials SET has_bom=1 WHERE id=?',(root,)); self.log('bom',root,'update',f'{len(items)}行')
  try:
   from infrastructure.events import WindowRefreshBus; WindowRefreshBus.publish({'type':'bom_changed','root':root})
  except Exception: pass
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
  r=self.db.conn.execute('SELECT bom_root_id,material_id FROM bom_items WHERE id=?',(bom_item_id,)).fetchone()
  if not r:return
  with self.db.transaction():
   ids=[bom_item_id]
   if recursive:
    frontier=[bom_item_id]
    while frontier:
     children=[x['id'] for x in self.db.conn.execute('SELECT id FROM bom_items WHERE parent_item_id IN (%s)' % ','.join('?'*len(frontier)), frontier)]
     ids.extend(children); frontier=children
   for bid in ids:
    self.db.conn.execute('DELETE FROM alternates WHERE bom_item_id=?',(bid,)); self.db.conn.execute('DELETE FROM bom_items WHERE id=?',(bid,))
   self.log('bom',r['bom_root_id'],'delete',f'删除行{bom_item_id}及下阶{len(ids)-1}行')
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
  w=wb.create_sheet('物料库'); w.append(['序号','物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN','M/P'])
  for n,r in enumerate(self.materials(),1): w.append([n,r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag']])
  c=wb.create_sheet('变更记录'); c.append(['序号','变更时间','变更详细内容','变更日期','变更时间'])
  for n,r in enumerate(self.db.conn.execute('SELECT * FROM change_logs ORDER BY id'),1): c.append([n,r['changed_at'],r['detail'],r['changed_at'][:10],r['changed_at'][11:]])
  for r in self.skus():
   b=wb.create_sheet((r['base_code']+'-'+r['version'])[:31]); b.append(['序号','层级','父项编码','父项版本','物料基础编码','物料版本号','物料名称','物料规格描述','用量','单位','M/P','制造商','MPN'])
   for n,x in enumerate(self.bom(r['material_id']),1): b.append([n,x['level_no'],r['base_code'],r['version'],x['base_code'],x['version'],x['name'],x['description'],x['quantity'],x['unit'],x['mp_flag'],x['manufacturer'],x['mpn']])
  wb.save(path)
 def export_materials(self,path):
  wb=Workbook(); ws=wb.active; ws.title='变更记录'; ws.append(['序号','变更时间','变更详细内容','变更日期','变更时间']); ws2=wb.create_sheet('物料库'); ws2.append(['序号','物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN','M/P']);
  for n,r in enumerate(self.materials(),1): ws2.append([n,r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag']])
  for n,r in enumerate(self.db.conn.execute('SELECT * FROM change_logs ORDER BY id'),1): ws.append([n,r['changed_at'],r['detail'],r['changed_at'][:10],r['changed_at'][11:]])
  wb.save(path)
 def export_sku(self,sid,path):
  s=self.db.conn.execute('SELECT s.*,m.* FROM skus s JOIN materials m ON m.id=s.material_id WHERE s.id=?',(sid,)).fetchone(); wb=Workbook(); w=wb.active; w.title='变更记录'; w.append(['序号','变更时间','变更详细内容','变更日期','变更时间']); b=wb.create_sheet('SKU对应的BOM'); b.append(['序号','层级','父项编码','父项版本','物料基础编码','物料版本号','物料名称','物料规格描述','用量','单位','M/P','制造商','MPN']);
  for n,r in enumerate(self.bom(s['material_id']),1): b.append([n,r['level_no'],s['base_code'],s['version'],r['base_code'],r['version'],r['name'],r['description'],r['quantity'],r['unit'],r['mp_flag'],r['manufacturer'],r['mpn']])
  wb.save(path)
