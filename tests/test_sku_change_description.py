import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from ui.sku_change_description import ChangeDescriptionDialog,DESCRIPTION_ROLE
from PyQt5.QtWidgets import QApplication,QDialog
from PyQt5.QtCore import QEvent,Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtTest import QTest

class SkuDescriptionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_independent_storage_ui_save_cancel_clear_and_hover(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=str(Path(tmp)/'db');db=Database(path);s=Services(db)
   mid=s.create_material(dict(base_code='R',version='1',name='root',unit='pcs'));sid=s.create_sku(mid);copied=s.copy_sku_bom(sid)
   w=MainWindow(s)
   try:
    def edit(d):d.editor.setPlainText('第一行\n第二行 <内容>');return QDialog.Accepted
    with patch.object(ChangeDescriptionDialog,'exec_',edit):w.edit_sku_change_description(sid)
    self.assertEqual(s.skus()[0]['change_description'],'第一行\n第二行 <内容>');self.assertEqual(s.skus()[1]['change_description'],'')
    self.assertEqual(w.table.item(0,4).data(DESCRIPTION_ROLE),'第一行\n第二行 <内容>')
    with patch.object(ChangeDescriptionDialog,'exec_',return_value=QDialog.Rejected),patch.object(s,'update_sku_change_description') as save:
     w.edit_sku_change_description(sid);save.assert_not_called()
    w.show();self.app.processEvents();point=w.table.visualItemRect(w.table.item(0,4)).center();global_pos=w.table.viewport().mapToGlobal(point)
    event=QMouseEvent(QEvent.MouseMove,point,Qt.NoButton,Qt.NoButton,Qt.NoModifier)
    with patch('ui.sku_change_description.QCursor.pos',return_value=global_pos),patch('ui.sku_change_description.QToolTip.showText') as show:
     self.app.sendEvent(w.table.viewport(),event);QTest.qWait(350);show.assert_not_called();QTest.qWait(220)
     show.assert_called_once();self.assertIn('&lt;内容&gt;',show.call_args.args[1])
     w._description_hover.reset();s.update_sku_change_description(sid,'')
     self.app.sendEvent(w.table.viewport(),event);self.assertFalse(w._description_hover.timer.isActive())
    s.update_sku_change_description(copied,'镜像独立备注')
   finally:w.close();db.close()
   db=Database(path);self.assertEqual(Services(db).skus()[1]['change_description'],'镜像独立备注');db.close()
 def test_upgrade_existing_mirror_schema_defaults_blank(self):
  import sqlite3
  with tempfile.TemporaryDirectory() as tmp:
   path=str(Path(tmp)/'db');conn=sqlite3.connect(path)
   conn.execute('CREATE TABLE skus(id INTEGER PRIMARY KEY,material_id INTEGER,updated_at TEXT,mirror_version INTEGER NOT NULL DEFAULT 100,scope_id INTEGER NOT NULL DEFAULT 0,UNIQUE(material_id,mirror_version))')
   conn.execute('INSERT INTO skus VALUES(1,1,NULL,100,0)');conn.commit();conn.close()
   db=Database(path);self.assertEqual(db.conn.execute('SELECT change_description FROM skus').fetchone()[0],'');db.close()
