"""Per-history ECN form and a deterministic 500 ms ECN-cell tooltip."""
from html import escape
from PyQt5.QtCore import QObject,QEvent,QTimer,Qt,QPersistentModelIndex
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QPlainTextEdit,QDialogButtonBox,QToolTip,QLineEdit,QFormLayout,QLabel
from ui.interactive_windows import QDialog

ECN_ROLE=Qt.UserRole+20

class EcnDialog(QDialog):
    def __init__(self,values=('', '', ''),parent=None,readonly=False):
        super().__init__(parent);self.setWindowTitle('ECN内容');self.resize(640,440)
        layout=QVBoxLayout(self);form=QFormLayout()
        self.number=QLineEdit(values[0]);self.name=QLineEdit(values[1]);self.editor=QPlainTextEdit(values[2])
        form.addRow('ECN编号',self.number);form.addRow('ECN名称',self.name);layout.addLayout(form)
        layout.addWidget(QLabel('ECN变更内容'));layout.addWidget(self.editor)
        for field in (self.number,self.name,self.editor):field.setReadOnly(readonly)
        buttons=QDialogButtonBox(QDialogButtonBox.Close if readonly else QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        if readonly:layout.addWidget(QLabel('此BOM已锁定，仅可查看ECN内容。'))
    def values(self):return self.number.text(),self.name.text(),self.editor.toPlainText()

class EcnHover(QObject):
    def __init__(self,table):
        super().__init__(table);self.table=table;self.index=QPersistentModelIndex()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(500);self.timer.timeout.connect(self.show_ecn)
        table.setMouseTracking(True);table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)
        table.horizontalScrollBar().valueChanged.connect(self.reset)
        table.verticalScrollBar().valueChanged.connect(self.reset)
        table.model().modelAboutToBeReset.connect(self.reset)
        table.model().layoutAboutToBeChanged.connect(self.reset)
        table.model().dataChanged.connect(self.reset)
    def reset(self,*args):
        self.timer.stop();self.index=QPersistentModelIndex();QToolTip.hideText()
    def eventFilter(self,watched,event):
        if event.type()==QEvent.ToolTip:return True
        if event.type()==QEvent.MouseMove:
            index=self.table.indexAt(event.pos())
            if not index.isValid() or index.column()!=8 or not str(index.data(ECN_ROLE) or '').strip():self.reset();return False
            if self.index!=index:
                self.reset();self.index=QPersistentModelIndex(index);self.timer.start()
        elif event.type() in (QEvent.Leave,QEvent.Hide,QEvent.MouseButtonPress):self.reset()
        return False
    def show_ecn(self):
        if not self.index.isValid():return
        index=self.table.indexAt(self.table.viewport().mapFromGlobal(QCursor.pos()))
        if self.index!=index:return
        text=str(index.data(ECN_ROLE) or '')
        if text.strip():QToolTip.showText(QCursor.pos(),'<div style="white-space:pre-wrap">'+escape(text)+'</div>',self.table)
