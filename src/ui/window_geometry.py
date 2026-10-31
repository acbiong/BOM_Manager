"""Share the latest geometry per window type; batch portable config writes."""
import hashlib
import logging
import weakref
from PyQt5.QtCore import QObject, QEvent, QByteArray, Qt, QTimer
from PyQt5 import sip
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QWidget, QApplication, QDialog, QProgressDialog, QMessageBox, QInputDialog, QLabel


class WindowGeometryMemory(QObject):
    def __init__(self, app, config):
        super().__init__(app)
        self.config = config
        self.seen = weakref.WeakSet()
        self.last_geometry = weakref.WeakKeyDictionary()
        self.restoring = weakref.WeakSet()
        self.pending = {}
        self.placements = {}
        self.placement_timer = QTimer(self)
        self.placement_timer.setSingleShot(True)
        self.placement_timer.timeout.connect(self.settle_placements)
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
    def transient(window):
        # Short-lived prompts must not inherit stale/shared progress geometry.
        return isinstance(window, (QProgressDialog, QMessageBox, QInputDialog))

    @staticmethod
    def target_screen(window):
        parent = window.parentWidget()
        owner = parent.window() if parent is not None else QApplication.activeWindow()
        if owner is not None and owner is not window and owner.isVisible():
            return QApplication.screenAt(owner.frameGeometry().center()) or owner.screen()
        return QApplication.screenAt(QCursor.pos()) or window.screen() or QApplication.primaryScreen()

    def center_dialog(self, window):
        if window in self.restoring:
            return
        screen = self.target_screen(window)
        if screen is None or window.isMaximized() or window.isFullScreen():
            return
        self.restoring.add(window)
        try:
            available = screen.availableGeometry()
            if isinstance(window, QProgressDialog):
                for label in window.findChildren(QLabel):
                    label.setWordWrap(True)
                # Keep an explicitly fixed progress width. Raising its maximum
                # would let QProgressDialog resize on a later long stage label.
                window.setMaximumWidth(min(window.maximumWidth(), max(200, available.width()-20)))
                window.resize(min(window.width(), window.maximumWidth()), window.height())
            frame = window.frameGeometry()
            offset = available.center()-frame.center()
            offset.setX(max(available.left()-frame.left(), offset.x()))
            offset.setY(max(available.top()-frame.top(), offset.y()))
            window.move(window.pos()+offset)
        finally:
            self.restoring.discard(window)

    def place_transient(self, window):
        if window in self.restoring:
            return
        self.center_dialog(window)
        # One manager-owned timer/slot, never a lambda parented to a temporary
        # native QMessageBox. Keep wrappers alive only for these bounded passes.
        self.placements[window] = 3
        if not self.placement_timer.isActive():self.placement_timer.start(0)

    def settle_placements(self):
        for window, passes in list(self.placements.items()):
            if sip.isdeleted(window) or not window.isVisible():
                self.placements.pop(window, None)
                continue
            self.safely(self.center_dialog, window)
            if passes <= 1:self.placements.pop(window, None)
            elif window in self.placements:self.placements[window] = passes-1
        if self.placements:self.placement_timer.start(50)

    @staticmethod
    def geometry(window):
        return bytes(window.saveGeometry().toBase64()).decode('ascii')

    def restore(self, window):
        if self.transient(window):
            self.place_transient(window)
            return
        if window in self.seen:
            return
        self.seen.add(window)
        self.restoring.add(window)
        try:
            key = self.key(window)
            value = self.values.get(key) or self.values.get(self.key(window, legacy=True), '')
            restored = False
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
            if not restored and isinstance(window, QDialog):
                self.restoring.discard(window)
                self.place_transient(window)
        finally:
            self.restoring.discard(window)
            self.last_geometry[window] = self.geometry(window)

    def save(self, window):
        if self.transient(window) or window not in self.seen or window in self.restoring:
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
        if kind in (QEvent.Hide, QEvent.Close, QEvent.DeferredDelete):
            self.placements.pop(obj, None)
            if not self.placements:self.placement_timer.stop()
        if kind in (QEvent.Show, QEvent.Hide, QEvent.Resize, QEvent.Move, QEvent.WindowStateChange) and self.eligible(obj):
            if kind == QEvent.Show:
                self.safely(self.restore, obj)
            elif self.transient(obj):
                if kind == QEvent.Resize and obj.isVisible():
                    self.safely(self.place_transient, obj)
            elif kind == QEvent.Hide:
                self.safely(self.save, obj)
                self.flush()
            elif obj.isVisible():
                self.safely(self.save, obj)
        return False
