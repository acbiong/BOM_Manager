"""Independent nonmodal interaction windows with compatible result APIs.

A local event loop preserves the existing validation/transaction continuation,
while show() (never Qt's modal exec) leaves every other window interactive.
Native transient ownership is cleared without losing Python/Qt lifetime ownership.
"""
from PyQt5 import sip
from PyQt5.QtCore import Qt, QEventLoop, QObject, QEvent
from PyQt5.QtWidgets import (QDialog as QtDialog, QMainWindow as QtMainWindow,
    QInputDialog as QtInputDialog, QFileDialog as QtFileDialog,
    QColorDialog as QtColorDialog, QMessageBox as QtMessageBox,
    QProgressDialog as QtProgressDialog, QLineEdit)
from PyQt5.QtGui import QColor


class IndependentWindow:
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setWindowFlags((self.windowFlags() & ~Qt.WindowType_Mask & ~Qt.WindowStaysOnTopHint) | Qt.Window)
        self.setWindowModality(Qt.NonModal)

    def show(self):
        self.setWindowModality(Qt.NonModal)
        super().show()

    def showEvent(self,event):
        super().showEvent(event)
        handle=self.windowHandle()
        if handle is not None:handle.setTransientParent(None)


class OwnerGuard(QObject):
    def __init__(self,dialog):
        super().__init__(dialog);self.dialog=dialog;self.owner=dialog.parentWidget()
        self.service=getattr(self.owner,'svc',None)
        self.database=getattr(self.service,'db',None)
        if self.owner is not None:self.owner.installEventFilter(self)

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Close:self.dialog.reject()
        return False

    def valid(self):
        if self.owner is None:return True
        return (not sip.isdeleted(self.owner) and
                getattr(self.owner,'svc',None) is self.service and
                getattr(self.service,'db',None) is self.database)


class ResultWindow(IndependentWindow):
    def exec_(self):
        if getattr(self,'_waiting_result',False):return QtDialog.Rejected
        self._waiting_result=True;self._context_valid=True
        loop=QEventLoop();guard=OwnerGuard(self)
        result=[QtDialog.Rejected]
        def finished(value):result[0]=value;loop.quit()
        self.finished.connect(finished);self.destroyed.connect(loop.quit)
        self.setAttribute(Qt.WA_DeleteOnClose,False)
        self.setResult(QtDialog.Rejected)
        try:
            self.show();self.raise_();self.activateWindow()
            if self.isVisible():loop.exec_()
            if sip.isdeleted(self):return QtDialog.Rejected
            self._context_valid=guard.valid()
            return result[0] if self._context_valid else QtDialog.Rejected
        finally:
            if not sip.isdeleted(self):
                self.finished.disconnect(finished);self.destroyed.disconnect(loop.quit)
                self._waiting_result=False
                if guard.owner is not None and not sip.isdeleted(guard.owner):guard.owner.removeEventFilter(guard)
                guard.deleteLater()
    exec=exec_


class QDialog(ResultWindow,QtDialog):pass
class QMainWindow(IndependentWindow,QtMainWindow):pass
class QProgressDialog(IndependentWindow,QtProgressDialog):pass


class QInputDialog(ResultWindow,QtInputDialog):
    @staticmethod
    def getText(parent,title,label,echo=QLineEdit.Normal,text='',flags=Qt.WindowFlags(),inputMethodHints=Qt.ImhNone):
        d=QInputDialog(parent,flags);d.setWindowTitle(title);d.setLabelText(label);d.setTextEchoMode(echo);d.setTextValue(text);d.setInputMethodHints(inputMethodHints)
        ok=d.exec_()==QtDialog.Accepted
        if sip.isdeleted(d):return '',False
        value=d.textValue();d.deleteLater();return value,ok
    @staticmethod
    def getInt(parent,title,label,value=0,min=-2147483647,max=2147483647,step=1,flags=Qt.WindowFlags()):
        d=QInputDialog(parent,flags);d.setWindowTitle(title);d.setLabelText(label);d.setInputMode(d.IntInput);d.setIntRange(min,max);d.setIntStep(step);d.setIntValue(value)
        ok=d.exec_()==QtDialog.Accepted
        if sip.isdeleted(d):return value,False
        value=d.intValue();d.deleteLater();return value,ok
    @staticmethod
    def getItem(parent,title,label,items,current=0,editable=True,flags=Qt.WindowFlags(),inputMethodHints=Qt.ImhNone):
        d=QInputDialog(parent,flags);d.setWindowTitle(title);d.setLabelText(label);d.setComboBoxItems(items);d.setComboBoxEditable(editable);d.setInputMethodHints(inputMethodHints)
        if items:d.setTextValue(items[current])
        ok=d.exec_()==QtDialog.Accepted
        if sip.isdeleted(d):return '',False
        value=d.textValue();d.deleteLater();return value,ok


