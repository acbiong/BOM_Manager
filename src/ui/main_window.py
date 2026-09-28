"""PyQt主窗口、SKU清单、物料库和BOM编辑窗口。输入服务对象，输出桌面交互。编辑时间：2026-09-24。"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from pathlib import Path
from config.config_service import ConfigService
from database.database import Database
from infrastructure.events import WindowRefreshBus

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
class MainWindow(QMainWindow):
 def __init__(self,svc,version='0.0.1'):
  super().__init__(); self.svc=svc; self._bom_windows={}; self._materials=None; self.setWindowTitle('BOM管理系统'); self.resize(1100,700); self.version=version; self.build()
 def build(self):
  bar=self.menuBar(); fm=bar.addMenu('文件'); a=fm.addAction('选择SQLite数据库'); a.triggered.connect(self.select_database); a=fm.addAction('导出资料库'); a.triggered.connect(self.export_database);  mm=bar.addMenu('物料库'); a=mm.addAction('物料库窗口'); a.triggered.connect(self.show_materials); a=mm.addAction('刷新'); a.triggered.connect(self.refresh); pm=bar.addMenu('项目'); a=pm.addAction('修改项目信息'); a.triggered.connect(self.edit_project); sm=bar.addMenu('SKU'); a=sm.addAction('新建SKU'); a.triggered.connect(self.new_sku); a=sm.addAction('版本变更'); a.triggered.connect(self.change_sku_version); a=sm.addAction('删除SKU'); a.triggered.connect(self.delete_sku)
  self.table=QTableWidget(); self.table.setColumnCount(6); self.table.setHorizontalHeaderLabels(['打开','SKU编码','SKU名称','SKU描述','修改日期时间','ID']); self.table.hideColumn(5); self.table.setWordWrap(True); self.table.cellDoubleClicked.connect(self.open_bom)
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
   for window in list(self._bom_windows.values()):
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
   try:
    ok,fail=self.svc.import_materials(p,resolver); self.refresh();
    if self._materials is not None and self._materials.isVisible(): self._materials.refresh()
    dup=sum(1 for x in fail if '重复物料' in x[3]); QMessageBox.information(self,'导入结果',f'成功{len(ok)}条，失败{len(fail)-dup}条，发现{dup}个重复物料未导入')
   except Exception as e: QMessageBox.warning(self,'导入失败',str(e))
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
 def change_sku_version(self):
  r=self.table.currentRow()
  if r<0:return
  sid=int(self.table.item(r,5).text()); v,ok=QInputDialog.getText(self,'SKU版本变更','新版本号')
  if ok:
   try:self.svc.change_sku_version(sid,v.strip()); self.refresh()
   except Exception as e: QMessageBox.warning(self,'版本变更失败',str(e))
 def delete_sku(self):
  r=self.table.currentRow()
  if r<0:return
  sid=int(self.table.item(r,5).text())
  if QMessageBox.question(self,'确认','删除当前SKU及BOM？')==QMessageBox.Yes:self.svc.delete_sku(sid); self.refresh()
 def open_bom(self,row,col): self.open_bom_id(int(self.table.item(row,5).text()))
 def open_bom_id(self,sid):
  if sid not in self._bom_windows:
   row=self.svc.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone()
   if row is None:return
   window=BomWindow(self.svc,row['material_id'],self)
   self._bom_windows[sid]=window
   window.closed.connect(lambda:self._bom_windows.pop(sid,None))
  self.activate_window(self._bom_windows[sid])
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
  super().__init__(parent); self.setAttribute(Qt.WA_DeleteOnClose); self.svc=svc; self.root=root; self.current_item=None; self._deleted_relations=set(); self._loading_fields=False; self._saving=False; self.notice=QLabel(''); self.notice.setStyleSheet('color:red'); WindowRefreshBus.subscribe(self.on_external_change); self.setWindowTitle('BOM管理'); self.resize(1200,700); self.dirty=False
  self.tree=QTreeWidget(); self.tree.itemClicked.connect(self.show_item_info); self.tree.setWordWrap(True); self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.context_menu); self.tree.setHeaderLabels(['物料编码/名称','数量','单位','位置','备注']); self.tree.setMinimumWidth(420)
  self.fields={}; form=QFormLayout();
  for k,l in [('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料描述'),('quantity','物料数量'),('unit','物料单位'),('position','物料位置'),('manufacturer','物料制造商'),('mpn','物料MPN'),('mp_flag','M/P'),('remark','备注')]:
   w=QuantityEdit() if k=='quantity' else (QLineEdit() if k in ('position','remark') else QLabel()); self.fields[k]=w; form.addRow(l,w)
  self.fields['quantity'].valueChanged.connect(lambda value:self.update_tree_field('quantity',value))
  for key in ('position','remark'): self.fields[key].textChanged.connect(lambda value,k=key:self.update_tree_field(k,value))
  info_box=QGroupBox('物料信息'); info_box.setLayout(form); self.alt_table=QTableWidget(0,6); self.alt_table.setHorizontalHeaderLabels(['替代料编码','版本号','名称','描述','制造商','MPN']); alt_box=QGroupBox('替代料'); alt_l=QVBoxLayout(alt_box); alt_l.addWidget(self.alt_table)
  right=QWidget(); right_l=QVBoxLayout(right); right_l.addWidget(info_box); right_l.addWidget(alt_box); spl=QSplitter(); spl.addWidget(self.tree); spl.addWidget(right); spl.setStretchFactor(1,1); box=QWidget(); lay=QVBoxLayout(box); lay.addWidget(spl); self.setCentralWidget(box); self.menuBar().setCornerWidget(self.notice,Qt.TopRightCorner); tb=self.addToolBar('BOM'); self.save_action=QAction('保存',self); self.save_action.triggered.connect(self.save); self.save_action.setEnabled(False); tb.addAction(self.save_action); self.refresh_action=QAction('刷新',self); self.refresh_action.triggered.connect(self.refresh_external); self.refresh_action.setEnabled(False); tb.addAction(self.refresh_action); imp=QAction('导入BOM',self); imp.triggered.connect(self.import_bom); tb.addAction(imp); exp=QAction('导出SKU BOM',self); exp.triggered.connect(self.export_bom); tb.addAction(exp); alt=QAction('替代料',self); alt.triggered.connect(self.manage_alternates); tb.addAction(alt); self.load()
 def mark_dirty(self):
  self.dirty=True
  self.save_action.setEnabled(True)
 def on_external_change(self,event):
  if self._saving: return
  if event.get('type') in ('bom_changed','material_changed') and self.contains_material(event.get('root') if event.get('type')=='bom_changed' else event.get('id')):
   self.notice.setText('BOM有更新，请点击刷新或重新打开窗口'); self.refresh_action.setEnabled(True); self.statusBar().showMessage('检测到当前SKU包含的BOM有更新')
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
  if it is getattr(self,'root_item',None):
   m=QMenu(self); child=m.addAction('增加子级物料'); act=m.exec_(self.tree.viewport().mapToGlobal(pos))
   if act==child: self.add_relative(d,True)
   return
  m=QMenu(self); same=m.addAction('新增同级物料'); child=m.addAction('新增子级物料'); dele=m.addAction('删除物料'); act=m.exec_(self.tree.viewport().mapToGlobal(pos))
  if act in (same,child): self.add_relative(d, act==child); return
  if act==dele and QMessageBox.question(self,'确认','删除当前BOM物料？')==QMessageBox.Yes:
   self.remove_relation(it)
 def relation_key(self,item):
  data=item.data(0,Qt.UserRole) or {}; parent=item.parent()
  parent_data=parent.data(0,Qt.UserRole) if parent else {}
  return (parent_data.get('material_id'),data.get('material_id'),item.text(3))
 def remove_relation(self,item):
  """共享BOM只存一份关系，删除时同步移除当前树中该关系的所有副本。"""
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
    self.by.pop(removed_data.get('node_id'),None)
    pending.extend(removed.child(i) for i in range(removed.childCount()))
   node.parent().removeChild(node)
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
 def cached_values(self):
  values={}
  for i in range(self.tree.topLevelItemCount()):
   stack=[self.tree.topLevelItem(i)]
   while stack:
    item=stack.pop(); d=item.data(0,Qt.UserRole) or {}
    if not d.get('root') and d.get('material_id'):
     parent=item.parent(); pd=parent.data(0,Qt.UserRole) if parent else {}
     values[(pd.get('material_id'),d.get('material_id'),str(item.text(3)))] = (item.text(1),item.text(3),item.text(4))
    stack.extend([item.child(j) for j in range(item.childCount())])
  return values
 def refresh_external(self):
  cached=self.cached_values() if self.dirty else {}
  self.load(cached); self.notice.setText(''); self.statusBar().clearMessage(); self.refresh_action.setEnabled(False); self.save_action.setEnabled(self.dirty)
 def load(self,preserve=None):
  self.current_item=None; self.tree.clear(); self.by={}; root=self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone()
  self.setWindowTitle(f"{root['base_code']}-{root['version']} {root['name']}")
  self.root_item=QTreeWidgetItem(self.tree,[f"{root['base_code']}-{root['version']} {root['name']}",'','','','']); self.root_item.setData(0,Qt.UserRole,{'material_id':self.root,'root':True}); self.root_item.setExpanded(True)
  for r in self.svc.bom(self.root):
   if (r['parent_material_id'],r['material_id'],r['position'] or '') in self._deleted_relations:continue
   if r['parent_node_id'] is not None and r['parent_node_id'] not in self.by:continue
   parent=self.by.get(r['parent_node_id'],self.root_item); item=QTreeWidgetItem(parent,[f"{r['base_code']}-{r['version']} {r['name']}",f"{r['quantity']:.1f}",r['unit'],r['position'],r['remark']]); item.setData(0,Qt.UserRole,dict(r)); self.by[r['node_id']]=item
   if preserve:
    pd=parent.data(0,Qt.UserRole) or {}; values=preserve.get((pd.get('material_id'),r['material_id'],str(r['position'])))
    if values:
     item.setText(1,values[0]); item.setText(3,values[1]); item.setText(4,values[2]); d=item.data(0,Qt.UserRole) or {}; d.update({'quantity':float(values[0]),'position':values[1],'remark':values[2]}); item.setData(0,Qt.UserRole,d)
  fit_columns(self.tree)
  self.save_action.setEnabled(False); self.refresh_action.setEnabled(False)
  self.tree.setCurrentItem(self.root_item); self.show_item_info(self.root_item)
 def show_item_info(self,item,column=0):
  self.current_item=item
  d=item.data(0,Qt.UserRole) or {}
  if d.get('root'):
   r=self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone(); d=dict(r) if r else d
  self._loading_fields=True
  self.fields['quantity'].setEnabled(not (item.data(0,Qt.UserRole) or {}).get('root'))
  for k in self.fields: self.fields[k].setText(str(d.get(k,'') or ''))
  self._loading_fields=False
  self.alt_table.setRowCount(0)
  if d.get('id'):
   for r in self.svc.alternates(d['id']):
    row=self.alt_table.rowCount(); self.alt_table.insertRow(row)
    for j,k in enumerate(['base_code','version','name','description','manufacturer','mpn']): self.alt_table.setItem(row,j,QTableWidgetItem(str(r[k] or '')))
 def update_tree_field(self,key,value):
  if self._loading_fields or self.current_item is None or self.current_item is getattr(self,'root_item',None): return
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
  r=rows[items.index(x)]; self._deleted_relations.discard(((target.data(0,Qt.UserRole) or {}).get('material_id'),r['id'],'')); item=QTreeWidgetItem(target,[f"{r['base_code']}-{r['version']} {r['name']}",'1.0',r['unit'],'','']); temporary_id=-id(item); data={'id':temporary_id,'material_id':r['id'],'base_code':r['base_code'],'version':r['version'],'name':r['name'],'description':r['description'],'quantity':1,'unit':r['unit'],'position':'','manufacturer':r['manufacturer'],'mpn':r['mpn'],'mp_flag':r['mp_flag'],'remark':'','level_no':(parent.get('level_no') or 1)+(1 if child else 0),'parent_item_id':parent.get('id') if child else parent.get('parent_item_id')}; data.update(node_id=str(temporary_id),parent_node_id=(target.data(0,Qt.UserRole) or {}).get('node_id')); item.setData(0,Qt.UserRole,data); self.by[str(temporary_id)]=item; target.setExpanded(True); fit_columns(self.tree); self.mark_dirty(); self.tree.setCurrentItem(item); self.show_item_info(item)
  self.add_existing_children(item,r['id'],set())
  fit_columns(self.tree); self.mark_dirty(); self.tree.setCurrentItem(item); self.show_item_info(item)
 def add_existing_children(self,parent_item,material_id,ancestors):
  if material_id in ancestors:return
  ancestors=set(ancestors); ancestors.add(material_id)
  rows=self.svc.db.conn.execute('SELECT b.*,m.base_code,m.version,m.name,m.description,m.unit AS material_unit,m.manufacturer,m.mpn,m.mp_flag FROM material_bom_items b JOIN materials m ON m.id=b.child_material_id WHERE b.parent_material_id=? ORDER BY b.sort_no,b.id',(material_id,)).fetchall()
  parent_data=parent_item.data(0,Qt.UserRole) or {}
  for row in rows:
   if row['child_material_id'] in ancestors:continue
   child=QTreeWidgetItem(parent_item,[f"{row['base_code']}-{row['version']} {row['name']}",f"{row['quantity']:.1f}",row['material_unit'],row['position'],row['remark']]); d=dict(row); d.update({'material_id':row['child_material_id'],'unit':row['material_unit'],'parent_item_id':parent_data.get('id'),'level_no':(parent_data.get('level_no') or 0)+1}); d.update(node_id=f"{parent_data.get('node_id')}/{row['id']}",parent_node_id=parent_data.get('node_id')); child.setData(0,Qt.UserRole,d); self.by[d['node_id']]=child; self.add_existing_children(child,row['child_material_id'],ancestors)
  parent_item.setExpanded(True)
 def manage_alternates(self):
  it=self.tree.currentItem(); d=it.data(0,Qt.UserRole) if it else None
  if not d or not d.get('id'): QMessageBox.information(self,'提示','请先选择BOM物料'); return
  dlg=AlternateDialog(self.svc,d['id'],self); dlg.exec_()
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
    d.update(quantity=float(it.text(1)),position=it.text(3),remark=it.text(4),parent_material_id=parent_material)
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
  self.dirty=False; self._deleted_relations.clear(); self.load(); self.notice.setText(''); self.statusBar().clearMessage(); self.save_action.setEnabled(False); self.refresh_action.setEnabled(False)
  QMessageBox.information(self,'保存','BOM已保存')
  return True

class MaterialWindow(QMainWindow):
 closed=pyqtSignal()
 def __init__(self,svc,parent=None):
  super().__init__(parent); self.setAttribute(Qt.WA_DeleteOnClose); self.svc=svc; WindowRefreshBus.subscribe(self.on_event); self.setWindowTitle('物料库')
  menu=self.menuBar().addMenu('物料库'); a=menu.addAction('新建物料'); a.triggered.connect(parent.new_material if parent else self.new_material); a=menu.addAction('导入物料'); a.triggered.connect(parent.import_materials if parent else self.import_materials); a=menu.addAction('导出物料库'); a.triggered.connect(parent.export_materials if parent else self.export_materials); a=menu.addAction('导出模板'); a.triggered.connect(parent.template if parent else self.template); a=menu.addAction('刷新'); a.triggered.connect(self.refresh); self.resize(1000,600); self.t=QTableWidget(); self.t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.t.setEditTriggers(QAbstractItemView.NoEditTriggers); self.t.setColumnCount(10); self.t.setHorizontalHeaderLabels(['基础编码','版本号','名称','规格描述','单位','制造商','MPN','M/P','是否存在BOM结构','是否为呆滞料']); self.t.setWordWrap(True); self.setCentralWidget(self.t); self.t.setContextMenuPolicy(Qt.CustomContextMenu); self.t.customContextMenuRequested.connect(self.menu); self.t.cellDoubleClicked.connect(self.edit_current); self.refresh()
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
  m=QMenu(self); e=m.addAction('编辑物料'); v=m.addAction('物料版本变更'); d=m.addAction('删除物料'); d.setEnabled(material['idle']=='Y')
  reverse=m.addAction('物料反查') if material['idle']=='N' else None
  a=m.exec_(self.t.viewport().mapToGlobal(pos))
  if a is None:return
  if reverse is not None and a==reverse:
   MaterialUsageDialog(material,self.svc.material_usage(rid),self).exec_(); return
  if a==v:
   self.change_version(rid)
  elif a==e:
   r=self.svc.materials()[row]; dlg=MaterialDialog(self,{k:r[k] for k in ['base_code','version','name','description','unit','manufacturer','mpn','mp_flag']},readonly_keys={'base_code','version'})
   if dlg.exec_(): self.svc.update_material(rid,dlg.data()); self.refresh()
  elif a==d and d.isEnabled() and QMessageBox.question(self,'确认','删除物料？')==QMessageBox.Yes:
   try:self.svc.delete_material(rid); self.refresh()
   except Exception as ex: QMessageBox.warning(self,'无法删除',str(ex))
 def change_version(self,material_id):
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
  WindowRefreshBus.unsubscribe(self.on_event); self.closed.emit(); event.accept()
 def refresh(self):
  rs=self.svc.materials(); self.t.setRowCount(len(rs))
  for i,r in enumerate(rs):
   for j,v in enumerate([r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag'],r['has_bom'],r['idle']]):
    item=QTableWidgetItem(str(v or ''))
    if r['idle']=='Y': item.setBackground(QColor('red')); item.setForeground(QColor('black'))
    self.t.setItem(i,j,item)
  fit_columns(self.t)

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

class AlternateDialog(QDialog):
 def __init__(self,svc,item_id,parent=None):
  super().__init__(parent); self.svc=svc; self.item_id=item_id; self.setWindowTitle('替代料管理'); self.resize(700,350); v=QVBoxLayout(self); self.t=QTableWidget(); self.t.setColumnCount(6); self.t.setHorizontalHeaderLabels(['基础编码','版本号','名称','描述','制造商','MPN']); self.t.setWordWrap(True); v.addWidget(self.t); h=QHBoxLayout(); add=QPushButton('增加替代料'); add.clicked.connect(self.add); dele=QPushButton('删除选中'); dele.clicked.connect(self.remove); close=QPushButton('关闭'); close.clicked.connect(self.accept); h.addWidget(add); h.addWidget(dele); h.addWidget(close); v.addLayout(h); self.refresh()
 def refresh(self):
  rs=self.svc.alternates(self.item_id); self.t.setRowCount(len(rs))
  for i,r in enumerate(rs):
   for j,k in enumerate(['base_code','version','name','description','manufacturer','mpn']): self.t.setItem(i,j,QTableWidgetItem(str(r[k] or '')))
  fit_columns(self.t)
 def add(self):
  rs=self.svc.materials(); items=[f"{r['base_code']} {r['version']} {r['name']}" for r in rs]; x,ok=QInputDialog.getItem(self,'增加替代料','选择物料',items,0,False)
  if ok:self.svc.add_alternate(self.item_id,rs[items.index(x)]['id']); self.refresh()
 def remove(self):
  row=self.t.currentRow()
  if row<0:return
  aid=self.svc.alternates(self.item_id)[row]['id']
  if QMessageBox.question(self,'确认','删除替代料？')==QMessageBox.Yes:self.svc.remove_alternate(aid); self.refresh()
