"""PyQt主窗口、SKU清单、物料库和BOM编辑窗口。输入服务对象，输出桌面交互。编辑时间：2026-09-24。"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from infrastructure.events import WindowRefreshBus
class MaterialDialog(QDialog):
 def __init__(self,parent=None,data=None):
  super().__init__(parent); self.setWindowTitle('物料'); f=QFormLayout(self); data=data or {}; self.e={}
  for k,l in [('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料规格描述'),('manufacturer','物料制造商'),('mpn','物料MPN')]:
   w=QLineEdit(str(data.get(k,''))); self.e[k]=w; f.addRow(l,w)
  self.unit=QComboBox(); self.unit.addItems(['pcs','套','ml','L','mm','cm','m']); self.unit.setCurrentText(data.get('unit','pcs')); f.addRow('单位',self.unit)
  self.mp_flag=QComboBox(); self.mp_flag.addItems(['M','P']); self.mp_flag.setCurrentText(data.get('mp_flag','M')); f.addRow('M/P',self.mp_flag)
  b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)
 def data(self):
  d={k:w.text().strip() for k,w in self.e.items()}; d['unit']=self.unit.currentText(); d['mp_flag']=self.mp_flag.currentText(); return d
class MainWindow(QMainWindow):
 def __init__(self,svc,version='0.0.1'):
  super().__init__(); self.svc=svc; self.setWindowTitle('BOM管理系统'); self.resize(1100,700); self.version=version; self.build()
 def build(self):
  bar=self.menuBar(); fm=bar.addMenu('文件'); a=fm.addAction('选择SQLite数据库'); a.triggered.connect(self.select_database); a=fm.addAction('导出资料库'); a.triggered.connect(self.export_database); a=fm.addAction('导出物料库'); a.triggered.connect(self.export_materials); a=fm.addAction('导出模板'); a.triggered.connect(self.template); mm=bar.addMenu('物料库'); a=mm.addAction('新建物料'); a.triggered.connect(self.new_material); a=mm.addAction('物料库窗口'); a.triggered.connect(self.show_materials); a=mm.addAction('导入物料'); a.triggered.connect(self.import_materials); a=mm.addAction('刷新'); a.triggered.connect(self.refresh); pm=bar.addMenu('项目'); a=pm.addAction('修改项目信息'); a.triggered.connect(self.edit_project); sm=bar.addMenu('SKU'); a=sm.addAction('新建SKU'); a.triggered.connect(self.new_sku); a=sm.addAction('版本变更'); a.triggered.connect(self.change_sku_version); a=sm.addAction('删除SKU'); a.triggered.connect(self.delete_sku)
  self.table=QTableWidget(); self.table.setColumnCount(6); self.table.setHorizontalHeaderLabels(['打开','SKU编码','SKU名称','SKU描述','修改日期时间','ID']); self.table.hideColumn(5); self.table.cellDoubleClicked.connect(self.open_bom); self.setCentralWidget(self.table); self.statusBar().showMessage('版本 '+self.version); self.refresh()
 def refresh(self):
  rows=self.svc.skus(); self.table.setRowCount(len(rows));
  for i,r in enumerate(rows):
   btn=QPushButton('打开'); btn.clicked.connect(lambda _,sid=r['id']: self.open_bom_id(sid)); self.table.setCellWidget(i,0,btn); self.table.setItem(i,1,QTableWidgetItem(r['base_code']+'-'+r['version'])); self.table.setItem(i,2,QTableWidgetItem(r['name'])); self.table.setItem(i,3,QTableWidgetItem(r['description'])); self.table.setItem(i,4,QTableWidgetItem(r['updated_at'] or '')); self.table.setItem(i,5,QTableWidgetItem(str(r['id'])))
  self.statusBar().showMessage(f'共计{len(rows)}个SKU | 版本 {self.version}')
 def select_database(self):
  p=QFileDialog.getSaveFileName(self,'选择SQLite数据库','bom.db','SQLite (*.db)')[0]
  if p:
   from config.config_service import ConfigService
   c=ConfigService().load(); c['database']['path']=p; ConfigService().save(c); QMessageBox.information(self,'配置已保存','数据库路径已选择，请重启软件后生效：'+p)
 def export_database(self):
  p=QFileDialog.getSaveFileName(self,'导出资料库','资料库.xlsx','Excel (*.xlsx)')[0]
  if p:self.svc.export_database(p); QMessageBox.information(self,'完成','资料库导出成功')
 def edit_project(self):
  d=ProjectDialog(self,self.svc.project())
  if d.exec_(): self.svc.update_project(d.data()); self.setWindowTitle(d.data().get('project_name') or 'BOM管理系统')
 def show_materials(self):
  self._materials=MaterialWindow(self.svc,self); self._materials.show()
 def import_materials(self):
  p=QFileDialog.getOpenFileName(self,'导入物料清单','','Excel (*.xlsx)')[0]
  if p:
   try:
    ok,fail=self.svc.import_materials(p); self.refresh();
    if hasattr(self,'_materials') and self._materials.isVisible(): self._materials.refresh()
    QMessageBox.information(self,'导入结果',f'成功{len(ok)}条，失败{len(fail)}条')
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
 def __init__(self,svc,root,parent=None): super().__init__(parent); self.svc=svc; self.root=root; self.notice=QLabel(''); self.notice.setStyleSheet('color:red'); WindowRefreshBus.subscribe(self.on_external_change); self.setWindowTitle('BOM管理'); self.resize(900,600); self.dirty=False; self.tree=QTreeWidget(); self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.context_menu); self.tree.setHeaderLabels(['物料','数量','单位','位置']); self.info=QTextEdit(); self.info.setReadOnly(True); spl=QSplitter(); spl.addWidget(self.tree); spl.addWidget(self.info); box=QWidget(); lay=QVBoxLayout(box); lay.addWidget(self.notice); lay.addWidget(spl); self.setCentralWidget(box); tb=self.addToolBar('BOM'); save=QAction('保存',self); save.triggered.connect(self.save); tb.addAction(save); ref=QAction('刷新',self); ref.triggered.connect(lambda:(self.load(),self.notice.setText(''))); tb.addAction(ref); add=QAction('新增物料',self); add.triggered.connect(self.add); tb.addAction(add); imp=QAction('导入BOM',self); imp.triggered.connect(self.import_bom); tb.addAction(imp); exp=QAction('导出SKU BOM',self); exp.triggered.connect(self.export_bom); tb.addAction(exp); alt=QAction('替代料',self); alt.triggered.connect(self.manage_alternates); tb.addAction(alt); self.load()
 def on_external_change(self,event):
  if event.get('type')=='bom_changed' and event.get('root')==self.root:
   self.notice.setText('BOM有更新，请点击刷新或重新打开窗口'); self.statusBar().showMessage('检测到外部BOM更新')
 def closeEvent(self,event):
  WindowRefreshBus.unsubscribe(self.on_external_change); event.accept()
 def context_menu(self,pos):
  it=self.tree.itemAt(pos)
  if not it:return
  m=QMenu(self); same=m.addAction('新建同级物料'); child=m.addAction('新建下级物料'); edit=m.addAction('编辑数量/位置'); dele=m.addAction('删除物料'); act=m.exec_(self.tree.viewport().mapToGlobal(pos)); d=it.data(0,Qt.UserRole) or {}
  if act in (same,child): self.add_relative(d, act==child); return
  if act==edit:
   q,ok=QInputDialog.getDouble(self,'编辑数量','数量',float(it.text(1)),0.0001,1e12,4)
   if ok: it.setText(1,str(q)); self.dirty=True
  elif act==dele and QMessageBox.question(self,'确认','删除当前BOM物料？')==QMessageBox.Yes:
   self.svc.delete_bom_item(d.get('id')); self.load()
 def load(self):
  self.tree.clear(); rows=self.svc.bom(self.root); by={};
  for r in rows:
   parent=by.get(r['parent_item_id']); item=QTreeWidgetItem(parent or self.tree,[f"{r['base_code']}-{r['version']} {r['name']}",str(r['quantity']),r['unit'],r['position']]); item.setData(0,Qt.UserRole,dict(r)); by[r['id']]=item
  self.tree.itemClicked.connect(lambda i,c:self.info.setPlainText(str(i.data(0,Qt.UserRole))))
 def add_relative(self,parent,child):
  rows=self.svc.materials(); items=[f"{r['base_code']} {r['version']} {r['name']}" for r in rows]; x,ok=QInputDialog.getItem(self,'新建BOM物料','物料',items,0,False)
  if not ok:return
  r=rows[items.index(x)]; existing=[dict(z) for z in self.svc.bom(self.root)]; existing.append({'material_id':r['id'],'quantity':1,'unit':r['unit'],'position':'','level_no':(parent.get('level_no') or 1)+(1 if child else 0),'parent_item_id':parent.get('id') if child else parent.get('parent_item_id')}); self.svc.save_bom(self.root,existing); self.load()
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
  rows=self.svc.materials(); items=[f"{r['base_code']} {r['version']} {r['name']}" for r in rows]; x,ok=QInputDialog.getItem(self,'增加物料','物料',items,0,False)
  if ok:
   self.svc.save_bom(self.root,[*[(dict(r)) for r in self.svc.bom(self.root)],{'material_id':rows[items.index(x)]['id'],'quantity':1,'unit':rows[items.index(x)]['unit'],'level_no':1}]); self.load()
 def save(self):
  rows=[]
  for i in range(self.tree.topLevelItemCount()):
   def walk(it):
    d=it.data(0,Qt.UserRole) or {}; d['quantity']=float(it.text(1)); d['position']=it.text(3); rows.append(d)
    for j in range(it.childCount()): walk(it.child(j))
   walk(self.tree.topLevelItem(i))
  self.svc.save_bom(self.root,rows); self.dirty=False; QMessageBox.information(self,'保存','BOM已保存')

class MaterialWindow(QMainWindow):
 def __init__(self,svc,parent=None):
  super().__init__(parent); self.svc=svc; WindowRefreshBus.subscribe(self.on_event); self.setWindowTitle('物料库'); self.resize(1000,600); self.t=QTableWidget(); self.t.setColumnCount(10); self.t.setHorizontalHeaderLabels(['序号','基础编码','版本号','名称','规格描述','单位','制造商','MPN','M/P','呆滞物料']); self.setCentralWidget(self.t); self.t.setContextMenuPolicy(Qt.CustomContextMenu); self.t.customContextMenuRequested.connect(self.menu); self.refresh()
 def menu(self,pos):
  row=self.t.rowAt(pos.y())
  if row<0:return
  m=QMenu(self); e=m.addAction('编辑物料'); d=m.addAction('删除物料'); a=m.exec_(self.t.viewport().mapToGlobal(pos))
  rid=self.svc.materials()[row]['id']
  if a==e:
   r=self.svc.materials()[row]; dlg=MaterialDialog(self,{k:r[k] for k in ['base_code','version','name','description','unit','manufacturer','mpn']}); dlg.e['base_code'].setReadOnly(True); dlg.e['version'].setReadOnly(True)
   if dlg.exec_(): self.svc.update_material(rid,dlg.data()); self.refresh()
  elif a==d and QMessageBox.question(self,'确认','删除物料？')==QMessageBox.Yes:
   try:self.svc.delete_material(rid); self.refresh()
   except Exception as ex: QMessageBox.warning(self,'无法删除',str(ex))
 def on_event(self,event):
  if event.get('type')=='material_changed': self.refresh()
 def closeEvent(self,event):
  WindowRefreshBus.unsubscribe(self.on_event); event.accept()
 def refresh(self):
  rs=self.svc.materials(); self.t.setRowCount(len(rs))
  for i,r in enumerate(rs):
   for j,v in enumerate([i+1,r['base_code'],r['version'],r['name'],r['description'],r['unit'],r['manufacturer'],r['mpn'],r['mp_flag'],r['idle']]): self.t.setItem(i,j,QTableWidgetItem(str(v or '')))

class ProjectDialog(QDialog):
 def __init__(self,parent=None,row=None):
  super().__init__(parent); self.setWindowTitle('修改项目信息'); f=QFormLayout(self); self.e={}
  for k,l in [('project_name','项目名称'),('project_code','项目代码'),('product_name','产品名称'),('product_model','产品型号')]:
   w=QLineEdit(str((row or {}).get(k,''))); self.e[k]=w; f.addRow(l,w)
  b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)
 def data(self): return {k:w.text().strip() for k,w in self.e.items()}

class AlternateDialog(QDialog):
 def __init__(self,svc,item_id,parent=None):
  super().__init__(parent); self.svc=svc; self.item_id=item_id; self.setWindowTitle('替代料管理'); self.resize(700,350); v=QVBoxLayout(self); self.t=QTableWidget(); self.t.setColumnCount(6); self.t.setHorizontalHeaderLabels(['基础编码','版本号','名称','描述','制造商','MPN']); v.addWidget(self.t); h=QHBoxLayout(); add=QPushButton('增加替代料'); add.clicked.connect(self.add); dele=QPushButton('删除选中'); dele.clicked.connect(self.remove); close=QPushButton('关闭'); close.clicked.connect(self.accept); h.addWidget(add); h.addWidget(dele); h.addWidget(close); v.addLayout(h); self.refresh()
 def refresh(self):
  rs=self.svc.alternates(self.item_id); self.t.setRowCount(len(rs))
  for i,r in enumerate(rs):
   for j,k in enumerate(['base_code','version','name','description','manufacturer','mpn']): self.t.setItem(i,j,QTableWidgetItem(str(r[k] or '')))
 def add(self):
  rs=self.svc.materials(); items=[f"{r['base_code']} {r['version']} {r['name']}" for r in rs]; x,ok=QInputDialog.getItem(self,'增加替代料','选择物料',items,0,False)
  if ok:self.svc.add_alternate(self.item_id,rs[items.index(x)]['id']); self.refresh()
 def remove(self):
  row=self.t.currentRow()
  if row<0:return
  aid=self.svc.alternates(self.item_id)[row]['id']
  if QMessageBox.question(self,'确认','删除替代料？')==QMessageBox.Yes:self.svc.remove_alternate(aid); self.refresh()
