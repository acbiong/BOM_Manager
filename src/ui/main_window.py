"""PyQt主窗口、SKU清单、物料库和BOM编辑窗口。输入服务对象，输出桌面交互。编辑时间：2026-09-24。"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
class MaterialDialog(QDialog):
 def __init__(self,parent=None,data=None):
  super().__init__(parent); self.setWindowTitle('物料'); f=QFormLayout(self); self.e={}
  for k,l in [('base_code','物料基础编码'),('version','物料版本号'),('name','物料名称'),('description','物料规格描述'),('unit','单位'),('manufacturer','物料制造商'),('mpn','物料MPN')]:
   w=QLineEdit(str((data or {}).get(k,''))); self.e[k]=w; f.addRow(l,w)
  self.e['unit'].setText((data or {}).get('unit','pcs')); b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)
 def data(self): return {k:w.text().strip() for k,w in self.e.items()}
class MainWindow(QMainWindow):
 def __init__(self,svc,version='0.0.1'):
  super().__init__(); self.svc=svc; self.setWindowTitle('BOM管理系统'); self.resize(1100,700); self.version=version; self.build()
 def build(self):
  bar=self.menuBar(); fm=bar.addMenu('文件'); a=fm.addAction('导出资料库'); a.triggered.connect(self.export_database); a=fm.addAction('导出物料库'); a.triggered.connect(self.export_materials); a=fm.addAction('导出模板'); a.triggered.connect(self.template); mm=bar.addMenu('物料库'); a=mm.addAction('新建物料'); a.triggered.connect(self.new_material); a=mm.addAction('物料库窗口'); a.triggered.connect(self.show_materials); a=mm.addAction('导入物料'); a.triggered.connect(self.import_materials); a=mm.addAction('刷新'); a.triggered.connect(self.refresh); pm=bar.addMenu('项目'); a=pm.addAction('修改项目信息'); a.triggered.connect(self.edit_project); sm=bar.addMenu('SKU'); a=sm.addAction('新建SKU'); a.triggered.connect(self.new_sku); a=sm.addAction('删除SKU'); a.triggered.connect(self.delete_sku)
  self.table=QTableWidget(); self.table.setColumnCount(6); self.table.setHorizontalHeaderLabels(['打开','SKU编码','SKU名称','SKU描述','修改日期时间','ID']); self.table.hideColumn(5); self.table.cellDoubleClicked.connect(self.open_bom); self.setCentralWidget(self.table); self.statusBar().showMessage('版本 '+self.version); self.refresh()
 def refresh(self):
  rows=self.svc.skus(); self.table.setRowCount(len(rows));
  for i,r in enumerate(rows):
   btn=QPushButton('打开'); btn.clicked.connect(lambda _,sid=r['id']: self.open_bom_id(sid)); self.table.setCellWidget(i,0,btn); self.table.setItem(i,1,QTableWidgetItem(r['base_code']+'-'+r['version'])); self.table.setItem(i,2,QTableWidgetItem(r['name'])); self.table.setItem(i,3,QTableWidgetItem(r['description'])); self.table.setItem(i,4,QTableWidgetItem(r['updated_at'] or '')); self.table.setItem(i,5,QTableWidgetItem(str(r['id'])))
  self.statusBar().showMessage(f'共计{len(rows)}个SKU | 版本 {self.version}')
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
    ok,fail=self.svc.import_materials(p); self.refresh(); QMessageBox.information(self,'导入结果',f'成功{len(ok)}条，失败{len(fail)}条')
   except Exception as e: QMessageBox.warning(self,'导入失败',str(e))
 def new_material(self):
  d=MaterialDialog(self)
  if d.exec_():
   try:self.svc.create_material(d.data()); self.refresh()
   except Exception as e: QMessageBox.warning(self,'校验失败',str(e))
 def new_sku(self):
  rows=self.svc.materials(); items=[f"{r['base_code']} {r['version']} {r['name']}" for r in rows]; x,ok=QInputDialog.getItem(self,'新建SKU','选择物料',items,0,False)
  if ok:
   try: mid=rows[items.index(x)]['id']; sid=self.svc.create_sku(mid); self.refresh(); self.open_bom_id(sid)
   except Exception as e: QMessageBox.warning(self,'失败',str(e))
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
 def __init__(self,svc,root,parent=None): super().__init__(parent); self.svc=svc; self.root=root; self.setWindowTitle('BOM管理'); self.resize(900,600); self.dirty=False; self.tree=QTreeWidget(); self.tree.setHeaderLabels(['物料','数量','单位','位置']); self.info=QTextEdit(); self.info.setReadOnly(True); spl=QSplitter(); spl.addWidget(self.tree); spl.addWidget(self.info); self.setCentralWidget(spl); tb=self.addToolBar('BOM'); save=QAction('保存',self); save.triggered.connect(self.save); tb.addAction(save); add=QAction('新增物料',self); add.triggered.connect(self.add); tb.addAction(add); imp=QAction('导入BOM',self); imp.triggered.connect(self.import_bom); tb.addAction(imp); exp=QAction('导出SKU BOM',self); exp.triggered.connect(self.export_bom); tb.addAction(exp); self.load()
 def load(self):
  self.tree.clear(); rows=self.svc.bom(self.root); by={};
  for r in rows:
   parent=by.get(r['parent_item_id']); item=QTreeWidgetItem(parent or self.tree,[f"{r['base_code']}-{r['version']} {r['name']}",str(r['quantity']),r['unit'],r['position']]); item.setData(0,Qt.UserRole,dict(r)); by[r['id']]=item
  self.tree.itemClicked.connect(lambda i,c:self.info.setPlainText(str(i.data(0,Qt.UserRole))))
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
 def save(self): QMessageBox.information(self,'保存','BOM已保存')

class MaterialWindow(QMainWindow):
 def __init__(self,svc,parent=None):
  super().__init__(parent); self.svc=svc; self.setWindowTitle('物料库'); self.resize(1000,600); self.t=QTableWidget(); self.t.setColumnCount(10); self.t.setHorizontalHeaderLabels(['序号','基础编码','版本号','名称','规格描述','单位','制造商','MPN','M/P','呆滞物料']); self.setCentralWidget(self.t); self.t.setContextMenuPolicy(Qt.CustomContextMenu); self.t.customContextMenuRequested.connect(self.menu); self.refresh()
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
