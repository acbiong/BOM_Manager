"""100ms delayed, nonmodal progress; paint without re-entering application slots."""
import inspect
import logging
import time
from collections import deque
from functools import wraps
from PyQt5 import sip
from PyQt5.QtCore import Qt, QEvent, QThread
from PyQt5.QtWidgets import QApplication, QWidget
from infrastructure.operation_progress import _current

RECENT_OPERATIONS = deque(maxlen=200)


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

    def update(self, message=None, current=None, total=None):
        if self.paused is not None:return
        now = time.perf_counter()
        if message:self.message = message
        if now-self.started < self.threshold or now-self.last_paint < self.paint_interval:return
        if self.owner is not None and sip.isdeleted(self.owner):return
        self.last_paint = now
        if self.dialog is None:
            from ui.interactive_windows import QProgressDialog
            self.dialog = QProgressDialog(self.message, None, 0, 0, self.owner)
            self.dialog.setWindowTitle(self.title)
            self.dialog.setWindowFlags(self.dialog.windowFlags() & ~Qt.WindowCloseButtonHint)
            self.dialog.setMinimumDuration(2147483647)
            self.dialog.setAutoClose(False)
            self.dialog.setAutoReset(False)
            self.dialog.resize(380, 100)
        dialog = self.dialog
        if sip.isdeleted(dialog):return
        if not dialog.isVisible():
            screen = self.owner.screen() if self.owner is not None else QApplication.primaryScreen()
            if screen is not None:dialog.move(screen.availableGeometry().center()-dialog.rect().center())
        dialog.setLabelText(self.message)
        if total is not None and total > 0 and current is not None:
            dialog.setRange(0, int(total));dialog.setValue(min(int(current), int(total)))
        else:dialog.setRange(0, 0)
        if not dialog.isVisible():
            screen = (self.owner.screen() if self.owner is not None else QApplication.primaryScreen())
            if screen is not None:dialog.move(screen.availableGeometry().center()-dialog.rect().center())
            dialog.show();self.shown = True
        screen = self.owner.screen() if self.owner is not None else QApplication.primaryScreen()
        if screen is not None:dialog.move(dialog.pos()+screen.availableGeometry().center()-dialog.frameGeometry().center())
        # Do not process clicks, timers, or queued save/refresh slots mid-transaction.
        QApplication.sendPostedEvents(None, QEvent.UpdateRequest)
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
            self.dialog.close();self.dialog.deleteLater()
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
            app = QApplication.instance()
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
                _current.reset(token)
                controller.close(failed)
        return wrapped
    return decorate
