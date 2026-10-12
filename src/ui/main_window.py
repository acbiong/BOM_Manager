"""PyQt主窗口、SKU清单、物料库和BOM编辑窗口。输入服务对象，输出桌面交互。编辑时间：2026-09-24。"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSignal, QSettings, QTimer, QEvent, QSize, QSortFilterProxyModel
from PyQt5.QtGui import QColor, QBrush, QFont, QStandardItemModel, QStandardItem
from pathlib import Path
import os
from config.config_service import ConfigService, DEFAULT_MATERIAL_UNITS
from database.database import Database
from infrastructure.events import WindowRefreshBus
from services.services import MaterialHeaderError, BomImportError, MATERIAL_IMPORT_HEADERS, MATERIAL_IMPORT_DEFAULTS
from ui.theme import apply_theme, theme_icon
from ui.material_clipboard import copy_material, clipboard_material
from ui.material_search import MaterialSearchDialog
from ui.table_layout import fit_columns
from ui.about_dialog import AboutDialog

class QuantityEdit(QDoubleSpinBox):
 def __init__(self):
  super().__init__(); self.setDecimals(1); self.setRange(0.1,1e12); self.setSingleStep(0.1); self.setValue(1.0)
 def setText(self,value):
  self.setValue(float(value or 1.0))
 def text(self):
  return f'{self.value():.1f}'

class MaterialDialog(QDialog):
 def __init__(self,parent=None,data=None,readonly_keys=None):
  super().__init__(parent); self.setWindowTitle('物料'); f=QFormLayout(self); data=data or {}; self.e={}; readonly_keys=readonly_keys or set()
  for k,l in [('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料规格描述'),('manufacturer','物料制造商'),('mpn','物料MPN')]:
   if k in readonly_keys: w=QLabel(str(data.get(k,'')))
   else: w=QLineEdit(str(data.get(k,'')))
   self.e[k]=w; f.addRow(l,w)
  self.unit=QComboBox(); self.unit.addItems(parent.svc.UNITS if parent is not None and hasattr(parent,'svc') else list(DEFAULT_MATERIAL_UNITS)); self.unit.setCurrentIndex(self.unit.findText(data.get('unit',self.unit.itemText(0)))); self.unit.setEnabled('unit' not in readonly_keys); f.addRow('单位',self.unit)
  self.e['grade']=QLabel(str(data.get('grade',''))) if 'grade' in readonly_keys else QLineEdit(str(data.get('grade',''))); f.addRow('物料等级',self.e['grade'])
  self.mp_flag=QComboBox(); self.mp_flag.addItems(['M','P']); self.mp_flag.setCurrentText(data.get('mp_flag','M')); self.mp_flag.setEnabled('mp_flag' not in readonly_keys); f.addRow('M/P',self.mp_flag)
  b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)
 def data(self):
  d={k:w.text().strip() for k,w in self.e.items()}; d['unit']=self.unit.currentText(); d['mp_flag']=self.mp_flag.currentText(); return d
def choose_material_sheet(path,parent=None,kind='物料库'):
 from openpyxl import load_workbook
 wb=load_workbook(path,read_only=True,data_only=True)
 try:names=wb.sheetnames
 finally:wb.close()
 if len(names)==1:return names[0]
 if not names:raise ValueError('Excel文件中没有可读取的工作表')
 sheet,accepted=QInputDialog.getItem(parent,'选择'+kind+'工作表','请选择'+kind+'所在的工作表（Sheet）：',names,0,False)
 if not accepted:raise ValueError('用户取消选择工作表，未导入任何物料')
 return sheet

class MaterialHeaderMappingDialog(QDialog):
 def __init__(self,path,headers,missing,parent=None,sheet_name=None,required=None,config_service=None):
  super().__init__(parent); self.setWindowTitle(('BOM表头映射' if required else '物料表头映射')+(' — '+sheet_name if sheet_name else '')); self.resize(1000,620); self.required=list(required) if required else list(MATERIAL_IMPORT_HEADERS); self.combos={}; self.optional=set() if required else set(MATERIAL_IMPORT_DEFAULTS)
  self.mapping_config=config_service or getattr(getattr(parent,'svc',None),'config_service',None)
  self.mapping_kind='bom' if required else 'materials'
  remembered=self.mapping_config.import_mapping(self.mapping_kind) if self.mapping_config else {}
  self.source_headers=headers; self.alternate_groups=[]
  layout=QVBoxLayout(self); layout.addWidget(QLabel('请确认需求字段与文件列的映射关系：'))
  if required:
   button=QPushButton('增加替代料'); button.clicked.connect(self.add_alternate_mapping); layout.addWidget(button)
  self.mapping_table=QTableWidget(2,len(self.required)); self.mapping_table.setVerticalHeaderLabels(['需求表头','目标表头']); self.mapping_table.horizontalHeader().hide(); self.mapping_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
  for column,need in enumerate(self.required):
   item=QTableWidgetItem(need); item.setToolTip(('可选；新建未映射默认：'+(MATERIAL_IMPORT_DEFAULTS.get(need) or '空值')+'；覆盖时未映射保留原值') if need in self.optional else '必需映射'); item.setTextAlignment(Qt.AlignCenter); self.mapping_table.setItem(0,column,item)
   combo=QComboBox(); combo.setSizeAdjustPolicy(QComboBox.AdjustToContents); combo.addItem('（未映射）',''); combo.addItems([header for header in headers if header.strip()])
   if need not in missing and need in headers: combo.setCurrentText(need)
   self.combos[need]=combo; self.mapping_table.setCellWidget(1,column,combo)
   combo.currentTextChanged.connect(self.schedule_mapping_fit)
   combo.installEventFilter(self)
  self.mapping_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.mapping_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
  layout.addWidget(self.mapping_table)
  layout.addWidget(QLabel('文件读取预览（前20行）：'))
  self.preview=QTableWidget(); self.preview.setColumnCount(len(headers)); self.preview.setHorizontalHeaderLabels(headers); self.preview.setWordWrap(True); self.preview.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
  try:
   from openpyxl import load_workbook
   wb=load_workbook(path,read_only=True,data_only=True)
   try:
    ws=wb[sheet_name] if sheet_name is not None else wb.active; rows=list(ws.iter_rows(min_row=2,max_row=21,values_only=True))
   finally:wb.close()
   self.preview.setRowCount(len(rows))
   for r,row in enumerate(rows):
    for c in range(len(headers)): self.preview.setItem(r,c,QTableWidgetItem(str(row[c] or '') if c<len(row) else ''))
  except Exception as error: self.preview.setRowCount(1); self.preview.setItem(0,0,QTableWidgetItem('预览失败：'+str(error)))
  for column,header in enumerate(headers):
   if not header.strip():self.preview.setColumnHidden(column,True)
  layout.addWidget(self.preview,1); fit_columns(self.preview)
  self._mapping_fit_timer=QTimer(self); self._mapping_fit_timer.setSingleShot(True); self._mapping_fit_timer.timeout.connect(self.fit_mapping_columns)
  self.mapping_table.viewport().installEventFilter(self); self.mapping_table.installEventFilter(self)
  self.fit_mapping_columns()
  self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
  if required and remembered:
   import re
   numbers=sorted({int(match.group(1)) for key in remembered for match in [re.fullmatch(r'替代料([1-9][0-9]*)(?:编码|版本号)',key)] if match})
   for number in numbers:self.add_alternate_mapping(number=number)
  for field,combo in self.combos.items():
   if field in remembered:
    target=remembered[field]
    # 按列名恢复，缺失/歧义列保持未映射，不能退回同名或列序号猜测。
    combo.setCurrentIndex(combo.findText(target) if target and headers.count(target)==1 else 0)
  self.schedule_mapping_fit()
  buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.validate_mapping); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
 def add_alternate_mapping(self,number=None):
  if number is None or isinstance(number,bool):number=max([int(group[0].split('替代料')[1].split('编码')[0]) for group in self.alternate_groups] or [0])+1
  group=[f'替代料{number}编码',f'替代料{number}版本号']; self.alternate_groups.append(group)
  for field in group:
   column=self.mapping_table.columnCount(); self.mapping_table.insertColumn(column); self.required.append(field)
   item=QTableWidgetItem(field); item.setTextAlignment(Qt.AlignCenter); self.mapping_table.setItem(0,column,item)
   combo=QComboBox(); combo.addItem('（未映射）',''); combo.addItems([h for h in self.source_headers if h.strip()]); self.combos[field]=combo
   if field in self.source_headers:combo.setCurrentText(field)
   combo.setContextMenuPolicy(Qt.CustomContextMenu); combo.customContextMenuRequested.connect(lambda pos,f=field,w=combo:self.alternate_mapping_menu(f,w.mapToGlobal(pos)))
   combo.currentTextChanged.connect(self.schedule_mapping_fit); self.mapping_table.setCellWidget(1,column,combo)
  if not getattr(self,'_mapping_menu_connected',False):
   self.mapping_table.setContextMenuPolicy(Qt.CustomContextMenu); self.mapping_table.customContextMenuRequested.connect(self.mapping_context_menu); self._mapping_menu_connected=True
  self.schedule_mapping_fit()
 def mapping_context_menu(self,pos):
  column=self.mapping_table.columnAt(pos.x())
  if column>=0:self.alternate_mapping_menu(self.required[column],self.mapping_table.viewport().mapToGlobal(pos))
 def alternate_mapping_menu(self,field,pos):
  if not any(field in group for group in self.alternate_groups):return
  menu=QMenu(self); action=menu.addAction('删除替代料')
  if menu.exec_(pos)==action:self.remove_alternate_mapping(field)
 def remove_alternate_mapping(self,field):
  group=next(group for group in self.alternate_groups if field in group)
  for name in reversed(group):
   column=self.required.index(name); self.mapping_table.removeColumn(column); self.required.remove(name); self.combos.pop(name)
  self.alternate_groups.remove(group); self.schedule_mapping_fit()
 def schedule_mapping_fit(self,*args):
  if hasattr(self,'_mapping_fit_timer'):self._mapping_fit_timer.start(0)
 def eventFilter(self,obj,event):
  if event.type() in (QEvent.Resize,QEvent.Show,QEvent.FontChange,QEvent.StyleChange,QEvent.ApplicationFontChange):self.schedule_mapping_fit()
  return super().eventFilter(obj,event)
 def showEvent(self,event):
  super().showEvent(event); self.schedule_mapping_fit()
 def fit_mapping_columns(self):
  table=self.mapping_table; table.ensurePolished(); widths=[]; heights=[]
  for need in self.required:
   combo=self.combos[need]; combo.ensurePolished(); metrics=combo.fontMetrics()
   text_width=metrics.horizontalAdvance(combo.currentText())
   combo.setToolTip(combo.currentText())
   combo.view().setMinimumWidth(max(metrics.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))+48)
   option=QStyleOptionComboBox(); combo.initStyleOption(option)
   size=combo.style().sizeFromContents(QStyle.CT_ComboBox,option,QSize(text_width+16,metrics.height()+12),combo)
   width=max(size.width(),table.fontMetrics().horizontalAdvance(need)+24)
   height=max(size.height(),combo.sizeHint().height(),metrics.height()+16)
   # 样式可能额外占用内边距；按实际文字绘制区域补足，避免主题或缩放后被截断。
   option.rect.setRect(0,0,width,height)
   field=combo.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxEditField,combo)
   width+=max(0,text_width+12-field.width()); height+=max(0,metrics.height()+8-field.height())
   widths.append(width+4); heights.append(height+4)
  table.verticalHeader().setFixedWidth(max(table.verticalHeader().fontMetrics().horizontalAdvance(x) for x in ('需求表头','目标表头'))+24)
  extra=max(0,table.viewport().width()-sum(widths))
  table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
  for column,width in enumerate(widths):table.setColumnWidth(column,width+(extra*sum(widths[:column+1])//sum(widths)-extra*sum(widths[:column])//sum(widths)))
  # 不使用ResizeToContents覆盖组合框行高；需求行、目标行都按当前字体和主题计算。
  table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
  table.setRowHeight(0,table.fontMetrics().height()+20); table.setRowHeight(1,max(heights))
  table.setFixedHeight(table.rowHeight(0)+table.rowHeight(1)+table.horizontalScrollBar().sizeHint().height()+2*table.frameWidth()+4)
 def mapping(self): return {need:self.combos[need].currentText().strip() if self.combos[need].currentIndex()>0 else '' for need in self.required}
 def validate_mapping(self):
  values=self.mapping(); missing=[x for x in self.required if x not in self.optional and not values.get(x)]
  duplicates={x for x in values.values() if x and list(values.values()).count(x)>1}
  if missing or duplicates:
   detail=[]
   if missing: detail.append('未映射：'+ '、'.join(missing))
   if duplicates: detail.append('重复映射：'+ '、'.join(sorted(duplicates)))
   QMessageBox.warning(self,'表头映射错误','；'.join(detail)+'。请继续修改映射关系。'); return
  if self.mapping_config:
   try:self.mapping_config.save_import_mapping(self.mapping_kind,values)
   except (OSError,ValueError) as error:
    QMessageBox.warning(self,'映射保存失败',str(error));return
  self.accept()
class MaterialConflictDialog(QDialog):
 def __init__(self,incoming,existing,parent=None):
  super().__init__(parent); self.setWindowTitle('发现重复物料'); self.resize(1000,400); self.choice='cancel'
  layout=QVBoxLayout(self); title=QLabel('物料 '+incoming['物料基础编码']+incoming['物料版本号']+' 已存在。上行为数据库现有信息，下行为待导入信息；黄色单元格表示差异。'); title.setWordWrap(True); layout.addWidget(title)
  fields=[('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料规格描述'),('unit','单位'),('grade','物料等级'),('mp_flag','M/P'),('manufacturer','物料制造商'),('mpn','物料MPN')]
  self.table=QTableWidget(2,len(fields)); self.table.setHorizontalHeaderLabels([label for _,label in fields]); self.table.setVerticalHeaderLabels(['现有数据库','目标导入']); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
  for column,(key,label) in enumerate(fields):
   old=str(dict(existing).get(key,'') or ''); new=incoming.get(label,'')
   for row,value in enumerate((old,new)):
    item=QTableWidgetItem(value); item.setToolTip(value)
    if old!=new:item.setBackground(QColor('#ffe082')); item.setForeground(QColor('black'))
    self.table.setItem(row,column,item)
  layout.addWidget(self.table); fit_columns(self.table)
  buttons=QDialogButtonBox()
  for label,choice in [('覆盖','overwrite'),('跳过','skip'),('取消全部','cancel')]:
   button=buttons.addButton(label,QDialogButtonBox.ActionRole); button.clicked.connect(lambda _,value=choice:self.finish(value))
  layout.addWidget(buttons)
 def finish(self,choice):self.choice=choice; self.accept()

class MaterialImportResultDialog(QDialog):
 def __init__(self,ok,fail,parent=None):
  super().__init__(parent); self.setWindowTitle('物料导入结果')
  available=self.screen().availableGeometry(); self.setMaximumHeight(min(640,int(available.height()*0.85))); self.resize(min(900,int(available.width()*0.9)),min(560,self.maximumHeight()))
  automatic=[row for row in fail if row[3]=='重复物料信息相同，自动跳过']
  other=[row for row in fail if row[3] in ('跳过重复物料','用户取消')]
  errors=[row for row in fail if row[3] not in ('重复物料信息相同，自动跳过','跳过重复物料','用户取消')]
  layout=QVBoxLayout(self)
  summary=QLabel(f'成功导入：{len(ok)}条    导入失败：{len(errors)}条    自动跳过：{len(automatic)}条    其他未导入：{len(other)}条'); summary.setWordWrap(True); layout.addWidget(summary)
  self.tabs=QTabWidget(); self.details=QTextBrowser(); self.skipped_details=QTextBrowser(); self.other_details=QTextBrowser()
  for title,rows,view in [('导入失败',errors,self.details),('自动跳过',automatic,self.skipped_details),('其他未导入',other,self.other_details)]:
   view.setOpenExternalLinks(False); view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded); view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); view.setLineWrapMode(QTextEdit.WidgetWidth)
   view.setPlainText('\n\n'.join(f'第{row}行：{code or "（空编码）"} {name or "（空名称）"}\n原因：{reason}' for row,code,name,reason in rows) or '无此类记录。')
   self.tabs.addTab(view,f'{title}（{len(rows)}）')
  self.tabs.setCurrentIndex(0 if errors else 1 if automatic else 2 if other else 0)
  layout.addWidget(self.tabs,1)
  buttons=QDialogButtonBox(QDialogButtonBox.Ok); buttons.accepted.connect(self.accept); layout.addWidget(buttons)

def export_filename(text):
 import re
 return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', text).strip().rstrip('.')+'.xlsx'

def export_start_path(filename):
 import sys
 from PyQt5.QtCore import QSettings
 settings=QSettings('Biong','BOMManager'); folder=settings.value('export_directory','')
 if not folder or not Path(folder).is_dir():
  folder=str((Path(os.environ.get('APPIMAGE')).resolve().parent if os.environ.get('APPIMAGE') else (Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2])))
 return str(Path(folder)/filename)

def remember_export_path(path):
 from PyQt5.QtCore import QSettings
 QSettings('Biong','BOMManager').setValue('export_directory',str(Path(path).resolve().parent))


class MaterialSelectionDialog(QInputDialog):
 @staticmethod
 def getItem(parent,title,label,items,current=0,editable=True):
  dialog=MaterialSelectionDialog(parent); dialog.setWindowTitle(title); dialog.setLabelText(label)
  dialog.setComboBoxItems(items); dialog.setComboBoxEditable(True); dialog.resize(650,160)
  combo=dialog.findChild(QComboBox); combo.setInsertPolicy(QComboBox.NoInsert)
  completer=QCompleter(items,dialog); completer.setCaseSensitivity(Qt.CaseInsensitive); completer.setFilterMode(Qt.MatchContains); completer.setCompletionMode(QCompleter.PopupCompletion); combo.setCompleter(completer)
  combo.setCurrentIndex(-1); combo.lineEdit().setPlaceholderText('输入物料编码、版本或名称筛选')
  dialog._valid_choices=set(items)
  return (dialog.textValue(),True) if dialog.exec_()==QDialog.Accepted else ('',False)
 def accept(self):
  if self.textValue() not in self._valid_choices:
   QMessageBox.warning(self,'请选择物料','请从筛选结果中选择物料，不能使用任意输入文字。');return
  super().accept()

class NewSkuDialog(QDialog):
 def __init__(self,svc,parent=None):
  super().__init__(parent); self.svc=svc; self.material_id=None; self.setWindowTitle('新建SKU'); self.resize(650,160)
  layout=QVBoxLayout(self); layout.addWidget(QLabel('输入基础编码、版本号或名称筛选物料；已有BOM结构的物料不可用。'))
  self.combo=QComboBox(); self.combo.setEditable(True); self.combo.setInsertPolicy(QComboBox.NoInsert); self.combo.setMinimumWidth(500)
  self.model=QStandardItemModel(self); skus={row['material_id'] for row in svc.skus()}
  for row in svc.materials():
   reason='已有BOM结构，不可用' if row['has_bom']=='Y' else '已是SKU，不可用' if row['id'] in skus else ''
   item=QStandardItem(f"{row['base_code']}{row['version']} {row['name']}"+('（'+reason+'）' if reason else '')); item.setData(row['id'],Qt.UserRole); item.setEnabled(not reason); self.model.appendRow(item)
  self.combo.setModel(self.model); self.combo.setCurrentIndex(-1); self.combo.lineEdit().setPlaceholderText('输入物料编码或名称')
  self.proxy=QSortFilterProxyModel(self); self.proxy.setSourceModel(self.model); self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
  self.completer=QCompleter(self.proxy,self); self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion); self.combo.setCompleter(self.completer)
  self.combo.lineEdit().textEdited.connect(self.filter_materials); layout.addWidget(self.combo)
  buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
 def filter_materials(self,text):
  self.proxy.setFilterFixedString(text); self.completer.complete()
 def accept(self):
  text=self.combo.currentText(); matches=[self.model.item(i) for i in range(self.model.rowCount()) if self.model.item(i).text()==text]
  if not matches or not matches[0].isEnabled():QMessageBox.warning(self,'无法新建SKU','请选择可用的物料，不能使用任意输入文字或已有BOM结构的物料。'); return
  self.material_id=matches[0].data(Qt.UserRole); super().accept()

class MainWindow(QMainWindow):
 def __init__(self,svc,version='0.0.1'):
  super().__init__(); self.svc=svc; self._bom_windows={}; self._material_bom_windows={}; self._materials=None; self.setWindowTitle('BOM管理系统'); self.resize(1100,700); self.version=version; self.build(); WindowRefreshBus.subscribe(self.on_data_change)
 def on_data_change(self,event):
  if event.get('type') in ('bom_changed','material_changed'):self.refresh()
 def closeEvent(self,event):
  WindowRefreshBus.unsubscribe(self.on_data_change); super().closeEvent(event)
 def build(self):
  bar=self.menuBar(); fm=bar.addMenu('文件'); a=fm.addAction('选择SQLite数据库'); a.triggered.connect(self.select_database); a=fm.addAction('导出资料库'); a.triggered.connect(self.export_database); a=bar.addAction('物料库'); a.triggered.connect(self.show_materials); pm=bar.addMenu('项目'); a=pm.addAction('修改项目信息'); a.triggered.connect(self.edit_project); a=bar.addAction('新建SKU'); a.triggered.connect(self.new_sku); a=bar.addAction('关于'); a.triggered.connect(self.show_about)
  self.table=QTableWidget(); self.table.setColumnCount(6); self.table.setHorizontalHeaderLabels(['打开','SKU编码','SKU名称','SKU描述','修改日期时间','ID']); self.table.hideColumn(5); self.table.setWordWrap(True); self.table.cellDoubleClicked.connect(self.open_bom); self.table.setContextMenuPolicy(Qt.CustomContextMenu); self.table.customContextMenuRequested.connect(self.sku_context_menu)
  corner=QWidget(); corner_layout=QHBoxLayout(corner); corner_layout.setContentsMargins(0,0,4,0)
  self.theme_button=QToolButton(); self.theme_button.setIconSize(QSize(24,24)); self.theme_button.setAutoRaise(True); self.theme_button.clicked.connect(self.toggle_theme); corner_layout.addWidget(self.theme_button); bar.setCornerWidget(corner,Qt.TopRightCorner)
  self.set_theme(bool(QApplication.instance().property('bom_dark_theme')))
  self.setCentralWidget(self.table)
  self.count_label=QLabel(''); self.power_label=QLabel('Powered by Biong & BrainCo Inc.'); self.power_label.setAlignment(Qt.AlignCenter); self.version_label=QLabel('版本 '+self.version); footer=QWidget(); footer_l=QHBoxLayout(footer); footer_l.setContentsMargins(8,2,8,2); footer_l.addWidget(self.count_label); footer_l.addStretch(); footer_l.addWidget(self.power_label); footer_l.addStretch(); footer_l.addWidget(self.version_label); root_l=QVBoxLayout(); root_l.setContentsMargins(0,0,0,0); root_l.addWidget(self.table); root_l.addWidget(footer); container=QWidget(); container.setLayout(root_l); self.setCentralWidget(container); self.statusBar().setSizeGripEnabled(False); self.statusBar().hide(); self.refresh()
 def show_about(self):
  AboutDialog(self.version,self).exec_()
 def set_theme(self,dark):
  apply_theme(dark); self.theme_button.setIcon(theme_icon(dark))
  label='当前深色主题（月亮），点击切换浅色主题' if dark else '当前浅色主题（太阳），点击切换深色主题'
  self.theme_button.setToolTip(label); self.theme_button.setAccessibleName(label)
 def toggle_theme(self):self.set_theme(not bool(QApplication.instance().property('bom_dark_theme')))
 def refresh(self):
  project=self.svc.project(); name=(project['project_name'] or '').strip(); code=(project['project_code'] or '').strip(); prefix=' '.join(x for x in (code,name) if x and x!='请输入项目名称'); title=f'{prefix} BOM管理系统' if prefix else 'BOM管理系统'
  self.setWindowTitle(title)
  rows=self.svc.skus(); self.table.setRowCount(len(rows));
  for i,r in enumerate(rows):
   btn=QPushButton('打开'); btn.clicked.connect(lambda _,sid=r['id']: self.open_bom_id(sid)); self.table.setCellWidget(i,0,btn); self.table.setItem(i,1,QTableWidgetItem(r['base_code']+r['version'])); self.table.setItem(i,2,QTableWidgetItem(r['name'])); self.table.setItem(i,3,QTableWidgetItem(r['description'])); self.table.setItem(i,4,QTableWidgetItem(r['updated_at'] or '')); self.table.setItem(i,5,QTableWidgetItem(str(r['id'])))
  fit_columns(self.table)
  self.count_label.setText(f'共计{len(rows)}个SKU'); self.count_label.setToolTip('当前SKU总数')
 def select_database(self):
  current=Path(self.svc.db.path).expanduser()
  # 使用Qt对话框而非原生保存对话框，禁止已有数据库的“是否替换”确认。
  # 这样已有文件会直接作为候选数据库打开，输入新文件名仍可创建数据库。
  chooser=QFileDialog(self,'选择SQLite数据库',str(current),'SQLite (*.db *.sqlite);;所有文件 (*)')
  chooser.setFileMode(QFileDialog.AnyFile)
  chooser.setAcceptMode(QFileDialog.AcceptSave)
  chooser.setOption(QFileDialog.DontUseNativeDialog,True)
  chooser.setOption(QFileDialog.DontConfirmOverwrite,True)
  if chooser.exec_()!=QDialog.Accepted:return
  p=chooser.selectedFiles()[0] if chooser.selectedFiles() else ''
  if not p:return
  selected=Path(p).expanduser()
  existed=selected.exists()
  if selected.resolve() == current.resolve():
   QMessageBox.information(self,'数据库未切换','当前已经在使用该数据库：\n'+str(selected)); return
  new_db=None
  try:
   config_service=self.svc.config_service or ConfigService()
   relative_selected=config_service.relative_path(selected.resolve())
   selected.parent.mkdir(parents=True,exist_ok=True)
   # sqlite3.connect 对已有数据库是打开，对不存在的数据库才是创建，不会覆盖原文件。
   new_db=Database(str(selected))
   valid,missing=new_db.validate_schema()
   if not valid:
    new_db.close()
    raise ValueError('数据库结构不可用，缺少表：'+', '.join(missing))
   for window in list(self._material_bom_windows.values()):
    if not window.close(): new_db.close(); return
   if self._materials is not None: self._materials.close()
   c=config_service.load(); c['database']['path']=relative_selected; config_service.save(c)
   old_db=self.svc.db
   self.svc.db=new_db
   old_db.close()
   self.refresh()
   QMessageBox.information(self,'数据库已切换',('已打开已有数据库' if existed else '已创建并打开新数据库')+'：\n'+str(selected))
  except Exception as exc:
   if new_db is not None and new_db is not self.svc.db:new_db.close()
   QMessageBox.critical(self,'数据库错误','目标数据库无法使用，请重新选择数据库。\n\n'+str(exc))
 def export_database(self):
  p=QFileDialog.getSaveFileName(self,'导出资料库',export_start_path(export_filename((self.svc.project()['project_code']+' '+self.svc.project()['project_name']+' 资料库').strip())),'Excel (*.xlsx)')[0]
  if p:remember_export_path(p); self.svc.export_database(p); QMessageBox.information(self,'完成','资料库导出成功')
 def edit_project(self):
  d=ProjectDialog(self,self.svc.project())
  if d.exec_(): self.svc.update_project(d.data()); self.refresh()
 def activate_window(self,window):
  if window.isMinimized(): window.showNormal()
  else: window.show()
  window.raise_(); window.activateWindow()
 def show_materials(self):
  if self._materials is None:
   self._materials=MaterialWindow(self.svc,self)
   self._materials.closed.connect(lambda:setattr(self,'_materials',None))
  self.activate_window(self._materials)
 def import_materials(self):
  config_service=self.svc.config_service or ConfigService(Path(self.svc.db.path).parent); cfg=config_service.load()
  last=config_service.resolve_path(cfg['database']['last_import_dir']) if cfg['database'].get('last_import_dir') else Path.home()/'Desktop'
  last=str(last if last.is_dir() else Path.home()/'Desktop')
  p=QFileDialog.getOpenFileName(self,'导入物料清单',last,'Excel (*.xlsx)')[0]
  if p:
    cfg['database']['last_import_dir']=str(Path(p).parent); config_service.save(cfg)
    try:sheet_name=choose_material_sheet(p,self)
    except Exception as error:QMessageBox.warning(self,'导入失败',str(error)); return
    def resolver(d,old):
     dialog=MaterialConflictDialog(d,old,self); dialog.exec_(); return dialog.choice
    progress=QProgressDialog('正在导入物料，请稍候…','取消',0,100,self); progress.setWindowTitle('导入物料'); progress.setWindowModality(Qt.WindowModal); progress.setAutoClose(False); progress.show(); QApplication.processEvents()
    def update_progress(current,total):
     progress.setMaximum(max(total,1)); progress.setValue(min(current,total)); QApplication.processEvents()
    try:
     try: ok,fail=self.svc.import_materials(p,resolver,header_mapping=config_service.import_mapping('materials') or None,progress_callback=update_progress,sheet_name=sheet_name)
     except MaterialHeaderError as header_error:
      progress.close()
      mapping_dialog=MaterialHeaderMappingDialog(p,header_error.headers,header_error.missing,self,sheet_name=sheet_name,config_service=config_service)
      if mapping_dialog.exec_()!=QDialog.Accepted:
       progress.close(); QMessageBox.warning(self,'导入失败','用户取消表头映射：未完成必需表头对应关系。'); return
      progress=QProgressDialog('正在导入物料，请稍候…','取消',0,100,self); progress.setWindowTitle('导入物料'); progress.setWindowModality(Qt.WindowModal); progress.setAutoClose(False); progress.show(); QApplication.processEvents()
      ok,fail=self.svc.import_materials(p,resolver,mapping_dialog.mapping(),update_progress,sheet_name=sheet_name)
     progress.setValue(progress.maximum()); progress.close()
     self.refresh();
     if self._materials is not None and self._materials.isVisible(): self._materials.refresh()
     MaterialImportResultDialog(ok,fail,self).exec_()
    except Exception as e:
     progress.close(); QMessageBox.warning(self,'导入失败',str(e))
 def new_material(self):
  d=MaterialDialog(self)
  if d.exec_():
   try:
    self.svc.create_material(d.data()); self.refresh();
    if self._materials is not None and self._materials.isVisible(): self._materials.refresh()
   except Exception as e: QMessageBox.warning(self,'校验失败',str(e))
 def new_sku(self):
  dialog=NewSkuDialog(self.svc,self)
  if dialog.exec_()==QDialog.Accepted:
   try:
    sid=self.svc.create_sku(dialog.material_id,require_empty_bom=True); self.refresh(); self.open_bom_id(sid)
   except Exception as error:QMessageBox.warning(self,'新建SKU失败',str(error))
 def change_sku_version(self,sid=None):
  r=self.table.currentRow() if sid is None else -1
  if sid is None and r<0:return
  if sid is None:sid=int(self.table.item(r,5).text())
  v,ok=QInputDialog.getText(self,'SKU版本变更','新版本号')
  if ok:
   try:self.svc.change_sku_version(sid,v.strip()); self.refresh()
   except Exception as e: QMessageBox.warning(self,'版本变更失败',str(e))
 def delete_sku(self,sid=None):
  r=self.table.currentRow() if sid is None else -1
  if sid is None:
   if r<0:return
   sid=int(self.table.item(r,5).text())
  if QMessageBox.question(self,'确认','删除当前SKU及BOM？')==QMessageBox.Yes:self.svc.delete_sku(sid); self.refresh()
 def sku_context_menu(self,pos):
  row=self.table.rowAt(pos.y())
  if row<0:return
  self.table.selectRow(row); sid=int(self.table.item(row,5).text())
  menu=QMenu(self); version=menu.addAction('版本变更'); export_action=menu.addAction('导出BOM'); purchase_action=menu.addAction('采购BOM导出'); delete=menu.addAction('删除SKU')
  action=menu.exec_(self.table.viewport().mapToGlobal(pos))
  if action==version:self.change_sku_version(sid)
  elif action==export_action:self.export_sku_id(sid)
  elif action==purchase_action:self.export_sku_id(sid,purchase=True)
  elif action==delete:self.delete_sku(sid)
 def export_sku_id(self,sid,purchase=False):
  row=self.svc.db.conn.execute('SELECT m.id AS material_id,m.base_code,m.version,m.name FROM skus s JOIN materials m ON m.id=s.material_id WHERE s.id=?',(sid,)).fetchone()
  if not row:return
  title='采购BOM导出' if purchase else '导出BOM'
  filename=row['base_code']+row['version']+' '+row['name']+(' 采购BOM' if purchase else '')
  p=QFileDialog.getSaveFileName(self,title,export_start_path(export_filename(filename)),'Excel (*.xlsx)')[0]
  if p:
   remember_export_path(p)
   if purchase:self.svc.export_purchase_bom(row['material_id'],p)
   else:self.svc.export_sku(sid,p)
   QMessageBox.information(self,'完成',title+'成功')
 def open_bom(self,row,col): self.open_bom_id(int(self.table.item(row,5).text()))
 def open_bom_id(self,sid):
  row=self.svc.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone()
  if row is None:return
  window=self.open_material_bom(row['material_id'])
  if window is not None:self._bom_windows[sid]=window
  return window
 def open_material_bom(self,material_id):
  if self.svc.db.conn.execute('SELECT 1 FROM materials WHERE id=?',(material_id,)).fetchone() is None:return
  if material_id not in self._material_bom_windows:
   window=BomWindow(self.svc,material_id,self)
   self._material_bom_windows[material_id]=window
   def unregister():
    self._material_bom_windows.pop(material_id,None)
    for sid,opened in list(self._bom_windows.items()):
     if opened is window:self._bom_windows.pop(sid,None)
   window.closed.connect(unregister)
  window=self._material_bom_windows[material_id]
  self.activate_window(window)
  return window
 def export_materials(self):
  p=QFileDialog.getSaveFileName(self,'导出物料库',export_start_path(export_filename((self.svc.project()['project_code']+' '+self.svc.project()['project_name']+' 物料库').strip())),'Excel (*.xlsx)')[0]
  if p:remember_export_path(p); self.svc.export_materials(p); QMessageBox.information(self,'完成','导出成功')
 def template(self):
  p=QFileDialog.getSaveFileName(self,'导出模板',export_start_path('物料模板.xlsx'),'Excel (*.xlsx)')[0]
  if p:
   remember_export_path(p)
   from openpyxl import Workbook; w=Workbook(); w.active.append(MATERIAL_IMPORT_HEADERS); w.save(p); w.close()
class BomImportIssuesDialog(QDialog):
 def __init__(self,error,parent=None):
  super().__init__(parent); self.setWindowTitle('BOM导入失败')
  self.resize(800,520); self.setMaximumHeight(640)
  layout=QVBoxLayout(self)
  summary=QLabel(f'扫描完成，共发现{len(error.issues)}个问题。未导入，原有编辑和数据库保持不变。'); summary.setWordWrap(True); layout.addWidget(summary)
  self.details=QTextBrowser(); self.details.setPlainText('\n\n'.join(error.issues)); layout.addWidget(self.details)
  buttons=QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

class BomImportConflictDialog(QDialog):
 def __init__(self,conflicts,parent=None):
  super().__init__(parent);self.setWindowTitle('导入子BOM与系统不一致');self.resize(1100,580);self.choice='stop'
  layout=QVBoxLayout(self)
  label=QLabel('发现以下子BOM差异。请选择停止导入、保留系统子BOM，或使用新导入子BOM。继续导入仅更新编辑缓存，点击保存后才写入数据库；共享此子BOM的其他SKU也会受到保存的影响。')
  label.setWordWrap(True);layout.addWidget(label)
  self.table=QTableWidget(len(conflicts),5);self.table.setHorizontalHeaderLabels(['父项物料','子项物料','不一致项','系统子BOM','新导入子BOM'])
  self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.setWordWrap(True)
  self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded);self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
  for row,conflict in enumerate(conflicts):
   for column,key in enumerate(('parent','material','difference','system','incoming')):self.table.setItem(row,column,QTableWidgetItem(conflict[key]))
  layout.addWidget(self.table);fit_columns(self.table);self.table.resizeRowsToContents()
  buttons=QDialogButtonBox()
  for text,choice in [('停止导入','stop'),('继续导入并以系统子BOM为准','system'),('继续导入并以新导入子BOM为准','incoming')]:
   button=buttons.addButton(text,QDialogButtonBox.ActionRole);button.setAutoDefault(False);button.clicked.connect(lambda _,value=choice:self.finish(value))
  layout.addWidget(buttons)
 def finish(self,choice):self.choice=choice;self.accept() if choice!='stop' else self.reject()

class BomTreeWidget(QTreeWidget):
 def drawRow(self,painter,option,index):
  super().drawRow(painter,option,index)
  painter.save(); painter.setPen(self.palette().mid().color())
  rect=option.rect
  painter.drawLine(0,rect.bottom(),self.viewport().width(),rect.bottom())
  for column in range(self.columnCount()):
   x=self.header().sectionViewportPosition(column)+self.columnWidth(column)-1
   painter.drawLine(x,rect.top(),x,rect.bottom())
  painter.restore()

class BomWindow(QMainWindow):
 closed=pyqtSignal()
 def __init__(self,svc,root,parent=None):
  super().__init__(parent); self.setAttribute(Qt.WA_DeleteOnClose); self.svc=svc; self.root=root; self.current_item=None; self._deleted_relations=set(); self._alternate_edits={}; self._external_paths=set(); self._draft_baselines={}; self._loading_fields=False; self._saving=False; self.notice=QLabel(''); self.notice.setStyleSheet('color:red'); WindowRefreshBus.subscribe(self.on_external_change); self.setWindowTitle('BOM管理'); self.resize(1200,700); self.dirty=False
  self.tree=BomTreeWidget(); self.tree.itemClicked.connect(self.show_item_info); self.tree.setWordWrap(True); self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.context_menu); self.tree.setHeaderLabels(['物料编码/名称','数量','单位','位置','备注']); self.tree.setMinimumWidth(420)
  import hashlib
  database_path=str(Path(self.svc.db.path).resolve())
  self._expansion_settings=QSettings('Biong','BOMManager')
  self._expansion_key='bom_expansion/'+hashlib.sha256(database_path.encode()).hexdigest()+'/'+str(self.root)
  import json
  try:self._expansion_state=json.loads(self._expansion_settings.value(self._expansion_key,'{}'))
  except (ValueError,TypeError):self._expansion_state={}
  self._rendering_tree=False
  self.tree.itemExpanded.connect(self.remember_expansion);self.tree.itemCollapsed.connect(self.remember_expansion)
  self.fields={}; form=QFormLayout();
  for k,l in [('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料描述'),('quantity','物料数量'),('unit','物料单位'),('grade','物料等级'),('position','物料位置'),('manufacturer','物料制造商'),('mpn','物料MPN'),('mp_flag','M/P'),('remark','备注')]:
   w=QuantityEdit() if k=='quantity' else (QLineEdit() if k in ('position','remark') else QLabel()); self.fields[k]=w; form.addRow(l,w)
  self.fields['quantity'].valueChanged.connect(lambda value:self.update_tree_field('quantity',value))
  for key in ('position','remark'): self.fields[key].textChanged.connect(lambda value,k=key:self.update_tree_field(k,value))
  info_box=QGroupBox('物料信息'); info_box.setLayout(form); self.alt_table=QTableWidget(0,6); self.alt_table.setHorizontalHeaderLabels(['替代料编码','版本号','名称','描述','制造商','MPN']); self.alt_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.alt_table.setContextMenuPolicy(Qt.CustomContextMenu); self.alt_table.customContextMenuRequested.connect(self.alternate_menu); alt_box=QGroupBox('替代料'); alt_l=QVBoxLayout(alt_box); alt_l.addWidget(self.alt_table)
  right=QWidget(); right_l=QVBoxLayout(right); right_l.addWidget(info_box); right_l.addWidget(alt_box); spl=QSplitter(); spl.addWidget(self.tree); spl.addWidget(right); spl.setStretchFactor(1,1); box=QWidget(); lay=QVBoxLayout(box); lay.addWidget(spl); self.setCentralWidget(box); self.statusBar().addWidget(self.notice); tb=self.addToolBar('BOM'); self.save_action=QAction('保存',self); self.save_action.triggered.connect(self.save); self.save_action.setEnabled(False); tb.addAction(self.save_action); self.refresh_action=QAction('刷新',self); self.refresh_action.triggered.connect(self.refresh_external); self.refresh_action.setEnabled(False); tb.addAction(self.refresh_action); self.export_action=QAction('导出BOM',self); self.export_action.triggered.connect(self.export_bom); self.export_action.setEnabled(False); tb.addAction(self.export_action)
  self.purchase_export_action=QAction('采购BOM导出',self); self.purchase_export_action.triggered.connect(self.export_purchase_bom); self.purchase_export_action.setEnabled(self.export_action.isEnabled()); tb.addAction(self.purchase_export_action)
  self.export_action.changed.connect(lambda:self.purchase_export_action.setEnabled(self.export_action.isEnabled()))
  self.load()
 def mark_dirty(self):
  self.dirty=True
  self.save_action.setEnabled(True)
  self.export_action.setEnabled(False)
  self.refresh_styles()
 def on_external_change(self,event):
  if self._saving: return
  if event.get('type') in ('bom_changed','material_changed') and self.contains_material(event.get('root') if event.get('type')=='bom_changed' else event.get('id')):
   self.notice.setText('BOM有更新，请点击刷新或重新打开窗口'); self.export_action.setEnabled(False); self.refresh_action.setEnabled(True); self.statusBar().clearMessage()
 def closeEvent(self,event):
  if not self.dirty: WindowRefreshBus.unsubscribe(self.on_external_change); self.closed.emit(); event.accept(); return
  box=QMessageBox(self); box.setWindowTitle('BOM未保存'); box.setText('BOM结构或物料信息已修改，是否保存？'); save=box.addButton('保存并退出',QMessageBox.AcceptRole); discard=box.addButton('不保存退出',QMessageBox.DestructiveRole); cancel=box.addButton('取消',QMessageBox.RejectRole); box.exec_()
  if box.clickedButton()==save:
   if self.save(): WindowRefreshBus.unsubscribe(self.on_external_change); self.closed.emit(); event.accept()
   else: event.ignore()
  elif box.clickedButton()==discard: WindowRefreshBus.unsubscribe(self.on_external_change); self.closed.emit(); event.accept()
  else: event.ignore()

 def context_menu(self,pos):
  it=self.tree.itemAt(pos)
  if not it:return
  d=it.data(0,Qt.UserRole) or {}
  if d.get('_deleted'):return
  if it is getattr(self,'root_item',None):
   m=QMenu(self); child=m.addAction('增加子级物料'); imp=m.addAction('导入BOM'); (imp.setEnabled(it.childCount()==0 and not self.svc.bom(self.root)) if hasattr(imp,'setEnabled') else None); (imp.setToolTip('当前物料已有下阶物料，不能重复导入' if not imp.isEnabled() else '导入当前物料的下阶BOM') if hasattr(imp,'setToolTip') else None); clipboard_actions=self.clipboard_actions(m,it); act=m.exec_(self.tree.viewport().mapToGlobal(pos))
   if self.handle_clipboard_action(act,clipboard_actions,it):return
   if act==child:self.add_relative(d,True)
   elif act==imp:self.import_bom(it)
   return
  m=QMenu(self); same=m.addAction('新增同级物料'); child=m.addAction('新增子级物料'); imp=m.addAction('导入BOM'); (imp.setEnabled(it.childCount()==0 and not self.svc.bom(d.get('material_id'))) if hasattr(imp,'setEnabled') else None); (imp.setToolTip('当前物料已有下阶物料，不能重复导入' if not imp.isEnabled() else '导入当前物料的下阶BOM') if hasattr(imp,'setToolTip') else None); dele=m.addAction('删除物料'); alternate=m.addAction('增加替代料'); up=m.addAction('物料上移'); down=m.addAction('物料下移'); up.setEnabled(self.can_move_item(it,-1)); down.setEnabled(self.can_move_item(it,1)); clipboard_actions=self.clipboard_actions(m,it); act=m.exec_(self.tree.viewport().mapToGlobal(pos))
  if self.handle_clipboard_action(act,clipboard_actions,it):return
  if act==up:self.move_item(it,-1); return
  if act==down:self.move_item(it,1); return
  if act==imp:self.import_bom(it); return
  if act==alternate:
   self.tree.setCurrentItem(it); self.show_item_info(it); self.add_alternate(); return
  if act in (same,child): self.add_relative(d, act==child); return
  if act==dele and QMessageBox.question(self,'确认','删除当前BOM物料？')==QMessageBox.Yes:
   self.remove_relation(it)
 def can_move_item(self,item,direction):
  parent=item.parent()
  if parent is None or direction not in (-1,1) or (item.data(0,Qt.UserRole) or {}).get('_deleted'):return False
  return 0<=parent.indexOfChild(item)+direction<parent.childCount()
 def move_item(self,item,direction):
  if not self.can_move_item(item,direction):return
  parent=item.parent(); index=parent.indexOfChild(item); expanded=item.isExpanded()
  parent.takeChild(index); parent.insertChild(index+direction,item); item.setExpanded(expanded)
  data=item.data(0,Qt.UserRole) or {}; data['_moved']=True; item.setData(0,Qt.UserRole,data)
  # 同一共享父物料的多个显示位置同步排序，避免保存时被另一副本覆盖。
  parent_id=(parent.data(0,Qt.UserRole) or {})['material_id']
  order=[(parent.child(i).data(0,Qt.UserRole) or {}).get('material_id') for i in range(parent.childCount())]
  for _,other in list(self.expansion_nodes()):
   if other is parent or (other.data(0,Qt.UserRole) or {}).get('material_id')!=parent_id:continue
   children=other.takeChildren(); rank={mid:i for i,mid in enumerate(order)}
   children.sort(key=lambda child:rank.get((child.data(0,Qt.UserRole) or {}).get('material_id'),len(rank)))
   other.addChildren(children)
   for child in children:
    d=child.data(0,Qt.UserRole) or {}
    if d.get('material_id')==data['material_id']:d['_moved']=True;child.setData(0,Qt.UserRole,d)
  self.mark_dirty(); self.tree.setCurrentItem(item); self.show_item_info(item); self.tree.scrollToItem(item); self.remember_expansion()
 def clipboard_actions(self,menu,item):
  actions={'copy':menu.addAction('复制物料')}
  material=clipboard_material(self.svc)
  if material:
   for key,label,child in [('same','粘贴为同级物料',False),('child','粘贴为子级物料',True)]:
    action=menu.addAction(label); reason=self.paste_block_reason(item,child,material['id'])
    action.setEnabled(not reason); action.setToolTip(reason or label); actions[key]=action
  return actions
 def handle_clipboard_action(self,action,actions,item):
  if action is None:return False
  if action==actions['copy']:
   copy_material(self.svc,(item.data(0,Qt.UserRole) or {})['material_id']); return True
  for key,child in [('same',False),('child',True)]:
   if key in actions and action==actions[key]:
    if actions[key].isEnabled():self.paste_material(item,child)
    return True
  return False
 def paste_block_reason(self,item,child,material_id):
  target=item if child else item.parent()
  if target is None:return 'SKU根节点不能增加同级物料'
  if (item.data(0,Qt.UserRole) or {}).get('_deleted'):return '待删除物料不能粘贴'
  if any((target.child(i).data(0,Qt.UserRole) or {}).get('material_id')==material_id for i in range(target.childCount())):return '目标父级下已存在相同物料'
  # 合并数据库和当前编辑树的关系，检查跨分支、未保存关系导致的循环。
  graph={}
  for row in self.svc.db.conn.execute('SELECT parent_material_id,child_material_id FROM material_bom_items'):
   graph.setdefault(row[0],set()).add(row[1])
  for _,node in self.expansion_nodes():
   if node.parent() is not None:
    parent_id=(node.parent().data(0,Qt.UserRole) or {}).get('material_id')
    graph.setdefault(parent_id,set()).add((node.data(0,Qt.UserRole) or {}).get('material_id'))
  target_id=(target.data(0,Qt.UserRole) or {}).get('material_id'); pending=[material_id]; visited=set()
  while pending:
   mid=pending.pop()
   if mid==target_id:return '粘贴会造成循环引用'
   if mid in visited:continue
   visited.add(mid); pending.extend(graph.get(mid,()))
  return ''
 def paste_material(self,item,child):
  material=clipboard_material(self.svc)
  if material is None:return
  reason=self.paste_block_reason(item,child,material['id'])
  if reason:return
  target=item if child else item.parent()
  added=self.insert_material(target,material)
  if not child:
   target.takeChild(target.indexOfChild(added)); target.insertChild(target.indexOfChild(item)+1,added)
  self.tree.setCurrentItem(added); self.show_item_info(added); self.tree.scrollToItem(added)
  return added
 def relation_key(self,item):
  data=item.data(0,Qt.UserRole) or {}; parent=item.parent()
  parent_data=parent.data(0,Qt.UserRole) if parent else {}
  return (parent_data.get('material_id'),data.get('material_id'),item.text(3))
 def remove_relation(self,item):
  """将共享关系的所有显示副本标记为待删除，保存前保留可见。"""
  if item is self.root_item:return
  key=self.relation_key(item); relation_id=(item.data(0,Qt.UserRole) or {}).get('id')
  matches=[]; stack=[self.root_item]
  while stack:
   node=stack.pop(); data=node.data(0,Qt.UserRole) or {}
   if node is not self.root_item and (self.relation_key(node)==key or (relation_id and relation_id>0 and data.get('id')==relation_id)):
    matches.append(node)
   else: stack.extend(node.child(i) for i in range(node.childCount()))
  if relation_id and relation_id>0:
   original=self.svc.db.conn.execute('SELECT parent_material_id,child_material_id,position FROM material_bom_items WHERE id=?',(relation_id,)).fetchone()
   if original:self._deleted_relations.add((original[0],original[1],original[2] or ''))
  self.current_item=None
  for node in matches:
   data=node.data(0,Qt.UserRole) or {}; current_key=self.relation_key(node)
   self._deleted_relations.add(current_key)
   self._deleted_relations.add((current_key[0],current_key[1],data.get('position','') or ''))
   pending=[node]
   while pending:
    removed=pending.pop(); removed_data=removed.data(0,Qt.UserRole) or {}
    removed_data['_deleted']=True; removed.setData(0,Qt.UserRole,removed_data)
    pending.extend(removed.child(i) for i in range(removed.childCount()))
  self.mark_dirty(); self.tree.setCurrentItem(self.root_item); self.show_item_info(self.root_item)
 def contains_material(self,material_id):
  if material_id is None:return False
  if material_id==self.root:return True
  for i in range(self.tree.topLevelItemCount()):
   stack=[self.tree.topLevelItem(i)]
   while stack:
    item=stack.pop(); d=item.data(0,Qt.UserRole) or {}
    if d.get('material_id')==material_id:return True
    stack.extend([item.child(j) for j in range(item.childCount())])
  return False
 def capture_item(self,item):
  data=dict(item.data(0,Qt.UserRole) or {})
  data.update(quantity=float(item.text(1)),position=item.text(3),remark=data.get('remark',''))
  return {'data':data,'children':[self.capture_item(item.child(n)) for n in range(item.childCount())]}
 def capture_tree(self):
  return [self.capture_item(self.root_item.child(n)) for n in range(self.root_item.childCount())]
 def database_tree(self,root=None):
  roots=[]; nodes={}; alternate_cache={}
  for row in self.svc.bom(self.root if root is None else root):
   if row['id'] not in alternate_cache:alternate_cache[row['id']]=[r['material_id'] for r in self.svc.alternates(row['id'])]
   node={'data':dict(row),'children':[]}; node['data']['_db_alternates']=alternate_cache[row['id']]; nodes[row['node_id']]=node
   parent=nodes.get(row['parent_node_id'])
   (parent['children'] if parent else roots).append(node)
  return roots
 def mark_external_differences(self,before_nodes,after_nodes,path=()):
  before=self.snapshot_map(before_nodes,path); after=self.snapshot_map(after_nodes,path)
  changed=set(before.keys()-after.keys())
  for key,node in after.items():
   old=before.get(key)
   if old is None or self.remote_signature(old)!=self.remote_signature(node):changed.add(key)
  # 只记录自身变化；子项增删由子项路径表示，不能将父级误判为变化物料。
  self._external_paths.update(changed)
 def refresh_drafts(self,nodes,conflicts,path=()):
  from copy import deepcopy
  materials={row['id']:row for row in self.svc.materials()}
  def walk(node,parent_path):
   data=node['data']; draft_id=data.get('id'); current_path=parent_path+(data['material_id'],)
   baseline=self._draft_baselines.get(draft_id)
   if baseline is not None and not data.get('_deleted'):
    fresh=deepcopy(baseline); material=materials.get(data['material_id'])
    if material is not None:
     for field in ('base_code','version','name','description','unit','grade','manufacturer','mpn','mp_flag'):fresh['data'][field]=material[field]
     fresh['children']=self.database_tree(data['material_id'])
     def added(nodes):
      for child in nodes:
       child['data']['_added']=True; added(child['children'])
     added(fresh['children'])
     self.mark_external_differences([baseline],[fresh],parent_path)
     node=self.merge_refresh([baseline],[node],[fresh],conflicts)[0]
     self._draft_baselines[draft_id]=deepcopy(fresh)
   node['children']=[walk(child,current_path) for child in node['children']]
   return node
  return [walk(node,path) for node in nodes]
 def merge_refresh(self,baseline,local,remote,conflicts):
  """三方合并：只把本地相对载入基线的修改覆盖到最新数据库结构。"""
  from copy import deepcopy
  def identity(node,all_nodes):
   mid=node['data']['material_id']
   # 正常BOM同一父级仅出现一次物料；兼容历史多位置同物料关系。
   duplicate=any(sum(n['data']['material_id']==mid for n in group)>1 for group in all_nodes)
   return (mid,node['data'].get('id')) if duplicate else (mid,)
  groups=(baseline,local,remote)
  base={identity(n,groups):n for n in baseline}; ours={identity(n,groups):n for n in local}; theirs={identity(n,groups):n for n in remote}
  def modified(node,original):
   data=node['data']; previous=original['data']
   if data.get('_moved') or data.get('_deleted') or (data.get('_added') and not previous.get('_added')):return True
   if data.get('id') in self._alternate_edits and self._alternate_edits[data['id']]!=previous.get('_db_alternates',[]):return True
   if any(data.get(k)!=previous.get(k) for k in ('quantity','position','remark')):return True
   if [n['data'].get('id') for n in node['children']]!=[n['data'].get('id') for n in original['children']]:return True
   return any(modified(child,old) for child,old in zip(node['children'],original['children']))
  merged=[]
  for key,new in theirs.items():
   previous=base.get(key); edit=ours.get(key)
   if edit is not None and edit['data'].get('_deleted'):
    merged.append(deepcopy(edit)); continue
   if previous is not None and edit is None:continue  # 本地明确删除，刷新不能恢复。
   if edit is None:merged.append(deepcopy(new)); continue
   if previous is None:
    if edit['data'].get('id')!=new['data'].get('id'):conflicts.append('双方新增相同物料')
    previous={'data':{},'children':[]}
   result=deepcopy(new)
   if edit['data'].get('_added'):result['data']['_added']=True
   if edit['data'].get('_moved'):result['data']['_moved']=True
   for field in ('quantity','position','remark'):
    value=edit['data'].get(field)
    if value!=previous['data'].get(field):
     if new['data'].get(field)!=previous['data'].get(field) and value!=new['data'].get(field):conflicts.append('同一字段同时修改')
     result['data'][field]=value
   old_id=edit['data'].get('id'); new_id=result['data'].get('id')
   if old_id in self._alternate_edits and old_id!=new_id:self._alternate_edits[new_id]=list(self._alternate_edits[old_id])
   result['children']=self.merge_refresh(previous['children'],edit['children'],new['children'],conflicts)
   merged.append(result)
  for key,edit in ours.items():
   if key in theirs:continue
   previous=base.get(key)
   if previous is None or edit['data'].get('_deleted') or modified(edit,previous):
    if previous is not None and not edit['data'].get('_deleted'):conflicts.append('外部删除了本地已编辑物料')
    merged.append(deepcopy(edit))
  if any(node['data'].get('_moved') for node in local):
   rank={node['data']['material_id']:i for i,node in enumerate(local)}
   merged.sort(key=lambda node:rank.get(node['data']['material_id'],len(rank)))
  return merged
 def refresh_external(self):
  from copy import deepcopy
  fresh=self.database_tree(); conflicts=[]
  root=dict(self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone())
  if any(root.get(k)!=self._root_baseline.get(k) for k in ('base_code','version','name','description','unit','grade','manufacturer','mpn','mp_flag')):self._external_paths.add(())
  self._root_baseline=root
  self.mark_external_differences(self._baseline_tree,fresh)
  local=self.refresh_drafts(self.capture_tree(),conflicts) if self.dirty else []
  merged=self.merge_refresh(self._baseline_tree,local,fresh,conflicts) if self.dirty else fresh
  def exclude_deleted(nodes,parent_id):
   result=[]
   for node in nodes:
    data=node['data']
    if (parent_id,data['material_id'],data.get('position','') or '') in self._deleted_relations:data['_deleted']=True
    node['children']=exclude_deleted(node['children'],data['material_id']); result.append(node)
   return result
  self.render_tree(exclude_deleted(merged,self.root)); self._baseline_tree=deepcopy(fresh)
  self.notice.setText(''); self.statusBar().clearMessage(); self.refresh_action.setEnabled(False); self.save_action.setEnabled(True); self.export_action.setEnabled(False); self.refresh_styles()
  if conflicts:self.statusBar().showMessage('已加载外部更新；检测到冲突，已保留本地未保存修改，请核对后保存。')
 def load(self,preserve=None):
  from copy import deepcopy
  fresh=self.database_tree(); self.render_tree(fresh); self._baseline_tree=deepcopy(fresh); self._root_baseline=dict(self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone()); self._external_paths.clear(); self._draft_baselines.clear(); self.refresh_styles()
  self.save_action.setEnabled(False); self.refresh_action.setEnabled(False); self.export_action.setEnabled(True)
 def expansion_nodes(self):
  if not hasattr(self,'root_item'):return
  def walk(item,path):
   data=item.data(0,Qt.UserRole) or {}; key=path+'/'+str(data.get('material_id'))
   yield key,item
   for index in range(item.childCount()):yield from walk(item.child(index),key)
  yield from walk(self.root_item,'')
 def remember_expansion(self,*args):
  if self._rendering_tree:return
  import json
  self._expansion_state={key:item.isExpanded() for key,item in self.expansion_nodes()}
  self._expansion_settings.setValue(self._expansion_key,json.dumps(self._expansion_state));self._expansion_settings.sync()
 def render_tree(self,nodes):
  if hasattr(self,'root_item'):self.remember_expansion()
  self._rendering_tree=True
  self.current_item=None; self.tree.clear(); self.by={}; root=self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone()
  self.setWindowTitle(f"{root['base_code']}{root['version']} {root['name']}")
  self.root_item=QTreeWidgetItem(self.tree,[f"{root['base_code']}{root['version']} {root['name']}",'','','','']); self.root_item.setData(0,Qt.UserRole,{'material_id':self.root,'root':True}); self.root_item.setExpanded(True)
  def append(node,parent,path,level):
   data=dict(node['data']); data.setdefault('_edit_base',{k:data.get(k) for k in ('quantity','position','remark')}); parent_data=parent.data(0,Qt.UserRole) or {}
   node_id=f"{path}/{data['id']}"
   data.update(node_id=node_id,parent_node_id=path or None,parent_material_id=parent_data['material_id'],parent_item_id=parent_data.get('id'),level_no=level)
   item=QTreeWidgetItem(parent,[f"{data['base_code']}{data['version']} {data['name']}",f"{data['quantity']:.1f}",data['unit'],data.get('position',''),data.get('remark','')]); item.setData(0,Qt.UserRole,data); self.by[node_id]=item
   for child in node['children']:append(child,item,node_id,level+1)
  for node in nodes:append(node,self.root_item,'',1)
  for key,item in self.expansion_nodes():
   if key in self._expansion_state:item.setExpanded(self._expansion_state[key])
  self._rendering_tree=False
  fit_columns(self.tree); self.tree.setCurrentItem(self.root_item); self.show_item_info(self.root_item)
 def snapshot_map(self,nodes,path=()):
  result={}
  for node in nodes:
   key=path+(node['data']['material_id'],); result[key]=node
   result.update(self.snapshot_map(node['children'],key))
  return result
 def remote_signature(self,node):
  fields=('material_id','quantity','position','remark','base_code','version','name','description','unit','grade','manufacturer','mpn','mp_flag','_db_alternates')
  return [node['data'].get(k) for k in fields]
 def refresh_styles(self):
  if not hasattr(self,'root_item'):return
  baseline=self.snapshot_map(getattr(self,'_baseline_tree',[]))
  def style(item,path,added=False,deleted=False,external=False):
   data=item.data(0,Qt.UserRole) or {}; root=item is self.root_item
   if not root:path=path+(data['material_id'],)
   external=external or path in self._external_paths
   added=added or data.get('_added',False); deleted=deleted or data.get('_deleted',False)
   if deleted and not data.get('_deleted'):
    data['_deleted']=True; item.setData(0,Qt.UserRole,data)
   draft=self._draft_baselines.get(data.get('id'))
   if draft is not None:
    baseline[path]=draft; baseline.update(self.snapshot_map(draft['children'],path))
   original=baseline.get(path,{}).get('data',data.get('_edit_base',{}))
   changed={column for field,column in [('quantity',1),('position',3),('remark',4)] if not root and data.get(field,'')!=original.get(field,'')}
   alternate_changed=self.alternate_key(item) in self._alternate_edits and self.alternate_ids(item)!=original.get('_db_alternates',[])
   if alternate_changed:changed.add(0)
   for column in range(self.tree.columnCount()):
    if column==2:item.setTextAlignment(column,Qt.AlignCenter)
    font=QFont(self.tree.font()); font.setStrikeOut(bool(deleted)); font.setBold(column in changed and not deleted)
    item.setFont(column,font)
    color=QColor('red') if deleted else QColor('green') if added else QColor('#9a6700') if changed else None
    item.setForeground(column,QBrush(color) if color else QBrush(QColor('white')) if external else QBrush())
    moved=data.get('_moved',False)
    if moved and not color:item.setForeground(column,QBrush(QColor('#202020')))
    item.setBackground(column,QBrush(QColor('#f8d7e3')) if moved else QBrush(QColor('#4a148c')) if external else QBrush())
   remark=data.get('remark','') if not root else ''
   display=remark
   if external:display=(remark+'\n' if remark else '')+'有其他BOM更新导入此变更'
   item.setText(4,display); item.setToolTip(4,remark)
   for n in range(item.childCount()):style(item.child(n),path,added,deleted,external)
  style(self.root_item,())
  fit_columns(self.tree)
 def locate_material(self,material_id,parent_id=None):
  # 仅展开目标的祖先路径，保留已有窗口中的编辑缓存和其他展开状态。
  for _,item in self.expansion_nodes():
   data=item.data(0,Qt.UserRole) or {}
   if data.get('material_id',self.root if data.get('root') else None)!=material_id:continue
   if parent_id is not None and data.get('parent_material_id')!=parent_id:continue
   if data.get('_deleted'):continue
   ancestor=item.parent()
   while ancestor is not None:
    ancestor.setExpanded(True); ancestor=ancestor.parent()
   self.tree.setCurrentItem(item); self.show_item_info(item); self.tree.scrollToItem(item,QAbstractItemView.PositionAtCenter)
   return True
  return False
 def show_item_info(self,item,column=0):
  self.current_item=item
  d=item.data(0,Qt.UserRole) or {}
  if d.get('root'):
   r=self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone(); d=dict(r) if r else d
  self._loading_fields=True
  editable=not ((item.data(0,Qt.UserRole) or {}).get('root') or (item.data(0,Qt.UserRole) or {}).get('_deleted'))
  for field in ('quantity','position','remark'):self.fields[field].setEnabled(editable)
  for k in self.fields: self.fields[k].setText(str(d.get(k,'') or ''))
  self._loading_fields=False
  self.alt_table.setRowCount(0)
  if not (item.data(0,Qt.UserRole) or {}).get('root'):
   materials={row['id']:row for row in self.svc.materials()}
   for material_id in self.alternate_ids(item):
    r=materials.get(material_id)
    if r is None:continue
    row=self.alt_table.rowCount(); self.alt_table.insertRow(row)
    for j,k in enumerate(['base_code','version','name','description','manufacturer','mpn']):
     cell=QTableWidgetItem(str(r[k] or '')); cell.setData(Qt.UserRole,material_id); self.alt_table.setItem(row,j,cell)
  fit_columns(self.alt_table)
 def update_tree_field(self,key,value):
  if self._loading_fields or self.current_item is None or self.current_item is getattr(self,'root_item',None): return
  if (self.current_item.data(0,Qt.UserRole) or {}).get('_deleted'):return
  value=f'{float(value):.1f}' if key=='quantity' else value
  col={'quantity':1,'position':3,'remark':4}[key]; self.current_item.setText(col,value); d=self.current_item.data(0,Qt.UserRole) or {}; d[key]=float(value) if key=='quantity' and value else value; self.current_item.setData(0,Qt.UserRole,d); self.mark_dirty()
 def add_relative(self,parent,child):
  target=self.by.get(parent.get('node_id'),self.root_item) if child else (self.by.get(parent.get('parent_node_id'),self.root_item) or self.root_item)
  used={target.child(i).data(0,Qt.UserRole).get('material_id') for i in range(target.childCount()) if target.child(i).data(0,Qt.UserRole)}
  blocked=set(used)
  node=target; ancestors=set()
  while node is not None:
   node_data=node.data(0,Qt.UserRole) or {}
   if node_data.get('material_id'): ancestors.add(node_data['material_id'])
   node=node.parent()
  blocked.update(ancestors)
  for candidate in self.svc.materials():
   if any(row['material_id'] in ancestors for row in self.svc.bom(candidate['id'])): blocked.add(candidate['id'])
  rows=[r for r in self.svc.materials() if r['id'] not in blocked]; items=[f"{r['base_code']}{r['version']} {r['name']}" for r in rows]
  if not items: QMessageBox.information(self,'提示','当前父级下已没有可新增的物料'); return
  x,ok=MaterialSelectionDialog.getItem(self,'新建BOM物料','物料',items,0,False)
  if not ok:return
  self.insert_material(target,rows[items.index(x)])
 def insert_material(self,target,r):
  parent=target.data(0,Qt.UserRole) or {}
  self._deleted_relations.discard((parent.get('material_id'),r['id'],''))
  item=QTreeWidgetItem(target,[f"{r['base_code']}{r['version']} {r['name']}",'1.0',r['unit'],'',''])
  temporary_id=-id(item); data=dict(r)
  data.update(_added=True,id=temporary_id,material_id=r['id'],quantity=1.0,position='',remark='',level_no=(parent.get('level_no') or 0)+1,parent_item_id=parent.get('id'),parent_material_id=parent.get('material_id'),node_id=str(temporary_id),parent_node_id=parent.get('node_id'))
  item.setData(0,Qt.UserRole,data); self.by[str(temporary_id)]=item; target.setExpanded(True)
  self.add_existing_children(item,r['id'],set())
  self._draft_baselines[temporary_id]=self.capture_item(item)
  fit_columns(self.tree); self.mark_dirty(); self.tree.setCurrentItem(item); self.show_item_info(item)
  return item
 def add_existing_children(self,parent_item,material_id,ancestors):
  if material_id in ancestors:return
  ancestors=set(ancestors); ancestors.add(material_id)
  rows=self.svc.db.conn.execute('SELECT b.*,m.base_code,m.version,m.name,m.description,m.unit AS material_unit,m.grade,m.manufacturer,m.mpn,m.mp_flag FROM material_bom_items b JOIN materials m ON m.id=b.child_material_id WHERE b.parent_material_id=? ORDER BY b.sort_no,b.id',(material_id,)).fetchall()
  parent_data=parent_item.data(0,Qt.UserRole) or {}
  for row in rows:
   if row['child_material_id'] in ancestors:continue
   child=QTreeWidgetItem(parent_item,[f"{row['base_code']}{row['version']} {row['name']}",f"{row['quantity']:.1f}",row['material_unit'],row['position'],row['remark']]); d=dict(row); d['_added']=parent_data.get('_added',False); d['_db_alternates']=[a['material_id'] for a in self.svc.alternates(row['id'])]; d.update({'material_id':row['child_material_id'],'unit':row['material_unit'],'parent_item_id':parent_data.get('id'),'level_no':(parent_data.get('level_no') or 0)+1}); d.update(node_id=f"{parent_data.get('node_id')}/{row['id']}",parent_node_id=parent_data.get('node_id')); child.setData(0,Qt.UserRole,d); self.by[d['node_id']]=child; self.add_existing_children(child,row['child_material_id'],ancestors)
  parent_item.setExpanded(True)
 def alternate_key(self,item):
  data=item.data(0,Qt.UserRole) or {}
  return data.get('id') or data.get('node_id')
 def alternate_ids(self,item):
  key=self.alternate_key(item)
  if key in self._alternate_edits:return list(self._alternate_edits[key])
  return [row['material_id'] for row in self.svc.alternates(key)] if isinstance(key,int) and key>0 else []
 def add_alternate(self):
  item=self.tree.currentItem()
  if item is None or item is self.root_item or (item.data(0,Qt.UserRole) or {}).get('_deleted'):return
  existing=self.alternate_ids(item); data=item.data(0,Qt.UserRole) or {}
  rows=[row for row in self.svc.materials() if row['id']!=data.get('material_id') and row['id'] not in existing]
  if not rows: QMessageBox.information(self,'增加替代料','没有可选替代料'); return
  choices=[f"{row['base_code']}{row['version']} {row['name']}" for row in rows]
  choice,ok=MaterialSelectionDialog.getItem(self,'增加替代料','选择物料',choices,0,False)
  if not ok:return
  self._alternate_edits[self.alternate_key(item)]=existing+[rows[choices.index(choice)]['id']]
  self.mark_dirty(); self.show_item_info(item)
 def alternate_menu(self,pos):
  row=self.alt_table.rowAt(pos.y()); item=self.current_item
  if row<0 or item is None or item is self.root_item or (item.data(0,Qt.UserRole) or {}).get('_deleted'):return
  menu=QMenu(self); remove=menu.addAction('删除替代料')
  if menu.exec_(self.alt_table.viewport().mapToGlobal(pos))!=remove:return
  if QMessageBox.question(self,'确认','删除当前替代料？')!=QMessageBox.Yes:return
  material_id=self.alt_table.item(row,0).data(Qt.UserRole)
  self._alternate_edits[self.alternate_key(item)]=[mid for mid in self.alternate_ids(item) if mid!=material_id]
  self.mark_dirty(); self.show_item_info(item)
 def import_bom(self,selected_item=None):
  if self.dirty and QMessageBox.question(self,'BOM未保存','导入成功后将替换当前编辑缓存，是否放弃当前未保存编辑并继续？')!=QMessageBox.Yes:return
  p=QFileDialog.getOpenFileName(self,'导入BOM','','Excel (*.xlsx)')[0]
  if not p:return
  try:
   sheet=choose_material_sheet(p,self,'BOM')
   from openpyxl import load_workbook
   wb=load_workbook(p,read_only=True,data_only=True)
   try:headers=[str(value if value is not None else '').strip() for value in next(wb[sheet].iter_rows(values_only=True),())]
   finally:wb.close()
   dialog=MaterialHeaderMappingDialog(p,headers,[h for h in self.svc.BOM_HEADERS if h not in headers],self,sheet_name=sheet,required=self.svc.BOM_HEADERS,config_service=self.svc.config_service or ConfigService(Path(self.svc.db.path).parent))
   if dialog.exec_()!=QDialog.Accepted:raise ValueError('用户取消BOM表头映射，未导入')
   target_root=(selected_item.data(0,Qt.UserRole) or {}).get('material_id') if selected_item is not None else self.root
   def resolve_conflicts(conflicts):
    decision=BomImportConflictDialog(conflicts,self);decision.exec_();return decision.choice
   nodes=self.svc.import_bom(p,target_root,sheet_name=sheet,header_mapping=dialog.mapping(),persist=False,conflict_resolver=resolve_conflicts)
   self.stage_import(nodes) if target_root==self.root else self.stage_import_subtree(selected_item,nodes)
   QMessageBox.information(self,'导入完成','BOM已导入编辑缓存，请检查后点击“保存”写入数据库。')
  except BomImportError as error:BomImportIssuesDialog(error,self).exec_()
  except Exception as error:QMessageBox.warning(self,'导入失败',str(error))
 def stage_import(self,nodes):
  from copy import deepcopy
  baseline=self.database_tree()
  self._deleted_relations.clear(); self._alternate_edits.clear(); self._draft_baselines.clear(); self._external_paths.clear()
  def compare(old,new,parent):
   old_by={n['data']['material_id']:n for n in old}
   new_ids={n['data']['material_id'] for n in new}
   for node in new:
    data=node['data']; previous=old_by.get(data['material_id'])
    if 'alternate_material_ids' in data:self._alternate_edits[data['id']]=list(data['alternate_material_ids'])
    if previous is None:
     data['_added']=True
     if data['id']<0:self._draft_baselines[data['id']]=deepcopy(node)
    compare(previous['children'] if previous else [],node['children'],data['material_id'])
   for node in old:
    if node['data']['material_id'] not in new_ids:
     deleted=deepcopy(node); deleted['data']['_deleted']=True; new.append(deleted)
     data=deleted['data']; self._deleted_relations.add((parent,data['material_id'],data.get('position','') or ''))
  compare(baseline,nodes,self.root)
  self._baseline_tree=deepcopy(baseline)
  self.render_tree(nodes); self.mark_dirty()
  self.notice.clear(); self.refresh_action.setEnabled(False); self.statusBar().clearMessage()
 def export_purchase_bom(self):
  if not self.purchase_export_action.isEnabled():return
  material=self.svc.material_snapshot(self.root)
  filename=material['base_code']+material['version']+' '+material['name']+' 采购BOM'
  p=QFileDialog.getSaveFileName(self,'采购BOM导出',export_start_path(export_filename(filename)),'Excel (*.xlsx)')[0]
  if p:
   remember_export_path(p);self.svc.export_purchase_bom(self.root,p);QMessageBox.information(self,'完成','采购BOM导出成功')
 def export_bom(self):
  if not self.export_action.isEnabled():return
  material=self.svc.material_snapshot(self.root)
  p=QFileDialog.getSaveFileName(self,'导出BOM',export_start_path(export_filename(material['base_code']+material['version']+' '+material['name'])),'Excel (*.xlsx)')[0]
  if p:
   remember_export_path(p)
   r=self.svc.db.conn.execute('SELECT id FROM skus WHERE material_id=?',(self.root,)).fetchone()
   if r:self.svc.export_sku(r['id'],p); QMessageBox.information(self,'完成','导出成功')
 def add(self):
  self.add_relative({'id':None,'parent_item_id':None,'level_no':0},False)
 def stage_import_subtree(self,item,nodes):
  from copy import deepcopy
  while item.childCount():item.takeChild(0)
  data=item.data(0,Qt.UserRole) or {}
  def append(node,parent,path,level):
   d=dict(node['data']); d['_added']=d.get('_added',True); d.update(parent_material_id=data.get('material_id'),parent_item_id=data.get('id'),node_id=f'{path}/{d["id"]}',parent_node_id=path,level_no=level)
   child=QTreeWidgetItem(parent,[f"{d['base_code']}{d['version']} {d['name']}",f"{d['quantity']:.1f}",d['unit'],d.get('position',''),d.get('remark','')]);child.setData(0,Qt.UserRole,d)
   for grand in node['children']:append(grand,child,d['node_id'],level+1)
  for node in nodes:append(node,item,data.get('node_id',''),(data.get('level_no') or 0)+1)
  item.setExpanded(True);self.mark_dirty();self.tree.setCurrentItem(item);self.show_item_info(item)
 def save(self):
  self._saving=True
  try:
   rows=[]
   def walk(it,parent_material):
    d=dict(it.data(0,Qt.UserRole) or {})
    if d.get('_deleted'):return
    d.update(quantity=float(it.text(1)),position=it.text(3),remark=d.get('remark',''),parent_material_id=parent_material,replace_children=True)
    if self.alternate_key(it) in self._alternate_edits:d['alternate_material_ids']=self.alternate_ids(it)
    rows.append(d)
    for j in range(it.childCount()): walk(it.child(j),d['material_id'])
   for j in range(self.root_item.childCount()): walk(self.root_item.child(j),self.root)
   self.svc.save_bom(self.root,rows)
  except Exception as error:
   self.mark_dirty()
   QMessageBox.warning(self,'保存失败',f'BOM未保存，编辑内容已保留。\n{error}')
   return False
  finally:
   self._saving=False
  self.dirty=False; self._deleted_relations.clear(); self.export_action.setEnabled(True); self._alternate_edits.clear(); self.load(); self.notice.setText(''); self.statusBar().clearMessage(); self.save_action.setEnabled(False); self.refresh_action.setEnabled(False)
  QMessageBox.information(self,'保存','BOM已保存')
  return True

class MaterialColumnFilterDialog(QDialog):
 def __init__(self,title,values,condition=None,parent=None):
  super().__init__(parent); self.setWindowTitle('筛选：'+title); self.resize(420,460)
  layout=QVBoxLayout(self); self.query=QLineEdit(); self.query.setPlaceholderText('包含文字（可留空，不区分大小写）'); layout.addWidget(self.query)
  self.values=sorted(set(values)); self.list=QListWidget(); layout.addWidget(self.list)
  query,selected=condition or ('',None); self.query.setText(query)
  for value in self.values:
   item=QListWidgetItem(value or '（空白）',self.list); item.setData(Qt.UserRole,value); item.setCheckState(Qt.Checked if selected is None or value in selected else Qt.Unchecked)
  actions=QHBoxLayout(); all_button=QPushButton('全选'); none_button=QPushButton('全不选'); actions.addWidget(all_button); actions.addWidget(none_button); layout.addLayout(actions)
  all_button.clicked.connect(lambda:self.set_checks(Qt.Checked)); none_button.clicked.connect(lambda:self.set_checks(Qt.Unchecked))
  buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
 def set_checks(self,state):
  for index in range(self.list.count()):self.list.item(index).setCheckState(state)
 def condition(self):
  selected={self.list.item(i).data(Qt.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.Checked}
  return self.query.text().strip(),None if selected==set(self.values) else selected

class MaterialWindow(QMainWindow):
 closed=pyqtSignal()
 def __init__(self,svc,parent=None):
  super().__init__(parent); self.setAttribute(Qt.WA_DeleteOnClose); self.svc=svc; self._filters={}; self._local_bom_windows={}; WindowRefreshBus.subscribe(self.on_event); self.setWindowTitle('物料库')
  menu=self.menuBar(); a=menu.addAction('查找物料'); a.triggered.connect(self.search_materials); a=menu.addAction('新建物料'); a.triggered.connect(parent.new_material if parent else self.new_material); a=menu.addAction('导入物料'); a.triggered.connect(parent.import_materials if parent else self.import_materials); a=menu.addAction('导出物料库'); a.triggered.connect(parent.export_materials if parent else self.export_materials); a=menu.addAction('导出模板'); a.triggered.connect(parent.template if parent else self.template); self.resize(1000,600); self.t=QTableWidget(); self.t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.t.setEditTriggers(QAbstractItemView.NoEditTriggers); self.t.setColumnCount(11); self.t.setHorizontalHeaderLabels(['基础编码','版本号','名称','规格描述','单位','物料等级','制造商','MPN','M/P','是否存在BOM结构','是否为呆滞料']); self.t.setWordWrap(True); self.setCentralWidget(self.t); self.t.setContextMenuPolicy(Qt.CustomContextMenu); self.t.customContextMenuRequested.connect(self.menu); self.t.cellDoubleClicked.connect(self.edit_current)
  self._column_labels=[self.t.horizontalHeaderItem(i).text() for i in range(self.t.columnCount())]
  header=self.t.horizontalHeader(); header.setSectionsClickable(True); header.sectionClicked.connect(self.filter_menu); self.refresh()
 def search_materials(self):
  if not hasattr(self,'_search_dialog'):self._search_dialog=MaterialSearchDialog(self)
  self._search_dialog.show();self._search_dialog.raise_();self._search_dialog.activateWindow()
 def locate_material(self,material_id):
  self.refresh()
  for row in range(self.t.rowCount()):
   if self.t.item(row,0).data(Qt.UserRole)!=material_id:continue
   if self.t.isRowHidden(row):self._filters.clear();self.apply_filters()
   self.t.setCurrentCell(row,0);self.t.selectRow(row);self.t.scrollToItem(self.t.item(row,0),QAbstractItemView.PositionAtCenter)
   return True
  return False
 def filter_menu(self,column):
  menu=QMenu(self); choose=menu.addAction('筛选此列…'); clear=menu.addAction('清除此列筛选'); clear.setEnabled(column in self._filters); clear_all=menu.addAction('清除全部筛选'); clear_all.setEnabled(bool(self._filters))
  header=self.t.horizontalHeader(); from PyQt5.QtCore import QPoint
  action=menu.exec_(header.mapToGlobal(QPoint(header.sectionViewportPosition(column),header.height())))
  if action==choose:
   values=[self.t.item(row,column).text() for row in range(self.t.rowCount())]
   dialog=MaterialColumnFilterDialog(self._column_labels[column],values,self._filters.get(column),self)
   if dialog.exec_()==QDialog.Accepted:
    condition=dialog.condition()
    if condition==('',None):self._filters.pop(column,None)
    else:self._filters[column]=condition
    self.apply_filters()
  elif action==clear:self._filters.pop(column,None); self.apply_filters()
  elif action==clear_all:self._filters.clear(); self.apply_filters()
 def apply_filters(self):
  visible=0
  for row in range(self.t.rowCount()):
   match=True
   for column,(query,selected) in self._filters.items():
    value=self.t.item(row,column).text()
    if query.casefold() not in value.casefold() or (selected is not None and value not in selected):match=False; break
   self.t.setRowHidden(row,not match); visible+=int(match)
  for column,label in enumerate(self._column_labels):
   item=self.t.horizontalHeaderItem(column); item.setText(label+(' [筛选] ▾' if column in self._filters else ' ▾')); item.setToolTip('点击筛选；多列条件同时生效')
  self.statusBar().showMessage(f'显示 {visible} / {self.t.rowCount()} 个物料')
 def edit_current(self,row,column):
  rs=self.svc.materials();
  if row<0 or row>=len(rs): return
  r=rs[row]; dlg=MaterialDialog(self,{k:r[k] for k in ['base_code','version','name','description','unit','grade','manufacturer','mpn','mp_flag']},readonly_keys={'base_code','version'})
  if dlg.exec_():
   try:self.svc.update_material(r['id'],dlg.data()); self.refresh()
   except Exception as e: QMessageBox.warning(self,'保存失败',str(e))
 def menu(self,pos):
  row=self.t.rowAt(pos.y())
  if row<0:return
  material=self.svc.materials()[row]; rid=material['id']
  m=QMenu(self); e=m.addAction('编辑物料'); v=m.addAction('物料版本变更'); v.setEnabled(not any(sku['material_id']==rid for sku in self.svc.skus())); d=m.addAction('删除物料'); d.setEnabled(material['idle']=='Y')
  edit_bom=m.addAction('编辑物料BOM结构') if material['has_bom']=='Y' else None
  reverse=m.addAction('物料反查') if material['idle']=='N' else None
  copy=m.addAction('复制物料')
  a=m.exec_(self.t.viewport().mapToGlobal(pos))
  if a==copy:copy_material(self.svc,rid); return
  if a is None:return
  if edit_bom is not None and a==edit_bom:
   self.open_material_bom(rid); return
  if reverse is not None and a==reverse:
   MaterialUsageDialog(material,self.svc.material_usage(rid),self).exec_(); return
  if a==v and v.isEnabled():
   self.change_version(rid)
  elif a==e:
   r=self.svc.materials()[row]; dlg=MaterialDialog(self,{k:r[k] for k in ['base_code','version','name','description','unit','grade','manufacturer','mpn','mp_flag']},readonly_keys={'base_code','version'})
   if dlg.exec_(): self.svc.update_material(rid,dlg.data()); self.refresh()
  elif a==d and d.isEnabled() and QMessageBox.question(self,'确认','删除物料？')==QMessageBox.Yes:
   try:self.svc.delete_material(rid); self.refresh()
   except Exception as ex: QMessageBox.warning(self,'无法删除',str(ex))
 def open_material_bom(self,material_id):
  main=self.parent()
  while main is not None and not isinstance(main,MainWindow): main=main.parent()
  if main is not None:return main.open_material_bom(material_id)
  if material_id not in self._local_bom_windows:
   window=BomWindow(self.svc,material_id,self); self._local_bom_windows[material_id]=window
   window.closed.connect(lambda:self._local_bom_windows.pop(material_id,None))
  window=self._local_bom_windows[material_id]
  if window.isMinimized():window.showNormal()
  else:window.show()
  window.raise_(); window.activateWindow(); return window
 def change_version(self,material_id):
  if any(sku['material_id']==material_id for sku in self.svc.skus()):
   QMessageBox.information(self,'SKU版本变更','请在SKU窗口中进行版本变更。'); return
  try:
   references=self.svc.material_version_references(material_id)
   old=next(row for row in self.svc.materials() if row['id']==material_id)
   if references:
    dialog=MaterialVersionDialog(old,references,self)
    if dialog.exec_()!=QDialog.Accepted:return
    version=dialog.version.text(); selected=dialog.selected_parents()
   else:
    version,ok=QInputDialog.getText(self,'物料版本变更','新版本号',text=old['version'])
    if not ok:return
    selected=set()
   self.svc.change_material_version(material_id,version,selected,{r['parent_id'] for r in references})
   self.refresh()
   if self.parent() is not None and hasattr(self.parent(),'refresh'): self.parent().refresh()
  except Exception as error: QMessageBox.warning(self,'版本变更失败',str(error))
 def new_material(self):
  d=MaterialDialog(self)
  if d.exec_(): self.svc.create_material(d.data()); self.refresh()
 def import_materials(self):
  p=QFileDialog.getOpenFileName(self,'导入物料清单','','Excel (*.xlsx)')[0]
  if p:
   try:
    sheet_name=choose_material_sheet(p,self)
    config_service=self.svc.config_service or ConfigService(Path(self.svc.db.path).parent)
    try:ok,fail=self.svc.import_materials(p,sheet_name=sheet_name,header_mapping=config_service.import_mapping('materials') or None)
    except MaterialHeaderError as error:
     dialog=MaterialHeaderMappingDialog(p,error.headers,error.missing,self,sheet_name=sheet_name,config_service=config_service)
     if dialog.exec_()!=QDialog.Accepted:raise ValueError('用户取消表头映射，未导入任何物料')
     ok,fail=self.svc.import_materials(p,header_mapping=dialog.mapping(),sheet_name=sheet_name)
    self.refresh(); MaterialImportResultDialog(ok,fail,self).exec_()
   except Exception as error:QMessageBox.warning(self,'导入失败',str(error))
 def export_materials(self):
  p=QFileDialog.getSaveFileName(self,'导出物料库',export_start_path(export_filename((self.svc.project()['project_code']+' '+self.svc.project()['project_name']+' 物料库').strip())),'Excel (*.xlsx)')[0]
  if p:remember_export_path(p); self.svc.export_materials(p)
 def template(self):
  p=QFileDialog.getSaveFileName(self,'导出模板',export_start_path('物料模板.xlsx'),'Excel (*.xlsx)')[0]
  if p:
   remember_export_path(p)
   from openpyxl import Workbook; w=Workbook(); w.active.append(MATERIAL_IMPORT_HEADERS); w.save(p); w.close()
 def on_event(self,event):
  if event.get('type') in ('material_changed','bom_changed','sku_changed'): self.refresh()
 def closeEvent(self,event):
  for window in list(self._local_bom_windows.values()):
   if not window.close(): event.ignore(); return
  WindowRefreshBus.unsubscribe(self.on_event); self.closed.emit(); event.accept()
 def refresh(self):
  rs=self.svc.materials(); self.t.setRowCount(len(rs))
  for i,r in enumerate(rs):
   for j,v in enumerate([r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['grade'],r['manufacturer'],r['mpn'],r['mp_flag'],r['has_bom'],r['idle']]):
    item=QTableWidgetItem(str(v or '')); item.setData(Qt.UserRole,r['id'])
    if self._column_labels[j] in ('版本号','单位','M/P','是否存在BOM结构','是否为呆滞料'):item.setTextAlignment(Qt.AlignCenter)
    if r['idle']=='Y': item.setBackground(QColor('red')); item.setForeground(QColor('black'))
    self.t.setItem(i,j,item)
  self.apply_filters(); fit_columns(self.t)

class MaterialVersionDialog(QDialog):
 def __init__(self,material,references,parent=None):
  super().__init__(parent); self.setWindowTitle('物料版本变更'); self.resize(720,430)
  layout=QVBoxLayout(self)
  label=QLabel(f"{material['base_code']}{material['version']} {material['name']}"); label.setWordWrap(True); layout.addWidget(label)
  form=QFormLayout(); self.version=QLineEdit(material['version']); form.addRow('新版本号',self.version); layout.addLayout(form)
  text=QLabel('该物料被如下BOM所使用，请勾选需要同步使用新版本的BOM。'); text.setWordWrap(True); layout.addWidget(text)
  self.references=QTreeWidget(); self.references.setHeaderLabels(['','SKU','父项物料']); self.references.setRootIsDecorated(False); self.references.setWordWrap(True)
  for reference in references:
   item=QTreeWidgetItem(self.references,['','\n'.join(reference['sku_labels']),reference['parent_label']]); item.setData(0,Qt.UserRole,reference['parent_id']); item.setCheckState(0,Qt.Checked)
  fit_columns(self.references); self.references.header().setSectionResizeMode(0,QHeaderView.Fixed); self.references.setColumnWidth(0,40); layout.addWidget(self.references)
  self.note=QLabel('同一父级BOM由多个SKU共享时统一更新，下方列出全部受影响SKU。\n全部勾选直接修改原物料；部分或全部不勾选则保留旧物料并创建新版本。')
  self.note.setWordWrap(True); self.note.setAlignment(Qt.AlignLeft|Qt.AlignBottom)
  font=self.note.font(); font.setPointSizeF(max(7.0,font.pointSizeF()-2)); self.note.setFont(font); layout.addWidget(self.note)
  buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
 def selected_parents(self):
  return {self.references.topLevelItem(n).data(0,Qt.UserRole) for n in range(self.references.topLevelItemCount()) if self.references.topLevelItem(n).checkState(0)==Qt.Checked}
 def accept(self):
  if not self.version.text().strip(): QMessageBox.warning(self,'版本号无效','版本号不能为空'); return
  super().accept()

class MaterialUsageDialog(QDialog):
 def __init__(self,material,usages,parent=None):
  super().__init__(parent); self.material_id=material['id']; self.usages=usages; self.setWindowTitle('物料反查'); self.resize(720,430)
  layout=QVBoxLayout(self); title=QLabel(f"{material['base_code']}{material['version']} {material['name']}"); title.setWordWrap(True); layout.addWidget(title)
  self.table=QTableWidget(len(usages),1); self.table.setHorizontalHeaderLabels(['包含此物料的SKU / 父级物料']); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setWordWrap(True)
  for index,usage in enumerate(usages):
   item=QTableWidgetItem(f"SKU：{usage['sku']}\n父级物料：{usage['parent']}"); item.setData(Qt.UserRole,usage.get('sku_id')); self.table.setItem(index,0,item)
  self.table.cellDoubleClicked.connect(self.open_sku); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
  fit_columns(self.table); layout.addWidget(self.table)
  buttons=QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
 def open_sku(self,row,column=0):
  item=self.table.item(row,0)
  if item is None:return
  sku_id=item.data(Qt.UserRole)
  if sku_id is None:
   QMessageBox.information(self,'无对应SKU','此引用属于独立BOM，未包含在任何SKU中。'); return
  main=self.parent()
  while main is not None and not isinstance(main,MainWindow): main=main.parent()
  if main is None:return
  if main.svc.db.conn.execute('SELECT 1 FROM skus WHERE id=?',(sku_id,)).fetchone() is None:
   QMessageBox.information(self,'SKU不存在','该SKU已删除，请重新进行物料反查。'); return
  self.accept()  # 先结束模态反查，避免目标BOM被反查弹窗阻挡。
  window=main.open_bom_id(sku_id)
  if window is not None:window.locate_material(self.material_id,self.usages[row].get('parent_id'))
 def resizeEvent(self,event):
  super().resizeEvent(event)
  self.table.resizeRowsToContents()

class ProjectDialog(QDialog):
 def __init__(self,parent=None,row=None):
  super().__init__(parent); self.setWindowTitle('修改项目信息'); f=QFormLayout(self); self.e={}
  for k,l in [('project_name','项目名称'),('project_code','项目代码'),('product_name','产品名称'),('product_model','产品型号')]:
   try: value=row[k] if row is not None else ''
   except (KeyError,IndexError,TypeError): value=''
   w=QLineEdit(str(value or '')); self.e[k]=w; f.addRow(l,w)
  b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)
 def data(self): return {k:w.text().strip() for k,w in self.e.items()}
