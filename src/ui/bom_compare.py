"""Aligned, read-only side-by-side BOM comparison."""
from difflib import SequenceMatcher
from html import escape
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QColor, QTextDocument, QPalette
from PyQt5.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QMessageBox,QStyledItemDelegate,QStyleOptionViewItem,QStyle,QApplication)
from services.bom_compare import FIELDS,compare_boms,value

RICH_TEXT_ROLE = Qt.UserRole + 1

def character_diff(text, other):
    """Escape literal material text; bold only nonmatching character spans."""
    chunks = []
    for operation, start, end, _, _ in SequenceMatcher(None,text,other,autojunk=False).get_opcodes():
        if start == end:continue
        fragment = escape(text[start:end])
        chunks.append(fragment if operation == 'equal' else '<b>'+fragment+'</b>')
    return ''.join(chunks).replace('\n','<br>')

class DifferenceDelegate(QStyledItemDelegate):
    def document(self, option, index):
        doc = QTextDocument();doc.setDocumentMargin(2);doc.setDefaultFont(option.font)
        text = index.data(RICH_TEXT_ROLE)
        if text is None:text=escape(str(index.data() or '')).replace('\n','<br>')
        if option.font.strikeOut():text='<s>'+text+'</s>'
        doc.setHtml('<div style="white-space: pre-wrap;">'+text+'</div>')
        doc.setTextWidth(max(1,option.rect.width()-6))
        return doc
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        doc=self.document(opt,index);opt.text=''
        style=opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem,opt,painter,opt.widget)
        painter.save();painter.setClipRect(opt.rect);painter.translate(opt.rect.left()+3,opt.rect.top())
        context=doc.documentLayout().PaintContext()
        context.palette.setColor(QPalette.Text,opt.palette.color(QPalette.HighlightedText if opt.state & QStyle.State_Selected else QPalette.Text))
        doc.documentLayout().draw(painter,context);painter.restore()
    def sizeHint(self,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        if opt.widget:opt.rect.setWidth(opt.widget.columnWidth(index.column()))
        return QSize(opt.rect.width(),int(self.document(opt,index).size().height())+6)

class BomCompareDialog(QDialog):
    COLORS={'added':'#b9e9c3','deleted':'#f2b4b4','modified':'#ffe49a'}
    def __init__(self,service,parent=None):
        super().__init__(parent)
        self.service=service;self.setWindowTitle('BOM对比');self.resize(1400,800)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('对比已保存的BOM（不包含编辑窗口中未保存的修改）。绿色：右侧新增；黄色：差异单元格；红色删除线：右侧删除；仅差异文字加粗。'))
        selectors=QHBoxLayout();layout.addLayout(selectors)
        self.left=QComboBox();self.right=QComboBox()
        for label,combo in [('左侧基准BOM',self.left),('右侧目标BOM',self.right)]:
            selectors.addWidget(QLabel(label));selectors.addWidget(combo,1)
            combo.setMinimumWidth(0);combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.currentIndexChanged.connect(self.clear_results)
        tables=QHBoxLayout();layout.addLayout(tables,1)
        self.tables=[]
        for side in range(2):
            table=QTableWidget(0,len(FIELDS)+1);self.tables.append(table);tables.addWidget(table,1)
            table.setHorizontalHeaderLabels(['状态']+[label for _,label in FIELDS])
            table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True)
            table.setItemDelegate(DifferenceDelegate(table))
            table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.verticalHeader().hide();table.setColumnWidth(0,125)
            for i in range(1,len(FIELDS)+1):table.setColumnWidth(i,150 if i in (1,3,4,13) else 95)
        self.row_timer=QTimer(self);self.row_timer.setSingleShot(True);self.row_timer.timeout.connect(self.align_rows)
        a,b=self.tables
        for source,target in [(a,b),(b,a)]:
            source.verticalScrollBar().valueChanged.connect(target.verticalScrollBar().setValue)
            source.horizontalScrollBar().valueChanged.connect(target.horizontalScrollBar().setValue)
            source.horizontalHeader().sectionResized.connect(lambda *args:self.row_timer.start(0))
            source.horizontalHeader().sectionResized.connect(lambda col,old,new,t=target:t.setColumnWidth(col,new))
        self.summary=QLabel('请选择左右BOM后点击对比。');layout.addWidget(self.summary)
        self.button=QPushButton('对比');self.button.clicked.connect(self.compare);layout.addWidget(self.button)
        self.reload_choices()
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
        names={'added':'新增','deleted':'删除','modified':'修改','same':'相同'}
        for table in self.tables:table.setRowCount(len(rows))
        for r,diff in enumerate(rows):
            for table,node,other in ((self.tables[0],diff.left,diff.right),(self.tables[1],diff.right,diff.left)):
                texts=([names[diff.status]]+[value(node,k) for k,_ in FIELDS]) if node else ['']*(len(FIELDS)+1)
                for c,text in enumerate(texts):
                    item=QTableWidgetItem(text);table.setItem(r,c,item);item.setToolTip(text)
                    # Status is metadata, not a changed BOM field. Empty/identical cells stay unstyled.
                    if c and node:
                        peer=value(other,FIELDS[c-1][0]) if other else ''
                        if text!=peer:
                            item.setBackground(QColor(self.COLORS['modified' if other else diff.status]))
                            item.setForeground(QColor('#202020'))
                            item.setData(RICH_TEXT_ROLE,character_diff(text,peer))
                            font=item.font();font.setStrikeOut(diff.status=='deleted');item.setFont(font)
        self.align_rows()
        counts={s:sum(d.status==s for d in rows) for s in names}
        self.summary.setText('；'.join(f'{names[s]}：{counts[s]}' for s in names)+'（含根节点，排序变化不作为内容差异）')

    def align_rows(self):
        for table in self.tables:table.resizeRowsToContents()
        for row in range(self.tables[0].rowCount()):
            height=max(t.rowHeight(row) for t in self.tables)
            for table in self.tables:table.setRowHeight(row,height)
