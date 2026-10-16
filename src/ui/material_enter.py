"""Enter confirms a selected material, or selects the first search result."""
from PyQt5.QtCore import QObject,QEvent,Qt

class FirstMaterialOnEnter(QObject):
    def __init__(self,combo,confirm=None):
        super().__init__(combo)
        self.combo=combo
        self.confirm=confirm
        for widget in (combo,combo.lineEdit(),combo.completer().popup(),combo.completer().popup().viewport()):
            widget.installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Return,Qt.Key_Enter):
            text=self.combo.currentText().strip().casefold()
            model=self.combo.model()
            popup=self.combo.completer().popup()
            highlighted=popup.currentIndex() if popup.isVisible() else None
            selected=str(highlighted.data() or '') if highlighted is not None and highlighted.isValid() else self.combo.currentText()
            for row in range(model.rowCount()):
                index=model.index(row,self.combo.modelColumn())
                if model.flags(index)&Qt.ItemIsEnabled and str(index.data() or '')==selected:
                    self.combo.setCurrentIndex(row)
                    self.combo.lineEdit().setText(selected)
                    popup.hide()
                    if self.confirm is not None:self.confirm()
                    return True
            for row in range(model.rowCount()):
                index=model.index(row,self.combo.modelColumn())
                if model.flags(index)&Qt.ItemIsEnabled and text in str(index.data() or '').casefold():
                    self.combo.setCurrentIndex(row)
                    self.combo.lineEdit().setText(str(index.data()))
                    self.combo.completer().popup().hide()
                    break
            return True
        return False
