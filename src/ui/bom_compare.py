"""Aligned, read-only side-by-side BOM comparison."""
from difflib import SequenceMatcher
from html import escape
from PyQt5.QtCore import Qt, QSize, QTimer, QItemSelection, QItemSelectionModel
from PyQt5.QtGui import QColor, QTextDocument, QPalette, QKeySequence, QFontMetrics, QFont, QTextOption
from PyQt5.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QMessageBox,QStyledItemDelegate,QStyleOptionViewItem,QStyle,QApplication,QShortcut)
from ui.bom_compare_table import BomCompareTable
from services.bom_compare import FIELDS,compare_boms,value

RICH_TEXT_ROLE = Qt.UserRole + 1
DISPLAY_FIELDS = [('material_code','物料编码') if key=='base_code' else (key,label)
                  for key,label in FIELDS if key!='version']

def display_value(node, field):
    if field=='material_code':return value(node,'base_code')+value(node,'version')
    return value(node,field)

def character_diff(text, other, color=None):
    """Escape literal material text; bold only nonmatching character spans."""
    chunks = []
    for operation, start, end, _, _ in SequenceMatcher(None,text,other,autojunk=False).get_opcodes():
        if start == end:continue
        fragment = escape(text[start:end])
        highlight='<b>'+fragment+'</b>'
        if color:highlight='<span style="background-color: '+color+'; color: #202020;">'+highlight+'</span>'
        chunks.append(fragment if operation == 'equal' else highlight)
    return ''.join(chunks).replace('\n','<br>')

