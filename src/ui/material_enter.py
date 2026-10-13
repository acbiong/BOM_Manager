"""Enter selects the first available material without accepting the dialog."""
from PyQt5.QtCore import QObject,QEvent,Qt

class FirstMaterialOnEnter(QObject):
    def __init__(self,combo):
        super().__init__(combo)
        self.combo=combo
        for widget in (combo,combo.lineEdit(),combo.completer().popup(),combo.completer().popup().viewport()):
            widget.installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Return,Qt.Key_Enter):
            text=self.combo.currentText().strip().casefold()
            model=self.combo.model()
            for row in range(model.rowCount()):
                index=model.index(row,self.combo.modelColumn())
                if model.flags(index)&Qt.ItemIsEnabled and text in str(index.data() or '').casefold():
                    self.combo.setCurrentIndex(row)
                    self.combo.lineEdit().setText(str(index.data()))
                    self.combo.completer().popup().hide()
                    break
            return True
        return False
