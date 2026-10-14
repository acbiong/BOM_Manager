"""Per-mirror change notes and a deterministic 500 ms version-cell tooltip."""
from html import escape
from PyQt5.QtCore import QObject,QEvent,QTimer,Qt,QPersistentModelIndex
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QPlainTextEdit,QDialogButtonBox,QToolTip

DESCRIPTION_ROLE=Qt.UserRole+20

class ChangeDescriptionDialog(QDialog):
    def __init__(self,text,parent=None):
        super().__init__(parent);self.setWindowTitle('编辑变更描述');self.resize(560,320)
        layout=QVBoxLayout(self);self.editor=QPlainTextEdit();self.editor.setPlainText(text or '')
        self.editor.setPlaceholderText('输入此SKU镜像的变更描述，可分多行填写');layout.addWidget(self.editor)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def description(self):return self.editor.toPlainText()

class VersionDescriptionHover(QObject):
    def __init__(self,table):
        super().__init__(table);self.table=table;self.index=QPersistentModelIndex()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(500);self.timer.timeout.connect(self.show_description)
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
            if not index.isValid() or index.column()!=4 or not str(index.data(DESCRIPTION_ROLE) or '').strip():self.reset();return False
            if self.index!=index:
                self.reset();self.index=QPersistentModelIndex(index);self.timer.start()
        elif event.type() in (QEvent.Leave,QEvent.Hide,QEvent.MouseButtonPress):self.reset()
        return False
    def show_description(self):
        if not self.index.isValid():return
        index=self.table.indexAt(self.table.viewport().mapFromGlobal(QCursor.pos()))
        if self.index!=index:return
        text=str(index.data(DESCRIPTION_ROLE) or '')
        if text.strip():QToolTip.showText(QCursor.pos(),'<div style="white-space:pre-wrap">'+escape(text)+'</div>',self.table)
