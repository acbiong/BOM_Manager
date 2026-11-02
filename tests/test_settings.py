import os,sys,tempfile,unittest
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QLineEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette,QColor
from config.config_service import ConfigService
from config.appearance import load,save,DEFAULT_EXPORT_COLORS
from database.database import Database
from services.services import Services
from services.bom_colors import save as save_rows
from ui.settings_dialog import SettingsDialog
from ui.theme import apply_theme,apply_font_size
from ui.main_window import MainWindow,BomWindow
from openpyxl import Workbook

class SettingsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.config=ConfigService(self.tmp.name);self.size=self.app.font().pointSizeF()
 def tearDown(self):
  apply_theme(False);apply_font_size(self.size);self.tmp.cleanup()
 def test_persistence_cancel_defaults_and_validation(self):
  self.assertEqual(load(self.config),(10,DEFAULT_EXPORT_COLORS))
  d=SettingsDialog(self.config);d.font_size.setValue(16);d.set_color(0,'#123456');d.reject()
  self.assertEqual(load(self.config),(10,DEFAULT_EXPORT_COLORS))
  d.accept();self.assertEqual(load(ConfigService(self.tmp.name)),(16,['#123456',*DEFAULT_EXPORT_COLORS[1:]]))
  d.defaults();d.accept();self.assertEqual(load(self.config),(10,DEFAULT_EXPORT_COLORS));d.close()
  cfg=self.config.load();cfg['ui']['font_size']='invalid';cfg['ui']['bom_export_level_colors']='["wrong"]';self.config.save(cfg)
  self.assertEqual(load(self.config),(10,DEFAULT_EXPORT_COLORS))
  with self.assertRaises(ValueError):save(self.config,30,DEFAULT_EXPORT_COLORS)
 def test_export_levels_custom_override_and_no_database_changes(self):
  db=Database(str(Path(self.tmp.name)/'db'));s=Services(db,self.config)
  try:
   mids=[s.create_material(dict(base_code=str(i),version='100',name=str(i),unit='pcs')) for i in range(7)]
   for a,b in zip(mids,mids[1:]):s.save_bom(a,[dict(material_id=b,quantity=1,unit='pcs')])
   colors=['#111111','#222222','#333333','#444444','#eeeeee'];save(self.config,12,colors)
   with db.transaction():save_rows(s,[(mids[1],mids[2],'#abcdef')])
   before=list(db.conn.iterdump());wb=Workbook();s.write_bom_sheet(wb.active,mids[0])
   expected=['111111','222222','abcdef','444444','eeeeee','eeeeee','eeeeee']
   self.assertEqual([wb.active.cell(r,1).fill.fgColor.rgb[-6:] for r in range(2,9)],expected)
   self.assertEqual(wb.active['A2'].font.color.rgb[-6:],'ffffff')
   self.assertEqual(wb.active['A4'].font.color.rgb[-6:],'000000')
   self.assertEqual(list(db.conn.iterdump()),before);wb.close()
   save(self.config,12,['']*5);wb=Workbook();s.write_bom_sheet(wb.active,mids[0]);self.assertIsNone(wb.active['A2'].fill.patternType);self.assertEqual(wb.active['A4'].fill.fgColor.rgb[-6:],'abcdef');wb.close()
  finally:db.close()
 def test_settings_menu_nonmodal_font_and_dark_readability_preserve_draft(self):
  db=Database(str(Path(self.tmp.name)/'db'));s=Services(db,self.config)
  root=s.create_material(dict(base_code='R',version='100',name='Root',unit='pcs'));child=s.create_material(dict(base_code='C',version='100',name='Child',unit='pcs'));s.save_bom(root,[dict(material_id=child,quantity=1,unit='pcs')])
  main=MainWindow(s);bom=BomWindow(s,root,main)
  try:
   actions=[a.text() for a in main.menuBar().actions()];self.assertEqual(actions[-2:],['设置','关于'])
   main.show_settings();dialog=main._settings_dialog;self.assertEqual(dialog.windowModality(),Qt.NonModal)
   node=bom.root_item.child(0);bom.show_item_info(node);bom.fields['quantity'].setValue(2)
   before=bom.history_rows();dialog.font_size.setValue(14);dialog.accept()
   self.assertEqual(main.font().pointSize(),14);self.assertEqual(bom.font().pointSize(),14)
   self.assertEqual(bom.tree.font().pointSize(),14);self.assertEqual(node.font(0).pointSize(),14)
   field=QLineEdit();self.assertEqual(field.font().pointSize(),14);field.close()
   apply_theme(True);self.app.processEvents()
   self.assertEqual(node.foreground(0).color(),QColor('#ffd477'))
   self.assertEqual(self.app.palette().color(QPalette.Mid),QColor('#7e899c'))
   self.assertIn('gridline-color:#7e899c',self.app.styleSheet())
   self.assertEqual(bom.history_rows(),before);self.assertTrue(bom.dirty)
   apply_theme(False);self.app.processEvents();self.assertEqual(node.foreground(0).color(),QColor('#9a6700'))
  finally:bom.dirty=False;bom.close();main.close();db.close()
