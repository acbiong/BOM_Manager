"""Aligned, read-only side-by-side BOM comparison."""
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QMessageBox)
from services.bom_compare import FIELDS,compare_boms,value

class BomCompareDialog(QDialog):
    COLORS={'added':'#b9e9c3','deleted':'#f2b4b4','modified':'#ffe49a'}
    def __init__(self,service,parent=None):
        super().__init__(parent)
        self.service=service;self.setWindowTitle('BOM对比');self.resize(1400,800)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('对比已保存的BOM（不包含编辑窗口中未保存的修改）。绿色：右侧新增；黄色：双方修改；红色删除线：右侧删除。'))
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
            table.setHorizontalHeaderLabels(['层级 / 状态']+[label for _,label in FIELDS])
            table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True)
            table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.verticalHeader().hide();table.setColumnWidth(0,125)
            for i in range(1,len(FIELDS)+1):table.setColumnWidth(i,150 if i in (1,3,4,13) else 95)
        a,b=self.tables
        for source,target in [(a,b),(b,a)]:
            source.verticalScrollBar().valueChanged.connect(target.verticalScrollBar().setValue)
            source.horizontalScrollBar().valueChanged.connect(target.horizontalScrollBar().setValue)
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
            for table,node in zip(self.tables,(diff.left,diff.right)):
                for c,text in enumerate(([f"{'  '*diff.depth}{diff.depth} / {names[diff.status]}"]+[value(node,k) for k,_ in FIELDS]) if node else ['']*(len(FIELDS)+1)):
                    item=QTableWidgetItem(text);table.setItem(r,c,item)
                    item.setToolTip(text)
                    if node and diff.status!='same':
                        item.setBackground(QColor(self.COLORS[diff.status]));item.setForeground(QColor('#202020'))
                        font=item.font();font.setStrikeOut(diff.status=='deleted')
                        font.setBold(c>0 and FIELDS[c-1][0] in diff.changed);item.setFont(font)
            for table in self.tables:table.resizeRowToContents(r)
            height=max(t.rowHeight(r) for t in self.tables)
            for table in self.tables:table.setRowHeight(r,height)
        counts={s:sum(d.status==s for d in rows) for s in names}
        self.summary.setText('；'.join(f'{names[s]}：{counts[s]}' for s in names)+'（含根节点，排序变化不作为内容差异）')
