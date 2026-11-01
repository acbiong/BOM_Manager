"""Wrapped BOM rows and persistent, explicitly dragged column widths."""
import json
import math
from functools import lru_cache
from PyQt5 import sip
from PyQt5.QtCore import QObject, QEvent, QPointF, QSettings, QSize, QTimer, Qt
from PyQt5.QtGui import QFont, QFontMetrics, QPalette, QTextLayout, QTextOption
from PyQt5.QtWidgets import QHeaderView, QStyledItemDelegate, QStyleOptionViewItem, QStyle
from infrastructure.operation_progress import silent_progress


def text_layout(text,font,width,alignment):
    layout=QTextLayout(text.replace('\n','\u2028'),font)
    option=QTextOption();option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    option.setAlignment(Qt.Alignment(alignment));layout.setTextOption(option)
    height=0;count=0;layout.beginLayout()
    while True:
        line=layout.createLine()
        if not line.isValid():break
        line.setLineWidth(max(1,width));line.setPosition(QPointF(0,height))
        height+=line.height();count+=1
    layout.endLayout()
    return layout,math.ceil(height),count


@lru_cache(maxsize=4096)
def text_size(text,font_key,width,alignment):
    font=QFont();font.fromString(font_key)
    _,height,count=text_layout(text,font,width,alignment)
    return height,count>1


class BomTreeDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        tree=self.parent();opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        width=tree.columnWidth(index.column())
        if index.column()==tree.treePosition():
            depth=int(tree.rootIsDecorated());parent=index.parent()
            while parent.isValid():depth+=1;parent=parent.parent()
            width-=depth*tree.indentation()
        height,wrapped=text_size(opt.text,opt.font.toString(),max(1,width-8),int(opt.displayAlignment & Qt.AlignHorizontal_Mask))
        if not wrapped:
            opt.features &= ~QStyleOptionViewItem.WrapText
            return super().sizeHint(opt,index)
        return QSize(max(1,width),max(opt.fontMetrics.height(),height)+2)

    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        layout,height,count=text_layout(opt.text,opt.font,max(1,opt.rect.width()-8),int(opt.displayAlignment & Qt.AlignHorizontal_Mask))
        if count<=1:
            super().paint(painter,option,index);return
        opt.text='';self.parent().style().drawControl(QStyle.CE_ItemViewItem,opt,painter,self.parent())
        painter.save();painter.setClipRect(opt.rect)
        painter.setPen(opt.palette.color(QPalette.HighlightedText if opt.state & QStyle.State_Selected else QPalette.Text))
        layout.draw(painter,QPointF(opt.rect.left()+4,opt.rect.top()+max(1,(opt.rect.height()-height)/2)));painter.restore()