class QFileDialog(ResultWindow,QtFileDialog):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.setOption(self.DontUseNativeDialog,True)
    def accept(self):
        from pathlib import Path
        paths=self.selectedFiles()
        confirm=(self.acceptMode()==self.AcceptSave and not self.testOption(self.DontConfirmOverwrite)
                 and paths and Path(paths[0]).is_file())
        if confirm:
            if QMessageBox.question(self,'确认覆盖','文件已存在，是否覆盖？\n'+paths[0],QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
            self.setOption(self.DontConfirmOverwrite,True)
        try:super().accept()
        finally:
            if confirm and not sip.isdeleted(self):self.setOption(self.DontConfirmOverwrite,False)
    @staticmethod
    def _file(parent,caption,directory,filter,initialFilter,options,save=False,folder=False):
        d=QFileDialog(parent,caption,directory,filter)
        d.setOptions(options|d.DontUseNativeDialog)
        d.setFileMode(d.Directory if folder else d.AnyFile if save else d.ExistingFile)
        d.setAcceptMode(d.AcceptSave if save else d.AcceptOpen)
        if initialFilter:d.selectNameFilter(initialFilter)
        ok=d.exec_()==QtDialog.Accepted
        if sip.isdeleted(d):return '',''
        paths=d.selectedFiles() if ok else [];selected=d.selectedNameFilter();d.deleteLater()
        return (paths[0] if paths else ''),selected
    @staticmethod
    def getOpenFileName(parent=None,caption='',directory='',filter='',initialFilter='',options=QtFileDialog.Options()):
        return QFileDialog._file(parent,caption,directory,filter,initialFilter,options)
    @staticmethod
    def getSaveFileName(parent=None,caption='',directory='',filter='',initialFilter='',options=QtFileDialog.Options()):
        return QFileDialog._file(parent,caption,directory,filter,initialFilter,options,save=True)
    @staticmethod
    def getExistingDirectory(parent=None,caption='',directory='',options=QtFileDialog.ShowDirsOnly):
        return QFileDialog._file(parent,caption,directory,'','',options,folder=True)[0]


class QColorDialog(ResultWindow,QtColorDialog):
    @staticmethod
    def getColor(initial=Qt.white,parent=None,title='',options=QtColorDialog.ColorDialogOptions()):
        d=QColorDialog(initial,parent);d.setWindowTitle(title);d.setOptions(options|d.DontUseNativeDialog)
        ok=d.exec_()==QtDialog.Accepted
        if sip.isdeleted(d):return QColor()
        value=d.currentColor() if ok else QColor();d.deleteLater();return value


class QMessageBox(ResultWindow,QtMessageBox):
    def clickedButton(self):
        return super().clickedButton() if not sip.isdeleted(self) and getattr(self,'_context_valid',True) else None
    @staticmethod
    def question(parent,title,text,buttons=QtMessageBox.Yes|QtMessageBox.No,defaultButton=QtMessageBox.NoButton):
        d=QMessageBox(parent);d.setWindowTitle(title);d.setText(text);d.setIcon(d.Question);d.setStandardButtons(buttons)
        if defaultButton!=d.NoButton:d.setDefaultButton(defaultButton)
        result=d.exec_()
        if not sip.isdeleted(d):d.deleteLater()
        return result
