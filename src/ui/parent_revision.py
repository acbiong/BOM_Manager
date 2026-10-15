from PyQt5.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QComboBox,QDialogButtonBox,QMessageBox,QAbstractItemView
from PyQt5.QtCore import Qt

class ParentRevisionDialog(QDialog):
    def __init__(self,service,conflicts,parent=None):
        super().__init__(parent);self.setWindowTitle('子物料基础编码变化 — 父物料需要升版');self.resize(1000,500)
        self.combos={};layout=QVBoxLayout(self)
        label=QLabel('以下非SKU父物料的直接子料基础编码集合发生变化，请选择或输入父物料新版本号。\nSKU不受此检查限制；仅子项版本及数量、位置、备注、顺序、替代料变化不要求父项升版。取消将保留编辑缓存。');label.setWordWrap(True);layout.addWidget(label)
        table=QTableWidget(len(conflicts),4);self.table=table;table.setHorizontalHeaderLabels(['父物料','原子料基础编码','新子料基础编码','父物料新版本号']);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True)
        for row,problem in enumerate(conflicts):
            material=service.material_snapshot(problem['material_id'])
            for col,value in enumerate([problem['label'],'\n'.join(problem['before']) or '（空）','\n'.join(problem['after']) or '（空）']):table.setItem(row,col,QTableWidgetItem(value))
            combo=QComboBox();combo.setEditable(True);combo.addItem('')
            for other in service.db.conn.execute('SELECT version FROM materials WHERE base_code=? AND id<>? ORDER BY version',(material['base_code'],material['id'])):combo.addItem(other[0])
            self.combos[material['id']]=combo;table.setCellWidget(row,3,combo)
        table.horizontalHeader().setStretchLastSection(True);table.resizeColumnsToContents();table.resizeRowsToContents();layout.addWidget(table)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.validate);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def versions(self):return {mid:combo.currentText().strip() for mid,combo in self.combos.items()}
    def validate(self):
        if not all(self.versions().values()):QMessageBox.warning(self,'版本号未填写','请为每个父物料选择或输入新版本号。');return
        self.accept()
