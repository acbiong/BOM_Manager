import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QPlainTextEdit
from PyQt5.QtCore import QRect
from PyQt5.QtGui import QImage,QPainter
from database.database import Database
from services.services import Services
from ui.main_window import MaterialWindow,BomWindow

class HeaderBomLayoutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_header_animation_title_menu_and_wrapping_draft(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));svc=Services(db)
   svc.update_project(dict(project_code='PRJ',project_name='项目名称'))
   root=svc.create_material(dict(base_code='SKU',version='100',name='SKU scrolling header ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789 这是滚动显示的长物料名称'*8,unit='pcs'))
   child=svc.create_material(dict(base_code='PART',version='100',name='子物料',description='很长的规格描述'*30,unit='pcs'))
   sid=svc.create_sku(root);svc.save_bom(root,[dict(material_id=child,quantity=1,unit='pcs')])
   library=MaterialWindow(svc);bom=BomWindow(svc,root)
   try:
    self.assertEqual(library.windowTitle(),'PRJ 项目名称 物料库')
    self.assertEqual([a.text() for a in library.menuBar().actions()][-2:],['导出模板','查找物料'])
    library._selected_skus={sid};library.refresh();library.show();self.app.processEvents()
    library.t.horizontalScrollBar().setValue(library.t.horizontalScrollBar().maximum());self.app.processEvents()
    header=library.t.horizontalHeader();header.timer.stop()
    # Paint the SKU section explicitly: native Windows viewport grabs may
    # reuse a cached backing store and never invoke the animation painter.
    column=header.first_sku_column
    self.assertEqual(column,len(library._base_column_labels))
    self.assertIn('SKU100',header.model().headerData(column,1))
    self.assertFalse(header.isSectionHidden(column))
    def frame(elapsed):
     header.clock=SimpleNamespace(elapsed=lambda:elapsed)
     result=QImage(header.sectionSize(column),header.height(),QImage.Format_ARGB32)
     result.fill(0);painter=QPainter(result)
     try:header.paintSection(painter,QRect(0,0,result.width(),result.height()),column)
     finally:painter.end()
     return result
    first=frame(0);second=frame(2500)
    if first==second:
     output=Path(__file__).parents[1]/'test_reports';output.mkdir(exist_ok=True)
     first.save(str(output/'header_frame0.png'));second.save(str(output/'header_frame2500.png'))
    self.assertNotEqual(first,second,f'size={first.width()}x{first.height()}, font={header.font().toString()}, text={header.model().headerData(column,1)!r}, style={header.style().objectName()}')
    header.hide();self.assertFalse(header.timer.isActive())
    bom.show();self.app.processEvents()
    self.assertEqual(bom.default_panel_width,bom.fontMetrics().horizontalAdvance('M')*100)
    sizes=bom.bom_splitter.sizes();self.assertLess(abs(sizes[0]-sizes[1]),50)
    self.assertTrue(bom.fields['description'].wordWrap())
    node=bom.root_item.child(0);bom.show_item_info(node)
    remark='这是一条很长的备注'*30
    bom.fields['remark'].setText(remark);bom.fields['position'].setText('位置一\n位置二')
    self.assertEqual(bom.fields['remark'].lineWrapMode(),QPlainTextEdit.WidgetWidth)
    self.assertTrue(bom.dirty)
    bom.show_item_info(bom.root_item);bom.show_item_info(node)
    self.assertEqual(bom.fields['remark'].text(),remark)
    self.assertEqual(bom.fields['position'].text(),'位置一\n位置二')
   finally:bom.dirty=False;bom.close();library.close();db.close()
