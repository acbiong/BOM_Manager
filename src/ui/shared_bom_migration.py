"""Explicit conflict resolution before opening legacy mirror databases."""
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QComboBox,QTextBrowser,QDialogButtonBox,QMessageBox
from services.shared_bom import is_shared,migration_candidates,conflicts,migrate

class SharedBomMigrationDialog(QDialog):
    def __init__(self,db,candidates,parent=None):
        super().__init__(parent);self.setWindowTitle('统一公共子BOM结构 — 逐项确认');self.resize(1100,700)
        self.db=db;self.candidates=candidates;self.combos={}
        layout=QVBoxLayout(self)
        label=QLabel('仅SKU保留镜像。以下非SKU物料在公共结构和镜像中存在差异，请逐项选择保留的结构。\n选择包含子项、数量、位置、备注、排序及替代料。确认前不会迁移；取消则不打开此数据库。迁移前自动备份。');label.setWordWrap(True);layout.addWidget(label)
        self.table=QTableWidget(len(candidates),2);self.table.setHorizontalHeaderLabels(['物料','保留结构来源']);layout.addWidget(self.table)
        for row,(mid,variants) in enumerate(candidates.items()):
            material=db.conn.execute('SELECT base_code,version,name FROM materials WHERE id=?',(mid,)).fetchone()
            self.table.setItem(row,0,QTableWidgetItem(f'{material[0]}{material[1]} {material[2]}'))
            combo=QComboBox();combo.addItem('请选择保留哪份结构',None)
            for v in variants:combo.addItem(v['label']+f'（{len(v["rows"])}个直接子项）',v['scope'])
            self.combos[mid]=combo;self.table.setCellWidget(row,1,combo)
        self.table.resizeColumnsToContents();self.table.horizontalHeader().setStretchLastSection(True)
        self.preview=QTextBrowser();layout.addWidget(self.preview,1)
        self.table.currentCellChanged.connect(lambda row,*args:self.show_variants(row))
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.validate);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        if candidates:self.table.setCurrentCell(0,0)
    def show_variants(self,row):
        if row<0:return
        mid=list(self.candidates)[row];lines=[]
        def name(mid):
            r=self.db.conn.execute('SELECT base_code,version,name FROM materials WHERE id=?',(mid,)).fetchone()
            return f'{r[0]}{r[1]} {r[2]}' if r else str(mid)
        for variant in self.candidates[mid]:
            lines.append(variant['label'])
            for i,item in enumerate(variant['rows'],1):lines.append(f"{i}. {name(item['child_material_id'])} | 用量 {item['quantity']} {item['unit']} | 位置 {item['position']} | 备注 {item['remark']} | 替代料："+'、'.join(name(a) for a in item['alternates']))
            if not variant['rows']:lines.append('（无子项）')
            lines.append('')
        self.preview.setPlainText('\n'.join(lines))
    def choices(self):return {mid:combo.currentData() for mid,combo in self.combos.items()}
    def validate(self):
        if any(v is None for v in self.choices().values()):QMessageBox.warning(self,'尚未选择','请为每个冲突物料选择保留的结构。');return
        try:migrate(self.db,self.choices())
        except Exception as error:QMessageBox.warning(self,'迁移失败',str(error));return
        self.accept()

def prepare_shared_bom(db,parent=None):
    if is_shared(db.conn):return True
    pending=conflicts(migration_candidates(db))
    if pending:return SharedBomMigrationDialog(db,pending,parent).exec_()==QDialog.Accepted
    migrate(db);return True
