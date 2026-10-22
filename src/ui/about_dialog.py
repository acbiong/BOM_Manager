"""关于窗口：显示软件身份、仓库、构建提交及版权。编辑时间：2026-10-10。"""
from html import escape
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLabel, QScrollArea, QWidget, QDialogButtonBox
from ui.interactive_windows import QDialog
from infrastructure.build_info import load_build_info, COPYRIGHT, REPOSITORY_URL


class AboutDialog(QDialog):
    def __init__(self, version, parent=None):
        super().__init__(parent)
        self.setWindowTitle('关于 BOM管理系统')
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        area = QScrollArea()
        area.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        info = load_build_info()
        self.labels = {}
        for key, title, value in [
            ('name', '软件名称', 'BOM管理系统'), ('version', '软件版本', version),
            ('repository', 'Git网址', info.get('repository') or REPOSITORY_URL),
            ('commit', '提交编号', info.get('commit') or '未提供提交信息'),
            ('author', '提交作者', info.get('author') or '未提供'),
            ('date', '提交时间', info.get('date') or '未提供'),
            ('message', '提交说明', info.get('message') or '未提供'),
            ('copyright', '版权声明', COPYRIGHT)]:
            label = QLabel(str(value))
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if key == 'repository' and str(value).startswith('https://'):
                label.setTextFormat(Qt.RichText)
                label.setText(f'<a href="{escape(value, quote=True)}">{escape(value)}</a>')
                label.setTextInteractionFlags(Qt.TextBrowserInteraction)
                label.setOpenExternalLinks(True)
            self.labels[key] = label
            form.addRow(title, label)
        area.setWidget(content)
        layout.addWidget(area)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
