"""Nonmodal material history decisions and immutable subtree inspection."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QRadioButton, QTreeWidget, QTreeWidgetItem, QAbstractItemView,QScrollArea,QWidget,QFormLayout,QHBoxLayout,QComboBox,QSplitter,QGroupBox)
from ui.interactive_windows import QDialog,QMessageBox
from services import material_history as history
from domain.quantity import format_quantity


class MaterialHistoryChoiceDialog(QDialog):
    def __init__(self, service, mid, title, parent=None,impact_mid=None):
        super().__init__(parent); self.setWindowTitle(title+' — 物料历史版本'); self.resize(850,480)
        layout=QVBoxLayout(self); material=service.material_snapshot(mid)
        label=QLabel(material['base_code']+material['version']+' '+material['name']+
                     '\n请选择本次修改的处理范围。仅在保存BOM后生效，取消不写入数据。旧SKU历史版本始终不变。');label.setWordWrap(True);layout.addWidget(label)
        self.sync=QRadioButton('更新所有受影响SKU的最新历史版本BOM');self.fork=QRadioButton('创建新的物料历史版本，仅当前BOM使用');self.fork.setChecked(True)
        from services.current_catalog import latest_skus
        is_latest=getattr(service,'sku_id',None) in {s['id'] for s in latest_skus(getattr(service,'primary',service))}
        self.sync.setEnabled(is_latest)
        if not is_latest:self.sync.setToolTip('当前是旧SKU历史版本，只能保存独立的物料历史状态')
        layout.addWidget(self.sync);layout.addWidget(self.fork)
        self.service=service;self.impact_mid=mid if impact_mid is None else impact_mid
        owners=history.affected(service,[self.impact_mid]);table=QTableWidget(len(owners),3);self.table=table
        table.setHorizontalHeaderLabels(['SKU编码','SKU名称','SKU历史版本']);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True)
        for row,(sku,_) in enumerate(owners.values()):
            for col,value in enumerate([sku['base_code']+sku['version'],sku['name']+('（已锁定）' if sku['locked'] else ''),sku['mirror_version']]):table.setItem(row,col,QTableWidgetItem(str(value)))
        table.resizeColumnsToContents();table.horizontalHeader().setStretchLastSection(True);layout.addWidget(table,1)
        note=QLabel('新增替代料不要求父物料编码升版；其他属性修改及删除替代料会检查普通父项编码升版。SKU编码版本仍由用户手动管理。');note.setWordWrap(True);layout.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def mode(self):return 'sync' if self.sync.isChecked() else 'fork'
    def accept(self):
        locked=[sku for sku,_ in history.affected(self.service,[self.impact_mid]).values() if sku['locked']]
        if self.sync.isChecked() and locked:
            QMessageBox.warning(self,'BOM已锁定','下列BOM已被锁定，请解除锁定后再同步，或者选择创建独立物料历史版本：\n'+'\n'.join(s['base_code']+s['version']+' '+s['name']+' 历史版本'+str(s['mirror_version']) for s in locked));return
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
    choice=MaterialHistoryChoiceDialog(source,mid,'编辑物料',owner)
    if choice.exec_()!=QDialog.Accepted:return False
    rows=[dict(r,alternate_material_ids=[a['material_id'] for a in source.alternates(r['id'])]) for r in source.bom(root)]
    conflicts=history.collect_conflicts(source,root,rows,{mid:data},choice.mode())
    versions={}
    if conflicts:
        revision=ParentRevisionDialog(source,conflicts,owner)
        if revision.exec_()!=QDialog.Accepted:return False
        versions=revision.versions()
    history.save(source,root,rows,{mid:data},choice.mode(),versions)
    return True
