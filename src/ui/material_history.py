"""Nonmodal material history decisions and immutable subtree inspection."""
from PyQt5.QtCore import Qt,QEvent,QTimer
from PyQt5.QtGui import QColor,QBrush,QFont,QPalette
from PyQt5.QtWidgets import (QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QPushButton, QTreeWidget, QTreeWidgetItem, QAbstractItemView,QScrollArea,QWidget,QFormLayout,QHBoxLayout,QComboBox,QSplitter,QGroupBox)
from ui.interactive_windows import QDialog,QMessageBox
from services import material_history as history
from domain.quantity import format_quantity
from html import escape
from ui.bom_change_style import ADDED,DELETED,MODIFIED,MOVED,MOVED_TEXT,level_background,change_foreground

HISTORY_DIFF_ROLE=Qt.UserRole+2


class MaterialHistoryChoiceDialog(QDialog):
    def __init__(self, service, mid, title, parent=None,impact_mid=None,comparison=None,scope=None):
        super().__init__(parent); self.setWindowTitle(title+' — 物料历史版本'); self.resize(850,480)
        layout=QVBoxLayout(self); material=service.material_snapshot(mid)
        label=QLabel(material['base_code']+material['version']+' '+material['name']+
                     '\n当前BOM始终参与变更。仅列出作为主料使用的其他BOM，包含旧SKU历史及不同物料历史；仅作替代料的不参与判断。仅在保存BOM后生效。');label.setWordWrap(True);layout.addWidget(label)
        from services import history_selection
        self.service=service;self.material_id=mid;self.impact_mid=impact_mid
        from services.history_state import matching_skus
        all_refs=history_selection.references(service,mid) if scope is None else scope[0]
        self.matching_sku_ids=matching_skus(service,mid,comparison,all_refs) if scope is None else scope[1]
        self.comparison=comparison
        displayed=[r for r in all_refs if r['id'] not in self.matching_sku_ids]
        self.reference_token=history_selection.reference_token(all_refs)
        if comparison is not None:label.setText(label.text()+'\n已排除物料及替代料内容与本次待保存状态一致的BOM，仅提示仍有差异的BOM。')
        table=QTableWidget(len(displayed),5);self.table=table
        table.setHorizontalHeaderLabels(['一同变更','SKU编码','SKU名称','SKU历史版本','物料历史版本']);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True)
        for row,sku in enumerate(displayed):
            check=QTableWidgetItem();check.setData(Qt.UserRole,sku['id']);check.setCheckState(Qt.Unchecked)
            check.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable if not sku['locked'] else Qt.NoItemFlags)
            table.setItem(row,0,check)
            name=sku['name']+('（已锁定，不能变更）' if sku['locked'] else '')
            for col,value in enumerate([sku['base_code']+sku['version'],name,sku['mirror_version'],sku['material_history_version']],1):table.setItem(row,col,QTableWidgetItem(str(value)))
        actions=QHBoxLayout()
        for title,checked in [('全选可变更BOM',True),('全不选',False)]:
            button=QPushButton(title);button.clicked.connect(lambda _,value=checked:self.select_all(value));actions.addWidget(button)
        layout.addLayout(actions)
        table.resizeColumnsToContents();table.horizontalHeader().setStretchLastSection(True);layout.addWidget(table,1)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        table.itemChanged.connect(self.update_note);self.update_note()
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def select_all(self,checked):
        for row in range(self.table.rowCount()):
            item=self.table.item(row,0)
            if item.flags() & Qt.ItemIsEnabled:item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    def mode(self):
        from services.history_selection import Selection
        ids=frozenset(self.table.item(row,0).data(Qt.UserRole) for row in range(self.table.rowCount()) if self.table.item(row,0).checkState()==Qt.Checked)
        return Selection(self.material_id,ids,self.reference_token,self.impact_mid,self.comparison,self.matching_sku_ids)
    def update_note(self,*args):
        count=len(self.mode().sku_ids)
        self.note.setText(('全部需要变更的主料BOM已勾选；状态一致的BOM无需重复变更。' if self.comparison is not None else '全部主料引用BOM一同变更，不因替代料引用新增历史版本。') if count==self.table.rowCount() else
                         '有其他BOM未参与变更：保留其原内容，为本次变更新增或复用对应物料历史版本。')
    def accept(self):
        from services import history_selection
        refs=history_selection.references(self.service,self.material_id)
        if self.reference_token!=history_selection.reference_token(refs):
            QMessageBox.warning(self,'引用范围已变化','其他BOM内容、引用或锁定状态已变化，请取消后重新选择。');return
        if self.comparison is not None:
            from services.history_state import matching_skus
            if self.matching_sku_ids!=matching_skus(self.service,self.material_id,self.comparison,refs):
                QMessageBox.warning(self,'物料状态已变化','其他BOM的物料或替代料内容已变化，请取消后重新选择。');return
        super().accept()


