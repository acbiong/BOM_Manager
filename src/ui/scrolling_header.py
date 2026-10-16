"""Two-line SKU headers scroll clipped text without changing column widths."""
from PyQt5.QtCore import Qt, QTimer, QElapsedTimer, QRect
from PyQt5.QtWidgets import QHeaderView, QStyleOptionHeader, QStyle


class ScrollingSkuHeader(QHeaderView):
    def __init__(self, parent=None, first_sku_column=11):
        super().__init__(Qt.Horizontal, parent)
        self.first_sku_column = first_sku_column
        self.clock = QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.animate)

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def animate(self):
        # Only repaint visible clipped SKU headers, never table cells.
        for column in range(self.first_sku_column, self.count()):
            x = self.sectionViewportPosition(column)
            width = self.sectionSize(column)
            if self.isSectionHidden(column) or x + width <= 0 or x >= self.viewport().width():
                continue
            text = str(self.model().headerData(column, Qt.Horizontal) or '')
            if any(self.fontMetrics().horizontalAdvance(line) > width - 12 for line in text.split('\n')):
                self.viewport().update(QRect(x, 0, width, self.height()))

    def paintSection(self, painter, rect, logical_index):
        if logical_index < self.first_sku_column:
            return super().paintSection(painter, rect, logical_index)
        option = QStyleOptionHeader()
        self.initStyleOption(option)
        option.rect = rect
        option.section = logical_index
        option.text = ''
        painter.save()
        try:
            self.style().drawControl(QStyle.CE_Header, option, painter, self)
        finally:
            painter.restore()
        lines = str(self.model().headerData(logical_index, Qt.Horizontal) or '').split('\n')
        painter.save()
        painter.setFont(self.font())
        painter.setPen(option.palette.buttonText().color())
        content = rect.adjusted(6, 0, -6, 0)
        painter.setClipRect(content)
        metrics = painter.fontMetrics()
        height = metrics.height()
        top = rect.top() + (rect.height() - height * len(lines)) // 2
        for index, line in enumerate(lines):
            width = metrics.horizontalAdvance(line)
            overflow = max(0, width - content.width())
            offset = 0
            if overflow:
                # Pause at both ends, then smoothly reverse; every character appears.
                travel = overflow / 30.0
                phase = (self.clock.elapsed() / 1000.0) % (2 * travel + 2)
                offset = min(overflow, max(0, (phase - 1) * 30)) if phase <= travel + 2 else max(0, overflow - (phase - travel - 2) * 30)
            x = content.left() - int(offset) if overflow else content.left() + (content.width() - width) // 2
            painter.drawText(x, top + index * height + metrics.ascent(), line)
        painter.restore()
