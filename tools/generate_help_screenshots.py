#!/usr/bin/env python3
"""Build-time help screenshots from a real project database; never run by the app."""
import os, shutil, sys, tempfile, sqlite3
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
from PyQt5.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
CONFIG=Path(os.environ.get('BOM_HELP_CONFIG','/home/biong/Documents/BOM/config.ini')).expanduser()
OUT=Path(os.environ.get('BOM_HELP_OUTPUT',str(ROOT/'.tmp/help_screenshots')))

def capture(widget,path):
    widget.show(); QApplication.processEvents(); pix=widget.grab()
    if pix.isNull(): raise RuntimeError('无法截取帮助页面：'+str(path))
    pix.save(str(path),'PNG')

def main():
    from config.config_service import ConfigService
    from config.project_registry import ProjectRegistry
    from database.database import Database
    from services.services import Services
    if not CONFIG.is_file():
        if 'BOM_HELP_CONFIG' in os.environ:raise SystemExit('指定的帮助截图配置不存在：'+str(CONFIG))
        shipped=ROOT/'resources/help_screenshots'
        from ui.help_guides import GUIDE_KEYS
        if any(not (shipped/(key+'.png')).is_file() for key in GUIDE_KEYS):raise SystemExit('缺少随源码提供的教程标注截图')
        OUT.mkdir(parents=True,exist_ok=True)
        for image in shipped.iterdir():
            if image.suffix in ('.png','.json'):shutil.copy2(image,OUT/image.name)
        print('使用随源码提供的静态帮助截图');return
    from config.config_service import read_config_file
    source_config=ConfigService(CONFIG.parent); raw=read_config_file(CONFIG)
    records=[dict(raw[section]) for section in raw.sections() if section.startswith('project:')]
    if raw.get('database','path',fallback=''):records.insert(0,{'path':raw['database']['path']})
    dbpath=None
    for record in records:
        try:
            p=source_config.resolve_path(record.get('path',''))
            if p.is_file() and p.stat().st_size: dbpath=p;break
        except (OSError,ValueError): pass
    if dbpath is None: raise SystemExit('帮助截图配置中没有可用数据库')
    OUT.mkdir(parents=True,exist_ok=True)
    for old in OUT.glob('*.png'):old.unlink()
    with tempfile.TemporaryDirectory(prefix='bom-help-build-') as tmp:
        demo_db_path=Path(tmp)/'demo.db'
        source=sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True);target=sqlite3.connect(demo_db_path)
        try:source.backup(target)
        finally:target.close();source.close()
        cfg=ConfigService(tmp); db=Database(str(demo_db_path)); svc=Services(db,cfg)
        from ui.main_window import MainWindow,MaterialDialog,NewSkuDialog,MaterialHeaderMappingDialog
        from ui.material_search import MaterialSearchDialog
        app=QApplication.instance() or QApplication([])
        from version import get_version
        main=MainWindow(svc,get_version());main.show();QApplication.processEvents()
        capture(main,OUT/'sku_overview.png')
        main.show_materials();materials=main._materials;capture(materials,OUT/'material_library.png')
        row=svc.db.conn.execute('SELECT id FROM skus ORDER BY id LIMIT 1').fetchone()
        bom=main.open_bom_id(row['id']) if row else None
        capture(bom or main,OUT/'bom_window.png')
        capture(main.menuBar(),OUT/'menu_theme.png')
        first=svc.db.conn.execute('SELECT * FROM materials ORDER BY id LIMIT 1').fetchone();data=dict(first) if first else {}
        dialog=MaterialDialog(main,data=data,readonly_keys={'base_code','version'});dialog.setWindowTitle('实际：新建/编辑物料');capture(dialog,OUT/'step02_material.png');dialog.close();dialog.deleteLater()
        headers=['物料基础编码','物料版本号','物料名称','物料规格','单位','物料等级','M/P'];rows=[tuple(data.get(k) or '' for k in ('base_code','version','name','description','unit','grade','mp_flag'))]
        dialog=MaterialHeaderMappingDialog('帮助中心示例.xlsx',headers,[],main,preview_rows=rows);capture(dialog,OUT/'step03_mapping.png');dialog.close();dialog.deleteLater()
        dialog=NewSkuDialog(svc,main);dialog.setWindowTitle('实际：新建SKU');capture(dialog,OUT/'step04_sku.png');dialog.close();dialog.deleteLater()
        if bom:
            capture(bom.tree,OUT/'step05_bom_tree.png');capture(bom.tree,OUT/'step06_bom_edit.png');capture(bom.info_scroll,OUT/'step07_bom_info.png');capture(bom.tree,OUT/'step09_bom_lock.png')
        else:
            capture(main,OUT/'step05_bom_tree.png');capture(main,OUT/'step06_bom_edit.png');capture(main,OUT/'step07_bom_info.png');capture(main,OUT/'step09_bom_lock.png')
        capture(main,OUT/'step01_project.png');capture(main,OUT/'step08_export.png')
        search=MaterialSearchDialog(materials);capture(search,OUT/'step10_search.png');search.close();search.deleteLater()
        capture(materials.t,OUT/'tip01_filter.png');capture(bom.tree if bom else main,OUT/'tip02_clipboard.png');capture(bom.tree if bom else main,OUT/'tip03_colors.png');capture(bom.info_scroll if bom else main,OUT/'tip04_shared.png');capture(materials,OUT/'tip05_mapping.png');capture(main,OUT/'tip06_theme.png')
        from help_action_screenshots import generate
        generate(OUT,main,materials,bom,svc)
        if bom: bom.dirty=False;bom.close()
        materials.close();main.close();db.close()
    expected=['sku_overview','material_library','bom_window','menu_theme']+[f'step{i:02d}_{x}' for i,x in [(1,'project'),(2,'material'),(3,'mapping'),(4,'sku'),(5,'bom_tree'),(6,'bom_edit'),(7,'bom_info'),(8,'export'),(9,'bom_lock'),(10,'search')]]+['tip%02d_%s'%v for v in [(1,'filter'),(2,'clipboard'),(3,'colors'),(4,'shared'),(5,'mapping'),(6,'theme')]]
    from ui.help_guides import GUIDE_KEYS
    expected+=GUIDE_KEYS
    missing=[x for x in expected if not (OUT/(x+'.png')).is_file()]
    if missing:raise SystemExit('缺少帮助截图：'+','.join(missing))
    print(f'帮助静态截图已生成：{len(expected)}张，数据源：{dbpath}')
if __name__=='__main__':main()
