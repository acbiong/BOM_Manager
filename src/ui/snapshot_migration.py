"""Migrate existing effective graphs without replacing any historical variant."""
from PyQt5.QtWidgets import QMessageBox
from ui.interactive_windows import QMessageBox
from services.snapshot_bom import migrate,enabled

def prepare_snapshot_bom(db,parent=None):
    was_migrated=enabled(db)
    try:
        migrate(db)
        from services.current_catalog import initialize
        initialize(db)
        from services.services import Services
        from services.bom_maintenance import cleanup_orphan_boms
        cleanup_orphan_boms(Services(db),backup=True,compact=True)
        from services.material_history import initialize as initialize_material_history
        initialize_material_history(db)
        count=db.conn.execute('SELECT COUNT(*) FROM bom_revision_legacy_conflicts').fetchone()[0]
        if count and not was_migrated:QMessageBox.information(parent,'历史BOM校验','已完整保留现有各历史版本结构，并创建迁移前备份。\n发现'+str(count)+'项历史父物料版本对应不同子料基础编码的情况；编辑保存这些BOM时将要求选择父物料新版本，旧历史记录不会被自动改写。')
        return True
    except Exception as error:
        QMessageBox.warning(parent,'BOM存储迁移失败',str(error));return False
