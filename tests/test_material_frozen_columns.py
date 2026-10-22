import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication,QDialog,QListWidget
from ui.interactive_windows import QDialog
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow

class FrozenColumnsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_frozen_scrolling_selection_filters_and_sku_visibility(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   mids=[s.create_material(dict(base_code=f'CODE{i:02}',version='1',name=f'物料{i}',unit='pcs')) for i in range(40)]
   a=s.create_sku(mids[0]);b=s.create_sku(mids[1]);main=MainWindow(s);main.show_materials();w=main._materials;w.resize(700,350);self.app.processEvents()
   try:
    table=w.t;table.sync_frozen();self.assertEqual(w._column_labels[11],'CODE001\n物料0')
    self.assertIs(table.model(),table.frozen.model());self.assertIs(table.selectionModel(),table.frozen.selectionModel())
    x=table.frozen.x();table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum());self.app.processEvents();self.assertEqual(table.frozen.x(),x)
    self.assertFalse(table.frozen.isColumnHidden(2));self.assertTrue(table.frozen.isColumnHidden(3))
    table.verticalScrollBar().setValue(80);self.assertEqual(table.frozen.verticalScrollBar().value(),table.verticalScrollBar().value())
    self.assertEqual(table.frozen.viewport().mapTo(table,table.frozen.viewport().rect().topLeft()).y(),table.viewport().y())
    table.frozen.setColumnWidth(2,150);self.assertEqual(table.columnWidth(2),150)
    seen=[];table.cellDoubleClicked.connect(lambda r,c:seen.append((r,c)))
    with patch('ui.main_window.MaterialDialog.exec_',return_value=QDialog.Rejected):table.frozen.doubleClicked.emit(table.model().index(0,2))
    self.assertEqual(seen,[(0,2)])
    def choose(dialog):
     items=dialog.findChild(QListWidget);self.assertEqual(items.count(),2);items.item(0).setCheckState(Qt.Unchecked);items.item(1).setCheckState(Qt.Checked);return QDialog.Accepted
    with patch.object(QDialog,'exec_',choose):w.choose_sku_columns()
    self.assertTrue(table.isColumnHidden(11));self.assertFalse(table.isColumnHidden(12))
    with patch.object(QDialog,'exec_',return_value=QDialog.Rejected):w.choose_sku_columns()
    self.assertEqual(w._hidden_skus,{a})
    main.sort_skus(1);main.sort_skus(1);self.assertEqual(w._sku_column_ids,[b,a]);self.assertTrue(table.isColumnHidden(12))
    w._filters[0]=('CODE00',None);w.apply_filters()
    self.assertTrue(table.isRowHidden(1));self.assertTrue(table.frozen.isRowHidden(1))
    s.delete_sku(a);self.assertEqual(w._hidden_skus,set())
   finally:w.close();main.close();db.close()
