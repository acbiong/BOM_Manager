"""PyQt主窗口、SKU清单、物料库和BOM编辑窗口。输入服务对象，输出桌面交互。编辑时间：2026-09-24。"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QEvent, QSize
from PyQt5.QtGui import QColor, QBrush, QFont
from pathlib import Path
from config.config_service import ConfigService
from database.database import Database
from infrastructure.events import WindowRefreshBus
from services.services import MaterialHeaderError

class QuantityEdit(QDoubleSpinBox):
 def __init__(self):
  super().__init__(); self.setDecimals(1); self.setRange(0.1,1e12); self.setSingleStep(0.1); self.setValue(1.0)
 def setText(self,value):
  self.setValue(float(value or 1.0))
 def text(self):
  return f'{self.value():.1f}'

def fit_columns(widget):
 """按内容自适应列宽，限制在5~25个中文字符，并启用换行。"""
 widget.setWordWrap(True)
 header=widget.header() if hasattr(widget,'header') else widget.horizontalHeader()
 char_width=max(widget.fontMetrics().horizontalAdvance('中'),1)
 minimum=5*char_width; maximum=25*char_width
 header.setStretchLastSection(False)
 for i in range(header.count()):
  if hasattr(widget,'isColumnHidden') and widget.isColumnHidden(i): continue
  header.setSectionResizeMode(i,QHeaderView.ResizeToContents)
  width=max(minimum,min(maximum,header.sectionSize(i)))
  header.setSectionResizeMode(i,QHeaderView.Interactive)
  header.resizeSection(i,width)
 if hasattr(widget,'resizeRowsToContents'): widget.resizeRowsToContents()
class MaterialDialog(QDialog):
 def __init__(self,parent=None,data=None,readonly_keys=None):
  super().__init__(parent); self.setWindowTitle('物料'); f=QFormLayout(self); data=data or {}; self.e={}; readonly_keys=readonly_keys or set()
  for k,l in [('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料规格描述'),('manufacturer','物料制造商'),('mpn','物料MPN')]:
   if k in readonly_keys: w=QLabel(str(data.get(k,'')))
   else: w=QLineEdit(str(data.get(k,'')))
   self.e[k]=w; f.addRow(l,w)
  self.unit=QComboBox(); self.unit.addItems(['pcs','套','ml','L','mm','cm','m']); self.unit.setCurrentText(data.get('unit','pcs')); self.unit.setEnabled('unit' not in readonly_keys); f.addRow('单位',self.unit)
  self.mp_flag=QComboBox(); self.mp_flag.addItems(['M','P']); self.mp_flag.setCurrentText(data.get('mp_flag','M')); self.mp_flag.setEnabled('mp_flag' not in readonly_keys); f.addRow('M/P',self.mp_flag)
  b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)
 def data(self):
  d={k:w.text().strip() for k,w in self.e.items()}; d['unit']=self.unit.currentText(); d['mp_flag']=self.mp_flag.currentText(); return d
class MaterialHeaderMappingDialog(QDialog):
 def __init__(self,path,headers,missing,parent=None):
  super().__init__(parent); self.setWindowTitle('物料表头映射'); self.resize(1000,620); self.required=['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN']; self.combos={}
  layout=QVBoxLayout(self); layout.addWidget(QLabel('未能自动识别全部表头，请为每个需求字段选择文件中的对应列：'))
  self.mapping_table=QTableWidget(2,len(self.required)); self.mapping_table.setVerticalHeaderLabels(['需求表头','目标表头']); self.mapping_table.horizontalHeader().hide(); self.mapping_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
  for column,need in enumerate(self.required):
   item=QTableWidgetItem(need); item.setTextAlignment(Qt.AlignCenter); self.mapping_table.setItem(0,column,item)
   combo=QComboBox(); combo.setSizeAdjustPolicy(QComboBox.AdjustToContents); combo.addItem('（未映射）',''); combo.addItems(headers)
   if need not in missing and need in headers: combo.setCurrentText(need)
   self.combos[need]=combo; self.mapping_table.setCellWidget(1,column,combo)
   combo.currentTextChanged.connect(self.schedule_mapping_fit)
   combo.installEventFilter(self)
  self.mapping_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
  layout.addWidget(self.mapping_table)
  layout.addWidget(QLabel('文件读取预览（前20行）：'))
  self.preview=QTableWidget(); self.preview.setColumnCount(len(headers)); self.preview.setHorizontalHeaderLabels(headers); self.preview.setWordWrap(True)
  try:
   from openpyxl import load_workbook
   ws=load_workbook(path,read_only=True,data_only=True).active; rows=list(ws.iter_rows(min_row=2,max_row=21,values_only=True)); self.preview.setRowCount(len(rows))
   for r,row in enumerate(rows):
    for c in range(len(headers)): self.preview.setItem(r,c,QTableWidgetItem(str(row[c] or '') if c<len(row) else ''))
  except Exception as error: self.preview.setRowCount(1); self.preview.setItem(0,0,QTableWidgetItem('预览失败：'+str(error)))
  layout.addWidget(self.preview,1); fit_columns(self.preview)
  self._mapping_fit_timer=QTimer(self); self._mapping_fit_timer.setSingleShot(True); self._mapping_fit_timer.timeout.connect(self.fit_mapping_columns)
  self.mapping_table.viewport().installEventFilter(self); self.mapping_table.installEventFilter(self)
  self.fit_mapping_columns()
  self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
  buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.validate_mapping); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
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
   text_width=max(metrics.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))
   option=QStyleOptionComboBox(); combo.initStyleOption(option)
   size=combo.style().sizeFromContents(QStyle.CT_ComboBox,option,QSize(text_width+16,metrics.height()+12),combo)
   width=max(size.width(),combo.sizeHint().width(),table.fontMetrics().horizontalAdvance(need)+24)
   height=max(size.height(),combo.sizeHint().height(),metrics.height()+16)
   # 样式可能额外占用内边距；按实际文字绘制区域补足，避免主题或缩放后被截断。
   option.rect.setRect(0,0,width,height)
   field=combo.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxEditField,combo)
   width+=max(0,text_width+12-field.width()); height+=max(0,metrics.height()+8-field.height())
   widths.append(width+4); heights.append(height+4)
  table.verticalHeader().setFixedWidth(max(table.verticalHeader().fontMetrics().horizontalAdvance(x) for x in ('需求表头','目标表头'))+24)
  extra=max(0,table.viewport().width()-sum(widths))
  table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
  for column,width in enumerate(widths):table.setColumnWidth(column,width+extra//len(widths)+(column<extra%len(widths)))
  # 不使用ResizeToContents覆盖组合框行高；需求行、目标行都按当前字体和主题计算。
  table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
  table.setRowHeight(0,table.fontMetrics().height()+20); table.setRowHeight(1,max(heights))
  table.setFixedHeight(table.rowHeight(0)+table.rowHeight(1)+table.horizontalScrollBar().sizeHint().height()+2*table.frameWidth()+4)
 def mapping(self): return {need:self.combos[need].currentText().strip() if self.combos[need].currentIndex()>0 else '' for need in self.required}
 def validate_mapping(self):
  values=self.mapping(); missing=[x for x in self.required if not values.get(x)]
  duplicates={x for x in values.values() if x and list(values.values()).count(x)>1}
  if missing or duplicates:
   detail=[]
   if missing: detail.append('未映射：'+ '、'.join(missing))
   if duplicates: detail.append('重复映射：'+ '、'.join(sorted(duplicates)))
   QMessageBox.warning(self,'表头映射错误','；'.join(detail)+'。请继续修改映射关系。'); return
  self.accept()
class MaterialImportResultDialog(QDialog):
 def __init__(self,ok,fail,parent=None):
  super().__init__(parent); self.setWindowTitle('物料导入结果')
  available=self.screen().availableGeometry(); self.setMaximumHeight(min(640,int(available.height()*0.85))); self.resize(min(900,int(available.width()*0.9)),min(560,self.maximumHeight()))
  layout=QVBoxLayout(self); duplicates=sum('重复物料' in row[3] for row in fail)
  summary=QLabel(f'成功导入：{len(ok)}条    失败/未导入：{len(fail)}条    其中重复未导入：{duplicates}条'); summary.setWordWrap(True); layout.addWidget(summary)
  self.details=QTextBrowser(); self.details.setOpenExternalLinks(False); self.details.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded); self.details.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.details.setLineWrapMode(QTextEdit.WidgetWidth)
  self.details.setPlainText('\n\n'.join(f'第{row}行：{code or "（空编码）"} {name or "（空名称）"}\n原因：{reason}' for row,code,name,reason in fail) or '全部物料导入成功，无失败或跳过条目。')
  layout.addWidget(self.details,1)
  buttons=QDialogButtonBox(QDialogButtonBox.Ok); buttons.accepted.connect(self.accept); layout.addWidget(buttons)

class MainWindow(QMainWindow):
 def __init__(self,svc,version='0.0.1'):
  super().__init__(); self.svc=svc; self._bom_windows={}; self._material_bom_windows={}; self._materials=None; self.setWindowTitle('BOM管理系统'); self.resize(1100,700); self.version=version; self.build()
 def build(self):
  bar=self.menuBar(); fm=bar.addMenu('文件'); a=fm.addAction('选择SQLite数据库'); a.triggered.connect(self.select_database); a=fm.addAction('导出资料库'); a.triggered.connect(self.export_database); a=bar.addAction('物料库'); a.triggered.connect(self.show_materials); pm=bar.addMenu('项目'); a=pm.addAction('修改项目信息'); a.triggered.connect(self.edit_project); a=bar.addAction('新建SKU'); a.triggered.connect(self.new_sku)
  self.table=QTableWidget(); self.table.setColumnCount(6); self.table.setHorizontalHeaderLabels(['打开','SKU编码','SKU名称','SKU描述','修改日期时间','ID']); self.table.hideColumn(5); self.table.setWordWrap(True); self.table.cellDoubleClicked.connect(self.open_bom); self.table.setContextMenuPolicy(Qt.CustomContextMenu); self.table.customContextMenuRequested.connect(self.sku_context_menu)
  self.project_label=QLabel(); self.project_label.setAlignment(Qt.AlignCenter); self.project_label.setStyleSheet('font-size:18px;font-weight:bold;padding:8px;')
  body=QWidget(); layout=QVBoxLayout(body); layout.addWidget(self.project_label); layout.addWidget(self.table); self.setCentralWidget(body)
  self.power_label=QLabel('Power by Biong'); self.version_label=QLabel('版本 '+self.version); self.statusBar().addPermanentWidget(self.power_label); self.statusBar().addPermanentWidget(self.version_label); self.statusBar().showMessage(''); self.refresh()
 def refresh(self):
  project=self.svc.project(); self.project_label.setText(project['project_name'] or '请输入项目名称')
  rows=self.svc.skus(); self.table.setRowCount(len(rows));
  for i,r in enumerate(rows):
   btn=QPushButton('打开'); btn.clicked.connect(lambda _,sid=r['id']: self.open_bom_id(sid)); self.table.setCellWidget(i,0,btn); self.table.setItem(i,1,QTableWidgetItem(r['base_code']+'-'+r['version'])); self.table.setItem(i,2,QTableWidgetItem(r['name'])); self.table.setItem(i,3,QTableWidgetItem(r['description'])); self.table.setItem(i,4,QTableWidgetItem(r['updated_at'] or '')); self.table.setItem(i,5,QTableWidgetItem(str(r['id'])))
  fit_columns(self.table)
  self.statusBar().showMessage(f'共计{len(rows)}个SKU')
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
  selected.parent.mkdir(parents=True,exist_ok=True)
  existed=selected.exists()
  if selected.resolve() == current.resolve():
   QMessageBox.information(self,'数据库未切换','当前已经在使用该数据库：\n'+str(selected)); return
  try:
   # sqlite3.connect 对已有数据库是打开，对不存在的数据库才是创建，不会覆盖原文件。
   new_db=Database(str(selected))
   valid,missing=new_db.validate_schema()
   if not valid:
    new_db.close()
    raise ValueError('数据库结构不可用，缺少表：'+', '.join(missing))
   for window in list(self._material_bom_windows.values()):
    if not window.close(): new_db.close(); return
   if self._materials is not None: self._materials.close()
   old_db=self.svc.db
   self.svc.db=new_db
   old_db.close()
   c=ConfigService().load(); c['database']['path']=str(selected); ConfigService().save(c)
   self.refresh()
   QMessageBox.information(self,'数据库已切换',('已打开已有数据库' if existed else '已创建并打开新数据库')+'：\n'+str(selected))
  except Exception as exc:
   QMessageBox.critical(self,'数据库错误','目标数据库无法使用，请重新选择数据库。\n\n'+str(exc))
 def export_database(self):
  p=QFileDialog.getSaveFileName(self,'导出资料库','资料库.xlsx','Excel (*.xlsx)')[0]
  if p:self.svc.export_database(p); QMessageBox.information(self,'完成','资料库导出成功')
 def edit_project(self):
  d=ProjectDialog(self,self.svc.project())
  if d.exec_(): self.svc.update_project(d.data()); self.setWindowTitle(d.data().get('project_name') or 'BOM管理系统'); self.refresh()
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
  cfg=ConfigService(Path(self.svc.db.path).parent).load(); last=cfg['database'].get('last_import_dir',str(Path.home()/'Desktop')); last=last if Path(last).is_dir() else str(Path.home()/'Desktop')
  p=QFileDialog.getOpenFileName(self,'导入物料清单',last,'Excel (*.xlsx)')[0]
  if p:
    cfg['database']['last_import_dir']=str(Path(p).parent); ConfigService(Path(self.svc.db.path).parent).save(cfg)
    def resolver(d,old):
     box=QMessageBox(self); box.setWindowTitle('发现重复物料'); box.setText(f"物料 {d['物料基础编码']}-{d['物料版本号']}（{d['物料名称']}）已存在，是否覆盖？"); cover=box.addButton('覆盖',QMessageBox.AcceptRole); skip=box.addButton('跳过',QMessageBox.DestructiveRole); cancel=box.addButton('取消全部',QMessageBox.RejectRole); box.exec_(); return 'overwrite' if box.clickedButton()==cover else ('skip' if box.clickedButton()==skip else 'cancel')
    progress=QProgressDialog('正在导入物料，请稍候…','取消',0,100,self); progress.setWindowTitle('导入物料'); progress.setWindowModality(Qt.WindowModal); progress.setAutoClose(False); progress.show(); QApplication.processEvents()
    def update_progress(current,total):
     progress.setMaximum(max(total,1)); progress.setValue(min(current,total)); QApplication.processEvents()
    try:
     try: ok,fail=self.svc.import_materials(p,resolver,progress_callback=update_progress)
     except MaterialHeaderError as header_error:
      progress.close()
      mapping_dialog=MaterialHeaderMappingDialog(p,header_error.headers,header_error.missing,self)
      if mapping_dialog.exec_()!=QDialog.Accepted:
       progress.close(); QMessageBox.warning(self,'导入失败','用户取消表头映射：未完成必需表头对应关系。'); return
      progress=QProgressDialog('正在导入物料，请稍候…','取消',0,100,self); progress.setWindowTitle('导入物料'); progress.setWindowModality(Qt.WindowModal); progress.setAutoClose(False); progress.show(); QApplication.processEvents()
      ok,fail=self.svc.import_materials(p,resolver,mapping_dialog.mapping(),update_progress)
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
  rows=self.svc.materials(); items=[f"{r['base_code']} {r['version']} {r['name']}" for r in rows]; x,ok=QInputDialog.getItem(self,'新建SKU','选择物料',items,0,False)
  if ok:
   try: mid=rows[items.index(x)]['id']; sid=self.svc.create_sku(mid); self.refresh(); self.open_bom_id(sid)
   except Exception as e: QMessageBox.warning(self,'失败',str(e))
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
  menu=QMenu(self); version=menu.addAction('版本变更'); delete=menu.addAction('删除SKU')
  action=menu.exec_(self.table.viewport().mapToGlobal(pos))
  if action==version:self.change_sku_version(sid)
  elif action==delete:self.delete_sku(sid)
 def open_bom(self,row,col): self.open_bom_id(int(self.table.item(row,5).text()))
 def open_bom_id(self,sid):
  row=self.svc.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone()
  if row is None:return
  window=self.open_material_bom(row['material_id'])
  if window is not None:self._bom_windows[sid]=window
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
  p=QFileDialog.getSaveFileName(self,'导出物料库','物料库.xlsx','Excel (*.xlsx)')[0]
  if p:self.svc.export_materials(p); QMessageBox.information(self,'完成','导出成功')
 def template(self):
  p=QFileDialog.getSaveFileName(self,'导出模板','物料模板.xlsx','Excel (*.xlsx)')[0]
  if p:
   from openpyxl import Workbook; w=Workbook(); w.active.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN']); w.save(p)
class BomWindow(QMainWindow):
 closed=pyqtSignal()
 def __init__(self,svc,root,parent=None):
  super().__init__(parent); self.setAttribute(Qt.WA_DeleteOnClose); self.svc=svc; self.root=root; self.current_item=None; self._deleted_relations=set(); self._alternate_edits={}; self._external_paths=set(); self._draft_baselines={}; self._loading_fields=False; self._saving=False; self.notice=QLabel(''); self.notice.setStyleSheet('color:red'); WindowRefreshBus.subscribe(self.on_external_change); self.setWindowTitle('BOM管理'); self.resize(1200,700); self.dirty=False
  self.tree=QTreeWidget(); self.tree.itemClicked.connect(self.show_item_info); self.tree.setWordWrap(True); self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.context_menu); self.tree.setHeaderLabels(['物料编码/名称','数量','单位','位置','备注']); self.tree.setMinimumWidth(420)
  self.fields={}; form=QFormLayout();
  for k,l in [('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料描述'),('quantity','物料数量'),('unit','物料单位'),('position','物料位置'),('manufacturer','物料制造商'),('mpn','物料MPN'),('mp_flag','M/P'),('remark','备注')]:
   w=QuantityEdit() if k=='quantity' else (QLineEdit() if k in ('position','remark') else QLabel()); self.fields[k]=w; form.addRow(l,w)
  self.fields['quantity'].valueChanged.connect(lambda value:self.update_tree_field('quantity',value))
  for key in ('position','remark'): self.fields[key].textChanged.connect(lambda value,k=key:self.update_tree_field(k,value))
  info_box=QGroupBox('物料信息'); info_box.setLayout(form); self.alt_table=QTableWidget(0,6); self.alt_table.setHorizontalHeaderLabels(['替代料编码','版本号','名称','描述','制造商','MPN']); self.alt_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.alt_table.setContextMenuPolicy(Qt.CustomContextMenu); self.alt_table.customContextMenuRequested.connect(self.alternate_menu); alt_box=QGroupBox('替代料'); alt_l=QVBoxLayout(alt_box); alt_l.addWidget(self.alt_table)
  right=QWidget(); right_l=QVBoxLayout(right); right_l.addWidget(info_box); right_l.addWidget(alt_box); spl=QSplitter(); spl.addWidget(self.tree); spl.addWidget(right); spl.setStretchFactor(1,1); box=QWidget(); lay=QVBoxLayout(box); lay.addWidget(spl); self.setCentralWidget(box); self.statusBar().addWidget(self.notice); tb=self.addToolBar('BOM'); self.save_action=QAction('保存',self); self.save_action.triggered.connect(self.save); self.save_action.setEnabled(False); tb.addAction(self.save_action); self.refresh_action=QAction('刷新',self); self.refresh_action.triggered.connect(self.refresh_external); self.refresh_action.setEnabled(False); tb.addAction(self.refresh_action); imp=QAction('导入BOM',self); imp.triggered.connect(self.import_bom); tb.addAction(imp); exp=QAction('导出SKU BOM',self); exp.triggered.connect(self.export_bom); tb.addAction(exp); self.load()
 def mark_dirty(self):
  self.dirty=True
  self.save_action.setEnabled(True)
  self.refresh_styles()
 def on_external_change(self,event):
  if self._saving: return
  if event.get('type') in ('bom_changed','material_changed') and self.contains_material(event.get('root') if event.get('type')=='bom_changed' else event.get('id')):
   self.notice.setText('BOM有更新，请点击刷新或重新打开窗口'); self.refresh_action.setEnabled(True); self.statusBar().clearMessage()
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
   m=QMenu(self); child=m.addAction('增加子级物料'); act=m.exec_(self.tree.viewport().mapToGlobal(pos))
   if act==child: self.add_relative(d,True)
   return
  m=QMenu(self); same=m.addAction('新增同级物料'); child=m.addAction('新增子级物料'); dele=m.addAction('删除物料'); alternate=m.addAction('增加替代料'); act=m.exec_(self.tree.viewport().mapToGlobal(pos))
  if act==alternate:
   self.tree.setCurrentItem(it); self.show_item_info(it); self.add_alternate(); return
  if act in (same,child): self.add_relative(d, act==child); return
  if act==dele and QMessageBox.question(self,'确认','删除当前BOM物料？')==QMessageBox.Yes:
   self.remove_relation(it)
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
     for field in ('base_code','version','name','description','unit','manufacturer','mpn','mp_flag'):fresh['data'][field]=material[field]
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
   if data.get('_deleted') or (data.get('_added') and not previous.get('_added')):return True
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
  return merged
 def refresh_external(self):
  from copy import deepcopy
  fresh=self.database_tree(); conflicts=[]
  root=dict(self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone())
  if any(root.get(k)!=self._root_baseline.get(k) for k in ('base_code','version','name','description','unit','manufacturer','mpn','mp_flag')):self._external_paths.add(())
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
  self.notice.setText(''); self.statusBar().clearMessage(); self.refresh_action.setEnabled(False); self.save_action.setEnabled(self.dirty or bool(self._external_paths)); self.refresh_styles()
  if conflicts:self.statusBar().showMessage('已加载外部更新；检测到冲突，已保留本地未保存修改，请核对后保存。')
 def load(self,preserve=None):
  from copy import deepcopy
  fresh=self.database_tree(); self.render_tree(fresh); self._baseline_tree=deepcopy(fresh); self._root_baseline=dict(self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone()); self._external_paths.clear(); self._draft_baselines.clear(); self.refresh_styles()
  self.save_action.setEnabled(False); self.refresh_action.setEnabled(False)
 def render_tree(self,nodes):
  self.current_item=None; self.tree.clear(); self.by={}; root=self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone()
  self.setWindowTitle(f"{root['base_code']}-{root['version']} {root['name']}")
  self.root_item=QTreeWidgetItem(self.tree,[f"{root['base_code']}-{root['version']} {root['name']}",'','','','']); self.root_item.setData(0,Qt.UserRole,{'material_id':self.root,'root':True}); self.root_item.setExpanded(True)
  def append(node,parent,path,level):
   data=dict(node['data']); data.setdefault('_edit_base',{k:data.get(k) for k in ('quantity','position','remark')}); parent_data=parent.data(0,Qt.UserRole) or {}
   node_id=f"{path}/{data['id']}"
   data.update(node_id=node_id,parent_node_id=path or None,parent_material_id=parent_data['material_id'],parent_item_id=parent_data.get('id'),level_no=level)
   item=QTreeWidgetItem(parent,[f"{data['base_code']}-{data['version']} {data['name']}",f"{data['quantity']:.1f}",data['unit'],data.get('position',''),data.get('remark','')]); item.setData(0,Qt.UserRole,data); self.by[node_id]=item
   for child in node['children']:append(child,item,node_id,level+1)
  for node in nodes:append(node,self.root_item,'',1)
  fit_columns(self.tree); self.tree.setCurrentItem(self.root_item); self.show_item_info(self.root_item)
 def snapshot_map(self,nodes,path=()):
  result={}
  for node in nodes:
   key=path+(node['data']['material_id'],); result[key]=node
   result.update(self.snapshot_map(node['children'],key))
  return result
 def remote_signature(self,node):
  fields=('material_id','quantity','position','remark','base_code','version','name','description','unit','manufacturer','mpn','mp_flag','_db_alternates')
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
    font=QFont(self.tree.font()); font.setStrikeOut(bool(deleted)); font.setBold(column in changed and not deleted)
    item.setFont(column,font)
    color=QColor('red') if deleted else QColor('green') if added else QColor('yellow') if changed else None
    item.setForeground(column,QBrush(color) if color else QBrush(QColor('white')) if external else QBrush())
    item.setBackground(column,QBrush(QColor('#4a148c')) if external else QBrush())
   remark=data.get('remark','') if not root else ''
   display=remark
   if external:display=(remark+'\n' if remark else '')+'有其他BOM更新导入此变更'
   item.setText(4,display); item.setToolTip(4,remark)
   for n in range(item.childCount()):style(item.child(n),path,added,deleted,external)
  style(self.root_item,())
  fit_columns(self.tree)
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
  rows=[r for r in self.svc.materials() if r['id'] not in blocked]; items=[f"{r['base_code']} {r['version']} {r['name']}" for r in rows]
  if not items: QMessageBox.information(self,'提示','当前父级下已没有可新增的物料'); return
  x,ok=QInputDialog.getItem(self,'新建BOM物料','物料',items,0,False)
  if not ok:return
  r=rows[items.index(x)]; self._deleted_relations.discard(((target.data(0,Qt.UserRole) or {}).get('material_id'),r['id'],'')); item=QTreeWidgetItem(target,[f"{r['base_code']}-{r['version']} {r['name']}",'1.0',r['unit'],'','']); temporary_id=-id(item); data={'_added':True,'id':temporary_id,'material_id':r['id'],'base_code':r['base_code'],'version':r['version'],'name':r['name'],'description':r['description'],'quantity':1,'unit':r['unit'],'position':'','manufacturer':r['manufacturer'],'mpn':r['mpn'],'mp_flag':r['mp_flag'],'remark':'','level_no':(parent.get('level_no') or 1)+(1 if child else 0),'parent_item_id':parent.get('id') if child else parent.get('parent_item_id')}; data.update(node_id=str(temporary_id),parent_node_id=(target.data(0,Qt.UserRole) or {}).get('node_id')); item.setData(0,Qt.UserRole,data); self.by[str(temporary_id)]=item; target.setExpanded(True); fit_columns(self.tree); self.mark_dirty(); self.tree.setCurrentItem(item); self.show_item_info(item)
  self.add_existing_children(item,r['id'],set())
  self._draft_baselines[temporary_id]=self.capture_item(item)
  fit_columns(self.tree); self.mark_dirty(); self.tree.setCurrentItem(item); self.show_item_info(item)
 def add_existing_children(self,parent_item,material_id,ancestors):
  if material_id in ancestors:return
  ancestors=set(ancestors); ancestors.add(material_id)
  rows=self.svc.db.conn.execute('SELECT b.*,m.base_code,m.version,m.name,m.description,m.unit AS material_unit,m.manufacturer,m.mpn,m.mp_flag FROM material_bom_items b JOIN materials m ON m.id=b.child_material_id WHERE b.parent_material_id=? ORDER BY b.sort_no,b.id',(material_id,)).fetchall()
  parent_data=parent_item.data(0,Qt.UserRole) or {}
  for row in rows:
   if row['child_material_id'] in ancestors:continue
   child=QTreeWidgetItem(parent_item,[f"{row['base_code']}-{row['version']} {row['name']}",f"{row['quantity']:.1f}",row['material_unit'],row['position'],row['remark']]); d=dict(row); d['_added']=parent_data.get('_added',False); d['_db_alternates']=[a['material_id'] for a in self.svc.alternates(row['id'])]; d.update({'material_id':row['child_material_id'],'unit':row['material_unit'],'parent_item_id':parent_data.get('id'),'level_no':(parent_data.get('level_no') or 0)+1}); d.update(node_id=f"{parent_data.get('node_id')}/{row['id']}",parent_node_id=parent_data.get('node_id')); child.setData(0,Qt.UserRole,d); self.by[d['node_id']]=child; self.add_existing_children(child,row['child_material_id'],ancestors)
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
  choices=[f"{row['base_code']}-{row['version']} {row['name']}" for row in rows]
  choice,ok=QInputDialog.getItem(self,'增加替代料','选择物料',choices,0,False)
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
 def import_bom(self):
  p=QFileDialog.getOpenFileName(self,'导入BOM','','Excel (*.xlsx)')[0]
  if p:
   try: n=self.svc.import_bom(p,self.root); self.load(); QMessageBox.information(self,'完成',f'导入{n}行')
   except Exception as e: QMessageBox.warning(self,'导入失败',str(e))
 def export_bom(self):
  p=QFileDialog.getSaveFileName(self,'导出BOM','SKU_BOM.xlsx','Excel (*.xlsx)')[0]
  if p:
   r=self.svc.db.conn.execute('SELECT id FROM skus WHERE material_id=?',(self.root,)).fetchone()
   if r:self.svc.export_sku(r['id'],p); QMessageBox.information(self,'完成','导出成功')
 def add(self):
  self.add_relative({'id':None,'parent_item_id':None,'level_no':0},False)
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
  self.dirty=False; self._deleted_relations.clear(); self._alternate_edits.clear(); self.load(); self.notice.setText(''); self.statusBar().clearMessage(); self.save_action.setEnabled(False); self.refresh_action.setEnabled(False)
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
  menu=self.menuBar(); a=menu.addAction('新建物料'); a.triggered.connect(parent.new_material if parent else self.new_material); a=menu.addAction('导入物料'); a.triggered.connect(parent.import_materials if parent else self.import_materials); a=menu.addAction('导出物料库'); a.triggered.connect(parent.export_materials if parent else self.export_materials); a=menu.addAction('导出模板'); a.triggered.connect(parent.template if parent else self.template); self.resize(1000,600); self.t=QTableWidget(); self.t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.t.setEditTriggers(QAbstractItemView.NoEditTriggers); self.t.setColumnCount(10); self.t.setHorizontalHeaderLabels(['基础编码','版本号','名称','规格描述','单位','制造商','MPN','M/P','是否存在BOM结构','是否为呆滞料']); self.t.setWordWrap(True); self.setCentralWidget(self.t); self.t.setContextMenuPolicy(Qt.CustomContextMenu); self.t.customContextMenuRequested.connect(self.menu); self.t.cellDoubleClicked.connect(self.edit_current)
  self._column_labels=[self.t.horizontalHeaderItem(i).text() for i in range(self.t.columnCount())]
  header=self.t.horizontalHeader(); header.setSectionsClickable(True); header.sectionClicked.connect(self.filter_menu); self.refresh()
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
  r=rs[row]; dlg=MaterialDialog(self,{k:r[k] for k in ['base_code','version','name','description','unit','manufacturer','mpn','mp_flag']},readonly_keys={'base_code','version'})
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
  a=m.exec_(self.t.viewport().mapToGlobal(pos))
  if a is None:return
  if edit_bom is not None and a==edit_bom:
   self.open_material_bom(rid); return
  if reverse is not None and a==reverse:
   MaterialUsageDialog(material,self.svc.material_usage(rid),self).exec_(); return
  if a==v and v.isEnabled():
   self.change_version(rid)
  elif a==e:
   r=self.svc.materials()[row]; dlg=MaterialDialog(self,{k:r[k] for k in ['base_code','version','name','description','unit','manufacturer','mpn','mp_flag']},readonly_keys={'base_code','version'})
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
  if p: self.svc.import_materials(p); self.refresh()
 def export_materials(self):
  p=QFileDialog.getSaveFileName(self,'导出物料库','物料库.xlsx','Excel (*.xlsx)')[0]
  if p:self.svc.export_materials(p)
 def template(self):
  p=QFileDialog.getSaveFileName(self,'导出模板','物料模板.xlsx','Excel (*.xlsx)')[0]
  if p:
   from openpyxl import Workbook; w=Workbook(); w.active.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN']); w.save(p)
 def on_event(self,event):
  if event.get('type') in ('material_changed','bom_changed','sku_changed'): self.refresh()
 def closeEvent(self,event):
  for window in list(self._local_bom_windows.values()):
   if not window.close(): event.ignore(); return
  WindowRefreshBus.unsubscribe(self.on_event); self.closed.emit(); event.accept()
 def refresh(self):
  rs=self.svc.materials(); self.t.setRowCount(len(rs))
  for i,r in enumerate(rs):
   for j,v in enumerate([r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag'],r['has_bom'],r['idle']]):
    item=QTableWidgetItem(str(v or ''))
    if r['idle']=='Y': item.setBackground(QColor('red')); item.setForeground(QColor('black'))
    self.t.setItem(i,j,item)
  self.apply_filters(); fit_columns(self.t)

class MaterialVersionDialog(QDialog):
 def __init__(self,material,references,parent=None):
  super().__init__(parent); self.setWindowTitle('物料版本变更'); self.resize(720,430)
  layout=QVBoxLayout(self)
  label=QLabel(f"{material['base_code']}-{material['version']} {material['name']}"); label.setWordWrap(True); layout.addWidget(label)
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
  super().__init__(parent); self.setWindowTitle('物料反查'); self.resize(720,430)
  layout=QVBoxLayout(self); title=QLabel(f"{material['base_code']}-{material['version']} {material['name']}"); title.setWordWrap(True); layout.addWidget(title)
  self.table=QTableWidget(len(usages),1); self.table.setHorizontalHeaderLabels(['包含此物料的SKU / 父级物料']); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setWordWrap(True)
  for index,usage in enumerate(usages):
   item=QTableWidgetItem(f"SKU：{usage['sku']}\n父级物料：{usage['parent']}"); item.setData(Qt.UserRole,usage.get('sku_id')); self.table.setItem(index,0,item)
  self.table.cellDoubleClicked.connect(self.open_sku); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
  self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.table.resizeRowsToContents(); layout.addWidget(self.table)
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
  main.open_bom_id(sku_id)
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
