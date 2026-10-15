import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QDialog,QLineEdit
from PyQt5.QtGui import QPalette,QColor
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow,MaterialWindow,BomWindow

class ThemeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_global_toggle_and_bom_edit_state(self):
  with tempfile.TemporaryDirectory() as td:
   db=Database(str(Path(td)/'test.db'));s=Services(db)
   root=s.create_material(dict(base_code='ROOT',version='1',name='根',unit='pcs'));child=s.create_material(dict(base_code='CHILD',version='1',name='子',unit='pcs'));s.save_bom(root,[dict(material_id=child,quantity=1,unit='pcs')])
   main=MainWindow(s);material=MaterialWindow(s,main);bom=BomWindow(s,root,main)
   try:
    main.set_theme(False);self.assertEqual(main.version_label.text(),'版本 '+main.version);self.assertEqual(main.count_label.text(),'共计0个SKU')
    corner=main.menuBar().cornerWidget(Qt.TopRightCorner);self.assertIs(corner.layout().itemAt(corner.layout().count()-1).widget(),main.theme_button)
    node=bom.root_item.child(0);bom.show_item_info(node);bom.fields['quantity'].setValue(2.0)
    self.assertEqual(node.foreground(0).color(),QColor('#9a6700'));self.assertTrue(bom.dirty)
    main.theme_button.click();self.app.processEvents()
    for widget in (main,material,bom):self.assertEqual(widget.palette().color(QPalette.Window),QColor('#24262b'))
    dialog=QDialog(main);field=QLineEdit(dialog);self.assertEqual(field.palette().color(QPalette.Base),QColor('#1c1e22'));dialog.close()
    self.assertIn('月亮',main.theme_button.toolTip());self.assertFalse(main.theme_button.icon().isNull())
    main.theme_button.click();self.app.processEvents();self.assertEqual(bom.palette().color(QPalette.Window),QColor('#f5f6f8'));self.assertEqual(node.text(1),'2');self.assertTrue(bom.dirty);self.assertIn('太阳',main.theme_button.toolTip())
   finally:bom.dirty=False;bom.close();material.close();main.set_theme(False);main.close();db.close()
