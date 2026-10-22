"""Validate and restore the last project, without silently creating a database."""
from PyQt5.QtWidgets import QMessageBox,QFileDialog,QInputDialog
from ui.interactive_windows import QFileDialog,QInputDialog,QMessageBox
from config.project_registry import ProjectRegistry

def recovery_choice(reason):
 box=QMessageBox();box.setWindowTitle('项目数据库不可用');box.setIcon(QMessageBox.Warning)
 box.setText('无法打开上次的项目数据库，请选择后续操作。');box.setInformativeText(str(reason))
 select=box.addButton('指定数据库',QMessageBox.ActionRole)
 other=box.addButton('打开其他项目',QMessageBox.ActionRole)
 close=box.addButton('关闭项目',QMessageBox.RejectRole);box.setDefaultButton(close);box.exec_()
 return 'select' if box.clickedButton()==select else 'other' if box.clickedButton()==other else 'close'

def occupied_choice(reason,parent=None):
 box=QMessageBox(parent);box.setWindowTitle('当前项目已经被打开');box.setIcon(QMessageBox.Warning)
 box.setText('当前项目已经被其他软件打开，请打开其他项目或关闭项目。');box.setInformativeText(str(reason))
 other=box.addButton('打开其他项目',QMessageBox.ActionRole);close=box.addButton('关闭项目',QMessageBox.RejectRole)
 box.setDefaultButton(close);box.exec_();return 'other' if box.clickedButton()==other else 'close'

def restore_project(config,cfg):
 from main import open_existing_database,selected_database_path,database_error_message
 from ui.snapshot_migration import prepare_snapshot_bom
 from services.services import Services
 from infrastructure.project_lock import ProjectInUseError
 registry=ProjectRegistry(config);value=cfg['database'].get('path','').strip()
 key=cfg.get('projects','active',fallback='') or None
 if not value:return None
 candidate=None
 while True:
  db=None;occupied=False
  try:
   path=selected_database_path(candidate) if candidate else config.resolve_path(value)
   config.relative_path(path)
   db=open_existing_database(path,exclusive=True)
   if not prepare_snapshot_bom(db):raise ValueError('项目数据库结构升级或校验未通过')
   if candidate:
    key=registry.remember(path,dict(Services(db).project()),key=key)
    registry.activate(key)
    latest=config.load();cfg.clear();cfg.read_dict({s:dict(latest[s]) for s in latest.sections()})
   return db
  except Exception as error:
   if db is not None:db.close()
   occupied=isinstance(error,ProjectInUseError)
   reason=database_error_message(error,candidate or value)
  while True:
   choice=occupied_choice(reason) if occupied else recovery_choice(reason)
   if choice=='close':
    latest=config.load();latest['database']['path']=''
    if latest.has_section('projects'):latest.remove_option('projects','active')
    config.save(latest);cfg['database']['path']='';return None
   if choice=='select':
    selected=QFileDialog.getOpenFileName(None,'指定项目数据库',str(config.base),'SQLite (*.db *.sqlite *.sqlite3);;所有文件 (*)')[0]
    if not selected:continue
    candidate=selected;break
   records=registry.entries()
   if not records:
    QMessageBox.information(None,'无历史项目','暂无其他历史项目，请指定已有数据库或关闭项目后新建/导入项目。');continue
   labels=[' '.join(r.get(k,'') for k in ('project_code','project_name')).strip()+' — '+r['path'] for r in records]
   label,ok=QInputDialog.getItem(None,'打开其他项目','请选择项目：',labels,0,False)
   if not ok:continue
   record=records[labels.index(label)];key=record['id'];value=record['path'];candidate=None
   # Activate settings only after the selected database passed validation.
   try:candidate=str(config.resolve_path(value))
   except ValueError:candidate=value
   break
