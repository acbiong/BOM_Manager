"""Keep the visible BOM tree anchored while draft operations change selection."""
from functools import wraps
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QAbstractItemView


def preserve_bom_view(method):
    @wraps(method)
    def wrapped(self,*args,**kwargs):
        tree=self.tree
        if getattr(tree,'_hold_view',False):
            return method(self,*args,**kwargs)
        anchor=tree.itemAt(QPoint(1,0))
        if anchor is None:
            anchor=tree.itemAt(QPoint(1,tree.fontMetrics().height()))
        y=tree.visualItemRect(anchor).top() if anchor is not None else 0
        vertical=tree.verticalScrollBar().value()
        horizontal=tree.horizontalScrollBar().value()
        widths=[tree.columnWidth(i) for i in range(tree.columnCount())]
        layout=getattr(tree,'_proportional_columns',None)
        defaults=dict(layout.widths) if layout else None
        tree._hold_view=True
        tree.setUpdatesEnabled(False)
        try:
            return method(self,*args,**kwargs)
        finally:
            if layout is not None:layout.widths=defaults
            for column,width in enumerate(widths):tree.setColumnWidth(column,width)
            tree.doItemsLayout()
            tree.verticalScrollBar().setValue(vertical)
            if anchor is not None:
                tree.verticalScrollBar().setValue(tree.verticalScrollBar().value()+tree.visualItemRect(anchor).top()-y)
            tree.horizontalScrollBar().setValue(horizontal)
            tree._hold_view=False
            selected=tree.currentItem()
            if selected is not None:
                rect=tree.visualItemRect(selected)
                visible=not rect.isEmpty() and rect.bottom()>=0 and rect.top()<tree.viewport().height()
                if not visible:
                    ancestor=selected.parent()
                    while ancestor is not None:
                        ancestor.setExpanded(True)
                        ancestor=ancestor.parent()
                    tree.doItemsLayout()
                    tree.scrollToItem(selected,QAbstractItemView.PositionAtCenter)
                    tree.horizontalScrollBar().setValue(horizontal)
            tree.setUpdatesEnabled(True)
    return wrapped
