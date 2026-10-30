from PyQt5.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QComboBox,QDialogButtonBox,QMessageBox,QAbstractItemView
from ui.interactive_windows import QDialog,QMessageBox
from PyQt5.QtCore import Qt

class ParentRevisionDialog(QDialog):
    def __init__(self,service,conflicts,parent=None):
        super().__init__(parent);self.setWindowTitle('BOM变更检查 — 父物料编码需要升版');self.resize(1000,500)
        self.combos={};layout=QVBoxLayout(self)
        label=QLabel('请为以下普通父项选择或输入新的物料编码版本号。表格列出具体差异及其他引用方。\n启用物料历史记录后，物料属性、数量、位置、备注、删除替代料均检查父项编码升版；单纯新增替代料及排序不要求升版。\nSKU不受此自动升版限制；取消不写入数据库。');label.setWordWrap(True);layout.addWidget(label)
        table=QTableWidget(len(conflicts),5);self.table=table;table.setHorizontalHeaderLabels(['父物料','移除的子料基础编码','新增的子料基础编码','引用此父物料的其他SKU / 历史版本','父物料新版本号']);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        for row,problem in enumerate(conflicts):
            material=service.material_snapshot(problem['material_id'])
            before=set(problem['before']);after=set(problem['after'])
            removed=[code for code in problem['before'] if code not in after]
            added=[code for code in problem['after'] if code not in before]
            usages='\n'.join(f"{sku['base_code']}{sku['version']} {sku['name']} / 历史版本{sku['mirror_version']}" for sku in problem.get('other_skus',[]))
            for col,value in enumerate([problem['label']+('\n'+problem['detail'] if problem.get('detail') else ''),'\n'.join(removed) or '（无）','\n'.join(added) or '（无）',usages or '（无其他SKU引用）']):
                item=QTableWidgetItem(value);item.setTextAlignment(Qt.AlignLeft|Qt.AlignTop);table.setItem(row,col,item)
            combo=QComboBox();combo.setEditable(True);combo.addItem('')
            for other in service.db.conn.execute('SELECT version FROM materials WHERE base_code=? AND id<>? ORDER BY version',(material['base_code'],material['id'])):combo.addItem(other[0])
            self.combos[material['id']]=combo;table.setCellWidget(row,4,combo)
        table.horizontalHeader().setStretchLastSection(True);table.resizeColumnsToContents();table.resizeRowsToContents();layout.addWidget(table,1)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.validate);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def versions(self):return {mid:combo.currentText().strip() for mid,combo in self.combos.items()}
    def validate(self):
        if not all(self.versions().values()):QMessageBox.warning(self,'版本号未填写','请为每个父物料选择或输入新版本号。');return
        self.accept()
