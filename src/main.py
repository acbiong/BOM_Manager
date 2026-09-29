"""程序入口：初始化SQLite和PyQt主窗口，冻结模式下将配置写入可执行文件目录。编辑时间：2026-09-24。"""
import sys, os, traceback
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMessageBox
from config.config_service import ConfigService
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from version import get_version
VERSION=get_version()
def app_base():
 if getattr(sys,'frozen',False):
  # AppImage内容挂载在只读临时目录，配置、数据库和错误日志不能写入该目录。
  # 使用用户配置目录，避免文件管理器直接启动时因写日志失败而静默退出。
  root=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'BOM管理系统'
  root.mkdir(parents=True,exist_ok=True)
  return root
 return Path(__file__).resolve().parents[1]
def main():
 app=QApplication(sys.argv); base=app_base()
 try:
  cfg=ConfigService(base).load(); db=Database(cfg['database']['path']); valid,missing=db.validate_schema()
  if not valid: db.recreate_schema()
  w=MainWindow(Services(db),VERSION); w.show(); rc=app.exec_(); db.close(); return rc
 except Exception as exc:
  log=base/'startup_error.log'
  try: log.write_text(traceback.format_exc(),encoding='utf-8')
  except OSError:
   log=Path(os.environ.get('TMPDIR','/tmp'))/'BOM管理系统_startup_error.log'
   log.write_text(traceback.format_exc(),encoding='utf-8')
  QMessageBox.critical(None,'BOM管理系统启动失败',f'{exc}\n\n详细信息已写入：{log}')
  return 1
if __name__=='__main__': sys.exit(main())
