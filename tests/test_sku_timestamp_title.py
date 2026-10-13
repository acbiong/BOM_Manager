import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from PyQt5.QtWidgets import QApplication, QFileDialog
from database.database import Database
from services.services import Services
from ui.main_window import MainWindow, MaterialWindow


class SkuTimestampTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name) / 'db'))
        self.s = Services(self.db)
        self.s.update_project({'project_code': 'PRJ', 'project_name': '项目甲'})
        self.root, self.other, self.unrelated, self.parent, self.child, self.alt = [
            self.s.create_material(dict(base_code=x, version='1', name=x, unit='pcs'))
            for x in ['R', 'O', 'U', 'P', 'C', 'A']]
        for mid in (self.root, self.other, self.unrelated):
            self.s.create_sku(mid)
        for mid in (self.root, self.other):
            self.s.save_bom(mid, [dict(material_id=self.parent, quantity=1, unit='pcs')])
        self.w = MainWindow(self.s)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.db.close)
        self.addCleanup(self.w.close)

    def reset_times(self):
        self.db.conn.execute("UPDATE materials SET updated_at='2000-01-01 00:00:00'")
        self.db.conn.commit()
        self.w.refresh()

    def assert_changed(self, *changed):
        for row in self.s.skus():
            self.assertEqual(row['updated_at'] != '2000-01-01 00:00:00', row['material_id'] in changed)
        self.assertEqual([self.w.table.item(i, 4).text() for i in range(3)],
                         [r['updated_at'] for r in self.s.skus()])

    def test_local_quantity_does_not_touch_other_skus(self):
        self.reset_times()
        self.s.save_bom(self.root, [dict(material_id=self.parent, quantity=2, unit='pcs')])
        self.assert_changed(self.root)

    def test_shared_bom_add_edit_alternate_delete_updates_linked_skus(self):
        for items in (
            [dict(material_id=self.child, quantity=1, unit='pcs')],
            [dict(material_id=self.child, quantity=2, unit='pcs')],
            [dict(material_id=self.child, quantity=2, unit='pcs', alternate_material_ids=[self.alt])],
            [],
        ):
            with self.subTest(items=items):
                self.reset_times()
                self.s.save_bom(self.parent, items)
                self.assert_changed(self.root, self.other)

    def test_shared_descendant_saved_from_sku_updates_both(self):
        self.reset_times()
        self.s.save_bom(self.root, [
            dict(material_id=self.parent, quantity=1, unit='pcs'),
            dict(material_id=self.child, parent_material_id=self.parent, quantity=1, unit='pcs')])
        self.assert_changed(self.root, self.other)

    def test_unchanged_save_and_preview_do_not_update_time(self):
        self.reset_times()
        self.s.save_bom(self.root, [dict(material_id=self.parent, quantity=1, unit='pcs')])
        self.s.save_bom(self.parent, [dict(material_id=self.child, quantity=1, unit='pcs')], preview=True)
        self.assert_changed()

    def test_sku_info_edit_updates_list_immediately(self):
        self.reset_times()
        self.s.update_material(self.root, dict(name='新SKU名称', unit='pcs'))
        self.assert_changed(self.root)
        self.assertEqual(self.w.table.item(0, 2).text(), '新SKU名称')

    def test_project_title_export_names_and_single_footer(self):
        self.w.show()
        self.app.processEvents()
        self.assertEqual(self.w.windowTitle(), 'PRJ 项目甲 BOM管理系统')
        self.assertTrue(self.w.statusBar().isHidden())
        self.assertTrue(self.w.count_label.isVisible())
        for label in (self.w.power_label, self.w.version_label):
            self.assertIs(label.parentWidget(), self.w.count_label.parentWidget())
            self.assertEqual(label.geometry().center().y(), self.w.count_label.geometry().center().y())
        mw = MaterialWindow(self.s, self.w)
        try:
            for callback, filename in ((self.w.export_database, 'PRJ 项目甲 资料库.xlsx'),
                                       (self.w.export_materials, 'PRJ 项目甲 物料库.xlsx'),
                                       (mw.export_materials, 'PRJ 项目甲 物料库.xlsx')):
                with patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')) as dialog:
                    callback()
                    self.assertEqual(Path(dialog.call_args.args[2]).name, filename)
        finally:
            mw.close()

    def test_rapid_saves_update_both_tables_and_linked_list(self):
        self.s.save_bom(self.parent,[dict(material_id=self.child,quantity=1,unit='pcs')])
        previous={row['material_id']:row['updated_at'] for row in self.s.skus()}
        for quantity in (2,3):
            self.s.save_bom(self.parent,[dict(material_id=self.child,quantity=quantity,unit='pcs')])
            current={row['material_id']:row['updated_at'] for row in self.s.skus()}
            for root in (self.root,self.other):
                self.assertGreater(current[root],previous[root])
                stored=self.db.conn.execute('SELECT updated_at FROM skus WHERE material_id=?',(root,)).fetchone()[0]
                self.assertEqual(stored,current[root])
            self.assertEqual(current[self.unrelated],previous[self.unrelated])
            displayed={int(self.w.table.item(i,5).text()):self.w.table.item(i,4).text() for i in range(self.w.table.rowCount())}
            for sku in self.s.skus():self.assertEqual(displayed[sku['id']],sku['updated_at'])
            previous=current
        self.s.save_bom(self.parent,[dict(material_id=self.child,quantity=3,unit='pcs')])
        self.assertEqual({row['material_id']:row['updated_at'] for row in self.s.skus()},previous)
