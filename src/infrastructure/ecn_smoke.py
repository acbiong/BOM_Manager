"""Packaged ECN persistence/export and literal compare clipboard checks."""
from pathlib import Path


def exercise_ecn(service,report_path):
    from PyQt5.QtCore import QPoint
    from PyQt5.QtWidgets import QApplication,QMenu
    from unittest.mock import patch
    from openpyxl import load_workbook
    from ui.sku_ecn import EcnDialog
    from ui.bom_compare import BomCompareDialog
    app=QApplication.instance()
    mid=service.create_material(dict(base_code='ECNSMOKE',version='100',name='ECN窗口验证',unit='pcs'))
    sid=service.create_sku(mid);copy=service.copy_sku_bom(sid)
    form=EcnDialog(('ECN-001','工程变更','内容第一行\n内容第二行'))
    try:
        form.show();app.processEvents()
        if app.platformName() not in ('offscreen','minimal'):
            from PyQt5.QtTest import QTest
            assert QTest.qWaitForWindowExposed(form,3000)
        assert form.grab().save(str(Path(report_path).with_suffix('.ecn.png')))
        service.update_sku_ecn(copy,*form.values())
    finally:form.close()
    path=Path(report_path).with_suffix('.ecn.xlsx');service.export_sku_list(path);book=load_workbook(path)
    try:
        assert book.sheetnames==['SKU清单','ECN']
        sheet=book['ECN'];column=next(c.column for c in sheet[1] if c.value=='ECNSMOKE100 ECN窗口验证')
        row=next(r[0].row for r in sheet.iter_rows(min_row=2) if r[1].value=='ECN-001')
        assert sheet.cell(row,column).value=='【101】\n内容第一行\n内容第二行'
        assert all(d.width<=30 for d in sheet.column_dimensions.values())
    finally:book.close()
    compare=BomCompareDialog(service)
    try:
        compare.left.setCurrentIndex(compare.left.findData(sid));compare.right.setCurrentIndex(compare.right.findData(copy));compare.compare()
        table=compare.tables[1]
        for label,expected in [('复制物料编码','ECNSMOKE100'),('复制物料名称','ECN窗口验证')]:
            with patch.object(QMenu,'exec_',lambda menu,*_,key=label:next(a for a in menu.actions() if a.text()==key)):
                compare.context_menu(table,table.model().index(0,0),QPoint())
            assert app.clipboard().text()==expected
    finally:compare.close()
    return ['ecn_window_persistence_matrix_export','compare_material_name_and_code_clipboard']
