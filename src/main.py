"""程序入口：初始化配置、数据库和PyQt主窗口。编辑时间：2026-09-24。"""
import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication,QMessageBox
from config.config_service import ConfigService
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from version import get_version
VERSION=get_version()
def main():
 base=Path(__file__).resolve().parents[1]; cfg=ConfigService(base).load(); db=Database(cfg['database']['path']); valid,missing=db.validate_schema(); app=QApplication(sys.argv);
 if not valid:
  QMessageBox.warning(None,'数据库结构异常','缺少数据表：'+','.join(missing)+'，将自动修复。'); db.recreate_schema()
 w=MainWindow(Services(db),VERSION); w.show(); rc=app.exec_(); db.close(); return rc
if __name__=='__main__':sys.exit(main())
