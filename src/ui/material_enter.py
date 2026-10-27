"""Stable filtered-material keyboard navigation and Enter confirmation."""
from PyQt5.QtCore import QObject,QEvent,Qt,QSignalBlocker

class FirstMaterialOnEnter(QObject):
    def __init__(self,combo,confirm=None):
        super().__init__(combo)
        self.combo=combo
        self.confirm=confirm
        for widget in (combo,combo.lineEdit(),combo.completer().popup(),combo.completer().popup().viewport()):
            widget.installEventFilter(self)
    def navigate(self,direction):
        # Handle keys from either the editor or completion popup. Do not let
        # QComboBox replace the search text while the user browses candidates.
        completer=self.combo.completer();popup=completer.popup()
        if not popup.isVisible():
            completer.setCompletionPrefix(self.combo.currentText())
            completer.complete()
        model=popup.model()
        if model is None:return
        rows=[row for row in range(model.rowCount()) if model.flags(model.index(row,0))&Qt.ItemIsEnabled and model.flags(model.index(row,0))&Qt.ItemIsSelectable]
        if not rows:return
        current=popup.currentIndex().row()
        if current not in rows:row=rows[0] if direction>0 else rows[-1]
        else:row=rows[max(0,min(len(rows)-1,rows.index(current)+direction))]
        blocker=QSignalBlocker(completer)
        popup.setCurrentIndex(model.index(row,0));popup.scrollTo(model.index(row,0))
        del blocker
    def eventFilter(self,obj,event):
        if event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Down,Qt.Key_Up) and event.modifiers()==Qt.NoModifier:
            self.navigate(1 if event.key()==Qt.Key_Down else -1)
            return True
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
