"""Saved color swatches and context menu for BOM rows."""
import json
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor,QIcon,QPixmap
from PyQt5.QtWidgets import QMenu,QColorDialog,QMessageBox

DEFAULTS=[['浅红','#f8d7da'],['浅黄','#fff3cd'],['浅蓝','#d6e9ff'],['浅绿','#d4edda']]

def palette(config):
    from services.bom_colors import normalize
    raw=config.load().get('bom_colors','palette',fallback=None)
    if raw is None:return [list(row) for row in DEFAULTS]
    try:return [[str(name),normalize(color)] for name,color in json.loads(raw) if color]
    except (ValueError,TypeError,KeyError):return [list(row) for row in DEFAULTS]

def save_palette(config,values):
    cfg=config.load()
    if not cfg.has_section('bom_colors'):cfg.add_section('bom_colors')
    cfg['bom_colors']['palette']=json.dumps(values,ensure_ascii=False);config.save(cfg)

class ColorMenu(QMenu):
    def __init__(self,window,items,parent):
        super().__init__('设置颜色',parent);self.window=window;self.items=items;self.config=window.svc.config_service
        self.setContextMenuPolicy(Qt.CustomContextMenu);self.customContextMenuRequested.connect(self.remove_color)
        self.populate()
    def populate(self):
        self.clear()
        for name,color in palette(self.config):
            swatch=QPixmap(18,18);swatch.fill(QColor(color));action=self.addAction(QIcon(swatch),name);action.setData(color)
            action.triggered.connect(lambda checked=False,c=color:self.window.set_row_color(self.items,c))
        self.addSeparator();self.addAction('清除颜色',lambda:self.window.set_row_color(self.items,''))
        self.addAction('设置更多颜色',self.more)
    def more(self):
        color=QColorDialog.getColor(QColor('#ffffff'),self.window,'选择BOM背景颜色',QColorDialog.DontUseNativeDialog)
        if not color.isValid():return
        value=color.name();self.window.set_row_color(self.items,value)
        if QMessageBox.question(self.window,'保存颜色','是否将此颜色保存到“设置颜色”菜单？',QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)==QMessageBox.Yes:
            values=palette(self.config)
            if not any(c==value for _,c in values):values.append([value,value]);save_palette(self.config,values)
    def remove_color(self,pos):
        action=self.actionAt(pos)
        if action is None or not action.data():return
        menu=QMenu(self);remove=menu.addAction('删除颜色')
        if menu.exec_(self.mapToGlobal(pos))==remove:
            save_palette(self.config,[(n,c) for n,c in palette(self.config) if c!=action.data()]);self.populate()
