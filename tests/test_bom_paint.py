import os,sys,unittest
from pathlib import Path
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPainter,QPixmap
from PyQt5.QtWidgets import QApplication,QTreeWidgetItem,QStyleOptionViewItem
from ui.main_window import BomTreeWidget
from infrastructure.operation_progress import _current

class BomPaintTests(unittest.TestCase):
 def test_paint_does_not_dispatch_pending_events_inside_active_painter(self):
  app=QApplication.instance() or QApplication([])
  tree=BomTreeWidget();tree.setColumnCount(5);tree.addTopLevelItem(QTreeWidgetItem(['P100','1','pcs','','']))
  tree.show();app.processEvents();called=[]
  canvas=QPixmap(600,60);painter=QPainter(canvas)
  option=QStyleOptionViewItem();option.rect=canvas.rect()
  QTimer.singleShot(0,lambda:called.append(painter.isActive()))
  token=_current.set(SimpleNamespace(update=lambda *args:app.processEvents()))
  try:
   tree.drawRow(painter,option,tree.model().index(0,0))
   self.assertFalse(called,'queued events ran during tree painting')
  finally:_current.reset(token);painter.end();tree.close()
  app.processEvents();self.assertEqual(called,[False])
