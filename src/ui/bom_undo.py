"""Window-local undo/redo of unsaved BOM drafts; never reverses database writes."""
from copy import deepcopy
from functools import wraps
from time import monotonic
from PyQt5.QtCore import QObject,QEvent,Qt
from PyQt5.QtWidgets import QAction
from infrastructure.events import WindowRefreshBus


def undoable(method):
    @wraps(method)
    def wrapped(window,*args,**kwargs):
        history=getattr(window,'history',None)
        if history is None or history.depth or history.restoring or window._loading_fields:
            return method(window,*args,**kwargs)
        before=history.capture();history.depth+=1
        try:return method(window,*args,**kwargs)
        finally:
            history.depth-=1
            key=(args[0],id(window.current_item)) if method.__name__=='update_tree_field' else None
            history.record(before,history.capture(),key)
    return wrapped


class BomUndo(QObject):
    def __init__(self,window,toolbar):
        super().__init__(window);self.w=window;self.undo_stack=[];self.redo_stack=[];self.depth=0;self.restoring=False;self.last_key=None;self.last_time=0
        window.undo_action=QAction('撤销',window);window.redo_action=QAction('恢复',window)
        for action,shortcut,callback in [(window.undo_action,'Ctrl+Z',self.undo),(window.redo_action,'Ctrl+Y',self.redo)]:
            action.setShortcut(shortcut);action.setShortcutContext(Qt.WindowShortcut);action.triggered.connect(callback);toolbar.insertAction(window.refresh_action,action)
        for key in ('quantity','position','remark'):
            widget=window.fields[key];widget.installEventFilter(self)
            for child in widget.findChildren(QObject):child.installEventFilter(self)
        self.update()
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.FocusIn,QEvent.FocusOut):self.last_key=None
        if event.type() in (QEvent.ShortcutOverride,QEvent.KeyPress) and event.modifiers()==Qt.ControlModifier and event.key() in (Qt.Key_Z,Qt.Key_Y):
            if event.type()==QEvent.KeyPress:
                (self.undo if event.key()==Qt.Key_Z else self.redo)()
            event.accept();return True
        return super().eventFilter(obj,event)
    def update(self):
        allowed=not self.w.is_locked() and not self.w._saving
        self.w.undo_action.setEnabled(allowed and bool(self.undo_stack));self.w.redo_action.setEnabled(allowed and bool(self.redo_stack))
    def clear(self):
        self.undo_stack.clear();self.redo_stack.clear();self.last_key=None;self.update()
    def capture(self):
        w=self.w
        def path(item):
            result=[]
            while item is not None and item.parent() is not None:
                result.insert(0,item.parent().indexOfChild(item));item=item.parent()
            return tuple(result)
        state={name:deepcopy(getattr(w,name,None)) for name in ('_history_decision_tokens','_material_edits','_history_choices','_history_parent_versions','_deleted_relations','_alternate_edits','_draft_baselines','_external_paths','_baseline_tree','_root_baseline','_root_color_dirty')}
        state.update(tree=deepcopy(w.capture_tree()),root=deepcopy(w.root_item.data(0,Qt.UserRole)),dirty=w.dirty,save=w.save_action.isEnabled(),export=w.export_action.isEnabled())
        state['external_info']=(getattr(w,'_undo_external_epoch',0),w.notice.text(),w.refresh_action.isEnabled())
        state['view']=(path(w.tree.currentItem()),[path(item) for item in w.tree.selectedItems()],[(path(item),item.isExpanded()) for _,item in w.expansion_nodes()],w.tree.verticalScrollBar().value(),w.tree.horizontalScrollBar().value())
        return state
    def record(self,before,after,key):
        if {k:v for k,v in before.items() if k not in ('view','external_info','_history_decision_tokens')}=={k:v for k,v in after.items() if k not in ('view','external_info','_history_decision_tokens')}:return
        now=monotonic()
        if key is not None and key==self.last_key and now-self.last_time<0.8 and self.undo_stack and not self.redo_stack:
            self.undo_stack[-1]=(self.undo_stack[-1][0],after)
        else:self.undo_stack.append((before,after))
        self.undo_stack=self.undo_stack[-100:];self.redo_stack.clear();self.last_key=key;self.last_time=now;self.update()
    def restore(self,state):
        w=self.w;self.restoring=True;w.tree.setUpdatesEnabled(False)
        try:
            for name,value in state.items():
                if name.startswith('_'):setattr(w,name,deepcopy(value))
            w.render_tree(deepcopy(state['tree']),fit=False);w.root_item.setData(0,Qt.UserRole,deepcopy(state['root']));w.dirty=state['dirty']
            current,selected,expanded,vertical,horizontal=state['view']
            def item_at(path):
                item=w.root_item
                for index in path:
                    if index>=item.childCount():return w.root_item
                    item=item.child(index)
                return item
            for path,value in expanded:item_at(path).setExpanded(value)
            w.tree.clearSelection();w.tree.setCurrentItem(item_at(current))
            for path in selected:item_at(path).setSelected(True)
            w.show_item_info(item_at(current));w.refresh_styles();w.tree.doItemsLayout();w.tree.verticalScrollBar().setValue(vertical);w.tree.horizontalScrollBar().setValue(horizontal)
            epoch,notice,refresh=state['external_info']
            if epoch==getattr(w,'_undo_external_epoch',0):w.notice.setText(notice);w.refresh_action.setEnabled(refresh)
            w.save_action.setEnabled(state['save'] and not w.is_locked());w.export_action.setEnabled(state['export'] and not w.refresh_action.isEnabled())
        finally:self.restoring=False;w.tree.setUpdatesEnabled(True)
        w.svc.publish({'type':'bom_draft_changed'})
    def undo(self):
        if not self.undo_stack or self.w.is_locked() or self.w._saving:return
        entry=self.undo_stack.pop();self.restore(entry[0]);self.redo_stack.append(entry);self.last_key=None;self.update()
    def redo(self):
        if not self.redo_stack or self.w.is_locked() or self.w._saving:return
        entry=self.redo_stack.pop();self.restore(entry[1]);self.undo_stack.append(entry);self.last_key=None;self.update()
