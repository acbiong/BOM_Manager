"""Nonmodal application appearance and BOM workbook defaults."""
from PyQt5.QtCore import Qt,QSignalBlocker
from PyQt5.QtGui import QColor,QKeySequence
from PyQt5.QtWidgets import (QVBoxLayout,QFormLayout,QLabel,QSpinBox,QPushButton,
    QDialogButtonBox,QHBoxLayout,QWidget,QShortcut,QApplication)
from ui.interactive_windows import QDialog,QColorDialog,QMessageBox
from config.appearance import load,save,DEFAULT_FONT_SIZE,DEFAULT_EXPORT_COLORS
from services.bom_colors import foreground


class SettingsDialog(QDialog):
    def __init__(self,config,parent=None):
        super().__init__(parent);self.config=config;self.setWindowTitle('设置');self.resize(560,440)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        size,self.colors=load(config)
        self._original_font_size=QApplication.instance().font().pointSizeF();self._preview_active=True
        self.font_size=QSpinBox();self.font_size.setRange(8,24);self.font_size.setSuffix(' pt');self.font_size.setValue(size)
        form.addRow('软件字体大小',self.font_size)
        hint=QLabel('调整字号即时预览；取消或关闭还原，点击确定后保存。');hint.setWordWrap(True);layout.addWidget(hint)
        title=QLabel('BOM导出Excel默认背景颜色');layout.addWidget(title)
        colors_form=QFormLayout();layout.addLayout(colors_form);self.color_buttons=[]
        for level in range(5):
            row=QWidget();buttons=QHBoxLayout(row);buttons.setContentsMargins(0,0,0,0)
            button=QPushButton();self.color_buttons.append(button);button.clicked.connect(lambda checked=False,i=level:self.choose_color(i));buttons.addWidget(button,1)
            clear=QPushButton('无底色');clear.clicked.connect(lambda checked=False,i=level:self.set_color(i,''));buttons.addWidget(clear)
            colors_form.addRow('第1级：根节点（层级0）' if level==0 else f'第{level+1}级（层级{level}）',row)
        note=QLabel('BOM树手动设置的行颜色优先；第5级以后的节点沿用第5级颜色。\n仅用于BOM结构导出（含资料库中的BOM），不改变BOM树颜色及采购汇总。')
        note.setWordWrap(True);layout.addWidget(note)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel|QDialogButtonBox.RestoreDefaults)
        for role,text in ((QDialogButtonBox.Save,'确定'),(QDialogButtonBox.Cancel,'取消'),(QDialogButtonBox.RestoreDefaults,'恢复默认')):self.buttons.button(role).setText(text)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.defaults);layout.addWidget(self.buttons)
        self._bom_save_shortcut=QShortcut(QKeySequence.Save,self)
        self._bom_save_shortcut.setContext(Qt.WindowShortcut);self._bom_save_shortcut.activated.connect(self.accept)
        self.refresh_colors()
        self.font_size.valueChanged.connect(self.preview_font)
    def begin_session(self):
        self._original_font_size=QApplication.instance().font().pointSizeF()
        size,self.colors=load(self.config)
        with QSignalBlocker(self.font_size):self.font_size.setValue(size)
        self.refresh_colors();self._preview_active=True
    def showEvent(self,event):
        if not self._preview_active:self.begin_session()
        super().showEvent(event)
    def preview_font(self,size):
        from ui.theme import apply_font_size
        if self._preview_active:apply_font_size(size)
    def reject(self):
        from ui.theme import apply_font_size
        if self._preview_active:
            self._preview_active=False;apply_font_size(self._original_font_size)
        super().reject()
    def refresh_colors(self):
        for button,color in zip(self.color_buttons,self.colors):
            button.setText(color.upper() if color else '无底色')
            button.setStyleSheet(f'background-color:{color};color:{foreground(color)};' if color else '')
    def set_color(self,index,color):self.colors[index]=color;self.refresh_colors()
    def choose_color(self,index):
        color=QColorDialog.getColor(QColor(self.colors[index] or '#ffffff'),self,'选择导出背景颜色',QColorDialog.DontUseNativeDialog)
        if color.isValid():self.set_color(index,color.name())
    def defaults(self):
        self.font_size.setValue(DEFAULT_FONT_SIZE);self.colors=list(DEFAULT_EXPORT_COLORS);self.refresh_colors()
    def accept(self):
        try:save(self.config,self.font_size.value(),self.colors)
        except (OSError,ValueError) as error:QMessageBox.warning(self,'保存设置失败',str(error));return
        from ui.theme import apply_font_size
        apply_font_size(self.font_size.value());self._preview_active=False;super().accept()
