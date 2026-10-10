"""宽窗口比例扩展与窄窗口默认列宽/滚动条回归。"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QTableWidget,QTableWidgetItem,QTreeWidget,QTreeWidgetItem
from ui.table_layout import fit_columns

class TableLayoutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def settle(self):
  for _ in range(6):self.app.processEvents()
 def test_table_and_tree_fill_then_scroll_without_shrinking_defaults(self):
  for tree in (False,True):
   with self.subTest(tree=tree):
    widget=QTreeWidget() if tree else QTableWidget(1,3)
    try:
     widget.setColumnCount(3)
     if tree:
      widget.setHeaderLabels(['编码','名称','规格']);QTreeWidgetItem(widget,['A','物料名称较长','规格'*15])
     else:
      widget.setHorizontalHeaderLabels(['编码','名称','规格'])
      for col,text in enumerate(['A','物料名称较长','规格'*15]):widget.setItem(0,col,QTableWidgetItem(text))
     widget.resize(500,200);widget.show();fit_columns(widget);self.settle()
     base=widget._proportional_columns.widths.copy();total=sum(base.values())
     widget.resize(total+450,250);self.settle()
     header=widget.header() if tree else widget.horizontalHeader()
     widths=[header.sectionSize(i) for i in range(3)]
     self.assertEqual(sum(widths),widget.viewport().width())
     ratios=[widths[i]/base[i] for i in range(3)]
     self.assertLess(max(ratios)-min(ratios),0.05)
     widget.resize(200,250);self.settle()
     self.assertEqual([header.sectionSize(i) for i in range(3)],list(base.values()))
     self.assertGreater(widget.horizontalScrollBar().maximum(),0)
     self.assertTrue(widget.horizontalScrollBar().isVisible())
    finally:widget.close()
