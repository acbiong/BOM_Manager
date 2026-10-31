"""100ms delayed, nonmodal progress; native painting with guarded application operations."""
import inspect
import logging
import os
import time
from collections import deque
from functools import wraps
from PyQt5 import sip
from PyQt5.QtCore import Qt, QEvent, QThread, QEventLoop, QObject, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
from infrastructure.operation_progress import _current, _silent

RECENT_OPERATIONS = deque(maxlen=200)


class _PaintGuard(QObject):
    """Leave timer delivery pending and reject native close while work is active."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Timer:
            return True  # QTimer has not received it; its registered timer remains active.
        if event.type() == QEvent.Close:
            event.ignore()
            return True
        return False


class OperationProgress:
    threshold = 0.100
    paint_interval = 0.020

    def __init__(self, owner, title):
        self.owner = owner
        self.title = title
        self.message = '正在处理，请稍候…'
        self.started = time.perf_counter()
        self.last_paint = self.started-self.paint_interval
        self.dialog = None
        self.paused = None
        self.shown = False
        self.dispatching = False
        self.pending_operations = []
        self.pending_refreshes = {}

    def update(self, message=None, current=None, total=None):
        if self.paused is not None:return
        now = time.perf_counter()
        if message:self.message = message
        complete=total is not None and total>0 and current==total
        if now-self.started < self.threshold or (not complete and now-self.last_paint < self.paint_interval):return
        if self.owner is not None and sip.isdeleted(self.owner):return
        self.last_paint = now
        if self.dialog is None:
            from ui.interactive_windows import QProgressDialog
            self.dialog = QProgressDialog(self.message, None, 0, 0, self.owner)
            self.dialog.setWindowTitle(self.title)
            self.dialog.setWindowFlags(self.dialog.windowFlags() & ~Qt.WindowCloseButtonHint)
            if (QApplication.platformName() == 'xcb' and os.environ.get('WSL_DISTRO_NAME')
                    and os.environ.get('WAYLAND_DISPLAY')):
                # WSLg's XWayland/RAIL manager asynchronously relocates managed
                # windows after their first expose. This noninteractive progress
                # surface owns its position; leave ordinary dialogs managed.
                self.dialog.setWindowFlags(self.dialog.windowFlags() | Qt.X11BypassWindowManagerHint
                                           | Qt.WindowDoesNotAcceptFocus)
                self.dialog.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.dialog.setMinimumDuration(2147483647)
            self.dialog.setAutoClose(False)
            self.dialog.setAutoReset(False)
            # Fixed geometry prevents long stage labels from moving the window.
            from PyQt5.QtWidgets import QLabel
            label = QLabel(self.message, self.dialog)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumWidth(0)
            self.dialog.setLabel(label)
            screen = self.owner.screen() if self.owner is not None else QApplication.primaryScreen()
            width = min(520, screen.availableGeometry().width()-40) if screen else 520
            self.dialog.setFixedSize(width, 120)
        dialog = self.dialog
        if sip.isdeleted(dialog):return
        if not dialog.isVisible():
            screen = self.owner.screen() if self.owner is not None else QApplication.primaryScreen()
            if screen is not None:dialog.move(screen.availableGeometry().center()-dialog.rect().center())
        dialog.setLabelText(self.message)
        if total is not None and total > 0 and current is not None:
            dialog.setRange(0, int(total));dialog.setValue(min(int(current), int(total)))
        elif message is not None:dialog.setRange(0, 0)
        if not dialog.isVisible():
            screen = (self.owner.screen() if self.owner is not None else QApplication.primaryScreen())
            if screen is not None:dialog.move(screen.availableGeometry().center()-dialog.rect().center())
            dialog.show();dialog.raise_();self.shown = True
        # Dispatch native map/expose events: repaint alone cannot expose a new native window.
        app = QApplication.instance()
        guard = _PaintGuard()
        app.installEventFilter(guard)
        self.dispatching = True
        try:
            flags = (QEventLoop.ExcludeUserInputEvents | QEventLoop.ExcludeSocketNotifiers |
                     QEventLoop.X11ExcludeTimers)
            QApplication.processEvents(flags)
            # X11 mapping is asynchronous. Give the first expose a bounded
            # opportunity to arrive before repainting the backing store.
            deadline = time.monotonic() + .030
            while not dialog.windowHandle().isExposed() and time.monotonic() < deadline:
                QThread.msleep(1)
                QApplication.processEvents(flags)
        finally:
            self.dispatching = False
            app.removeEventFilter(guard)
        QApplication.sendPostedEvents(dialog, QEvent.UpdateRequest)
        dialog.repaint()

    def pause(self):
        self.paused = time.perf_counter()
        if self.dialog is not None and not sip.isdeleted(self.dialog):self.dialog.hide()

    def resume(self):
        if self.paused is not None:self.started += time.perf_counter()-self.paused
        self.paused = None

    def close(self, failed=False):
        elapsed = (time.perf_counter()-self.started)*1000
        if self.dialog is not None and not sip.isdeleted(self.dialog):
            # Stop Qt busy-bar style animations before scheduling destruction.
            self.dialog.setRange(0,100)
            self.dialog.close();self.dialog.deleteLater()
        for callback in self.pending_operations:
            QTimer.singleShot(0, callback)
        self.pending_operations.clear()
        record = dict(operation=self.title, ms=round(elapsed, 2), progress_shown=self.shown, failed=failed)
        RECENT_OPERATIONS.append(record)
        logging.getLogger(__name__).info('operation_timing %s', record)


def operation(title, owner=None):
    def decorate(function):
        parameters=list(inspect.signature(function).parameters.values())
        maximum=None if any(p.kind==p.VAR_POSITIONAL for p in parameters) else sum(p.kind in (p.POSITIONAL_ONLY,p.POSITIONAL_OR_KEYWORD) for p in parameters)
        @wraps(function)
        def wrapped(*args, **kwargs):
            # Qt normally drops excess signal arguments; decorators must retain that behavior.
            if maximum is not None:args=args[:maximum]
            if _silent.get():return function(*args, **kwargs)
            app = QApplication.instance()
            active = _current.get()
            if active is not None and active.dispatching:
                # Queued Qt slots can arrive with expose events. Run the entire
                # operation after the current transaction/refresh has finished.
                def later():
                    if args and isinstance(args[0], QWidget) and sip.isdeleted(args[0]):return
                    wrapped(*args, **kwargs)
                if title in ('刷新清单', '刷新BOM', '载入BOM'):
                    # Coalesce layout/refresh notifications; finish them using
                    # this operation's progress instead of opening new windows.
                    key = (id(args[0]) if args else None, function)
                    active.pending_refreshes[key] = later
                else:active.pending_operations.append(later)
                return None
            if app is None or QThread.currentThread() != app.thread() or _current.get() is not None:
                return function(*args, **kwargs)
            parent = args[0] if args and isinstance(args[0], QWidget) else app.activeWindow()
            if owner is not None:parent=owner(parent)
            controller = OperationProgress(parent, title)
            token = _current.set(controller)
            failed = False
            try:return function(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                try:
                    if not failed:
                        done = set()
                        while controller.pending_refreshes:
                            key, callback = controller.pending_refreshes.popitem()
                            if key not in done:
                                done.add(key)
                                callback()
                finally:
                    _current.reset(token)
                    controller.close(failed)
        return wrapped
    return decorate
