"""Persist top-level Qt window geometry in the portable application config."""
import hashlib
import logging
import weakref
from PyQt5.QtCore import QObject, QEvent, QByteArray, Qt
from PyQt5.QtWidgets import QWidget, QApplication


class WindowGeometryMemory(QObject):
    def __init__(self, app, config):
        super().__init__(app)
        self.config = config
        self.seen = weakref.WeakSet()
        settings = config.load()
        try:
            reset = settings.getboolean('ui', 'reset_window_geometry', fallback=False)
        except ValueError:
            reset = False
        if reset:
            settings.remove_section('window_geometry')
            config.save(settings)
        app.installEventFilter(self)
        app.aboutToQuit.connect(self.save_visible)

    def key(self, window):
        identity = type(window).__module__ + '.' + type(window).__name__
        if hasattr(window, 'root') and hasattr(window, 'svc'):
            identity += ':' + self.config.relative_path(window.svc.db.path) + ':' + str(window.root) + (':' + str(window.svc.scope_id) if getattr(window.svc,'scope_id',0) else '')
        elif type(window).__name__ in ('QDialog', 'QFileDialog', 'QMessageBox'):
            identity += ':' + window.windowTitle()
        return hashlib.sha256(identity.encode('utf-8')).hexdigest()

    def eligible(self, obj):
        return isinstance(obj, QWidget) and obj.isWindow() and obj.windowType() in (Qt.Window, Qt.Dialog)

    def restore(self, window):
        if window in self.seen:
            return
        self.seen.add(window)
        value = self.config.load().get('window_geometry', self.key(window), fallback='')
        if isinstance(value, str) and value:
            window.restoreGeometry(QByteArray.fromBase64(value.encode('ascii', errors='ignore')))
            # Keep saved windows reachable after a monitor/resolution change.
            if not window.isMaximized() and not window.isFullScreen():
                screen = QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
                available = screen.availableGeometry()
                window.resize(min(window.width(), available.width()), min(window.height(), available.height()))
                frame = window.frameGeometry()
                window.move(max(available.left(), min(frame.x(), available.right()-frame.width()+1)),
                            max(available.top(), min(frame.y(), available.bottom()-frame.height()+1)))

    def save(self, window):
        if window not in self.seen:
            return
        settings = self.config.load()
        if not settings.has_section('window_geometry'):
            settings.add_section('window_geometry')
        settings['window_geometry'][self.key(window)] = bytes(window.saveGeometry().toBase64()).decode('ascii')
        self.config.save(settings)

    def save_visible(self):
        for window in QApplication.topLevelWidgets():
            if self.eligible(window) and window.isVisible():
                self.safely(self.save, window)

    def safely(self, operation, window):
        try:
            operation(window)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            logging.getLogger(__name__).warning('Window geometry could not be saved/restored: %s', error)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Show, QEvent.Hide) and self.eligible(obj):
            self.safely(self.restore if event.type() == QEvent.Show else self.save, obj)
        return False
