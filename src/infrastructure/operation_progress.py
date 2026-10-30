"""Operation-local progress hooks. No Qt or database work runs on worker threads."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, TimeoutError

_current = ContextVar('operation_progress', default=None)
_stage = ContextVar('operation_progress_stage', default=None)
_silent = ContextVar('operation_progress_silent', default=False)


@contextmanager
def silent_progress():
    """Background UI synchronization must never create a progress window."""
    silent_token=_silent.set(True);token=_current.set(None);stage_token=_stage.set(None)
    try:yield
    finally:
        _stage.reset(stage_token);_current.reset(token);_silent.reset(silent_token)


def checkpoint(message=None, current=None, total=None):
    stage = _stage.get()
    if stage is not None:message, current, total = stage
    controller = _current.get()
    if controller is not None and not getattr(controller,'_updating',False):
        controller._updating=True
        try:controller.update(message, current, total)
        finally:controller._updating=False


def progress_iter(values, message=None):
    total = len(values) if hasattr(values, '__len__') else None
    for index, value in enumerate(values):
        checkpoint(message, index, total)
        yield value


def file_work(function, *args, **kwargs):
    """Only pure Excel/file work: never pass SQLite connections or Qt objects."""
    controller = _current.get()
    if controller is None:
        return function(*args, **kwargs)
    phase={'load_workbook':'正在读取Excel文件…','save':'正在写入Excel文件…','compare_trees':'正在计算BOM差异…'}.get(getattr(function,'__name__',''))
    checkpoint(phase)
    # The caller exclusively owns the workbook until the worker finishes.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='bom-file') as pool:
        future = pool.submit(function, *args, **kwargs)
        while True:
            try:
                return future.result(timeout=0.02)
            except TimeoutError:
                if future.done():return future.result()
                checkpoint(phase)


@contextmanager
def suspend_progress():
    controller = _current.get()
    token = _current.set(None)
    stage_token = _stage.set(None)
    if controller is not None:controller.pause()
    try:
        yield
    finally:
        if controller is not None:controller.resume()
        _current.reset(token)
        _stage.reset(stage_token)


def pause_progress(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with suspend_progress():return function(*args, **kwargs)
    return wrapped


@contextmanager
def progress_stage(message, completed, total):
    """Nested row/format/I/O checkpoints preserve the enclosing operation's scale."""
    token = _stage.set((message, completed, total))
    try:
        checkpoint()
        yield
    finally:
        _stage.reset(token)
