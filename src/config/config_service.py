"""INI配置服务：启动时自动创建配置。输入：应用目录；输出：配置字典。编辑时间：2026-09-24。"""
from configparser import ConfigParser
from pathlib import Path, PureWindowsPath
import ntpath
import posixpath
import re
DEFAULT_MATERIAL_UNITS=('pcs','套','ml','L','mm','cm','m','米','M','克','g')

def relative_config_path(value, base):
 """Return a portable relative spelling; never guess foreign drive/mount mappings."""
 value=str(value).replace('\\','/'); base=str(base).replace('\\','/')
 if not value:return ''
 if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://',value):
  raise ValueError('配置路径不能使用URI，请选择本地文件或本机挂载路径')
 windows=bool(PureWindowsPath(base).drive)
 flavor=ntpath if windows else posixpath
 drive=PureWindowsPath(value).drive
 if drive and not windows:
  raise ValueError('配置包含Windows绝对路径，无法在当前系统定位，请重新选择数据库并保存相对路径')
 if windows and ((drive and not ntpath.isabs(value)) or (value.startswith('/') and not drive)):
  raise ValueError('配置路径不属于当前系统或缺少完整盘符，请重新选择数据库')
 target=value if flavor.isabs(value) else flavor.join(base,value)
 try:return flavor.relpath(flavor.normpath(target),base).replace('\\','/')
 except ValueError as error:
  raise ValueError('数据库与config.ini位于不同盘符或共享根目录，无法保存相对路径；请将数据库放到配置文件同一盘符（建议同一文件夹）后重新选择') from error

class ConfigService:
 def __init__(self, base=None): self.base=Path(base or Path.cwd()).expanduser().resolve(); self.path=self.base/'config.ini'
 def load(self):
  c=ConfigParser(interpolation=None); changed=False
  if self.path.exists(): c.read(self.path,encoding='utf-8')
  if not c.has_section('database'): c['database']={"driver":"sqlite","path":"bom.db","host":"127.0.0.1","port":"3306","name":"bom"}; changed=True
  if not c.has_section('materials'):c.add_section('materials'); changed=True
  units=self.parse_units(c.get('materials','units',fallback=''))
  if not units:units=list(DEFAULT_MATERIAL_UNITS); changed=True
  normalized=', '.join(units)
  if c.get('materials','units',fallback='')!=normalized:c.set('materials','units',normalized); changed=True
  # Migrate native legacy paths; foreign absolute paths stay visible for recovery.
  before=dict(c['database'])
  self._normalize_paths(c,strict=False)
  if dict(c['database'])!=before:changed=True
  if changed:self._write(c)
  return c
 def relative_path(self,value):
  value=str(value)
  if value.startswith('~'):value=str(Path(value).expanduser())
  return relative_config_path(value,self.base)
 def resolve_path(self,value):
  return (self.base/self.relative_path(value)).resolve()
 def _normalize_paths(self,c,strict=True):
  if not c.has_section('database'):return
  for key in ('path','last_import_dir','last_bom_import_dir'):
   value=c['database'].get(key,'')
   if not value:continue
   try:c['database'][key]=self.relative_path(value)
   except ValueError:
    if key in ('last_import_dir','last_bom_import_dir'):c.remove_option('database',key)
    elif strict:raise
 def save(self,c):
  self._normalize_paths(c)
  self._write(c)
 def _write(self,c):
  self.base.mkdir(parents=True,exist_ok=True)
  with self.path.open('w',encoding='utf-8') as f:c.write(f)

 @staticmethod
 def parse_units(value):
  return list(dict.fromkeys(unit.strip() for unit in value.replace('，',',').replace('\n',',').split(',') if unit.strip()))
 def material_units(self):return self.parse_units(self.load()['materials']['units'])
 def restore_material_units(self):
  config=self.load(); config['materials']['units']=', '.join(DEFAULT_MATERIAL_UNITS); self.save(config)
  return list(DEFAULT_MATERIAL_UNITS)

 def import_mapping(self,kind):
  import json
  if kind not in ('materials','bom'):raise ValueError('未知导入类型')
  raw=self.load().get('import_mappings',kind,fallback='')
  try:mapping=json.loads(raw)
  except (ValueError,TypeError):return {}
  return mapping if isinstance(mapping,dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in mapping.items()) else {}
 def save_import_mapping(self,kind,mapping):
  import json
  if kind not in ('materials','bom'):raise ValueError('未知导入类型')
  config=self.load()
  if not config.has_section('import_mappings'):config.add_section('import_mappings')
  config['import_mappings'][kind]=json.dumps(mapping,ensure_ascii=False)
  self.save(config)

 def _sku_columns_key(self,database):
  import hashlib
  # Relative database identity remains portable when the project folder moves.
  identity=self.relative_path(database)
  return hashlib.sha256(identity.encode('utf-8')).hexdigest()
 def sku_columns(self,database):
  import json
  try:
   value=json.loads(self.load().get('sku_columns',self._sku_columns_key(database),fallback='[]'))
   return set(value) if isinstance(value,list) and all(type(v) is int for v in value) else set()
  except (ValueError,TypeError):return set()
 def save_sku_columns(self,database,selected):
  import json
  config=self.load()
  if not config.has_section('sku_columns'):config.add_section('sku_columns')
  config['sku_columns'][self._sku_columns_key(database)]=json.dumps(sorted(selected))
  self.save(config)
