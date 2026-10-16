from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QDialogButtonBox,QAbstractItemView

class BomSyncConfirmationDialog(QDialog):
    def __init__(self,plan,parent=None):
        super().__init__(parent);self.setWindowTitle('确认同步最新镜像BOM');self.resize(1100,600)
        layout=QVBoxLayout(self)
        label=QLabel('以下父物料的子BOM发生变化，并被其他SKU的最新镜像引用。请勾选需要同步的BOM。\n全部勾选直接同步；若有未勾选的BOM，需要为对应父物料选择新版本，未勾选的BOM保留原版本与结构。取消将保留编辑缓存。');label.setWordWrap(True);layout.addWidget(label)
        self.rows=[(p,s) for p in plan for s in p['other_skus']]
        self.table=QTableWidget(len(self.rows),4);self.table.setHorizontalHeaderLabels(['同步','父物料','具体变更','受影响SKU / 镜像'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.setWordWrap(True);self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded);self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        for row,(problem,sku) in enumerate(self.rows):
            check=QTableWidgetItem();check.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);check.setCheckState(Qt.Checked);self.table.setItem(row,0,check)
            values=[problem['label'],problem['detail'],f"{sku['base_code']}{sku['version']} {sku['name']} / 镜像{sku['mirror_version']}"]
            for col,value in enumerate(values,1):
                item=QTableWidgetItem(value);item.setTextAlignment(Qt.AlignTop|Qt.AlignLeft);self.table.setItem(row,col,item)
        for col,width in enumerate((55,220,440,300)):self.table.setColumnWidth(col,width)
        self.table.resizeRowsToContents();layout.addWidget(self.table,1)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def selections(self):
        result={}
        for row,(problem,sku) in enumerate(self.rows):
            selected=result.setdefault(problem['material_id'],set())
            if self.table.item(row,0).checkState()==Qt.Checked:selected.add(sku['id'])
        return result
