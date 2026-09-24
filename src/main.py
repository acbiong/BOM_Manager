"""程序入口：初始化配置、数据库和PyQt主窗口。编辑时间：2026-09-24。"""
import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication,QMessageBox
from config.config_service import ConfigService
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
VERSION='0.0.1'
def main():
 base=Path(__file__).resolve().parents[1]; cfg=ConfigService(base).load(); db=Database(cfg['database']['path']); app=QApplication(sys.argv); w=MainWindow(Services(db),VERSION); w.show(); rc=app.exec_(); db.close(); return rc
if __name__=='__main__':sys.exit(main())
