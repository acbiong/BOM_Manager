import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
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
 def test_font_live_preview_cancel_close_escape_and_reopen(self):
  from PyQt5.QtTest import QTest
  apply_font_size(11);save(self.config,11,DEFAULT_EXPORT_COLORS)
  original=self.config.path.read_bytes()
  existing=QLineEdit();dialog=SettingsDialog(self.config)
  try:
   for cancel in ('cancel','close','escape'):
    dialog.show();dialog.activateWindow();self.app.processEvents()
    self.assertEqual(dialog.font_size.value(),11)
    dialog.font_size.setValue(17);self.app.processEvents()
    created=QLineEdit()
    self.assertEqual(existing.font().pointSize(),17);self.assertEqual(created.font().pointSize(),17)
    self.assertEqual(self.config.path.read_bytes(),original)
    if cancel=='cancel':dialog.reject()
    elif cancel=='close':dialog.close()
    else:QTest.keyClick(dialog,Qt.Key_Escape)
    self.assertEqual(self.app.font().pointSize(),11)
    self.assertEqual(existing.font().pointSize(),11);self.assertEqual(created.font().pointSize(),11)
    self.assertEqual(self.config.path.read_bytes(),original);created.close()
   dialog.show();dialog.font_size.setValue(16);dialog.accept()
   self.assertEqual(load(self.config)[0],16)
   dialog.show();dialog.font_size.setValue(20);dialog.reject()
   self.assertEqual(self.app.font().pointSize(),16)
  finally:dialog.close();existing.close()
 def test_preview_defaults_and_failed_save_can_cancel(self):
  apply_font_size(13);save(self.config,13,DEFAULT_EXPORT_COLORS)
  original=self.config.path.read_bytes();dialog=SettingsDialog(self.config);dialog.show()
  try:
   dialog.defaults();self.assertEqual(self.app.font().pointSize(),10)
   self.assertEqual(self.config.path.read_bytes(),original)
   with patch('ui.settings_dialog.save',side_effect=OSError('write failed')),patch('ui.settings_dialog.QMessageBox.warning') as warning:
    dialog.accept();warning.assert_called_once()
   self.assertTrue(dialog.isVisible());dialog.reject()
   self.assertEqual(self.app.font().pointSize(),13);self.assertEqual(self.config.path.read_bytes(),original)
  finally:dialog.close()
 def test_ctrl_s_confirms_once_with_global_shortcut_handler(self):
  from ui.save_shortcut import install_save_shortcuts
  from PyQt5.QtTest import QTest
  manager=install_save_shortcuts(self.app)
  dialog=SettingsDialog(self.config);dialog.show();dialog.activateWindow();self.app.processEvents()
  try:
   dialog.font_size.setValue(15)
   with patch('ui.settings_dialog.save',wraps=save) as write:
    QTest.keyClick(dialog,Qt.Key_S,Qt.ControlModifier);self.app.processEvents();write.assert_called_once()
   self.assertFalse(dialog.isVisible());self.assertEqual(load(self.config)[0],15)
  finally:
   dialog.close();manager.shutdown()
   if hasattr(self.app,'_bom_save_shortcuts'):del self.app._bom_save_shortcuts
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