class DifferenceDelegate(QStyledItemDelegate):
    def document(self, option, index):
        doc = QTextDocument();doc.setDocumentMargin(2);doc.setDefaultFont(option.font)
        text = index.data(RICH_TEXT_ROLE)
        if text is None:text=escape(str(index.data() or '')).replace('\n','<br>')
        if option.font.strikeOut():text='<s>'+text+'</s>'
        doc.setHtml('<div style="white-space: pre-wrap;">'+text+'</div>')
        text_option=doc.defaultTextOption()
        text_option.setAlignment(option.displayAlignment & Qt.AlignHorizontal_Mask)
        text_option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere);doc.setDefaultTextOption(text_option)
        doc.setTextWidth(max(1,option.rect.width()-6))
        return doc
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        doc=self.document(opt,index);opt.text=''
        style=opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem,opt,painter,opt.widget)
        painter.save();painter.setClipRect(opt.rect);painter.translate(opt.rect.left()+3,opt.rect.top()+max(0,(opt.rect.height()-doc.size().height())/2))
        context=doc.documentLayout().PaintContext()
        context.palette.setColor(QPalette.Text,opt.palette.color(QPalette.HighlightedText if opt.state & QStyle.State_Selected else QPalette.Text))
        doc.documentLayout().draw(painter,context);painter.restore()
    def sizeHint(self,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        if opt.widget:opt.rect.setWidth(opt.widget.columnWidth(index.column()))
        return QSize(opt.rect.width(),int(self.document(opt,index).size().height())+6)

class BomCompareDialog(QDialog):
    COLORS={'added':'#82d99b','deleted':'#f28b82','modified':'#ffc35c'}
    ROW_COLOR='#fff6cf'
    def __init__(self,service,parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.setSizeGripEnabled(True)
        self.service=service;self.setWindowTitle('BOM对比');self.resize(1400,800)
        layout=QVBoxLayout(self)
        legend=QLabel('对比已保存的BOM（不包含编辑窗口中未保存的修改）。淡黄色行：存在差异；变化文字背景绿色：新增，红色：删除，橙黄色：修改，并加粗。父项变化不计入子项差异。序号按对齐后的展示顺序生成，不改变原BOM。')
        legend.setWordWrap(True);layout.addWidget(legend)
        self.fullscreen_button=QPushButton('全屏（F11）');self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        layout.addWidget(self.fullscreen_button)
        QShortcut(QKeySequence('F11'),self,activated=self.toggle_fullscreen)
        selectors=QHBoxLayout();layout.addLayout(selectors)
        self.left=QComboBox();self.right=QComboBox()
        for label,combo in [('左侧基准BOM',self.left),('右侧目标BOM',self.right)]:
            selectors.addWidget(QLabel(label));selectors.addWidget(combo,1)
            combo.setMinimumWidth(0);combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.currentIndexChanged.connect(self.clear_results)
        tables=QHBoxLayout();layout.addLayout(tables,1)
        self.tables=[]
        for side in range(2):
            table=BomCompareTable(0,len(DISPLAY_FIELDS)+1);self.tables.append(table);tables.addWidget(table,1)
            table.setHorizontalHeaderLabels(['状态']+[label for _,label in DISPLAY_FIELDS])
            table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setItemDelegate(DifferenceDelegate(table))
            table.frozen.setItemDelegate(DifferenceDelegate(table.frozen))
            table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
            table.verticalHeader().hide();table.setColumnWidth(0,125)
            for i in range(1,len(DISPLAY_FIELDS)+1):table.setColumnWidth(i,150 if i in (1,3,4,13) else 95)
        self.row_timer=QTimer(self);self.row_timer.setSingleShot(True);self.row_timer.timeout.connect(self.align_rows)
        self._syncing_selection=False
        a,b=self.tables
        for source,target in [(a,b),(b,a)]:
            source.layoutChanged.connect(lambda:self.row_timer.start(0))
            source.itemSelectionChanged.connect(lambda s=source,t=target:self.sync_selection(s,t))
            source.verticalScrollBar().valueChanged.connect(target.verticalScrollBar().setValue)
            source.horizontalScrollBar().valueChanged.connect(target.horizontalScrollBar().setValue)
            source.horizontalHeader().sectionResized.connect(lambda *args:self.row_timer.start(0))
            source.horizontalHeader().sectionResized.connect(lambda col,old,new,t=target:t.setColumnWidth(col,new))
        self.summary=QLabel('请选择左右BOM后点击对比。');layout.addWidget(self.summary)
        self.button=QPushButton('对比');self.button.clicked.connect(self.compare);layout.addWidget(self.button)
        self.reload_choices()
    def sync_selection(self,source,target):
        if self._syncing_selection:return
        self._syncing_selection=True
        try:
            rows=source.selectionModel().selectedRows()
            if not rows:
                target.clearSelection();return
            row=rows[0].row()
            if row>=target.rowCount():return
            first=target.model().index(row,0)
            last=target.model().index(row,target.columnCount()-1)
            target.selectionModel().select(QItemSelection(first,last),QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            target.selectionModel().setCurrentIndex(first,QItemSelectionModel.NoUpdate)
        finally:self._syncing_selection=False
    def clear_results(self,*args):
        if not hasattr(self,'tables'):return
        for table in self.tables:table.setRowCount(0)
        self.summary.setText('请选择左右BOM后点击对比。')
    def reload_choices(self):
        previous=[self.left.currentData(),self.right.currentData()]
        rows=list(self.service.skus())
        for index,combo in enumerate((self.left,self.right)):
            combo.clear()
            for row in rows:
                combo.addItem(f"{row['base_code']}{row['version']} {row['name']}  镜像{row['mirror_version']}",row['id'])
            chosen=combo.findData(previous[index])
            combo.setCurrentIndex(chosen if chosen>=0 else min(index,len(rows)-1))
        self.button.setEnabled(bool(rows))
    def compare(self):
        try:rows=compare_boms(self.service,self.left.currentData(),self.right.currentData())
        except Exception as exc:
            self.clear_results();QMessageBox.warning(self,'BOM对比失败',str(exc));self.reload_choices();return
        self.clear_results()
        names={'added':'新增','deleted':'删除','modified':'修改','same':'相同','replaced':'换料','exchanged':'交换'}
        for table in self.tables:table.setRowCount(len(rows))
        for r,diff in enumerate(rows):
            for table,node,other in ((self.tables[0],diff.left,diff.right),(self.tables[1],diff.right,diff.left)):
                side_status=diff.status
                texts=([names[side_status]]+[display_value(node,k) for k,_ in DISPLAY_FIELDS]) if node else ['']*(len(DISPLAY_FIELDS)+1)
                for c,text in enumerate(texts):
                    item=QTableWidgetItem(text);table.setItem(r,c,item);item.setToolTip(text)
                    field=DISPLAY_FIELDS[c-1][0] if c else 'status'
                    if field in ('status','level','serial','unit','quantity','mp_flag'):item.setTextAlignment(Qt.AlignCenter)
                    if diff.status!='same':
                        item.setBackground(QColor(self.ROW_COLOR));item.setForeground(QColor('#202020'))
                    # Only differing character spans get a stronger highlight.
                    if c and node:
                        peer=display_value(other,DISPLAY_FIELDS[c-1][0]) if other else ''
                        field=DISPLAY_FIELDS[c-1][0]
                        changed=field in diff.changed or (field=='material_code' and bool({'base_code','version'}.intersection(diff.changed)))
                        if text!=peer and (other is None or changed):
                            color=self.COLORS[side_status if other is None else 'modified']
                            item.setForeground(QColor('#202020'))
                            item.setData(RICH_TEXT_ROLE,character_diff(text,'' if field=='material_code' else peer,color))
                            font=item.font();font.setStrikeOut(side_status=='deleted');item.setFont(font)
        self.auto_columns()
        self.align_rows()
        counts={s:sum(d.status==s for d in rows) for s in names}
        self.summary.setText('；'.join(f'{names[s]}：{counts[s]}' for s in names)+'（含根节点，排序变化不作为内容差异）')

    def auto_columns(self):
        font=QFont(self.font());font.setBold(True);metrics=QFontMetrics(font)
        self.max_column_width=metrics.horizontalAdvance('中')*30
        for table in self.tables:table.horizontalHeader().setMaximumSectionSize(self.max_column_width)
        for col in range(self.tables[0].columnCount()):
            width=metrics.horizontalAdvance(self.tables[0].horizontalHeaderItem(col).text())+20
            for table in self.tables:
                for row in range(table.rowCount()):
                    for line in table.item(row,col).text().splitlines():
                        width=max(width,metrics.horizontalAdvance(line)+12)
            for table in self.tables:table.setColumnWidth(col,min(self.max_column_width,width))

    def toggle_fullscreen(self):
        if self.isFullScreen():
            if self._was_maximized:self.showMaximized()
            else:self.showNormal()
        else:
            self._was_maximized=self.isMaximized();self.showFullScreen()
        self.fullscreen_button.setText('退出全屏（F11）' if self.isFullScreen() else '全屏（F11）')
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen();event.accept();return
        super().keyPressEvent(event)
    def align_rows(self):
        if not self.tables or not self.tables[0].rowCount():return
        # Block intermediate scrollbar range/value updates while recomputing heights.
        position=self.tables[0].verticalScrollBar().value()
        bars=[t.verticalScrollBar() for t in self.tables]
        for bar in bars:bar.blockSignals(True)
        for table in self.tables:table.resizeRowsToContents()
        for row in range(self.tables[0].rowCount()):
            height=max(t.rowHeight(row) for t in self.tables)
            for table in self.tables:
                if table.frozen.isVisible():
                    option=QStyleOptionViewItem();option.widget=table.frozen
                    for col in table.FROZEN_COLUMNS:
                        height=max(height,table.frozen.itemDelegate().sizeHint(option,table.model().index(row,col)).height())
            for table in self.tables:table.setRowHeight(row,height)
        for bar in bars:bar.setValue(position);bar.blockSignals(False)
        for table in self.tables:table.sync_frozen()
