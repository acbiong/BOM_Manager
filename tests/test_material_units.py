import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication
from openpyxl import Workbook
from config.config_service import ConfigService,DEFAULT_MATERIAL_UNITS
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow,MaterialWindow,MaterialDialog

class MaterialUnitsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name); self.config=ConfigService(self.base); self.db=Database(str(self.base/'test.db'))
 def tearDown(self):self.db.close(); self.tmp.cleanup()
 def test_defaults_migration_and_restoration_preserve_database(self):
  self.config.path.write_text('[database]\npath = /custom/data.db\n[other]\nkey = keep\n',encoding='utf-8')
  self.assertEqual(self.config.material_units(),list(DEFAULT_MATERIAL_UNITS))
  cfg=self.config.load(); cfg['materials']['units']='箱,包'; self.config.save(cfg)
  self.assertEqual(self.config.material_units(),['箱','包'])
  self.config.restore_material_units(); cfg=self.config.load()
  self.assertEqual(cfg['database']['path'],'/custom/data.db'); self.assertEqual(cfg['other']['key'],'keep')
  cfg.remove_option('materials','units'); self.config.save(cfg); self.assertEqual(self.config.material_units(),list(DEFAULT_MATERIAL_UNITS))
  cfg=self.config.load();cfg['materials']['units']=' , ， ';self.config.save(cfg);self.assertEqual(self.config.material_units(),list(DEFAULT_MATERIAL_UNITS))
 def test_default_new_units_create_and_import(self):
  service=Services(self.db,self.config)
  for index,unit in enumerate(['米','M','克','g']):service.create_material(dict(base_code=f'A{index}',version='1',name='物料',unit=unit))
  workbook=Workbook(); workbook.active.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN'])
  for index,unit in enumerate(['米','M','克','g']):workbook.active.append([f'B{index}','1','物料','',unit,'厂家',''])
  path=self.base/'units.xlsx';workbook.save(path);workbook.close()
  ok,fail=service.import_materials(path);self.assertEqual(len(ok),4);self.assertEqual(fail,[])
 def test_custom_units_shared_by_ui_create_update_and_import(self):
  cfg=self.config.load();cfg['materials']['units']='箱, 箱，包, M, m';self.config.save(cfg)
  service=Services(self.db,self.config);self.assertEqual(service.UNITS,['箱','包','M','m'])
  main=MainWindow(service); material=MaterialWindow(service)
  try:
   for parent in (main,material):
    dialog=MaterialDialog(parent);self.assertEqual([dialog.unit.itemText(i) for i in range(dialog.unit.count())],service.UNITS);dialog.close()
   mid=service.create_material(dict(base_code='X',version='1',name='物料',unit='箱'))
   service.update_material(mid,dict(name='物料',unit='包'))
   with self.assertRaises(ValueError):service.update_material(mid,dict(name='物料',unit='pcs'))
   with self.assertRaises(ValueError):service.create_material(dict(base_code='Z',version='1',name='物料',unit='pcs'))
   wb=Workbook();wb.active.append(['物料基础编码','物料版本号','物料名称','物料规格描述','单位','物料制造商','物料MPN']);wb.active.append(['OK','1','物料','','箱','厂家','']);wb.active.append(['BAD','1','物料','','pcs','厂家','']);path=self.base/'custom.xlsx';wb.save(path);wb.close()
   ok,fail=service.import_materials(path);self.assertEqual(ok,['OK']);self.assertEqual(fail[0][1],'BAD')
  finally:material.close();main.close()
