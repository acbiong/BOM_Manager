"""Operation-local progress hooks. No Qt or database work runs on worker threads."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, TimeoutError

_current = ContextVar('operation_progress', default=None)


def checkpoint(message=None, current=None, total=None):
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
    if controller is not None:controller.pause()
    try:
        yield
    finally:
        if controller is not None:controller.resume()
        _current.reset(token)


def pause_progress(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with suspend_progress():return function(*args, **kwargs)
    return wrapped
