import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from openpyxl import Workbook
from PyQt5.QtWidgets import QApplication,QDialog,QFileDialog,QMessageBox
from ui.interactive_windows import QFileDialog,QMessageBox
from config.config_service import ConfigService
from database.database import Database
from services.services import Services,MATERIAL_IMPORT_HEADERS
from ui.main_window import MaterialHeaderMappingDialog,MaterialImportResultDialog,MainWindow,MaterialWindow

class ImportMappingMemoryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.config=ConfigService(self.base);self.file=self.base/'source.xlsx'
 def tearDown(self):self.tmp.cleanup()
 def write(self,headers,row=None):
  wb=Workbook();wb.active.append(headers)
  if row:wb.active.append(row)
  wb.save(self.file);wb.close()
 def dialog(self,headers,bom=False,config=None):
  self.write(headers)
  return MaterialHeaderMappingDialog(self.file,headers,[],required=Services.BOM_HEADERS if bom else None,config_service=config or self.config)
 def test_reopen_restores_by_name_across_column_order_and_explicit_blank(self):
  headers=['客户编码']+MATERIAL_IMPORT_HEADERS[1:]
  first=self.dialog(headers)
  try:
   first.combos['物料基础编码'].setCurrentText('客户编码');first.combos['物料等级'].setCurrentIndex(0);first.combos['M/P'].setCurrentIndex(0)
   first.validate_mapping();self.assertEqual(first.result(),QDialog.Accepted)
  finally:first.close()
  second=self.dialog(list(reversed(headers)),config=ConfigService(self.base))
  try:
   self.assertEqual(second.mapping()['物料基础编码'],'客户编码');self.assertEqual(second.mapping()['M/P'],'');self.assertEqual(second.mapping()['物料等级'],'')
  finally:second.close()
 def test_missing_remembered_header_is_unmapped_not_same_name_fallback(self):
  mapping={h:h for h in MATERIAL_IMPORT_HEADERS};mapping['物料名称']='旧名称列';self.config.save_import_mapping('materials',mapping)
  dialog=self.dialog(MATERIAL_IMPORT_HEADERS)
  try:
   self.assertEqual(dialog.mapping()['物料名称'],'')
   with patch.object(QMessageBox,'warning') as warning:dialog.validate_mapping();warning.assert_called_once()
   self.assertEqual(self.config.import_mapping('materials'),mapping)
   dialog.combos['物料名称'].setCurrentText('物料名称');dialog.reject()
   self.assertEqual(self.config.import_mapping('materials'),mapping)
  finally:dialog.close()
 def test_bom_alternate_groups_and_material_memory_are_independent(self):
  self.config.save_import_mapping('materials',{'物料基础编码':'客户编码'})
  headers=Services.BOM_HEADERS+['替代码','替版本']
  dialog=self.dialog(headers,bom=True)
  try:
   dialog.add_alternate_mapping();dialog.add_alternate_mapping();dialog.remove_alternate_mapping('替代料1编码')
   dialog.combos['替代料2编码'].setCurrentText('替代码');dialog.combos['替代料2版本号'].setCurrentText('替版本');dialog.validate_mapping()
   self.assertEqual(dialog.result(),QDialog.Accepted)
  finally:dialog.close()
  second=self.dialog(Services.BOM_HEADERS+['替代码'],bom=True)
  try:
   self.assertEqual(second.alternate_groups,[['替代料2编码','替代料2版本号']])
   self.assertEqual(second.mapping()['替代料2编码'],'替代码');self.assertEqual(second.mapping()['替代料2版本号'],'')
   second.remove_alternate_mapping('替代料2编码');second.validate_mapping()
   self.assertNotIn('替代料2编码',self.config.import_mapping('bom'))
   self.assertEqual(self.config.import_mapping('materials'),{'物料基础编码':'客户编码'})
  finally:second.close()
 def test_material_ui_uses_memory_before_automatic_same_name_matching(self):
  headers=MATERIAL_IMPORT_HEADERS+['客户编码']
  self.write(headers,['WRONG','1','名称','','pcs','等级','P','厂家','','RIGHT'])
  mapping={h:h for h in MATERIAL_IMPORT_HEADERS};mapping['物料基础编码']='客户编码';self.config.save_import_mapping('materials',mapping)
  db=Database(str(self.base/'db'));s=Services(db,self.config);main=MainWindow(s);material=MaterialWindow(s)
  try:
   for window in (main,material):
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.file),'')),patch.object(MaterialImportResultDialog,'exec_',return_value=QDialog.Accepted),patch.object(MaterialHeaderMappingDialog,'exec_') as mapping_ui:
     window.import_materials();mapping_ui.assert_not_called()
   self.assertEqual([r['base_code'] for r in s.materials()],['RIGHT'])
  finally:material.close();main.close();db.close()
 def test_corrupt_memory_falls_back_to_initial_matching(self):
  cfg=self.config.load();cfg['import_mappings']={'materials':'["invalid"]','bom':'broken'};self.config.save(cfg)
  self.assertEqual(self.config.import_mapping('materials'),{});self.assertEqual(self.config.import_mapping('bom'),{})
  dialog=self.dialog(MATERIAL_IMPORT_HEADERS)
  try:self.assertEqual(dialog.mapping()['物料名称'],'物料名称')
  finally:dialog.close()
 def test_mapping_selection_color_for_material_bom_and_external_with_memory(self):
  for kind in ('materials','bom','compare_bom'):
   with self.subTest(kind=kind):
    self.config.save_import_mapping(kind,{'物料名称':'缺失列'})
    dialog=MaterialHeaderMappingDialog('unused.xlsx',['物料名称','物料基础编码'],[],required=None if kind=='materials' else ['物料名称','物料基础编码'],preview_rows=[],config_service=self.config,mapping_kind=kind)
    try:
     name=dialog.combos['物料名称'];code=dialog.combos['物料基础编码']
     self.assertEqual(name.currentIndex(),0);self.assertEqual(name.styleSheet(),'');self.assertIn('#d9f2df',code.styleSheet())
     name.setCurrentText('物料名称');self.assertIn('#d9f2df',name.styleSheet());name.setCurrentIndex(0);self.assertEqual(name.styleSheet(),'')
     if kind!='materials':
      dialog.add_alternate_mapping();alternate=dialog.combos['替代料1编码'];self.assertEqual(alternate.styleSheet(),'')
      alternate.setCurrentText('物料基础编码');self.assertIn('#d9f2df',alternate.styleSheet());alternate.setCurrentIndex(0);self.assertEqual(alternate.styleSheet(),'')
    finally:dialog.close()
