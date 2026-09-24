"""INI配置服务：启动时自动创建配置。输入：应用目录；输出：配置字典。编辑时间：2026-09-24。"""
from configparser import ConfigParser
from pathlib import Path
class ConfigService:
 def __init__(self, base=None): self.base=Path(base or Path.cwd()); self.path=self.base/'config.ini'
 def load(self):
  c=ConfigParser()
  if self.path.exists(): c.read(self.path,encoding='utf-8')
  if not c.has_section('database'): c['database']={"driver":"sqlite","path":str(self.base/'bom.db'),"host":"127.0.0.1","port":"3306","name":"bom"}; self.save(c)
  return c
 def save(self,c):
  self.base.mkdir(parents=True,exist_ok=True)
  with self.path.open('w',encoding='utf-8') as f:c.write(f)
