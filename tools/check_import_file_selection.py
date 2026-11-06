"""Check real Linux file chooser selection without touching business data."""
import sys,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QLineEdit,QAbstractItemView
from PyQt5.QtCore import QTimer
from ui.interactive_windows import QFileDialog
from ui.import_paths import import_selection,remember_bom_import,remember_material_import
from config.config_service import ConfigService
app=QApplication([]);out=Path('test_reports/import_file_native');out.mkdir(parents=True,exist_ok=True);checks=[]
with tempfile.TemporaryDirectory() as tmp:
 base=Path(tmp);folder=base/'中文 共享目录';folder.mkdir();config=ConfigService(base/'app')
 for kind,title,remember in [('bom','导入BOM',remember_bom_import),('materials','导入物料清单',remember_material_import)]:
  file=folder/(title+'.xlsx');file.touch();remember(config,file)
  def inspect():
   for d in app.topLevelWidgets():
    if isinstance(d,QFileDialog) and d.isVisible():
     edit=d.findChild(QLineEdit,'fileNameEdit')
     checks.append(dict(kind=kind,selected=d.selectedFiles(),filename=edit.text(),passed=d.selectedFiles()==[str(file)] and edit.text()==file.name))
     d.grab().save(str(out/(kind+'.png')));d.reject()
  QTimer.singleShot(500,inspect)
  QFileDialog.getOpenFileName(None,title,import_selection(config,kind),'Excel (*.xlsx)')
assert len(checks)==2 and all(c['passed'] for c in checks),checks
(out/'summary.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2));print('IMPORT_FILE_SELECTION_NATIVE_OK')
