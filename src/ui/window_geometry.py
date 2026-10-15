"""Share the latest geometry per window type; batch portable config writes."""
import hashlib
import logging
import weakref
from PyQt5.QtCore import QObject, QEvent, QByteArray, Qt, QTimer
from PyQt5.QtWidgets import QWidget, QApplication


class WindowGeometryMemory(QObject):
    def __init__(self, app, config):
        super().__init__(app)
        self.config = config
        self.seen = weakref.WeakSet()
        self.last_geometry = weakref.WeakKeyDictionary()
        self.restoring = weakref.WeakSet()
        self.pending = {}
        settings = config.load()
        try:
            reset = settings.getboolean('ui', 'reset_window_geometry', fallback=False)
        except ValueError:
            reset = False
        if reset:
            settings.remove_section('window_geometry')
            config.save(settings)
        self.values = dict(settings['window_geometry']) if settings.has_section('window_geometry') else {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.flush)
        app.installEventFilter(self)
        app.aboutToQuit.connect(self.save_visible)

    def key(self, window, legacy=False):
        identity = type(window).__module__ + '.' + type(window).__name__
        if legacy and hasattr(window, 'root') and hasattr(window, 'svc'):
            identity += ':' + self.config.relative_path(window.svc.db.path) + ':' + str(window.root) + (':' + str(window.svc.scope_id) if getattr(window.svc,'scope_id',0) else '')
        elif type(window).__name__ in ('QDialog', 'QFileDialog', 'QMessageBox'):
            # Generic Qt dialogs serve different purposes; custom dialogs use their class.
            identity += ':' + window.windowTitle()
        return hashlib.sha256(identity.encode('utf-8')).hexdigest()

    def eligible(self, obj):
        return isinstance(obj, QWidget) and obj.isWindow() and obj.windowType() in (Qt.Window, Qt.Dialog)

    @staticmethod
    def geometry(window):
        return bytes(window.saveGeometry().toBase64()).decode('ascii')

    def restore(self, window):
        if window in self.seen:
            return
        self.seen.add(window)
        self.restoring.add(window)
        try:
            key = self.key(window)
            value = self.values.get(key) or self.values.get(self.key(window, legacy=True), '')
            if value:
                restored = window.restoreGeometry(QByteArray.fromBase64(value.encode('ascii', errors='ignore')))
                if restored and key not in self.values:
                    self.values[key] = value
                    self.pending[key] = value
                    self.timer.start()
                # Keep saved windows reachable after a monitor/resolution change.
                if not window.isMaximized() and not window.isFullScreen():
                    screen = QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
                    if screen is not None:
                        available = screen.availableGeometry()
                        window.resize(min(window.width(), available.width()), min(window.height(), available.height()))
                        frame = window.frameGeometry()
                        window.move(max(available.left(), min(frame.x(), available.right()-frame.width()+1)),
                                    max(available.top(), min(frame.y(), available.bottom()-frame.height()+1)))
        finally:
            self.restoring.discard(window)
            self.last_geometry[window] = self.geometry(window)

    def save(self, window):
        if window not in self.seen or window in self.restoring:
            return
        value = self.geometry(window)
        key = self.key(window)
        # Closing an older, unchanged window must not overwrite a newer adjustment.
        if self.last_geometry.get(window) == value and key in self.values:
            return
        self.last_geometry[window] = value
        self.values[key] = value
        self.pending[key] = value
        self.timer.start()

    def flush(self):
        self.timer.stop()
        if not self.pending:
            return
        try:
            settings = self.config.load()
            if not settings.has_section('window_geometry'):
                settings.add_section('window_geometry')
            settings['window_geometry'].update(self.pending)
            self.config.save(settings)
            self.pending.clear()
        except (OSError, ValueError, TypeError) as error:
            logging.getLogger(__name__).warning('Window geometry could not be saved: %s', error)

    def save_visible(self):
        for window in QApplication.topLevelWidgets():
            if self.eligible(window) and window.isVisible():
                self.safely(self.save, window)
        self.flush()

    def safely(self, operation, window):
        try:
            operation(window)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            logging.getLogger(__name__).warning('Window geometry could not be saved/restored: %s', error)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QEvent.Show, QEvent.Hide, QEvent.Resize, QEvent.Move, QEvent.WindowStateChange) and self.eligible(obj):
            if kind == QEvent.Show:
                self.safely(self.restore, obj)
            elif kind == QEvent.Hide:
                self.safely(self.save, obj)
                self.flush()
            elif obj.isVisible():
                self.safely(self.save, obj)
        return False
