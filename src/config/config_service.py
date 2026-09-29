"""INI配置服务：启动时自动创建配置。输入：应用目录；输出：配置字典。编辑时间：2026-09-24。"""
from configparser import ConfigParser
from pathlib import Path
DEFAULT_MATERIAL_UNITS=('pcs','套','ml','L','mm','cm','m','米','M','克','g')

class ConfigService:
 def __init__(self, base=None): self.base=Path(base or Path.cwd()); self.path=self.base/'config.ini'
 def load(self):
  c=ConfigParser(); changed=False
  if self.path.exists(): c.read(self.path,encoding='utf-8')
  if not c.has_section('database'): c['database']={"driver":"sqlite","path":str(self.base/'bom.db'),"host":"127.0.0.1","port":"3306","name":"bom"}; changed=True
  if not c.has_section('materials'):c.add_section('materials'); changed=True
  units=self.parse_units(c.get('materials','units',fallback=''))
  if not units:units=list(DEFAULT_MATERIAL_UNITS); changed=True
  normalized=', '.join(units)
  if c.get('materials','units',fallback='')!=normalized:c.set('materials','units',normalized); changed=True
  if changed:self.save(c)
  return c
 def save(self,c):
  self.base.mkdir(parents=True,exist_ok=True)
  with self.path.open('w',encoding='utf-8') as f:c.write(f)

 @staticmethod
 def parse_units(value):
  return list(dict.fromkeys(unit.strip() for unit in value.replace('，',',').replace('\n',',').split(',') if unit.strip()))
 def material_units(self):return self.parse_units(self.load()['materials']['units'])
 def restore_material_units(self):
  config=self.load(); config['materials']['units']=', '.join(DEFAULT_MATERIAL_UNITS); self.save(config)
  return list(DEFAULT_MATERIAL_UNITS)
