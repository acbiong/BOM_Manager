"""Choose independent BOM relationships for a multi-occurrence replacement."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,
                            QDialogButtonBox,QAbstractItemView,QMessageBox)
from ui.interactive_windows import QDialog,QMessageBox
from ui.table_layout import fit_columns

class ReplacementSelectionDialog(QDialog):
    def __init__(self, groups, parent=None):
        super().__init__(parent)
        self.groups=groups
        self.setWindowTitle('选择同步替换的物料')
        self.resize(1050,580)
        layout=QVBoxLayout(self)
        label=QLabel('发现当前BOM中有相同物料，请勾选需要替换的关系，未勾选的保持不变。\n同一共享父级关系的全部路径列在同一行，使用同一勾选项。每个关系继承自身数量、位置、备注及替代料。')
        label.setWordWrap(True);layout.addWidget(label)
        self.table=QTableWidget(len(groups),7)
        self.table.setHorizontalHeaderLabels(['','BOM完整路径','物料','数量','位置','备注','检查结果'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row,group in enumerate(groups):
            node=group['nodes'][0];data=node.data(0,Qt.UserRole) or {}
            values=['', '\n'.join(group['paths']),node.text(0),node.text(1),data.get('position',''),data.get('remark',''),group['reason'] or ('共享关系，全部路径同步' if len(group['nodes'])>1 else '可替换')]
            for column,value in enumerate(values):
                cell=QTableWidgetItem(str(value or ''))
                if column==0:
                    cell.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable)
                    cell.setCheckState(Qt.Checked if group['current'] and not group['reason'] else Qt.Unchecked)
                    if group['reason']:cell.setFlags(Qt.NoItemFlags)
                cell.setToolTip(str(value or ''));self.table.setItem(row,column,cell)
        layout.addWidget(self.table);fit_columns(self.table)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def selected_nodes(self):
        return [node for row,group in enumerate(self.groups) if not group['reason'] and self.table.item(row,0).checkState()==Qt.Checked for node in group['nodes']]
    def accept(self):
        if not self.selected_nodes():
            QMessageBox.information(self,'未选择物料','请至少勾选一个需要替换的物料关系。');return
        super().accept()
