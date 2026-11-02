"""Shared colors for unsaved BOM changes and read-only history differences."""
from PyQt5.QtGui import QColor

ADDED='green'
DELETED='red'
MODIFIED='#9a6700'
MOVED='#f8d7e3'
MOVED_TEXT='#202020'


def level_background(depth,dark=False):
    alpha=(24,18,12,6,0)[min(depth,4)]
    return QColor(255,255,255,alpha) if dark else QColor(0,0,0,alpha)


def change_foreground(added=False,deleted=False,changed=False):
    from PyQt5.QtWidgets import QApplication
    app=QApplication.instance()
    dark=bool(app and app.property('bom_dark_theme'))
    if dark:return '#ff9494' if deleted else '#85e6a2' if added else '#ffd477' if changed else None
    return DELETED if deleted else ADDED if added else MODIFIED if changed else None
