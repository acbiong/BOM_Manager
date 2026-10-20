from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon,QPixmap,QPainter,QPen,QColor
from PyQt5.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QDialogButtonBox,QMessageBox,QAbstractItemView,QStyledItemDelegate
from services.sku_lock import LockedBomError

def lock_icon():
 pixmap=QPixmap(20,20);pixmap.fill(Qt.transparent);p=QPainter(pixmap);p.setRenderHint(QPainter.Antialiasing)
 p.setPen(QPen(QColor('#ad7623'),2));p.drawRoundedRect(6,2,8,10,4,4);p.setBrush(QColor('#d9a441'));p.drawRoundedRect(3,8,14,10,2,2)
 p.setPen(QPen(QColor('#423320'),2));p.drawLine(10,11,10,15);p.end();return QIcon(pixmap)

def show_operation_error(parent,title,error,prefix=''):
 if not isinstance(error,LockedBomError):QMessageBox.warning(parent,title,prefix+str(error));return
 dialog=QDialog(parent);dialog.setWindowTitle('BOM已锁定');dialog.resize(1000,420);layout=QVBoxLayout(dialog)
 text=QLabel('下列BOM已被锁定，请解除锁定后再进行编辑。'+('\n'+prefix if prefix else ''));text.setWordWrap(True);layout.addWidget(text)
 table=QTableWidget(len(error.details),3);table.setHorizontalHeaderLabels(['锁定的SKU / 历史版本','对应物料','父项物料']);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setWordWrap(True)
 for i,row in enumerate(error.details):
  for col,key in enumerate(('sku','material','parent')):table.setItem(i,col,QTableWidgetItem(row[key]))
 layout.addWidget(table)
 from ui.table_layout import fit_columns
 fit_columns(table);table.resizeRowsToContents()
 buttons=QDialogButtonBox(QDialogButtonBox.Ok);buttons.accepted.connect(dialog.accept);layout.addWidget(buttons)
 try:dialog.exec_()
 finally:dialog.deleteLater()


class CenteredLockDelegate(QStyledItemDelegate):
 def paint(self,painter,option,index):
  from PyQt5.QtWidgets import QStyleOptionViewItem,QStyle,QApplication
  opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
  icon=QIcon(opt.icon);opt.icon=QIcon();opt.text=''
  style=opt.widget.style() if opt.widget else QApplication.style()
  style.drawControl(QStyle.CE_ItemViewItem,opt,painter,opt.widget)
  if not icon.isNull():
   size=option.decorationSize
   rect=QStyle.alignedRect(option.direction,Qt.AlignCenter,size,option.rect)
   icon.paint(painter,rect,Qt.AlignCenter,QIcon.Normal if option.state & QStyle.State_Enabled else QIcon.Disabled)
