import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow
from ui.sku_ecn import EcnDialog,ECN_ROLE
from PyQt5.QtWidgets import QApplication,QDialog
from PyQt5.QtCore import QEvent,Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5 import sip

class SkuEcnTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def dispose_window(self,window):
  # close() only hides a QWidget; release native timers, filters and dialogs
  # while QApplication still exists, rather than during interpreter shutdown.
  window.close();window.deleteLater()
  self.app.sendPostedEvents(None,QEvent.DeferredDelete)
  self.assertTrue(sip.isdeleted(window))
 def test_independent_storage_ui_save_cancel_and_hover(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=str(Path(tmp)/'db');db=Database(path);s=Services(db)
   mid=s.create_material(dict(base_code='R',version='1',name='root',unit='pcs'));sid=s.create_sku(mid);copied=s.copy_sku_bom(sid)
   w=MainWindow(s)
   try:
    self.assertEqual([r['ecn_number'] for r in s.skus()],['/',''])
    self.assertEqual(w.table.horizontalHeaderItem(4).text(),'历史版本号')
    self.assertEqual(w.table.horizontalHeader().visualIndex(8),w.table.horizontalHeader().visualIndex(4)+1)
    def edit(d):d.number.setText('ECN-001');d.name.setText('名称');d.editor.setPlainText('第一行\n第二行 <内容>');return QDialog.Accepted
    with patch.object(EcnDialog,'exec_',edit),patch.object(w,'open_bom') as opened:
     w.sku_double_clicked(0,8);opened.assert_not_called()
    self.assertEqual(s.skus()[0]['ecn_content'],'第一行\n第二行 <内容>');self.assertEqual(s.skus()[1]['ecn_content'],'')
    self.assertEqual(w.table.item(0,8).text(),'ECN-001');self.assertFalse(w.table.item(0,4).font().bold())
    with patch.object(EcnDialog,'exec_',return_value=QDialog.Rejected),patch.object(s,'update_sku_ecn') as save:
     w.edit_sku_ecn(sid);save.assert_not_called()
    w.show();self.app.processEvents();w.table.scrollToItem(w.table.item(0,8));self.app.processEvents()
    point=w.table.visualItemRect(w.table.item(0,8)).center();global_pos=w.table.viewport().mapToGlobal(point)
    event=QMouseEvent(QEvent.MouseMove,point,Qt.NoButton,Qt.NoButton,Qt.NoModifier)
    with patch('ui.sku_ecn.QCursor.pos',return_value=global_pos),patch('ui.sku_ecn.QToolTip.showText') as show:
     self.app.sendEvent(w.table.viewport(),event);QTest.qWait(350);show.assert_not_called();QTest.qWait(220)
     show.assert_called_once();self.assertIn('&lt;内容&gt;',show.call_args.args[1]);self.assertIn('ECN-001',show.call_args.args[1]);self.assertIn('名称',show.call_args.args[1])
     w._ecn_hover.reset();point=w.table.visualItemRect(w.table.item(0,4)).center()
     self.app.sendEvent(w.table.viewport(),QMouseEvent(QEvent.MouseMove,point,Qt.NoButton,Qt.NoButton,Qt.NoModifier));self.assertFalse(w._ecn_hover.timer.isActive())
    s.update_sku_ecn(copied,'E2','','镜像独立内容');w.sort_skus(8);w.refresh()
    for row in range(w.table.rowCount()):self.assertEqual(w.table.item(row,8).text(),'E2' if int(w.table.item(row,6).text())==copied else 'ECN-001')
   finally:self.dispose_window(w);db.close()
   db=Database(path);self.assertEqual(Services(db).skus()[1]['ecn_content'],'镜像独立内容');db.close()
 def test_upgrade_existing_mirror_schema_defaults_blank(self):
  import sqlite3
  with tempfile.TemporaryDirectory() as tmp:
   path=str(Path(tmp)/'db');conn=sqlite3.connect(path)
   conn.execute('CREATE TABLE skus(id INTEGER PRIMARY KEY,material_id INTEGER,updated_at TEXT,mirror_version INTEGER NOT NULL DEFAULT 100,scope_id INTEGER NOT NULL DEFAULT 0,UNIQUE(material_id,mirror_version))')
   conn.execute('INSERT INTO skus VALUES(1,1,NULL,100,0)');conn.commit();conn.close()
   db=Database(path);self.assertEqual(db.conn.execute('SELECT ecn_content FROM skus').fetchone()[0],'');db.close()
 def test_edit_description_keeps_exact_mirror_selection_and_scroll(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   ids=[]
   for i in range(35):
    mid=s.create_material(dict(base_code=f'S{i:03}',version='1',name=f'SKU{i}',unit='pcs'));sid=s.create_sku(mid);ids.append(sid)
   mirror=s.copy_sku_bom(ids[20]);w=MainWindow(s);w.resize(800,450);w.show();self.app.processEvents()
   try:
    w.sort_skus(1);w.sort_skus(1)
    row=next(r for r in range(w.table.rowCount()) if int(w.table.item(r,6).text())==mirror)
    w.table.setCurrentCell(row,8);w.table.selectRow(row);w.table.scrollToItem(w.table.item(row,8));self.app.processEvents()
    before=w.table.verticalScrollBar().value()
    def edit(d):d.editor.setPlainText('修改描述');return QDialog.Accepted
    with patch.object(EcnDialog,'exec_',edit):w.edit_sku_ecn(mirror)
    self.app.processEvents()
    self.assertEqual(int(w.table.item(w.table.currentRow(),6).text()),mirror)
    self.assertEqual(w.table.currentColumn(),8)
    self.assertEqual({int(w.table.item(i.row(),6).text()) for i in w.table.selectedIndexes()},{mirror})
    self.assertEqual(w.table.verticalScrollBar().value(),before)
    self.assertEqual(w.table.item(w.table.currentRow(),8).data(ECN_ROLE).split('\n')[-1],'修改描述')
    w.sort_skus(5);w.sort_skus(5)
    with patch.object(EcnDialog,'exec_',edit):w.edit_sku_ecn(mirror)
    self.app.processEvents();self.assertEqual(int(w.table.item(w.table.currentRow(),6).text()),mirror)
    s.update_sku_ecn(mirror,'E2','','第二次修改');self.app.processEvents()
    self.assertEqual(int(w.table.item(w.table.currentRow(),6).text()),mirror)
   finally:self.dispose_window(w);db.close()
 def test_real_modal_close_focuses_edited_mirror_not_previous_current_item(self):
  from PyQt5.QtCore import QTimer
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   mid=s.create_material(dict(base_code='R',version='1',name='root',unit='pcs'));original=s.create_sku(mid);edited=s.copy_sku_bom(original)
   w=MainWindow(s);w.show();w.activateWindow();self.app.processEvents()
   real_exec=EcnDialog.exec_
   try:
    for accepted in (True,False):
     w.table.setCurrentCell(0,1);w.table.cellWidget(0,0).setFocus()
     def execute(dialog):
      dialog.editor.setPlainText('真实模态窗口保存')
      QTimer.singleShot(0,dialog.accept if accepted else dialog.reject)
      return real_exec(dialog)
     with patch.object(EcnDialog,'exec_',execute):w.edit_sku_ecn(edited)
     QTest.qWait(30)
     self.assertEqual(int(w.table.item(w.table.currentRow(),6).text()),edited)
     self.assertEqual({int(w.table.item(i.row(),6).text()) for i in w.table.selectedIndexes()},{edited})
     self.assertTrue(w.table.hasFocus())
   finally:self.dispose_window(w);db.close()
