"""Fresh startup/switch creates one database; real migrations retain recovery backups."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QDialog,QFileDialog,QMessageBox
from ui.interactive_windows import QFileDialog,QMessageBox
from config.config_service import ConfigService
from database.database import Database
from services.services import Services
from services.snapshot_bom import migrate
from services.current_catalog import initialize,enabled
from ui.snapshot_migration import prepare_snapshot_bom
from ui.main_window import MainWindow
import main


class DatabaseCreationFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_startup_and_reopen_leave_only_requested_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);data=base/'数据库';data.mkdir();target=data/'新项目.sqlite'
            config=ConfigService(base);cfg=config.load();cfg['database']['path']='bom.db'
            with patch.object(main,'choose_database_recovery',return_value='create'),patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):
                db=main.startup_database(config,cfg)
            try:
                self.assertTrue(prepare_snapshot_bom(db))
                self.assertTrue(enabled(Services(db)))
                self.assertEqual(db.conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(list(data.iterdir()),[target])
            finally:db.close()
            with patch.object(main,'choose_database_recovery') as choose:
                db=main.startup_database(config,config.load())
            try:
                self.assertTrue(prepare_snapshot_bom(db));choose.assert_not_called()
            finally:db.close()
            self.assertEqual(list(data.iterdir()),[target])

    def test_switch_to_new_database_does_not_create_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);data=base/'new';data.mkdir();target=data/'selected.db'
            config=ConfigService(base);config.load();svc=Services(Database(str(base/'old.db')),config)
            window=MainWindow(svc)
            try:
                with patch.object(QFileDialog,'exec_',return_value=QDialog.Accepted),patch.object(QFileDialog,'selectedFiles',return_value=[str(target)]),patch.object(QMessageBox,'information'),patch.object(QMessageBox,'critical') as error:
                    window.select_database()
                error.assert_not_called();self.assertEqual(Path(svc.db.path),target)
                self.assertTrue(enabled(svc));self.assertEqual(list(data.iterdir()),[target])
            finally:window.close();svc.db.close()
            self.assertEqual(list(data.iterdir()),[target])

    def test_populated_legacy_database_keeps_backup_and_stops_if_backup_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'legacy.db';db=Database(str(target))
            try:
                svc=Services(db);mid=svc.create_material(dict(base_code='OLD',version='1',name='旧物料',unit='pcs'))
                migrate(db)
                with patch('services.current_catalog.sqlite3.connect',side_effect=OSError('backup denied')):
                    with self.assertRaisesRegex(OSError,'backup denied'):initialize(db)
                self.assertFalse(enabled(svc));self.assertEqual(svc.material_snapshot(mid)['name'],'旧物料')
                initialize(db)
                backups=list(Path(tmp).glob('*.pre-latest-catalog-*.db'));self.assertEqual(len(backups),1)
                backup=sqlite3.connect(backups[0])
                try:
                    self.assertEqual(backup.execute('SELECT name FROM materials').fetchone()[0],'旧物料')
                    self.assertIsNone(backup.execute('SELECT 1 FROM app_metadata WHERE key=?',('latest_mirror_catalog_v1',)).fetchone())
                finally:backup.close()
                initialize(db);self.assertEqual(list(Path(tmp).glob('*.pre-latest-catalog-*.db')),backups)
            finally:db.close()
