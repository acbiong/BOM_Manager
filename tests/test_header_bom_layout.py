import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QPlainTextEdit
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
    header.clock=SimpleNamespace(elapsed=lambda:0);first=header.viewport().grab().toImage()
    header.clock=SimpleNamespace(elapsed=lambda:2500);second=header.viewport().grab().toImage()
    self.assertNotEqual(first,second)
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
