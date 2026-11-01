"""Nonmodal material history decisions and immutable subtree inspection."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QPushButton, QTreeWidget, QTreeWidgetItem, QAbstractItemView,QScrollArea,QWidget,QFormLayout,QHBoxLayout,QComboBox,QSplitter,QGroupBox)
from ui.interactive_windows import QDialog,QMessageBox
from services import material_history as history
from domain.quantity import format_quantity


class MaterialHistoryChoiceDialog(QDialog):
    def __init__(self, service, mid, title, parent=None,impact_mid=None):
        super().__init__(parent); self.setWindowTitle(title+' — 物料历史版本'); self.resize(850,480)
        layout=QVBoxLayout(self); material=service.material_snapshot(mid)
        label=QLabel(material['base_code']+material['version']+' '+material['name']+
                     '\n当前BOM始终参与变更。请选择同时变更的其他BOM，包含同SKU旧历史版本及不同物料历史版本。仅在保存BOM后生效。');label.setWordWrap(True);layout.addWidget(label)
        from services import history_selection
        self.service=service;self.material_id=mid;self.impact_mid=impact_mid
        self.reference_token=history_selection.token(service,mid)
        displayed=history_selection.references(service,mid)
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
        return Selection(self.material_id,ids,self.reference_token,self.impact_mid)
    def update_note(self,*args):
        count=len(self.mode().sku_ids)
        self.note.setText('全部引用BOM一同变更，不新增该物料历史版本。' if count==self.table.rowCount() else
                         '有其他BOM未参与变更：保留其原内容，为本次变更新增或复用对应物料历史版本。')
    def accept(self):
        from services import history_selection
        if self.reference_token!=history_selection.token(self.service,self.material_id):
            QMessageBox.warning(self,'引用范围已变化','其他BOM内容、引用或锁定状态已变化，请取消后重新选择。');return
        super().accept()


class MaterialHistoryDialog(QDialog):
    FIELDS=[('base_code','基础编码'),('version','物料版本号'),('name','名称'),('description','规格描述'),
            ('unit','单位'),('grade','物料等级'),('manufacturer','制造商'),('mpn','MPN'),('mp_flag','M/P'),
            ('history_version','物料历史版本'),('created_at','记录时间'),('alternates','替代料')]

    def __init__(self,service,mid,version,parent=None):
        super().__init__(parent);self.resize(1150,760);self.service=service;self.material_id=mid
        layout=QVBoxLayout(self);bar=QHBoxLayout();bar.addWidget(QLabel('查看物料历史版本：'))
        self.version_combo=QComboBox();self.version_combo.setMinimumWidth(130)
        for row in history.versions(service,mid):self.version_combo.addItem(str(row['history_version']),row['history_version'])
        bar.addWidget(self.version_combo);self.root_label=QLabel();self.root_label.setTextFormat(Qt.PlainText);self.root_label.setWordWrap(True);bar.addWidget(self.root_label,1);layout.addLayout(bar)
        self.info=QWidget();form=QFormLayout(self.info);form.setLabelAlignment(Qt.AlignRight|Qt.AlignVCenter);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.attribute_labels={};self.attribute_values={}
        for key,title in self.FIELDS:
            label=QLabel(title+'：');label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            value=QLabel();value.setAlignment(Qt.AlignLeft|Qt.AlignVCenter);value.setWordWrap(True);value.setTextFormat(Qt.PlainText);value.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
            value.setMinimumWidth(0);form.addRow(label,value);self.attribute_labels[key]=label;self.attribute_values[key]=value
        info_scroll=QScrollArea();info_scroll.setWidgetResizable(True);info_scroll.setWidget(self.info)
        info_group=QGroupBox('选中物料的历史属性');QVBoxLayout(info_group).addWidget(info_scroll)
        self.references_group=QGroupBox('包含当前物料历史版本的SKU BOM');reference_layout=QVBoxLayout(self.references_group)
        self.reference_label=QLabel();self.reference_label.setWordWrap(True);self.reference_label.setTextFormat(Qt.PlainText);reference_layout.addWidget(self.reference_label)
        self.references=QTableWidget(0,3);self.references.setHorizontalHeaderLabels(['SKU编码','SKU名称','SKU历史版本'])
        self.references.setEditTriggers(QAbstractItemView.NoEditTriggers);self.references.setSelectionBehavior(QAbstractItemView.SelectRows);self.references.setWordWrap(True)
        self.references.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded);self.references.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded);reference_layout.addWidget(self.references,1)
        panels=QSplitter();panels.addWidget(info_group);panels.addWidget(self.references_group);panels.setSizes([530,570]);panels.setMinimumHeight(200)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['物料编码','物料名称','物料历史版本','数量','单位','位置','备注','替代料']);self.tree.setWordWrap(True)
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
        service=self.service;mid=self.material_id;cache={}
        def read(material_id,revision):
            key=(material_id,revision)
            if key not in cache:cache[key]=history.read(service,material_id,revision)
            return cache[key]
        record=read(mid,version);attrs=record['attributes']
        label=attrs['base_code']+attrs['version']+' '+attrs['name']
        self.root_label.setText(label);self.setWindowTitle(label+' 物料历史版本'+str(version)+'（只读）')
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            def append(parent,material_id,revision,edge=None,ancestors=frozenset()):
                key=(material_id,revision)
                if key in ancestors:raise ValueError('物料历史数据存在循环引用')
                snapshot=read(material_id,revision);data=snapshot['attributes'];edge=edge or {};alternatives=[]
                for alt in edge.get('alternates',[]):
                    a=read(alt['material_id'],alt['history_version'])['attributes'];alternatives.append(a['base_code']+a['version']+' '+a['name'])
                item=QTreeWidgetItem(parent,[data['base_code']+data['version'],data['name'],str(revision),format_quantity(edge.get('quantity',1)),data['unit'],edge.get('position',''),edge.get('remark',''),'\n'.join(alternatives)])
                item.setData(0,Qt.UserRole,snapshot)
                for child in snapshot['children']:append(item,child['material_id'],child['history_version'],child,ancestors|{key})
                return item
            root=append(self.tree,mid,version);self.tree.setCurrentItem(root);self.tree.expandToDepth(1)
        finally:self.tree.blockSignals(False)
        self.show_info(root)
        from ui.table_layout import fit_columns
        fit_columns(self.tree)

    def show_info(self,item,previous=None):
        if item is None:return
        record=item.data(0,Qt.UserRole);a=record['attributes']
        values=dict(a,history_version=record['history_version'],created_at=record['created_at'].split('.')[0],
                    alternates=item.text(7))
        for key,_ in self.FIELDS:self.attribute_values[key].setText(str(values.get(key,'') or '（空）'))
        references=history.sku_references(self.service,record['material_id'],record['history_version'])
        title=a['base_code']+a['version']+' '+a['name']+' / 物料历史版本'+str(record['history_version'])
        self.reference_label.setText(title+('\n共计'+str(len(references))+'个SKU BOM（包含旧SKU历史版本）' if references else '\n此物料历史版本未被任何SKU BOM引用'))
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
