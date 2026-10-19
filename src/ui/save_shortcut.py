"""Window-local Ctrl+S activates the existing, unambiguous confirmation button."""
import weakref
from PyQt5 import sip
from PyQt5.QtCore import QObject,QEvent,Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QApplication,QDialog,QDialogButtonBox,QMessageBox,QShortcut


class SaveShortcuts(QObject):
    def __init__(self,app):
        super().__init__(app)
        self.shortcuts=[]
        app.installEventFilter(self)

    @staticmethod
    def target(window):
        if isinstance(window,QMessageBox):
            # Never choose Yes/overwrite/delete on behalf of the user.
            button=window.button(QMessageBox.Save)
            if button is not None and button.isVisible():return button
            saves=[b for b in window.buttons() if window.buttonRole(b)==QMessageBox.AcceptRole
                   and b.text().replace('&','').strip() in ('保存','保存并退出') and b.isVisible()]
            return saves[0] if len(saves)==1 else None
        candidates=[]
        for box in window.findChildren(QDialogButtonBox):
            if box.window() is not window:continue
            for button in box.buttons():
                if (box.buttonRole(button) in (QDialogButtonBox.AcceptRole,QDialogButtonBox.ApplyRole)
                        and button.isVisible()):candidates.append(button)
        return candidates[0] if len(candidates)==1 else None

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Show and isinstance(obj,QDialog) and not hasattr(obj,'_bom_save_shortcut'):
            shortcut=QShortcut(QKeySequence('Ctrl+S'),obj)
            shortcut.setContext(Qt.WindowShortcut);shortcut.setAutoRepeat(False)
            reference=weakref.ref(obj)
            def confirm():
                window=reference()
                if window is None or sip.isdeleted(window):return
                # A modeless child dialog must never save its parent BOM too.
                active=QApplication.activeModalWidget() or QApplication.activeWindow()
                if active is not window:return
                button=self.target(window)
                if button is not None and button.isEnabled():button.click()
            shortcut.activated.connect(confirm)
            obj._bom_save_shortcut=shortcut
            self.shortcuts.append((weakref.ref(obj),weakref.ref(shortcut)))
        return False

    def shutdown(self):
        app=QApplication.instance()
        if app is not None:app.removeEventFilter(self)
        for window_ref,shortcut_ref in self.shortcuts:
            window=window_ref();shortcut=shortcut_ref()
            if shortcut is not None and not sip.isdeleted(shortcut):
                shortcut.activated.disconnect();sip.delete(shortcut)
            if window is not None and not sip.isdeleted(window) and hasattr(window,'_bom_save_shortcut'):
                del window._bom_save_shortcut
        self.shortcuts.clear()


def install_save_shortcuts(app=None):
    app=app or QApplication.instance()
    if app is not None and not hasattr(app,'_bom_save_shortcuts'):
        app._bom_save_shortcuts=SaveShortcuts(app)
    return getattr(app,'_bom_save_shortcuts',None)
