"""Comparison-only sticky identity columns; underlying model/order is unchanged."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QTableWidget,QTableView,QAbstractItemView,QFrame

class BomCompareTable(QTableWidget):
    layoutChanged=pyqtSignal()
    FROZEN_COLUMNS=(2,3,4,5)  # serial, parent code, material code, name
    def __init__(self,*args):
        super().__init__(*args)
        self.frozen=QTableView(self);self.frozen.setModel(self.model())
        self.frozen.setSelectionModel(self.selectionModel())
        self.frozen.setFrameShape(QFrame.NoFrame);self.frozen.setFocusPolicy(Qt.NoFocus)
        self.frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.frozen.setSelectionMode(QAbstractItemView.SingleSelection)
        self.frozen.setWordWrap(True);self.frozen.verticalHeader().hide()
        self.frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        for col in range(self.columnCount()):self.frozen.setColumnHidden(col,col not in self.FROZEN_COLUMNS)
        self.frozen.hide()
        self.horizontalScrollBar().valueChanged.connect(self.sync_frozen)
        self.verticalScrollBar().valueChanged.connect(self.frozen.verticalScrollBar().setValue)
        self.frozen.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self.horizontalHeader().sectionResized.connect(self.sync_frozen)
        self.frozen.horizontalHeader().sectionResized.connect(lambda c,o,n:self.setColumnWidth(c,n) if self.columnWidth(c)!=n else None)
        self.verticalHeader().sectionResized.connect(lambda r,o,n:self.frozen.setRowHeight(r,n))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'frozen'):self.sync_frozen()
    def sync_frozen(self,*args):
        threshold=sum(self.columnWidth(c) for c in range(self.FROZEN_COLUMNS[0]))
        active=self.horizontalScrollBar().value()>=threshold
        self.frozen.setVisible(active)
        if not active:return
        natural=sum(self.columnWidth(c) for c in self.FROZEN_COLUMNS)
        available=max(1,self.viewport().width()-80)
        scale=min(1,available/max(1,natural))
        changed=False
        header=self.frozen.horizontalHeader();header.blockSignals(True)
        for col in self.FROZEN_COLUMNS:
            width=max(1,int(self.columnWidth(col)*scale))
            changed=changed or width!=self.frozen.columnWidth(col)
            self.frozen.setColumnWidth(col,width)
        header.blockSignals(False)
        self.frozen.horizontalHeader().setFixedHeight(self.horizontalHeader().height())
        width=sum(self.frozen.columnWidth(c) for c in self.FROZEN_COLUMNS)
        self.frozen.setGeometry(self.viewport().x(),self.frameWidth(),min(width,self.viewport().width()),self.horizontalHeader().height()+self.viewport().height())
        self.frozen.verticalScrollBar().setValue(self.verticalScrollBar().value());self.frozen.raise_()
        if changed:self.layoutChanged.emit()
