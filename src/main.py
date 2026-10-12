"""程序入口：初始化SQLite和PyQt主窗口，冻结模式下将配置写入可执行文件目录。编辑时间：2026-09-24。"""
import sys, os, traceback, sqlite3, tempfile
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMessageBox, QFileDialog
from config.config_service import ConfigService
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from infrastructure.single_instance import SingleInstance
from version import get_version
VERSION=get_version()
IS_WINDOWS=sys.platform=="win32"
def writable_directory(directory):
 # 用普通命名文件检测；SMB可能不支持TemporaryFile使用的O_TMPFILE。
 try:
  with tempfile.NamedTemporaryFile(prefix='.bom-write-',dir=directory):pass
  return True
 except OSError:return False

def database_creation_directory(requested,config_base):
 for directory in (Path(requested),Path(config_base),Path.home()):
  if directory.is_dir() and writable_directory(directory):return directory
 raise OSError('没有可写的数据库目录，请检查本地用户目录权限')

def app_base():
 if getattr(sys,'frozen',False):
  # 可写的AppImage实际文件所在目录支持便携配置；只读挂载目录则回退到用户目录。
  image_path=os.environ.get('APPIMAGE')
  image_dir=Path(image_path).expanduser().resolve().parent if image_path else (Path(sys.executable).resolve().parent if IS_WINDOWS else None)
  writable=bool(image_dir and writable_directory(image_dir))
  if writable:
   root=image_dir
  else:
   root=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local') if IS_WINDOWS else os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'BOM管理系统'
  root.mkdir(parents=True,exist_ok=True)
  return root
 return Path(__file__).resolve().parents[1]
def open_existing_database(path):
 path=Path(path).expanduser().resolve()
 if not path.is_file():raise ValueError(f'数据库文件不存在：{path}')
 if path.stat().st_size==0:raise ValueError('数据库文件为空，无法使用')
 # 验证阶段只读，禁止SQLite自动创建文件或修复不相关数据库。
 connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
 try:
  result=connection.execute('PRAGMA integrity_check').fetchall()
  if result!=[('ok',)]:raise ValueError('数据库完整性检查失败：'+str(result[:5]))
  required={
   'materials':'id,base_code,version,name,description,unit,manufacturer,mpn,mp_flag,has_bom,created_at,updated_at',
   'skus':'id,material_id,updated_at',
   'bom_items':'id,bom_root_id,parent_item_id,material_id,quantity,unit,position,level_no,remark,sort_no',
   'alternates':'id,bom_item_id,material_id,sort_no',
   'change_logs':'id,object_type,object_id,action,detail,changed_at',
   'project':'id,project_name,project_code,product_name,product_model'}
  for table,columns in required.items():connection.execute(f'SELECT {columns} FROM {table} LIMIT 0')
  if connection.execute('SELECT 1 FROM project WHERE id=1').fetchone() is None:raise ValueError('数据库缺少项目信息')
  tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if 'material_bom_items' in tables:connection.execute('SELECT id,parent_material_id,child_material_id,quantity,unit,position,remark,sort_no,created_at,updated_at FROM material_bom_items LIMIT 0')
 finally:connection.close()
 return Database(str(path))

def choose_database_recovery(reason):
 box=QMessageBox(); box.setWindowTitle('数据库不可用'); box.setIcon(QMessageBox.Warning)
 box.setText('数据库不存在或无法使用，请新建数据库或选择已有数据库。'); box.setInformativeText(str(reason))
 create=box.addButton('新建数据库',QMessageBox.ActionRole); select=box.addButton('选择数据库',QMessageBox.ActionRole); box.addButton('退出',QMessageBox.RejectRole); box.exec_()
 return 'create' if box.clickedButton()==create else 'select' if box.clickedButton()==select else None

def startup_database(config_service,cfg):
 path=Path(cfg['database'].get('path','bom.db')).expanduser()
 if not path.is_absolute():path=config_service.base/path
 try:return open_existing_database(path)
 except (OSError,sqlite3.Error,ValueError) as error:reason=str(error)
 while True:
  choice=choose_database_recovery(reason)
  if choice is None:return None
  start=str(database_creation_directory(path.parent,config_service.base) if choice=='create' else (path.parent if path.parent.is_dir() else config_service.base))
  if choice=='create':
   selected=QFileDialog.getSaveFileName(None,'新建SQLite数据库（可自行命名）',str(Path(start)/'bom.db'),'SQLite数据库 (*.db *.sqlite);;所有文件 (*)',options=QFileDialog.DontConfirmOverwrite|QFileDialog.DontUseNativeDialog)[0]
  else:selected=QFileDialog.getOpenFileName(None,'选择已有SQLite数据库',start,'SQLite数据库 (*.db *.sqlite);;所有文件 (*)',options=QFileDialog.DontUseNativeDialog)[0]
  if not selected:continue
  candidate=Path(selected).expanduser().resolve(); db=None
  try:
   if choice=='create':
    if not writable_directory(candidate.parent):raise PermissionError('所选目录为只读或无写入权限，无法新建数据库：'+str(candidate.parent)+'。请选择本地可写目录；下次选择窗口将自动回到可写目录。')
    # 排他创建占位文件，防止同名数据库被覆盖；只有用户选择新建才创建。
    with candidate.open('xb'):pass
    try:db=Database(str(candidate))
    except Exception:
     candidate.unlink(missing_ok=True); raise
   else:db=open_existing_database(candidate)
   cfg['database']['path']=str(candidate); config_service.save(cfg)
   return db
  except (OSError,sqlite3.Error,ValueError) as error:
   if db is not None:db.close()
   reason=('同名文件已存在，请选择其他名称或使用“选择数据库”。' if isinstance(error,FileExistsError) else str(error))
   path=candidate

def main():
 app=QApplication(sys.argv); guard=SingleInstance(); db=None; base=None
 try:
  if not guard.acquire():
   if not guard.notify_existing():QMessageBox.information(None,'软件已运行','该目录下的BOM管理系统已在运行或正在启动，请切换到已有窗口。')
   return 0
  base=app_base()
  config_service=ConfigService(base); cfg=config_service.load()
  if getattr(sys,'frozen',False) and os.environ.get('APPIMAGE') and base!=Path(os.environ['APPIMAGE']).resolve().parent:
   QMessageBox.information(None,'使用本地配置目录','软件所在目录为只读或无写入权限（网络共享可能以只读方式挂载）。\n配置保存在：'+str(config_service.path)+'\n新建数据库将默认使用可写目录，您也可以自行选择其他可写位置。')
  db=startup_database(config_service,cfg)
  if db is None:return 0
  w=MainWindow(Services(db,config_service),VERSION); w.show(); guard.set_window(w); return app.exec_()
 except Exception as exc:
  log=(base or Path(tempfile.gettempdir()))/'startup_error.log'
  try: log.write_text(traceback.format_exc(),encoding='utf-8')
  except OSError:
   log=Path(tempfile.gettempdir())/'BOM管理系统_startup_error.log'
   try:log.write_text(traceback.format_exc(),encoding='utf-8')
   except OSError:pass
  QMessageBox.critical(None,'BOM管理系统启动失败',f'{exc}\n\n详细信息已写入：{log}')
  return 1
 finally:
  try:
   if db is not None:db.close()
  finally:guard.close()
if __name__=='__main__':
 if '--smoke-test-report' in sys.argv:
  from infrastructure.smoke_test import run_smoke_test
  sys.exit(run_smoke_test(sys.argv[sys.argv.index('--smoke-test-report')+1]))
 sys.exit(main())
