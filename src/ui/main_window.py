"""PyQt主窗口、SKU清单、物料库和BOM编辑窗口。输入服务对象，输出桌面交互。编辑时间：2026-09-24。"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from pathlib import Path
from config.config_service import ConfigService
from database.database import Database
from infrastructure.events import WindowRefreshBus

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
  super().__init__(); self.svc=svc; self.setWindowTitle('BOM管理系统'); self.resize(1100,700); self.version=version; self.build()
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
   old_db=self.svc.db
   self.svc.db=new_db
   old_db.close()
   c=ConfigService().load(); c['database']['path']=str(selected); ConfigService().save(c)
   for attr in ('_materials','_bom'):
    window=getattr(self,attr,None)
    if window is not None: window.close()
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
 def show_materials(self):
  self._materials=MaterialWindow(self.svc,self); self._materials.show()
 def import_materials(self):
  cfg=ConfigService(Path(self.svc.db.path).parent).load(); last=cfg['database'].get('last_import_dir',str(Path.home()/'Desktop')); last=last if Path(last).is_dir() else str(Path.home()/'Desktop')
  p=QFileDialog.getOpenFileName(self,'导入物料清单',last,'Excel (*.xlsx)')[0]
  if p:
   cfg['database']['last_import_dir']=str(Path(p).parent); ConfigService(Path(self.svc.db.path).parent).save(cfg)
   def resolver(d,old):
    box=QMessageBox(self); box.setWindowTitle('发现重复物料'); box.setText(f"物料 {d['物料基础编码']}-{d['物料版本号']}（{d['物料名称']}）已存在，是否覆盖？"); cover=box.addButton('覆盖',QMessageBox.AcceptRole); skip=box.addButton('跳过',QMessageBox.DestructiveRole); cancel=box.addButton('取消全部',QMessageBox.RejectRole); box.exec_(); return 'overwrite' if box.clickedButton()==cover else ('skip' if box.clickedButton()==skip else 'cancel')
   try:
    ok,fail=self.svc.import_materials(p,resolver); self.refresh();
    if hasattr(self,'_materials') and self._materials.isVisible(): self._materials.refresh()
    dup=sum(1 for x in fail if '重复物料' in x[3]); QMessageBox.information(self,'导入结果',f'成功{len(ok)}条，失败{len(fail)-dup}条，发现{dup}个重复物料未导入')
   except Exception as e: QMessageBox.warning(self,'导入失败',str(e))
 def new_material(self):
  d=MaterialDialog(self)
  if d.exec_():
   try:
    self.svc.create_material(d.data()); self.refresh();
    if hasattr(self,'_materials') and self._materials.isVisible(): self._materials.refresh()
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
  r=self.svc.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone() if hasattr(self.svc,'conn') else self.svc.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone(); root=r['material_id']; w=BomWindow(self.svc,root,self); w.show(); self._bom=w
 def export_materials(self):
  p=QFileDialog.getSaveFileName(self,'导出物料库','物料库.xlsx','Excel (*.xlsx)')[0]
  if p:self.svc.export_materials(p); QMessageBox.information(self,'完成','导出成功')
 def template(self):
  p=QFileDialog.getSaveFileName(self,'导出模板','物料模板.xlsx','Excel (*.xlsx)')[0]
  if p:
   from openpyxl import Workbook; w=Workbook(); w.active.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN']); w.save(p)
class BomWindow(QMainWindow):
 def __init__(self,svc,root,parent=None):
  super().__init__(parent); self.svc=svc; self.root=root; self.current_item=None; self._loading_fields=False; self._saving=False; self.notice=QLabel(''); self.notice.setStyleSheet('color:red'); WindowRefreshBus.subscribe(self.on_external_change); self.setWindowTitle('BOM管理'); self.resize(1200,700); self.dirty=False
  self.tree=QTreeWidget(); self.tree.setWordWrap(True); self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.context_menu); self.tree.setHeaderLabels(['物料编码/名称','数量','单位','位置','备注']); self.tree.setMinimumWidth(420)
  self.fields={}; form=QFormLayout();
  for k,l in [('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料描述'),('quantity','物料数量'),('unit','物料单位'),('position','物料位置'),('manufacturer','物料制造商'),('mpn','物料MPN'),('mp_flag','M/P'),('remark','备注')]:
   w=QLineEdit() if k in ('quantity','position','remark') else QLabel(); self.fields[k]=w; form.addRow(l,w)
  for key in ('quantity','position','remark'): self.fields[key].textChanged.connect(lambda value,k=key:self.update_tree_field(k,value))
  info_box=QGroupBox('物料信息'); info_box.setLayout(form); self.alt_table=QTableWidget(0,6); self.alt_table.setHorizontalHeaderLabels(['替代料编码','版本号','名称','描述','制造商','MPN']); alt_box=QGroupBox('替代料'); alt_l=QVBoxLayout(alt_box); alt_l.addWidget(self.alt_table)
  right=QWidget(); right_l=QVBoxLayout(right); right_l.addWidget(info_box); right_l.addWidget(alt_box); spl=QSplitter(); spl.addWidget(self.tree); spl.addWidget(right); spl.setStretchFactor(1,1); box=QWidget(); lay=QVBoxLayout(box); lay.addWidget(spl); self.setCentralWidget(box); self.menuBar().setCornerWidget(self.notice,Qt.TopRightCorner); tb=self.addToolBar('BOM'); self.save_action=QAction('保存',self); self.save_action.triggered.connect(self.save); self.save_action.setEnabled(False); tb.addAction(self.save_action); self.refresh_action=QAction('刷新',self); self.refresh_action.triggered.connect(lambda:(self.load(),self.notice.setText(''))); self.refresh_action.setEnabled(False); tb.addAction(self.refresh_action); add=QAction('新增物料',self); add.triggered.connect(self.add); tb.addAction(add); imp=QAction('导入BOM',self); imp.triggered.connect(self.import_bom); tb.addAction(imp); exp=QAction('导出SKU BOM',self); exp.triggered.connect(self.export_bom); tb.addAction(exp); alt=QAction('替代料',self); alt.triggered.connect(self.manage_alternates); tb.addAction(alt); self.load()
 def mark_dirty(self):
  self.dirty=True
  self.save_action.setEnabled(True)
 def on_external_change(self,event):
  if self._saving: return
  if event.get('type')=='bom_changed' and event.get('root')==self.root:
   self.notice.setText('BOM有更新，请点击刷新或重新打开窗口'); self.refresh_action.setEnabled(True); self.statusBar().showMessage('检测到外部BOM更新')
 def closeEvent(self,event):
  if not self.dirty: WindowRefreshBus.unsubscribe(self.on_external_change); event.accept(); return
  box=QMessageBox(self); box.setWindowTitle('BOM未保存'); box.setText('BOM结构或物料信息已修改，是否保存？'); save=box.addButton('保存并退出',QMessageBox.AcceptRole); discard=box.addButton('不保存退出',QMessageBox.DestructiveRole); cancel=box.addButton('取消',QMessageBox.RejectRole); box.exec_()
  if box.clickedButton()==save: self.save(); WindowRefreshBus.unsubscribe(self.on_external_change); event.accept()
  elif box.clickedButton()==discard: WindowRefreshBus.unsubscribe(self.on_external_change); event.accept()
  else: event.ignore()

 def context_menu(self,pos):
  it=self.tree.itemAt(pos)
  if not it:return
  d=it.data(0,Qt.UserRole) or {}
  if it is getattr(self,'root_item',None):
   m=QMenu(self); child=m.addAction('增加子级物料'); act=m.exec_(self.tree.viewport().mapToGlobal(pos))
   if act==child: self.add_relative(d,True)
   return
  m=QMenu(self); same=m.addAction('新增同级物料'); child=m.addAction('新增子级物料'); edit=m.addAction('编辑数量/位置'); dele=m.addAction('删除物料'); act=m.exec_(self.tree.viewport().mapToGlobal(pos))
  if act in (same,child): self.add_relative(d, act==child); return
  if act==edit:
   q,ok=QInputDialog.getDouble(self,'编辑数量','数量',float(it.text(1)),0.0001,1e12,4)
   if ok: it.setText(1,str(q)); d['quantity']=q; it.setData(0,Qt.UserRole,d); self.mark_dirty(); self.tree.setCurrentItem(it); self.show_item_info(it)
  elif act==dele and QMessageBox.question(self,'确认','删除当前BOM物料？')==QMessageBox.Yes:
   parent=it.parent(); it.parent().removeChild(it) if parent else self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(it)); self.current_item=None; self.mark_dirty(); self.root_item.setSelected(True); self.tree.setCurrentItem(self.root_item); self.show_item_info(self.root_item)
 def load(self):
  self.tree.clear(); self.by={}; root=self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone()
  self.setWindowTitle(f"{root['base_code']}-{root['version']} {root['name']}")
  self.root_item=QTreeWidgetItem(self.tree,[f"{root['base_code']}-{root['version']} {root['name']}",'','','','']); self.root_item.setData(0,Qt.UserRole,{'material_id':self.root,'root':True}); self.root_item.setExpanded(True)
  for r in self.svc.bom(self.root):
   parent=self.by.get(r['parent_item_id'],self.root_item); item=QTreeWidgetItem(parent,[f"{r['base_code']}-{r['version']} {r['name']}",str(r['quantity']),r['unit'],r['position'],r['remark']]); item.setData(0,Qt.UserRole,dict(r)); self.by[r['id']]=item
  fit_columns(self.tree)
  self.save_action.setEnabled(False); self.refresh_action.setEnabled(False)
  self.tree.itemClicked.connect(self.show_item_info)
 def show_item_info(self,item,column=0):
  self.current_item=item
  d=item.data(0,Qt.UserRole) or {}
  if d.get('root'):
   r=self.svc.db.conn.execute('SELECT * FROM materials WHERE id=?',(self.root,)).fetchone(); d=dict(r) if r else d
  self._loading_fields=True
  for k in self.fields: self.fields[k].setText(str(d.get(k,'') or ''))
  self._loading_fields=False
  self.alt_table.setRowCount(0)
  if d.get('id'):
   for r in self.svc.alternates(d['id']):
    row=self.alt_table.rowCount(); self.alt_table.insertRow(row)
    for j,k in enumerate(['base_code','version','name','description','manufacturer','mpn']): self.alt_table.setItem(row,j,QTableWidgetItem(str(r[k] or '')))
 def update_tree_field(self,key,value):
  if self._loading_fields or self.current_item is None or self.current_item is getattr(self,'root_item',None): return
  col={'quantity':1,'position':3,'remark':4}[key]; self.current_item.setText(col,value); d=self.current_item.data(0,Qt.UserRole) or {}; d[key]=float(value) if key=='quantity' and value else value; self.current_item.setData(0,Qt.UserRole,d); self.mark_dirty()
 def add_relative(self,parent,child):
  target=self.by.get(parent.get('id'),self.root_item) if child else (self.by.get(parent.get('parent_item_id'),self.root_item) or self.root_item)
  used={target.child(i).data(0,Qt.UserRole).get('material_id') for i in range(target.childCount()) if target.child(i).data(0,Qt.UserRole)}
  rows=[r for r in self.svc.materials() if r['id'] not in used]; items=[f"{r['base_code']} {r['version']} {r['name']}" for r in rows]
  if not items: QMessageBox.information(self,'提示','当前父级下已没有可新增的物料'); return
  x,ok=QInputDialog.getItem(self,'新建BOM物料','物料',items,0,False)
  if not ok:return
  r=rows[items.index(x)]; item=QTreeWidgetItem(target,[f"{r['base_code']}-{r['version']} {r['name']}",'1',r['unit'],'','']); temporary_id=-id(item); data={'id':temporary_id,'material_id':r['id'],'base_code':r['base_code'],'version':r['version'],'name':r['name'],'description':r['description'],'quantity':1,'unit':r['unit'],'position':'','manufacturer':r['manufacturer'],'mpn':r['mpn'],'mp_flag':r['mp_flag'],'remark':'','level_no':(parent.get('level_no') or 1)+(1 if child else 0),'parent_item_id':parent.get('id') if child else parent.get('parent_item_id')}; item.setData(0,Qt.UserRole,data); self.by[temporary_id]=item; target.setExpanded(True); fit_columns(self.tree); self.mark_dirty(); self.tree.setCurrentItem(item); self.show_item_info(item)
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
  rows=[]
  for i in range(self.tree.topLevelItemCount()):
   def walk(it):
    d=it.data(0,Qt.UserRole) or {}; d['quantity']=float(it.text(1)); d['position']=it.text(3); d['remark']=it.text(4); rows.append(d)
    for j in range(it.childCount()): walk(it.child(j))
   top=self.tree.topLevelItem(i)
   for j in range(top.childCount()): walk(top.child(j))
  self.svc.save_bom(self.root,rows); self.dirty=False; self._saving=False; self.notice.setText(''); self.save_action.setEnabled(False); self.refresh_action.setEnabled(False); QMessageBox.information(self,'保存','BOM已保存')

class MaterialWindow(QMainWindow):
 def __init__(self,svc,parent=None):
  super().__init__(parent); self.svc=svc; WindowRefreshBus.subscribe(self.on_event); self.setWindowTitle('物料库')
  menu=self.menuBar().addMenu('物料库'); a=menu.addAction('新建物料'); a.triggered.connect(parent.new_material if parent else self.new_material); a=menu.addAction('导入物料'); a.triggered.connect(parent.import_materials if parent else self.import_materials); a=menu.addAction('导出物料库'); a.triggered.connect(parent.export_materials if parent else self.export_materials); a=menu.addAction('导出模板'); a.triggered.connect(parent.template if parent else self.template); a=menu.addAction('刷新'); a.triggered.connect(self.refresh); self.resize(1000,600); self.t=QTableWidget(); self.t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.t.setEditTriggers(QAbstractItemView.NoEditTriggers); self.t.setColumnCount(9); self.t.setHorizontalHeaderLabels(['基础编码','版本号','名称','规格描述','单位','制造商','MPN','M/P','是否存在BOM结构']); self.t.setWordWrap(True); self.setCentralWidget(self.t); self.t.setContextMenuPolicy(Qt.CustomContextMenu); self.t.customContextMenuRequested.connect(self.menu); self.t.cellDoubleClicked.connect(self.edit_current); self.refresh()
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
  m=QMenu(self); e=m.addAction('编辑物料'); v=m.addAction('物料版本变更'); d=m.addAction('删除物料'); a=m.exec_(self.t.viewport().mapToGlobal(pos))
  rid=self.svc.materials()[row]['id']
  if a==v:
   r=self.svc.materials()[row]; nv,ok=QInputDialog.getText(self,'物料版本变更','新版本号',text=r['version'])
   if ok:
    try:self.svc.change_material_version(r['id'],nv.strip()); self.refresh()
    except Exception as ex: QMessageBox.warning(self,'版本变更失败',str(ex))
  elif a==e:
   r=self.svc.materials()[row]; dlg=MaterialDialog(self,{k:r[k] for k in ['base_code','version','name','description','unit','manufacturer','mpn','mp_flag']},readonly_keys={'base_code','version'})
   if dlg.exec_(): self.svc.update_material(rid,dlg.data()); self.refresh()
  elif a==d and QMessageBox.question(self,'确认','删除物料？')==QMessageBox.Yes:
   try:self.svc.delete_material(rid); self.refresh()
   except Exception as ex: QMessageBox.warning(self,'无法删除',str(ex))
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
  if event.get('type')=='material_changed': self.refresh()
 def closeEvent(self,event):
  WindowRefreshBus.unsubscribe(self.on_event); event.accept()
 def refresh(self):
  rs=self.svc.materials(); self.t.setRowCount(len(rs))
  for i,r in enumerate(rs):
   for j,v in enumerate([r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag'],r['has_bom']]): self.t.setItem(i,j,QTableWidgetItem(str(v or '')))
  fit_columns(self.t)

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
