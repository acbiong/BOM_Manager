"""表格响应式列宽：保留默认宽度，宽窗口按比例填满，窄窗口横向滚动。编辑时间：2026-10-10。"""
from PyQt5.QtCore import QObject, QEvent, QTimer, Qt
from PyQt5.QtWidgets import QHeaderView


class ProportionalColumns(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        self.header = widget.header() if hasattr(widget, 'header') else widget.horizontalHeader()
        self.widths = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.apply)
        widget.viewport().installEventFilter(self)
        self.header.setStretchLastSection(False)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            self.timer.start(0)
        return False

    def apply(self):
        visible = [i for i in self.widths if i < self.header.count() and not self.header.isSectionHidden(i)]
        if not visible:
            return
        widths = {i: self.widths[i] for i in visible}
        fixed = [i for i in visible if self.header.sectionResizeMode(i) == QHeaderView.Fixed]
        for i in fixed:
            widths[i] = self.header.sectionSize(i)
        total = sum(widths.values())
        extra = max(0, self.widget.viewport().width() - total)
        flexible = [i for i in visible if i not in fixed]
        weight = sum(widths[i] for i in flexible)
        remaining = extra
        for index, i in enumerate(flexible):
            add = remaining if index == len(flexible)-1 else extra * widths[i] // max(1, weight)
            remaining -= add
            widths[i] += add
        for i in visible:
            if self.header.sectionSize(i) != widths[i]:
                self.header.resizeSection(i, widths[i])
        if hasattr(self.widget, 'resizeRowsToContents'):
            self.widget.resizeRowsToContents()


def fit_columns(widget):
    widget.setWordWrap(True)
    header = widget.header() if hasattr(widget, 'header') else widget.horizontalHeader()
    char_width = max(widget.fontMetrics().horizontalAdvance('中'), 1)
    widths = {}
    header.setStretchLastSection(False)
    for i in range(header.count()):
        if header.isSectionHidden(i):
            continue
        header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        widths[i] = max(5 * char_width, min(25 * char_width, header.sectionSize(i)))
        header.setSectionResizeMode(i, QHeaderView.Interactive)
    if not hasattr(widget, '_proportional_columns'):
        widget._proportional_columns = ProportionalColumns(widget)
    widget._proportional_columns.widths = widths
    widget._proportional_columns.apply()
