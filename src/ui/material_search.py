"""物料组合查找对话框：输入模糊条件，输出匹配清单并定位物料库。编辑时间：2026-10-10。"""
from ui.table_layout import fit_columns
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView, QLabel,
    QDialogButtonBox, QMessageBox)


class MaterialSearchDialog(QDialog):
    def __init__(self, library):
        super().__init__(library)
        self.library = library
        self.setWindowTitle('查找物料')
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('填写一个或多个条件，各条件同时满足；支持部分文字匹配，不区分大小写。'))
        form = QFormLayout()
        self.fields = {}
        for key, label in [('code', '物料编码'), ('name', '物料名称'),
                           ('description', '物料规格'), ('manufacturer', '制造商'), ('mpn', 'MPN')]:
            edit = QLineEdit()
            edit.returnPressed.connect(self.search)
            self.fields[key] = edit
            form.addRow(label, edit)
        layout.addLayout(form)
        self.search_button = QPushButton('查找')
        self.search_button.clicked.connect(self.search)
        layout.addWidget(self.search_button)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['物料库行号', '物料编码', '物料名称', '物料规格', '物料制造商', 'MPN'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.cellDoubleClicked.connect(self.locate)
        layout.addWidget(self.table)
        fit_columns(self.table)
        self.count_label = QLabel('请输入查找条件')
        layout.addWidget(self.count_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def search(self):
        queries = {key: edit.text().strip().casefold() for key, edit in self.fields.items() if edit.text().strip()}
        self.table.setRowCount(0)
        if not queries:
            self.count_label.setText('请至少输入一个查找条件')
            return
        for number, material in enumerate(self.library.svc.materials(), 1):
            values = dict(material)
            values['code'] = values['base_code'] + values['version']
            if not all(query in str(values.get(key) or '').casefold() for key, query in queries.items()):
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, value in enumerate((number, values['code'], values['name'], values['description'], values['manufacturer'], values['mpn'])):
                item = QTableWidgetItem(str(value or ''))
                item.setData(Qt.UserRole, material['id'])
                if col == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
        fit_columns(self.table)
        self.count_label.setText(f'共找到 {self.table.rowCount()} 个物料（行号对应物料库完整清单）')

    def locate(self, row, column=0):
        item = self.table.item(row, 0)
        if item is None:
            return
        if not self.library.locate_material(item.data(Qt.UserRole)):
            QMessageBox.information(self, '物料不存在', '该物料已删除，请重新查找。')
            self.search()
            return
        if self.library.isMinimized():
            self.library.showNormal()
        self.library.raise_()
        self.library.activateWindow()
        self.library.t.setFocus()
