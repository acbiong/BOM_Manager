"""Capture actual controls and annotate their measured rectangles at build time."""
import json, math
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt,QPoint,QRect,QPointF
from PyQt5.QtGui import QPainter,QPen,QColor,QPolygonF
from PyQt5.QtWidgets import QApplication,QDialogButtonBox,QMenu,QToolBar,QComboBox,QLineEdit,QAbstractItemView,QScrollArea


def generate(out,main,materials,bom,svc):
    from ui.main_window import ProjectDialog,CreateMaterialDialog,NewSkuDialog,MaterialHeaderMappingDialog
    from ui.interactive_windows import QFileDialog,QInputDialog
    from ui.material_search import MaterialSearchDialog
    from ui.help_guides import GUIDE_KEYS
    from services.services import MATERIAL_IMPORT_HEADERS
    manifest={};dialogs=[]
    def shown(w):
        w.show();QApplication.processEvents();return w
    def dialog(w):
        dialogs.append(w);return shown(w)
    def action(menu,text):
        return next(a for a in menu.actions() if a.text()==text)
    def snap(key,w,target=None,rect=None):
        shown(w)
        if target is not None:
            for area in w.findChildren(QScrollArea):
                if area.widget() is not None and area.widget().isAncestorOf(target):area.ensureWidgetVisible(target)
            QApplication.processEvents()
            rect=QRect(target.mapTo(w,QPoint(0,0)),target.size())
        rect=rect.adjusted(-2,-2,2,2).intersected(w.rect().adjusted(2,2,-2,-2))
        if rect.isEmpty():raise RuntimeError('截图目标不可见：'+key)
        pix=w.grab();ratio=pix.devicePixelRatio();pix.setDevicePixelRatio(1)
        r=QRect(round(rect.x()*ratio),round(rect.y()*ratio),round(rect.width()*ratio),round(rect.height()*ratio))
        painter=QPainter(pix);painter.setRenderHint(QPainter.Antialiasing);painter.setPen(QPen(QColor('#ed1826'),3));painter.setBrush(Qt.NoBrush);painter.drawRect(r)
        end=QPointF(r.center().x(),r.top())
        if r.top()>75:start=end+QPointF(55,-60)
        elif r.bottom()+75<pix.height():end=QPointF(r.center().x(),r.bottom());start=end+QPointF(55,60)
        else:end=QPointF(r.right(),r.center().y());start=end+QPointF(55,30)
        start.setX(max(12,min(pix.width()-12,start.x())));start.setY(max(12,min(pix.height()-12,start.y())))
        painter.drawLine(start,end);angle=math.atan2(end.y()-start.y(),end.x()-start.x());head=[end]
        for delta in (-.48,.48):head.append(end-QPointF(13*math.cos(angle+delta),13*math.sin(angle+delta)))
        painter.setBrush(QColor('#ed1826'));painter.drawPolygon(QPolygonF(head));painter.end()
        name='action_'+key
        if not pix.save(str(out/(name+'.png'))):raise RuntimeError('无法写入'+name)
        manifest[name]=dict(window=w.windowTitle(),target=[rect.x(),rect.y(),rect.width(),rect.height()],size=[pix.width(),pix.height()])
    def bar(key,w,text):
        menu=w.menuBar();a=action(menu,text);r=menu.actionGeometry(a);r.translate(menu.mapTo(w,QPoint()));snap(key,w,rect=r)
    def ok(key,w):snap(key,w,w.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok));w.hide()
    def save_button(w):
        return next(b for b in w.findChild(QDialogButtonBox).buttons() if w.findChild(QDialogButtonBox).buttonRole(b)==QDialogButtonBox.AcceptRole)
    def file_dialog(title,save,filename):
        w=QFileDialog(main,title,str(out), 'Excel (*.xlsx)' if filename.endswith('xlsx') else 'SQLite (*.db)')
        w.setOption(QFileDialog.DontUseNativeDialog,True);w.setOption(QFileDialog.DontConfirmOverwrite,True)
        w.setAcceptMode(QFileDialog.AcceptSave if save else QFileDialog.AcceptOpen);w.selectFile(filename);return dialog(w)
    bar('project_menu',main,'项目');menu=action(main.menuBar(),'项目').menu();shown(menu)
    snap('project_new',menu,rect=menu.actionGeometry(action(menu,'新增项目')));menu.hide()
    project=dialog(ProjectDialog(main,svc.project()));project.setWindowTitle('请填写新项目信息')
    for field,key in [('project_code','project_code'),('project_name','project_name'),('product_name','product_name'),('product_model','product_model')]:snap(key,project,project.e[field])
    ok('project_ok',project)
    f=file_dialog('创建新项目数据库',True,'新项目.db');snap('database_name',f,f.findChild(QLineEdit,'fileNameEdit'));snap('database_save',f,save_button(f));f.hide()
    bar('library_open',main,'物料库');bar('material_new',materials,'新建物料')
    data=dict(svc.db.conn.execute('SELECT * FROM materials ORDER BY id LIMIT 1').fetchone())
    material=dialog(CreateMaterialDialog(main,data=data))
    for field in ('base_code','version','name','description','grade','manufacturer','mpn'):
        snap('material_'+field,material,material.e[field])
    snap('material_unit',material,material.unit);snap('material_mp_flag',material,material.mp_flag);ok('material_ok',material)
    bar('import_open',materials,'导入物料')
    from openpyxl import Workbook
    book=Workbook();book.active.title='物料清单';book.active.append(MATERIAL_IMPORT_HEADERS);book.create_sheet('填写说明');book.save(out/'物料清单.xlsx');book.close()
    f=file_dialog('导入物料清单',False,'物料清单.xlsx');snap('import_file',f,f.findChild(QLineEdit,'fileNameEdit'));snap('import_file_ok',f,save_button(f));f.hide()
    sheet=QInputDialog(main);sheet.setWindowTitle('选择物料工作表');sheet.setLabelText('请选择物料所在的工作表（Sheet）：');sheet.setComboBoxItems(['物料清单','填写说明']);dialog(sheet)
    snap('import_sheet',sheet,sheet.findChild(QComboBox));ok('import_sheet_ok',sheet)
    rows=[tuple(data.get(k,'') or '' for k in ('base_code','version','name','description','unit','grade','mp_flag','manufacturer','mpn'))]
    mapping=dialog(MaterialHeaderMappingDialog('物料清单.xlsx',MATERIAL_IMPORT_HEADERS,[],main,preview_rows=rows))
    for i,field in enumerate(MATERIAL_IMPORT_HEADERS):
        mapping.mapping_table.scrollToItem(mapping.mapping_table.item(0,i),QAbstractItemView.PositionAtCenter);QApplication.processEvents();snap('mapping_'+str(i),mapping,mapping.combos[field])
    snap('mapping_preview',mapping,mapping.preview);ok('mapping_ok',mapping)
    bar('sku_new',main,'新建SKU');sku=dialog(NewSkuDialog(svc,main))
    candidate=next((i for i in range(sku.model.rowCount()) if sku.model.item(i).isEnabled()),None)
    if candidate is None:raise RuntimeError('截图数据库没有可用于新建SKU的物料')
    sku.combo.setCurrentIndex(candidate);snap('sku_input',sku,sku.combo)
    sku.combo.showPopup();QApplication.processEvents();view=sku.combo.view();view.scrollTo(view.model().index(candidate,0),QAbstractItemView.PositionAtCenter);QApplication.processEvents()
    popup=view.window();r=view.visualRect(view.model().index(candidate,0));r.translate(view.viewport().mapTo(popup,QPoint()));snap('sku_pick',popup,rect=r);sku.combo.hidePopup();ok('sku_ok',sku)
    row=0;main.table.selectRow(row);rect=main.table.visualItemRect(main.table.item(row,1));rect.translate(main.table.viewport().mapTo(main,QPoint()));snap('bom_open',main,rect=rect)
    if bom is None or bom.root_item.childCount()==0:raise RuntimeError('截图BOM必须包含子物料')
    # All edits below affect only the SQLite backup and in-memory demo.
    sid=getattr(bom.svc,'sku_id',None)
    if sid:svc.set_sku_locked(sid,False)
    else:
        svc.db.conn.execute('UPDATE skus SET locked=0 WHERE material_id=?',(bom.root,));svc.db.conn.commit()
    bom.apply_lock_state();bom.tree.expandToDepth(1);node=bom.root_item.child(0);bom.tree.setCurrentItem(node);bom.show_item_info(node)
    r=bom.tree.visualItemRect(node);r.translate(bom.tree.viewport().mapTo(bom,QPoint()));snap('bom_select',bom,rect=r)
    for field in ('quantity','position','remark'):
        bom.info_scroll.ensureWidgetVisible(bom.fields[field]);QApplication.processEvents();snap('bom_'+field,bom,bom.fields[field])
    bom.fields['remark'].setText('帮助示例：核对装配位置');QApplication.processEvents()
    toolbar=bom.findChild(QToolBar);snap('bom_save',bom,toolbar.widgetForAction(bom.save_action));bom.dirty=False;bom.load()
    snap('export_bom',bom,toolbar.widgetForAction(bom.export_action));snap('export_purchase',bom,toolbar.widgetForAction(bom.purchase_export_action))
    f=file_dialog('导出BOM',True,'SKU BOM.xlsx');snap('export_name',f,f.findChild(QLineEdit,'fileNameEdit'));snap('export_save',f,save_button(f));f.hide()
    bar('search_open',materials,'查找物料');search=dialog(MaterialSearchDialog(materials));search.fields['code'].setText(data['base_code']);snap('search_code',search,search.fields['code']);search.fields['name'].setText(data['name']);snap('search_name',search,search.fields['name']);snap('search_run',search,search.search_button);search.search()
    r=search.table.visualItemRect(search.table.item(0,1));r.translate(search.table.viewport().mapTo(search,QPoint()));snap('search_result',search,rect=r);search.hide()
    snap('sku_context',main,rect=rect)
    pos=main.table.visualItemRect(main.table.item(0,1)).center();sid=int(main.table.item(0,6).text());svc.set_sku_locked(sid,False)
    def menu_capture(menu,*args):
        shown(menu)
        for text,key in [('复制BOM','sku_copy'),('锁定SKU','sku_lock'),('取消锁定','sku_unlock')]:
            matches=[a for a in menu.actions() if a.text()==text]
            if matches:snap(key,menu,rect=menu.actionGeometry(matches[0]))
        menu.hide();return None
    with patch.object(QMenu,'exec_',menu_capture):main.sku_context_menu(pos)
    svc.set_sku_locked(sid,True)
    with patch.object(QMenu,'exec_',menu_capture):main.sku_context_menu(pos)
    from help_more_screenshots import generate as generate_more
    generate_more(locals())
    for w in dialogs:w.close();w.deleteLater()
    (out/'物料清单.xlsx').unlink(missing_ok=True)
    if set(manifest)!=set(GUIDE_KEYS):raise RuntimeError('教程标注资源不匹配：'+str(set(GUIDE_KEYS)^set(manifest)))
    (out/'actions.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