class MaterialHistoryDialog(QDialog):
    FIELDS=[('base_code','基础编码'),('version','物料版本号'),('name','名称'),('description','规格描述'),
            ('unit','单位'),('grade','物料等级'),('manufacturer','制造商'),('mpn','MPN'),('mp_flag','M/P'),
            ('quantity','用量'),('position','位置'),('remark','备注'),
            ('history_version','物料历史版本'),('created_at','记录时间'),('alternates','替代料')]

    def __init__(self,service,mid,version,parent=None):
        super().__init__(parent);self.resize(1150,760);self.service=service;self.material_id=mid
        self._style_timer=QTimer(self);self._style_timer.setSingleShot(True);self._style_timer.timeout.connect(self.restyle)
        layout=QVBoxLayout(self);bar=QHBoxLayout();bar.addWidget(QLabel('查看物料历史版本：'))
        self.version_combo=QComboBox();self.version_combo.setMinimumWidth(130)
        for row in history.versions(service,mid):self.version_combo.addItem(str(row['history_version']),row['history_version'])
        bar.addWidget(self.version_combo);self.root_label=QLabel();self.root_label.setTextFormat(Qt.PlainText);self.root_label.setWordWrap(True);bar.addWidget(self.root_label,1);layout.addLayout(bar)
        self.comparison_label=QLabel();self.comparison_label.setWordWrap(True);layout.addWidget(self.comparison_label)
        legend=QLabel(f'<span style="color:{ADDED}">新增</span>；<span style="color:{DELETED};text-decoration:line-through">删除</span>；<span style="color:{MODIFIED}"><b>修改字段加粗</b></span>；<span style="background-color:{MOVED};color:{MOVED_TEXT}">顺序调整</span>。标注与BOM编辑缓存一致；悬停查看前后值。')
        legend.setWordWrap(True);layout.addWidget(legend)
        self.info=QWidget();form=QFormLayout(self.info);form.setLabelAlignment(Qt.AlignRight|Qt.AlignVCenter);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.attribute_labels={};self.attribute_values={}
        for key,title in self.FIELDS:
            label=QLabel(title+'：');label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            value=QLabel();value.setAlignment(Qt.AlignLeft|Qt.AlignVCenter);value.setWordWrap(True);value.setTextFormat(Qt.PlainText);value.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
            value.setMinimumWidth(0);form.addRow(label,value);self.attribute_labels[key]=label;self.attribute_values[key]=value
        info_scroll=QScrollArea();info_scroll.setWidgetResizable(True);info_scroll.setWidget(self.info)
        info_group=QGroupBox('选中物料的历史属性');QVBoxLayout(info_group).addWidget(info_scroll)
        self.references_group=QGroupBox('以主料包含当前物料历史版本的SKU BOM');reference_layout=QVBoxLayout(self.references_group)
        self.reference_label=QLabel();self.reference_label.setWordWrap(True);self.reference_label.setTextFormat(Qt.PlainText);reference_layout.addWidget(self.reference_label)
        self.references=QTableWidget(0,3);self.references.setHorizontalHeaderLabels(['SKU编码','SKU名称','SKU历史版本'])
        self.references.setEditTriggers(QAbstractItemView.NoEditTriggers);self.references.setSelectionBehavior(QAbstractItemView.SelectRows);self.references.setWordWrap(True)
        self.references.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded);self.references.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded);reference_layout.addWidget(self.references,1)
        panels=QSplitter();panels.addWidget(info_group);panels.addWidget(self.references_group);panels.setSizes([530,570]);panels.setMinimumHeight(200)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['物料编码','物料名称','物料历史版本','数量','单位','位置','备注','替代料']);self.tree.setWordWrap(True)
        from ui.bom_compare import DifferenceDelegate
        self.tree.setItemDelegateForColumn(7,DifferenceDelegate(self.tree))
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded);self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        vertical=QSplitter(Qt.Vertical);vertical.addWidget(panels);vertical.addWidget(self.tree);vertical.setSizes([340,340]);layout.addWidget(vertical,1)
        self.tree.currentItemChanged.connect(self.show_info)
        index=self.version_combo.findData(version)
        if index<0:raise ValueError('物料历史版本不存在')
        self.version_combo.setCurrentIndex(index);self.load_version(version)
        self.version_combo.currentIndexChanged.connect(lambda _:self.load_version(self.version_combo.currentData()))
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def load_version(self,version):
        if version is None:return
        from ui.material_history_diff import compare
        from ui.bom_compare import RICH_TEXT_ROLE
        diff,self.previous_version=compare(self.service,self.material_id,version)
        record=diff['record'];attrs=record['attributes']
        label=attrs['base_code']+attrs['version']+' '+attrs['name']
        self.root_label.setText(label);self.setWindowTitle(label+' 物料历史版本'+str(version)+'（只读）')
        self.comparison_label.setText(f'历史版本 {version} 对比上一现存历史版本 {self.previous_version}；删除行仅用于对照。' if self.previous_version is not None else f'历史版本 {version} 为首个现存版本，无上一版本可比较。')
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            def append(parent,node):
                item=QTreeWidgetItem(parent,self.display_values(node['record'],node['edge'])+[self.alternative_text(node)])
                item.setData(0,Qt.UserRole,node['record']);item.setData(0,HISTORY_DIFF_ROLE,{k:v for k,v in node.items() if k!='children'})
                item.setData(7,RICH_TEXT_ROLE,self.alternative_html(node))
                if node['previous']:
                    old=self.display_values(node['previous'],node['old_edge'])
                    for column in node['columns']:
                        if column<7:item.setToolTip(column,f'上一版本：{old[column] or "（空）"}\n当前版本：{item.text(column) or "（空）"}')
                        else:item.setToolTip(column,'上一版本：'+(self.previous_alternative_text(node) or '（空）')+'\n当前版本：'+(self.alternative_text(node) or '（空）'))
                    if node['fields']:item.setToolTip(0,item.toolTip(0)+'\n修改属性：'+ '、'.join(title for key,title in self.FIELDS if key in node['fields']))
                if node['deleted']:
                    for col in range(8):item.setToolTip(col,'已从当前版本移除；显示上一版本内容供对照。')
                if node['moved']:item.setToolTip(0,item.toolTip(0)+'\n同级排列顺序发生变化。')
                for child in node['children']:append(item,child)
                return item
            root=append(self.tree,diff);self.tree.setCurrentItem(root);self.tree.expandToDepth(1)
        finally:self.tree.blockSignals(False)
        self.style_items()
        self.show_info(root)
        from ui.table_layout import fit_columns
        fit_columns(self.tree)

    @staticmethod
    def display_values(record,edge):
        a=record['attributes']
        return [a['base_code']+a['version'],a['name'],str(record['history_version']),format_quantity(edge.get('quantity',1)),edge.get('unit',a['unit']),edge.get('position',''),edge.get('remark','')]

    @staticmethod
    def alternative_label(alt):
        a=alt['record']['attributes']
        return a['base_code']+a['version']+' '+a['name']+' [历史版本'+str(alt['record']['history_version'])+']'

    def alternative_text(self,node):
        return '\n'.join(self.alternative_label(a)+('（已删除）' if a['state']=='deleted' else '') for a in node['alternatives'])

    def previous_alternative_text(self,node):
        return '\n'.join(self.alternative_label(dict(record=a)) for a in node['old_alternatives'])

    def alternative_html(self,node):
        parts=[]
        for alt in node['alternatives']:
            text=escape(self.alternative_label(alt)).replace('\n','<br>');state=alt['state']
            color={'added':ADDED,'deleted':DELETED,'modified':MODIFIED}.get(state)
            if state=='deleted':text='<s>'+text+'（已删除）</s>'
            if state=='modified':text='<b>'+text+'</b>'
            if color:text=f'<span style="color:{color}">'+text+'</span>'
            parts.append(text)
        return '<br>'.join(parts)

    def style_items(self):
        from PyQt5.QtWidgets import QApplication
        dark=bool(QApplication.instance().property('bom_dark_theme'))
        def style(item,depth):
            node=item.data(0,HISTORY_DIFF_ROLE);changed=bool(node['fields'] or node['columns'])
            color=change_foreground(node['added'],node['deleted'],changed)
            if node['moved'] and color is None:color=MOVED_TEXT
            background=QColor(MOVED) if node['moved'] else level_background(depth,dark)
            for column in range(self.tree.columnCount()):
                font=QFont(self.tree.font());font.setBold(column in node['columns'] and not node['deleted']);font.setStrikeOut(node['deleted'])
                item.setFont(column,font);item.setForeground(column,QBrush(QColor(color)) if color else QBrush());item.setBackground(column,QBrush(background))
            for i in range(item.childCount()):style(item.child(i),depth+1)
        if self.tree.topLevelItemCount():style(self.tree.topLevelItem(0),0)

    def style_info(self,item):
        if item is None:return
        node=item.data(0,HISTORY_DIFF_ROLE);previous=node['previous'];before=previous['attributes'] if previous else {}
        for key,_ in self.FIELDS:
            changed=key in node['fields'] or {'quantity':3,'unit':4,'position':5,'remark':6,'alternates':7,'history_version':2}.get(key) in node['columns']
            color=change_foreground(node['added'],node['deleted'],changed)
            value=self.attribute_values[key];font=QFont(self.font());font.setBold(changed and not node['deleted']);font.setStrikeOut(node['deleted']);value.setFont(font)
            palette=QPalette(self.palette())
            if color:palette.setColor(QPalette.WindowText,QColor(color))
            value.setPalette(palette);value.setToolTip('')
            if changed:
                if key=='alternates':old=self.previous_alternative_text(node)
                elif key=='quantity':old=format_quantity(node['old_edge'].get(key,1))
                elif key in ('position','remark','unit'):old=str(node['old_edge'].get(key,before.get(key,'')))
                else:old=str(previous['history_version'] if key=='history_version' else before.get(key,''))
                value.setToolTip('上一版本：'+(old or '（空）'))

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange,QEvent.StyleChange,QEvent.FontChange) and hasattr(self,'tree'):
            # Application theme propagation also overwrites child palettes/fonts.
            # Reapply once after that propagation, without rebuilding or querying.
            self._style_timer.start(0)

    def restyle(self):
        self.style_items();self.style_info(self.tree.currentItem())

    def show_info(self,item,previous=None):
        if item is None:return
        record=item.data(0,Qt.UserRole);a=record['attributes']
        node=item.data(0,HISTORY_DIFF_ROLE)
        values=dict(a,history_version=record['history_version'],created_at=record['created_at'].split('.')[0],
                    unit=node['edge'].get('unit',a['unit']),
                    quantity=format_quantity(node['edge'].get('quantity',1)),position=node['edge'].get('position',''),remark=node['edge'].get('remark',''),alternates=item.text(7))
        for key,_ in self.FIELDS:
            if key!='alternates':self.attribute_values[key].setText(str(values.get(key,'') or '（空）'))
        self.attribute_values['alternates'].setTextFormat(Qt.RichText)
        self.attribute_values['alternates'].setText(self.alternative_html(node) or '（空）')
        self.style_info(item)
        references=history.sku_references(self.service,record['material_id'],record['history_version'])
        title=a['base_code']+a['version']+' '+a['name']+' / 物料历史版本'+str(record['history_version'])
        self.reference_label.setText(('已删除的对照节点；以下为其原历史版本的主料引用。\n' if node['deleted'] else '')+title+('\n共计'+str(len(references))+'个主料引用SKU BOM（包含旧SKU历史版本）' if references else '\n此物料历史版本未被任何SKU BOM作为主料引用'))
        self.references.setRowCount(len(references))
        for row,sku in enumerate(references):
            for col,text in enumerate((sku['base_code']+sku['version'],sku['name'],sku['mirror_version'])):
                cell=QTableWidgetItem(str(text));cell.setData(Qt.UserRole,sku['id']);cell.setTextAlignment(Qt.AlignCenter if col==2 else Qt.AlignLeft|Qt.AlignVCenter);self.references.setItem(row,col,cell)
        from ui.table_layout import fit_columns
        fit_columns(self.references,apply=False)
        columns=self.references._proportional_columns
        columns.widths[1]=min(columns.widths[1],15*self.references.fontMetrics().horizontalAdvance('中'))
        columns.apply()


def update_library_material(owner,mid,data):
    """Library edits use the same checked transaction as BOM edits."""
    from services.snapshot_bom import revision_conflicts
    from ui.parent_revision import ParentRevisionDialog
    source,root=history.catalog_source(owner.svc,mid)
    if root is None:return owner.svc.update_material(mid,data)
    from services import history_selection
    if history_selection.references(source,mid):
        choice=MaterialHistoryChoiceDialog(source,mid,'编辑物料',owner)
        if choice.exec_()!=QDialog.Accepted:return False
        mode=choice.mode()
    else:mode=history_selection.select(source,mid)
    rows=[dict(r,alternate_material_ids=[a['material_id'] for a in source.alternates(r['id'])]) for r in source.bom(root)]
    conflicts=history.collect_conflicts(source,root,rows,{mid:data},mode)
    versions={}
    if conflicts:
        revision=ParentRevisionDialog(source,conflicts,owner)
        if revision.exec_()!=QDialog.Accepted:return False
        versions=revision.versions()
    history.save(source,root,rows,{mid:data},mode,versions)
    return True
