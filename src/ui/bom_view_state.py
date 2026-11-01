"""Keep the visible BOM tree anchored while draft operations change selection."""
from functools import wraps
from PyQt5.QtCore import QPoint,Qt
from PyQt5.QtWidgets import QAbstractItemView


def saved_view(window):
    """Capture logical paths before save replaces all tree items/relationship IDs."""
    tree=window.tree
    def path(item):
        result=[]
        while item is not None and item is not window.root_item:
            data=item.data(0,Qt.UserRole) or {}
            result.append((data['material_id'],data.get('position') or ''));item=item.parent()
        return tuple(reversed(result))
    current=tree.currentItem()
    while current is not None and (current.data(0,Qt.UserRole) or {}).get('_deleted'):current=current.parent()
    anchor=tree.itemAt(QPoint(1,0)) or tree.itemAt(QPoint(1,tree.fontMetrics().height()))
    return dict(current=path(current),selected=[path(n) for n in tree.selectedItems() if not (n.data(0,Qt.UserRole) or {}).get('_deleted')],
                expanded=[(path(n),n.isExpanded()) for _,n in window.expansion_nodes() if not (n.data(0,Qt.UserRole) or {}).get('_deleted')],
                anchor=path(anchor) if anchor is not None else None,y=tree.visualItemRect(anchor).top() if anchor is not None else 0,
                vertical=tree.verticalScrollBar().value(),horizontal=tree.horizontalScrollBar().value())


def restore_saved_view(window,state,revisions):
    """Follow saved parent revisions and keep the same occurrence selected."""
    tree=window.tree;nodes={():window.root_item}
    def walk(parent,path):
        for i in range(parent.childCount()):
            node=parent.child(i);data=node.data(0,Qt.UserRole) or {}
            key=path+((data['material_id'],data.get('position') or ''),)
            nodes[key]=node;walk(node,key)
    walk(window.root_item,())
    def mapped(path):return tuple((revisions.get(mid,mid),position) for mid,position in path)
    hold=getattr(tree,'_hold_view',False);tree._hold_view=True
    try:
        for path,expanded in state['expanded']:
            node=nodes.get(mapped(path))
            if node is not None:node.setExpanded(expanded)
        path=mapped(state['current'])
        while path not in nodes:path=path[:-1]
        current=nodes[path];tree.setCurrentItem(current);tree.clearSelection()
        for selected in state['selected']:
            node=nodes.get(mapped(selected))
            if node is not None:node.setSelected(True)
        if not tree.selectedItems():current.setSelected(True)
        window.show_item_info(current);tree.doItemsLayout()
        tree.verticalScrollBar().setValue(state['vertical'])
        anchor=nodes.get(mapped(state['anchor'])) if state['anchor'] is not None else None
        if anchor is not None:tree.verticalScrollBar().setValue(tree.verticalScrollBar().value()+tree.visualItemRect(anchor).top()-state['y'])
        tree.horizontalScrollBar().setValue(state['horizontal'])
    finally:tree._hold_view=hold


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
