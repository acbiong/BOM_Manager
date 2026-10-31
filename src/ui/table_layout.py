"""表格响应式列宽：保留默认宽度，宽窗口按比例填满，窄窗口横向滚动。编辑时间：2026-10-10。"""
from infrastructure.operation_progress import silent_progress
from PyQt5.QtCore import QObject, QEvent, QTimer, Qt
from PyQt5.QtWidgets import QHeaderView
from functools import wraps


def batch_table_update(attribute):
    """Paint the completed view once, including its frozen child view."""
    def decorate(function):
        @wraps(function)
        def wrapped(owner,*args,**kwargs):
            widget=getattr(owner,attribute);enabled=widget.updatesEnabled();muted=False;attached=True
            model=widget.model()
            signals=(model.dataChanged,model.headerDataChanged,model.rowsAboutToBeInserted,
                     model.rowsAboutToBeRemoved,model.columnsAboutToBeInserted,model.columnsAboutToBeRemoved,model.modelAboutToBeReset)
            def changing(*args):
                nonlocal muted,attached
                if enabled and not muted:widget.setUpdatesEnabled(False);muted=True
                # The first change is sufficient. Keeping Python slots connected
                # for every cell property costs more than the paint batching saves.
                for signal in signals:signal.disconnect(changing)
                attached=False
            for signal in signals:signal.connect(changing)
            try:return function(owner,*args,**kwargs)
            finally:
                if attached:
                    for signal in signals:signal.disconnect(changing)
                if muted:widget.setUpdatesEnabled(enabled)
        return wrapped
    return decorate


class ProportionalColumns(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        self.widget = widget
        self.header = widget.header() if hasattr(widget, 'header') else widget.horizontalHeader()
        self.widths = {}
        self._row_layout = None
        self.revision=0
        self.fit_signature=None
        model=widget.model()
        model.dataChanged.connect(self.data_changed)
        for signal in (model.headerDataChanged,model.rowsInserted,model.rowsRemoved,
                       model.columnsInserted,model.columnsRemoved,model.modelReset,model.layoutChanged):
            signal.connect(self.invalidate)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.apply)
        widget.viewport().installEventFilter(self)
        self.header.setStretchLastSection(False)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def invalidate(self,*args):self.revision+=1
    def data_changed(self,top_left,bottom_right,roles=None):
        if not roles or any(role in (Qt.DisplayRole,Qt.EditRole,Qt.FontRole,Qt.DecorationRole,Qt.SizeHintRole,Qt.CheckStateRole) for role in roles):self.invalidate()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            self.timer.start(0)
        return False

    @silent_progress()
    def apply(self):
        self.timer.stop()
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
            signature = (self.revision,self.widget.font().toString(),self.widget.rowCount(), tuple((i, widths[i]) for i in visible))
            if signature == self._row_layout:return
            self._row_layout = signature
            # One native layout pass; per-row progress pumping re-enters layout
            # while column widths are still changing and repeats expensive work.
            self.widget.resizeRowsToContents()


@silent_progress()
def fit_columns(widget, apply=True):
    widget.window().ensurePolished();widget.ensurePolished()
    widget.setWordWrap(True)
    header = widget.header() if hasattr(widget, 'header') else widget.horizontalHeader()
    char_width = max(widget.fontMetrics().horizontalAdvance('中'), 1)
    widths = {}
    header.setStretchLastSection(False)
    if not hasattr(widget, '_proportional_columns'):
        widget._proportional_columns = ProportionalColumns(widget)
    layout=widget._proportional_columns
    signature=(layout.revision,widget.font().toString(),header.font().toString(),
               tuple(header.isSectionHidden(i) for i in range(header.count())),
               tuple(getattr(widget,'_fixed_column_widths',{}).items()))
    if signature==layout.fit_signature:
        if apply:layout.apply()
        return
    for i in range(header.count()):
        if header.isSectionHidden(i):
            continue
        if i in getattr(widget, "_fixed_column_widths", {}):
            widths[i] = widget._fixed_column_widths[i]
            header.setSectionResizeMode(i, QHeaderView.Fixed)
            header.resizeSection(i, widths[i])
            continue
        header.setSectionResizeMode(i, QHeaderView.Interactive)
        # Measuring a ResizeToContents section forces all automatic sections to
        # resize repeatedly. Query each column exactly once instead.
        hint=max(widget.sizeHintForColumn(i),header.sectionSizeHint(i))
        widths[i] = max(5 * char_width, min(25 * char_width, hint))
    widget._proportional_columns.widths = widths
    layout.fit_signature=signature
    if apply:widget._proportional_columns.apply()
