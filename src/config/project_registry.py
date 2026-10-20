"""Portable project catalogue stored in the application's config.ini."""
from configparser import ConfigParser
from pathlib import Path
import json
import uuid
from config.config_service import ConfigService

FIELDS=('project_code','project_name','product_name','product_model')
SETTINGS=('materials','import_mappings')
HISTORY=('last_import_dir','last_bom_import_dir','last_compare_bom_file')

class ProjectRegistry:
 def __init__(self,config):self.config=config
 def entries(self):
  c=self.config.load();return [dict(c[s],id=s[8:]) for s in c.sections() if s.startswith('project:')]
 def get(self,key):return next((r for r in self.entries() if r['id']==key),None)
 def settings(self,c=None,source=None):
  c=c or self.config.load();source=source or self.config
  result={s:dict(c[s]) for s in SETTINGS if c.has_section(s)}
  result['database']={}
  for k in HISTORY:
   value=c.get('database',k,fallback='')
   if value:
    try:result['database'][k]=self.config.relative_path(source.resolve_path(value))
    except ValueError:pass
  return result
 def remember(self,path,metadata,key=None,settings=None,active=False):
  c=self.config.load();relative=self.config.relative_path(path)
  if key is None:
   key=next((r['id'] for r in self.entries() if r.get('path')==relative),None) or uuid.uuid4().hex
  section='project:'+key
  previous=dict(c[section]) if c.has_section(section) else {}
  c[section]={**previous,**{k:str(metadata.get(k,'') or '') for k in FIELDS},'path':relative}
  if settings is None and 'settings' not in previous:settings=self.settings(c)
  if settings is not None:c[section]['settings']=json.dumps(settings,ensure_ascii=False)
  if active:
   if not c.has_section('projects'):c.add_section('projects')
   c['projects']['active']=key;c['database']['path']=relative;c.remove_option('projects','excluded_current')
  self.config.save(c);return key
 def activate(self,key):
  c=self.config.load();r=c['project:'+key]
  settings=json.loads(r.get('settings','{}'))
  for section in SETTINGS:
   if section in settings:c[section]=settings[section]
  for field in HISTORY:
   c.remove_option('database',field)
   if settings.get('database',{}).get(field):c['database'][field]=settings['database'][field]
  if not c.has_section('projects'):c.add_section('projects')
  c['projects']['active']=key;c['database']['path']=r['path'];self.config.save(c)
 def delete(self,key):
  c=self.config.load();c.remove_section('project:'+key)
  if c.get('projects','active',fallback='')==key:
   c.remove_option('projects','active');c['projects']['excluded_current']=c['database']['path']
  self.config.save(c)
 def draft(self,metadata=None):
  c=self.config.load()
  if metadata is not None:c['new_project_draft']=metadata;self.config.save(c)
  return dict(c['new_project_draft']) if c.has_section('new_project_draft') else {}
 def clear_draft(self):
  c=self.config.load();c.remove_section('new_project_draft');self.config.save(c)
 def read_import(self,path):
  # Never call load() on the source: importing must not rewrite the old config.
  path=Path(path);c=ConfigParser(interpolation=None)
  with path.open(encoding='utf-8-sig') as stream:c.read_file(stream)
  value=c.get('database','path',fallback='').strip()
  if not value:raise ValueError('所选配置没有SQLite数据库路径')
  if c.get('database','driver',fallback='sqlite').lower() not in ('sqlite','sqlite3'):raise ValueError('只支持SQLite项目配置')
  source=ConfigService(path.parent);target=source.resolve_path(value)
  metadata=dict(c['project']) if c.has_section('project') else {}
  active=c.get('projects','active',fallback='')
  if active and c.has_section('project:'+active):metadata=dict(c['project:'+active])
  return target,metadata,self.settings(c,source)
