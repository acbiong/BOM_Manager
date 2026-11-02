"""应用级浅色/深色调色板及不依赖字体的主题图标。"""
import math
from PyQt5.QtCore import Qt,QPointF
from PyQt5.QtGui import QColor,QPalette,QIcon,QPixmap,QPainter,QPen
from PyQt5.QtWidgets import QApplication

def apply_theme(dark=False):
 app=QApplication.instance()
 if app.property('bom_fusion_initialized') and app.property('bom_dark_theme')==dark:return
 # Keep the existing Fusion style alive when opening additional windows.
 if not app.property('bom_fusion_initialized'):
  app.setStyle('Fusion');app.setProperty('bom_fusion_initialized',True)
 palette=QPalette()
 colors={
  QPalette.Window:('#f5f6f8','#24262b'),QPalette.WindowText:('#202124','#eceff4'),
  QPalette.Base:('#ffffff','#1c1e22'),QPalette.AlternateBase:('#edf0f4','#2d3037'),
  QPalette.Text:('#202124','#eceff4'),QPalette.Button:('#e9ecf1','#343841'),
  QPalette.ButtonText:('#202124','#eceff4'),QPalette.Highlight:('#2464a8','#356fae'),
  QPalette.HighlightedText:('#ffffff','#ffffff'),QPalette.ToolTipBase:('#fff8db','#353943'),
  QPalette.ToolTipText:('#202124','#eceff4'),QPalette.Link:('#195da8','#84baff'),
  QPalette.Light:('#ffffff','#505560'),QPalette.Midlight:('#e5e7eb','#41454f'),
  QPalette.Mid:('#b7bdc6','#7e899c'),QPalette.Dark:('#89909c','#8e9bb0'),QPalette.Shadow:('#555b65','#090a0c')}
 for role,values in colors.items():palette.setColor(role,QColor(values[int(dark)]))
 for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):palette.setColor(QPalette.Disabled,role,QColor('#777e88' if not dark else '#969ba5'))
 app.setProperty('bom_dark_theme',dark); app.setPalette(palette)
 hover='#405a78' if dark else '#d7e9ff'
 pressed='#294464' if dark else '#b7d5fa'
 text='#ffffff' if dark else '#12365c'
 hover_style=f'''
 QPushButton:enabled:hover, QToolButton:enabled:hover {{background-color:{hover};color:{text};}}
 QPushButton:enabled:pressed, QToolButton:enabled:pressed {{background-color:{pressed};color:{text};}}
 QMenuBar::item:selected, QMenu::item:selected:enabled {{background-color:{hover};color:{text};}}
 '''
 app.setStyleSheet(hover_style)
 if dark:
  app.setStyleSheet(app.styleSheet()+"""
  QAbstractItemView { gridline-color:#7e899c; }
  QHeaderView::section { background-color:#343d4c; color:#f2f5fa;
      border:0; border-right:1px solid #8290a5; border-bottom:1px solid #8290a5; padding:4px; }
  QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
      border:1px solid #8290a5; border-radius:3px; padding:3px;
      background-color:#1c1e22; color:#f2f5fa; selection-background-color:#356fae; }
  QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border:1px solid #91c6ff; }
  QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button { background:#343d4c; width:18px; border:1px solid #8290a5; }
  QComboBox::drop-down { width:20px; border-left:1px solid #8290a5; }
  QPushButton, QToolButton { border:1px solid #8290a5; border-radius:3px; padding:4px; }
  QPushButton:disabled, QToolButton:disabled { color:#a5adba; border-color:#566171; }
  QGroupBox { border:1px solid #8290a5; border-radius:4px; margin-top:10px; padding-top:8px; }
  QGroupBox::title { subcontrol-origin:margin; color:#f2f5fa; padding:0 5px; }
  QMenu { border:1px solid #8290a5; }
  QMenu::separator { height:1px; background:#8290a5; margin:4px 8px; }
  QTabBar::tab { background:#343d4c; color:#f2f5fa; border:1px solid #8290a5; padding:6px 10px; }
  QTabBar::tab:selected { background:#356fae; color:white; }
  QSplitter::handle { background:#8290a5; }
  QToolTip { color:#f2f5fa; background:#343d4c; border:1px solid #8290a5; }
  """+dark_arrow_style(app)+hover_style)
 for widget in app.topLevelWidgets():
  if hasattr(widget,'root_item') and hasattr(widget,'tree'):
   recolor_bom_tree(widget.tree,dark)
  widget.update()