class BomTreeColumns(QObject):
    KEY='bom_tree/column_widths_v1'

    def __init__(self,tree,settings=None):
        super().__init__(tree);self.tree=tree;self.header=tree.header()
        self.settings=settings if settings is not None else QSettings('Biong','BOMManager')
        try:
            saved=json.loads(self.settings.value(self.KEY,'{}'))
            self.manual={int(k):v for k,v in saved.items() if str(k) in ('0','1','2','3','4') and type(v) is int and 20<=v<=10000}
        except (ValueError,TypeError,AttributeError):self.manual={}
        self.revision=0;self.measured=None;self.widths={};self.layout_signature=None
        self.applying=False;self.dragging=False;self.changed=False;self.closed=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.fit)
        self.header.setStretchLastSection(False);self.header.setSectionResizeMode(QHeaderView.Interactive)
        self.header.viewport().installEventFilter(self);tree.viewport().installEventFilter(self);tree.installEventFilter(self)
        self.header.sectionResized.connect(self.resized)
        self.header.sectionHandleDoubleClicked.connect(self.reset_column)
        tree.model().dataChanged.connect(self.data_changed)
        for signal in (tree.model().modelReset,tree.model().rowsInserted,tree.model().rowsRemoved,tree.model().layoutChanged,tree.model().headerDataChanged):signal.connect(self.invalidate)
        tree.itemExpanded.connect(self.schedule);tree.itemCollapsed.connect(self.schedule)
        tree.setWordWrap(True);tree.setUniformRowHeights(False);tree.setTextElideMode(Qt.ElideNone)
        tree.setItemDelegate(BomTreeDelegate(tree))

    def schedule(self,*args):
        if not self.closed and not self.timer.isActive():self.timer.start(0)

    def shutdown(self):
        """An accepted close must cancel queued work before native destruction."""
        if self.closed:return
        self.closed=True;self.timer.stop()
        self.tree.removeEventFilter(self);self.tree.viewport().removeEventFilter(self)
        if not sip.isdeleted(self.header):self.header.viewport().removeEventFilter(self)
        if self.changed:self.persist()

    def invalidate(self,*args):self.revision+=1;self.schedule()

    def data_changed(self,first,last,roles=None):
        if not roles or any(role in (Qt.DisplayRole,Qt.EditRole,Qt.FontRole,Qt.SizeHintRole) for role in roles):self.invalidate()

    def eventFilter(self,obj,event):
        if sip.isdeleted(self.header):return False
        kind=event.type()
        if obj is self.tree and kind==QEvent.Close:
            self.shutdown();return False
        if obj is self.header.viewport():
            if kind==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:self.dragging=True
            elif kind==QEvent.MouseButtonRelease:
                self.dragging=False
                if self.changed:self.persist()
        elif kind in (QEvent.Show,QEvent.Resize):self.schedule()
        elif kind in (QEvent.FontChange,QEvent.StyleChange):self.invalidate()
        return False

    def persist(self):
        self.settings.setValue(self.KEY,json.dumps(self.manual));self.settings.sync();self.changed=False

    def resized(self,column,old,width):
        if self.applying:return
        if self.dragging:
            self.manual[column]=width;self.changed=True
        # Programmatic sizing and restoring never become a user preference.
        self.layout_signature=None;self.schedule()

    def reset_column(self,column):
        self.manual.pop(column,None);self.persist();self.measured=None;self.schedule()

    @silent_progress()
    def fit(self,apply=True):
        self.timer.stop();tree=self.tree;header=self.header
        if self.closed:return
        if getattr(tree.window(),'_rendering_tree',False) or header.count()!=5:return
        tree.ensurePolished()
        signature=(self.revision,tree.font().toString(),header.font().toString(),tuple(sorted(self.manual)))
        if signature!=self.measured:
            char=max(1,tree.fontMetrics().horizontalAdvance('中'))
            widths={i:max(header.minimumSectionSize(),header.sectionSizeHint(i)) for i in range(1,5) if i not in self.manual}
            # One content scan for the still-automatic columns, including collapsed children.
            pending=[tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
            while pending:
                item=pending.pop();pending.extend(item.child(i) for i in range(item.childCount()))
                for column in widths:
                    metrics=QFontMetrics(item.font(column).resolve(tree.font()))
                    value=max((metrics.horizontalAdvance(line) for line in item.text(column).split('\n')),default=0)+12
                    widths[column]=max(widths[column],value)
            for column in widths:
                if column in (3,4):widths[column]=min(widths[column],char*(25 if column==3 else 12))
            self.widths=widths;self.measured=signature
        if not apply:return
        widths={**self.widths,**self.manual}
        if 0 not in widths:widths[0]=max(tree.fontMetrics().horizontalAdvance('中')*12,tree.viewport().width()-sum(widths.values()))
        target=(self.revision,tree.font().toString(),tuple(sorted(widths.items())))
        if target==self.layout_signature:return
        self.applying=True
        try:
            for column,width in widths.items():
                if header.sectionSize(column)!=width:header.resizeSection(column,width)
            tree.doItemsLayout();tree.viewport().update()
            self.layout_signature=target
        finally:self.applying=False
