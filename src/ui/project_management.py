"""Project menu and safe database handover for the SKU window."""
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMenu,QFileDialog,QDialog,QMessageBox
from config.config_service import ConfigService
from config.project_registry import ProjectRegistry,FIELDS
from database.database import Database

class ProjectManagement:
 def setup_projects(self,file_menu,project_menu):
  self.svc.config_service=self.svc.config_service or ConfigService(Path(self.svc.db.path).parent)
  self.projects=ProjectRegistry(self.svc.config_service)
  config=self.svc.config_service.load()
  excluded=config.get('projects','excluded_current',fallback='')
  self._project_id=None if excluded==self.svc.config_service.relative_path(self.svc.db.path) else self.projects.remember(self.svc.db.path,dict(self.svc.project()),settings=self.projects.settings(),active=True)
  file_menu.addAction('导入项目数据库',self.import_project_database)
  project_menu.addAction('新增项目',self.new_project)
  project_menu.addAction('导入项目',self.import_project)
  self.history_menu=project_menu.addMenu('打开历史项目')
  self.history_menu.aboutToShow.connect(self.refresh_project_menu)
  self.history_menu.setContextMenuPolicy(Qt.CustomContextMenu)
  self.history_menu.customContextMenuRequested.connect(self.project_context_menu)
  project_menu.addSeparator()
 def refresh_project_menu(self):
  self.history_menu.clear()
  for record in self.projects.entries():
   label=' '.join(record.get(k,'').strip() for k in ('project_code','project_name')).strip() or '未命名项目'
   action=self.history_menu.addAction(label);action.setData(record['id']);action.setCheckable(True);action.setChecked(record['id']==self._project_id)
   action.triggered.connect(lambda checked=False,key=record['id']:self.open_history_project(key))
  if not self.history_menu.actions():self.history_menu.addAction('暂无历史项目').setEnabled(False)
 def project_context_menu(self,pos):
  action=self.history_menu.actionAt(pos)
  if action is None or not action.data():return
  menu=QMenu(self.history_menu);delete=menu.addAction('删除历史项目')
  if menu.exec_(self.history_menu.mapToGlobal(pos))==delete:self.delete_history_project(action.data())
 def delete_history_project(self,key):
  record=self.projects.get(key)
  if not record:return
  if QMessageBox.question(self,'删除历史项目','仅从历史项目列表移除“'+record.get('project_code','')+' '+record.get('project_name','')+'”，不会删除数据库文件。是否继续？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
  self.projects.delete(key)
  if self._project_id==key:self._project_id=None
  self.refresh_project_menu()
 def remember_current_project(self):
  if self._project_id:
   self.projects.remember(self.svc.db.path,dict(self.svc.project()),key=self._project_id,settings=self.projects.settings(),active=True)
 def choose_project_database(self,title='选择项目数据库'):
  return QFileDialog.getOpenFileName(self,title,str(self.svc.config_service.base),'SQLite (*.db *.sqlite *.sqlite3);;所有文件 (*)')[0]
 def open_history_project(self,key):
  record=self.projects.get(key)
  if not record:return
  try:path=self.svc.config_service.resolve_path(record['path'])
  except ValueError:path=None
  if path is None or not path.is_file():
   box=QMessageBox(self);box.setWindowTitle('项目数据库不存在');box.setText('找不到项目数据库：\n'+record.get('path','')+'\n请手动指定数据库、删除历史项目或取消。')
   select=box.addButton('指定数据库',QMessageBox.ActionRole);delete=box.addButton('删除历史项目',QMessageBox.DestructiveRole);box.addButton('取消',QMessageBox.RejectRole);box.exec_()
   if box.clickedButton()==delete:self.delete_history_project(key);return
   if box.clickedButton()!=select:return
   path=self.choose_project_database()
   if not path:return
  self.switch_project(path,key=key)
 def import_project_database(self):
  path=self.choose_project_database('导入项目数据库')
  if path:self.switch_project(path)
 def import_project(self):
  path=QFileDialog.getOpenFileName(self,'选择原项目config文件',str(self.svc.config_service.base),'配置文件 (*.ini);;所有文件 (*)')[0]
  if not path:return
  try:database,metadata,settings=self.projects.read_import(path)
  except Exception as error:QMessageBox.warning(self,'导入项目失败',str(error));return
  self.switch_project(database,metadata=metadata,settings=settings)
 def new_project(self):
  from ui.main_window import ProjectDialog
  dialog=ProjectDialog(self,self.projects.draft());dialog.setWindowTitle('请填写新项目信息')
  while True:
   if dialog.exec_()!=QDialog.Accepted:return
   metadata=dialog.data();self.projects.draft(metadata)
   if metadata['project_code'] and metadata['project_name']:break
   QMessageBox.warning(self,'项目信息不完整','请填写项目代码和项目名称。')
  chooser=QFileDialog(self,'创建新项目数据库',str(self.svc.config_service.base),'SQLite (*.db *.sqlite)')
  chooser.setFileMode(QFileDialog.AnyFile);chooser.setAcceptMode(QFileDialog.AcceptSave);chooser.setDefaultSuffix('db')
  chooser.setOption(QFileDialog.DontUseNativeDialog,True);chooser.setOption(QFileDialog.DontConfirmOverwrite,True)
  if chooser.exec_()!=QDialog.Accepted:return
  paths=chooser.selectedFiles()
  if paths and self.switch_project(paths[0],metadata=metadata,create=True):self.projects.clear_draft()
 def switch_project(self,path,key=None,metadata=None,settings=None,create=False):
  from main import open_existing_database,selected_database_path
  from ui.snapshot_migration import prepare_snapshot_bom
  candidate=None;created_path=None
  try:
   path=selected_database_path(str(path));self.svc.config_service.relative_path(path)
   if create and path.exists():raise ValueError('目标文件已存在，请为新项目选择一个未使用的数据库文件名。不会覆盖已有文件。')
   if path==Path(self.svc.db.path).resolve():
    if metadata:
     current=dict(self.svc.project());current.update({k:metadata[k] for k in FIELDS if k in metadata});self.svc.update_project(current)
    self._project_id=self.projects.remember(path,dict(self.svc.project()),key=key,settings=settings or self.projects.settings(),active=True)
    if settings:self.projects.activate(self._project_id);self.svc.UNITS=self.svc.config_service.material_units()
    self.refresh();return True
   if create:
    # Exclusive creation prevents accidentally opening/overwriting a competing file.
    with path.open('xb'):pass
    created_path=path
    candidate=Database(str(path))
   else:candidate=open_existing_database(path)
   if not prepare_snapshot_bom(candidate,self):return False
   windows=set(self._material_bom_windows.values())|set(self._bom_windows.values())
   if self._materials is not None:windows.update(self._materials._local_bom_windows.values())
   for window in windows:
    if not window.close():return False
   self.remember_current_project()
   from services.services import Services
   target=Services(candidate,self.svc.config_service)
   if metadata:
    values=dict(target.project());values.update({k:metadata[k] for k in FIELDS if k in metadata});target.update_project(values)
   new_key=self.projects.remember(path,dict(target.project()),key=key,settings=settings)
   self.projects.activate(new_key)
   if getattr(self,'_compare_dialog',None):self._compare_dialog.close();self._compare_dialog.deleteLater();self._compare_dialog=None
   if self._materials is not None:self._materials.close()
   if getattr(self,'_create_material_dialog',None):self._create_material_dialog.reject()
   old=self.svc.db;self.svc.db=candidate;candidate=None;created_path=None;old.close()
   self.svc.UNITS=self.svc.config_service.material_units();self._project_id=new_key
   self._sku_filters={};self.refresh();return True
  except Exception as error:
   QMessageBox.critical(self,'项目数据库错误','项目未切换，请重新选择可用的数据库。\n\n'+str(error));return False
  finally:
   if candidate is not None:candidate.close()
   if created_path is not None:created_path.unlink(missing_ok=True)
