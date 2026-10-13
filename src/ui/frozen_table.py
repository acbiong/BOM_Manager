"""Shared-model overlay keeps leading material identity columns visible."""
from PyQt5.QtCore import Qt,QEvent,QTimer
from PyQt5.QtWidgets import QTableWidget,QTableView,QAbstractItemView,QFrame

from ui.scrolling_header import ScrollingSkuHeader

class FrozenMaterialTable(QTableWidget):
 def __init__(self,parent=None):
  super().__init__(parent)
  self.setHorizontalHeader(ScrollingSkuHeader(self))
  self.frozen=QTableView(self);self.frozen.setModel(self.model());self.frozen.setSelectionModel(self.selectionModel())
  self.frozen.setFrameShape(QFrame.NoFrame);self.frozen.setFocusPolicy(Qt.NoFocus);self.frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
  self.frozen.setWordWrap(True);self.frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
  self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel);self.frozen.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
  self.frozen.verticalHeader().hide();self.frozen.horizontalHeader().setSectionsClickable(True)
  self.verticalScrollBar().valueChanged.connect(self.frozen.verticalScrollBar().setValue)
  self.frozen.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
  self.horizontalHeader().sectionResized.connect(self.sync_frozen)
  self.frozen.horizontalHeader().sectionResized.connect(lambda col,old,size:self.setColumnWidth(col,size) if self.columnWidth(col)!=size else None)
  self.verticalHeader().sectionResized.connect(lambda row,old,size:self.frozen.setRowHeight(row,size))
  self.frozen.doubleClicked.connect(lambda index:self.cellDoubleClicked.emit(index.row(),index.column()))
  self.frozen.setContextMenuPolicy(Qt.CustomContextMenu)
  self.frozen.customContextMenuRequested.connect(lambda pos:self.customContextMenuRequested.emit(self.viewport().mapFromGlobal(self.frozen.viewport().mapToGlobal(pos))))
  self.frozen.horizontalHeader().sectionClicked.connect(self.horizontalHeader().sectionClicked.emit)
  self.viewport().installEventFilter(self)
  self.model().columnsInserted.connect(self.sync_frozen);self.model().columnsRemoved.connect(self.sync_frozen)
  self.frozen.show()
 def eventFilter(self,obj,event):
  if event.type() in (QEvent.Resize,QEvent.Show):QTimer.singleShot(0,self.sync_frozen)
  return super().eventFilter(obj,event)
 def sync_frozen(self,*args):
  for col in range(self.columnCount()):
   self.frozen.setColumnHidden(col,col>=3)
   if col<3:self.frozen.setColumnWidth(col,self.columnWidth(col))
  for row in range(self.rowCount()):
   self.frozen.setRowHidden(row,self.isRowHidden(row));self.frozen.setRowHeight(row,self.rowHeight(row))
  self.frozen.horizontalHeader().setFixedHeight(self.horizontalHeader().height())
  width=sum(self.columnWidth(col) for col in range(min(3,self.columnCount())))
  self.frozen.setGeometry(self.viewport().x(),self.frameWidth(),min(width,self.viewport().width()),self.horizontalHeader().height()+self.viewport().height())
  self.frozen.verticalScrollBar().setValue(self.verticalScrollBar().value());self.frozen.raise_()
 def scrollTo(self,index,hint=QAbstractItemView.EnsureVisible):
  if index.column()<3:
   old=self.horizontalScrollBar().value();super().scrollTo(index,hint);self.horizontalScrollBar().setValue(old)
  else:super().scrollTo(index,hint)
