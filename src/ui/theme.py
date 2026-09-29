"""应用级浅色/深色调色板及不依赖字体的主题图标。"""
import math
from PyQt5.QtCore import Qt,QPointF
from PyQt5.QtGui import QColor,QPalette,QIcon,QPixmap,QPainter,QPen
from PyQt5.QtWidgets import QApplication

def apply_theme(dark=False):
 app=QApplication.instance(); app.setStyle('Fusion'); palette=QPalette()
 colors={
  QPalette.Window:('#f5f6f8','#24262b'),QPalette.WindowText:('#202124','#eceff4'),
  QPalette.Base:('#ffffff','#1c1e22'),QPalette.AlternateBase:('#edf0f4','#2d3037'),
  QPalette.Text:('#202124','#eceff4'),QPalette.Button:('#e9ecf1','#343841'),
  QPalette.ButtonText:('#202124','#eceff4'),QPalette.Highlight:('#2464a8','#356fae'),
  QPalette.HighlightedText:('#ffffff','#ffffff'),QPalette.ToolTipBase:('#fff8db','#353943'),
  QPalette.ToolTipText:('#202124','#eceff4'),QPalette.Link:('#195da8','#84baff'),
  QPalette.Light:('#ffffff','#505560'),QPalette.Midlight:('#e5e7eb','#41454f'),
  QPalette.Mid:('#b7bdc6','#25282f'),QPalette.Dark:('#89909c','#13151a'),QPalette.Shadow:('#555b65','#090a0c')}
 for role,values in colors.items():palette.setColor(role,QColor(values[int(dark)]))
 for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):palette.setColor(QPalette.Disabled,role,QColor('#777e88' if not dark else '#969ba5'))
 app.setProperty('bom_dark_theme',dark); app.setPalette(palette)
 for widget in app.topLevelWidgets():widget.update()

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