def theme_icon(dark):
 pixmap=QPixmap(32,32);pixmap.fill(Qt.transparent);p=QPainter(pixmap);p.setRenderHint(QPainter.Antialiasing)
 color=QColor('#dce6ff' if dark else '#9b6800');p.setPen(QPen(color,2.2));p.setBrush(color)
 if dark:
  p.drawEllipse(QPointF(16,16),11,11)
  p.setCompositionMode(QPainter.CompositionMode_Clear);p.drawEllipse(QPointF(21,11),10,10)
 else:
  p.drawEllipse(QPointF(16,16),6,6)
  for index in range(8):
   angle=index*math.pi/4;p.drawLine(QPointF(16+10*math.cos(angle),16+10*math.sin(angle)),QPointF(16+14*math.cos(angle),16+14*math.sin(angle)))
 p.end();return QIcon(pixmap)


def apply_font_size(size):
 """Scale explicit widget/item fonts as well as inherited application fonts."""
 from PyQt5.QtGui import QFont
 from PyQt5.QtWidgets import QTreeWidget,QTreeWidgetItemIterator,QTableWidget
 app=QApplication.instance()
 if app is None:return
 old=app.font().pointSizeF()
 if old==size:return
 widgets=list(app.allWidgets())
 explicit=[(w,QFont(w.font())) for w in widgets]
 items=[]
 for widget in widgets:
  if isinstance(widget,QTableWidget):
   for row in range(widget.rowCount()):
    for col in range(widget.columnCount()):
     item=widget.item(row,col)
     if item is not None and item.data(Qt.FontRole) is not None:items.append((item,None,QFont(item.font())))
  elif isinstance(widget,QTreeWidget):
   iterator=QTreeWidgetItemIterator(widget)
   while iterator.value():
    item=iterator.value()
    for col in range(widget.columnCount()):
     if item.data(col,Qt.FontRole) is not None:items.append((item,col,QFont(item.font(col))))
    iterator+=1
 font=QFont(app.font());font.setPointSizeF(size);app.setFont(font)
 for widget,font in explicit:
  font.setPointSizeF(size);widget.setFont(font)
 for item,column,font in items:
  font.setPointSizeF(size)
  if column is None:item.setFont(font)
  else:item.setFont(column,font)
 from ui.table_layout import fit_columns
 for widget in widgets:
  if isinstance(widget,(QTableWidget,QTreeWidget)):fit_columns(widget)
 app.setProperty('bom_font_size',size)


def recolor_bom_tree(tree,dark):
 from PyQt5.QtWidgets import QTreeWidgetItemIterator
 from ui.bom_change_style import level_background
 light=['#008000','#ff0000','#9a6700'];night=['#85e6a2','#ff9494','#ffd477']
 mapping=dict(zip(light,night)) if dark else dict(zip(night,light))
 iterator=QTreeWidgetItemIterator(tree)
 while iterator.value():
  item=iterator.value();depth=0;parent=item.parent()
  while parent is not None:depth+=1;parent=parent.parent()
  for column in range(tree.columnCount()):
   brush=item.foreground(column)
   if brush.style()!=Qt.NoBrush and brush.color().name() in mapping:item.setForeground(column,QColor(mapping[brush.color().name()]))
   background=item.background(column).color()
   if background.alpha()<255:item.setBackground(column,level_background(depth,dark))
  iterator+=1


def dark_arrow_style(app):
 from tempfile import TemporaryDirectory
 from pathlib import Path
 from PyQt5.QtGui import QPolygon
 from PyQt5.QtCore import QPoint
 if not hasattr(app,'_bom_arrow_images'):
  app._bom_arrow_images=TemporaryDirectory(prefix='bom-theme-')
  for name,points in [('up',[(0,5),(5,0),(10,5)]),('down',[(0,0),(5,5),(10,0)])]:
   pix=QPixmap(11,6);pix.fill(Qt.transparent);painter=QPainter(pix)
   painter.setPen(Qt.NoPen);painter.setBrush(QColor('#f2f5fa'))
   painter.drawPolygon(QPolygon([QPoint(x,y) for x,y in points]));painter.end()
   pix.save(str(Path(app._bom_arrow_images.name)/(name+'.png')))
 folder=Path(app._bom_arrow_images.name).as_posix()
 return (f"QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{image:url('{folder}/up.png');width:11px;height:6px;}}"
         f"QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QComboBox::down-arrow {{image:url('{folder}/down.png');width:11px;height:6px;}}")
