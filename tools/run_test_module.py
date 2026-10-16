"""Run one unittest file and release Qt while Python callbacks are still alive."""
from pathlib import Path
import sys
import unittest


def release_qt():
    widgets_module=sys.modules.get('PyQt5.QtWidgets')
    if widgets_module is None:return
    app=widgets_module.QApplication.instance()
    if app is None:return
    from PyQt5 import sip
    from PyQt5.QtCore import QEvent,Qt
    # Qt also lists completer popups and child dialogs as top-level widgets.
    # Their owners must delete them; scheduling them separately can race owner
    # destruction. Delete only independent application windows/dialogs here.
    windows=[window for window in app.topLevelWidgets()
             if window.parent() is None and window.windowType() in (Qt.Window,Qt.Dialog)]
    for window in windows:
        window.deleteLater()
    app.sendPostedEvents(None,QEvent.DeferredDelete)
    if any(not sip.isdeleted(window) for window in windows):
        raise RuntimeError('Qt test windows were not released')
    # Test classes retain QApplication references. Destroy the native object now,
    # before interpreter shutdown can tear down Python signal handlers first.
    sip.delete(app)
    if not sip.isdeleted(app):raise RuntimeError('Qt test application was not released')
    print(f'QT_CLEANUP_OK windows={len(windows)}',flush=True)


def main():
    path=Path(sys.argv[1]).resolve()
    if not path.is_file() or not path.name.startswith('test_') or path.suffix!='.py':
        raise ValueError('Expected an existing test_*.py file')
    suite=unittest.defaultTestLoader.discover(str(path.parent),pattern=path.name)
    try:
        result=unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        release_qt()
    return 0 if result.wasSuccessful() and result.testsRun else 1


if __name__=='__main__':raise SystemExit(main())
