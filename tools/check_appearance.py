"""Native settings/appearance smoke on disposable data; screenshots in reports."""
import sys,os,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'xcb'
from PyQt5.QtWidgets import QApplication,QDialogButtonBox
from PyQt5.QtTest import QTest
from PyQt5.QtCore import Qt
from database.database import Database
from config.config_service import ConfigService
from config.appearance import load
from services.services import Services
from ui.main_window import MainWindow
from ui.theme import apply_theme
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
out=Path('test_reports/appearance_native');out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
 db=Database(str(Path(temp)/'db'));svc=Services(db,ConfigService(temp))
 root=svc.create_material(dict(base_code='SKU',version='100',name='设置与主题验证',unit='pcs'))
 child=svc.create_material(dict(base_code='PART',version='100',name='物料文字与表格边界验证',unit='pcs'))
 svc.save_bom(root,[dict(material_id=child,quantity=2,unit='pcs')]);sid=svc.create_sku(root)
 main=MainWindow(svc);main.show();QTest.qWaitForWindowExposed(main)
 bom=main.open_bom_id(sid);main.show_materials();main.show_settings();dialog=main._settings_dialog
 try:
  assert QTest.qWaitForWindowExposed(dialog)
  assert dialog.windowModality()==Qt.NonModal
  baseline=app.font().pointSizeF();original=svc.config_service.path.read_bytes()
  dialog.font_size.setValue(16);app.processEvents()
  assert bom.tree.font().pointSize()==16
  assert svc.config_service.path.read_bytes()==original
  QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.Cancel),Qt.LeftButton)
  assert app.font().pointSizeF()==baseline
  main.show_settings();dialog.font_size.setValue(14);dialog.set_color(0,'#1b365d')
  before=list(db.conn.iterdump())
  QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.Save),Qt.LeftButton)
  app.processEvents();assert not dialog.isVisible();assert load(svc.config_service)[0]==14
  assert list(db.conn.iterdump())==before
  assert bom.tree.font().pointSize()==14
  for dark in (False,True):
   main.set_theme(dark);app.processEvents();main.show_settings()
   for name,window in [('settings',dialog),('sku',main),('bom',bom),('materials',main._materials)]:
    window.show();window.raise_();QTest.qWait(80);assert window.grab().save(str(out/(name+('_dark' if dark else '_light')+'.png')))
   dialog.reject()
  main.set_theme(False)
  (out/'summary.json').write_text(json.dumps(dict(passed=True,checks=['nonmodal','live_font_preview','cancel_restores_font','preview_does_not_write_config','actual_save','font_applied','config_persisted','database_unchanged','light_dark_windows'],screenshots=8),indent=2))
 finally:
  dialog.close();bom.dirty=False;bom.close();main.close();db.close()
print('APPEARANCE_NATIVE_OK')
