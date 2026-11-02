import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if sys.platform == 'win32' else 'offscreen')
sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication
from database.database import Database
from services.services import Services
from services import material_history as history
from ui.material_history import MaterialHistoryDialog, HISTORY_DIFF_ROLE
from ui.material_history_diff import compare, pair_children
from ui.bom_change_style import ADDED, DELETED, MODIFIED, MOVED, level_background


def example(directory):
    """Stored snapshots with metadata, relation, subtree and alternate changes."""
    db = Database(str(Path(directory) / 'history.db'))
    svc = Services(db)
    ids = {code: svc.create_material(dict(base_code=code, version='100', name=name, unit='pcs'))
           for code, name in [('R', '控制组件'), ('C', '主控板'), ('D', '旧组件'),
                              ('L', '组件内芯'), ('N', '新组件'), ('A', '旧替代料'),
                              ('B', '新替代料 <B> & 规格'), ('K', '固定件')]}
    svc.save_bom(ids['D'], [dict(material_id=ids['L'], quantity=1, unit='pcs')])
    svc.save_bom(ids['R'], [dict(material_id=ids[c], quantity=1, unit='pcs', position=c,
                                alternate_material_ids=[ids['A']] if c == 'C' else [])
                           for c in ('C', 'D', 'K')])
    svc.create_sku(ids['R'])
    from services.snapshot_bom import migrate
    from services.current_catalog import initialize
    migrate(db); initialize(db); history.initialize(db)
    old = history.read(svc, ids['R'], 100)
    with db.transaction():
        child = history.read(svc, ids['C'], 100)
        cv = history.record(db.conn, ids['C'], dict(child['attributes'], name='主控板改版', description='新增防护'), [])
        edges = [dict(old['children'][2]),
                 dict(old['children'][0], history_version=cv, quantity=2.5, unit='套', position='U1', remark='防护装配',
                      alternates=[dict(material_id=ids['B'], history_version=100)]),
                 dict(material_id=ids['N'], history_version=100, quantity=1, unit='pcs', position='N', remark='', alternates=[])]
        history.record(db.conn, ids['R'], old['attributes'], edges)
    return db, svc, ids


class MaterialHistoryDiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ui.theme import apply_theme
        apply_theme(False)
        self.temp = tempfile.TemporaryDirectory()
        self.db, self.s, self.ids = example(self.temp.name)
        self.windows = []

    def tearDown(self):
        for w in self.windows: w.close()
        self.db.close(); self.temp.cleanup()

    def viewer(self, version=101):
        w = MaterialHistoryDialog(self.s, self.ids['R'], version)
        self.windows.append(w)
        return w

    def test_snapshot_fields_relations_and_removed_subtree(self):
        diff, previous = compare(self.s, self.ids['R'], 101)
        self.assertEqual(previous, 100)
        child = diff['children'][1]
        self.assertEqual(child['fields'], {'name', 'description'})
        self.assertEqual(child['columns'], {1, 2, 3, 4, 5, 6, 7})
        self.assertTrue(diff['children'][2]['added'])
        removed = diff['children'][3]
        self.assertTrue(removed['deleted'])
        self.assertTrue(removed['children'][0]['deleted'])
        self.assertEqual([a['state'] for a in child['alternatives']], ['added', 'deleted'])

    def test_first_version_is_unmarked_baseline(self):
        w = self.viewer(100)
        self.assertIsNone(w.previous_version)
        root = w.tree.topLevelItem(0)
        for item in [root] + [root.child(i) for i in range(root.childCount())]:
            data = item.data(0, HISTORY_DIFF_ROLE)
            self.assertFalse(data['added'] or data['deleted'] or data['moved'] or data['columns'] or data['fields'])
            self.assertTrue(all(not a['state'] for a in data['alternatives']))

    def test_nearest_existing_previous_with_gap(self):
        self.db.conn.execute('UPDATE material_histories SET history_version=105 WHERE material_id=? AND history_version=101', (self.ids['R'],))
        diff, previous = compare(self.s, self.ids['R'], 105)
        self.assertEqual(previous, 100)
        self.assertEqual(diff['children'][1]['fields'], {'name', 'description'})

    def test_child_compares_to_root_snapshot_not_child_predecessor(self):
        child = history.read(self.s, self.ids['C'], 101)
        with self.db.transaction():
            history.record(self.db.conn, self.ids['C'], dict(child['attributes'], name='另一个BOM的中间状态'), [])
            cv = history.record(self.db.conn, self.ids['C'], dict(child['attributes'], name='最终状态'), [])
            root = history.read(self.s, self.ids['R'], 101)
            edges = [dict(e, history_version=cv) if e['material_id'] == self.ids['C'] else e for e in root['children']]
            rv = history.record(self.db.conn, self.ids['R'], root['attributes'], edges)
        diff, _ = compare(self.s, self.ids['R'], rv)
        self.assertEqual(diff['children'][1]['previous']['history_version'], 101)

    def test_insertion_is_not_reorder_and_duplicate_positions_match(self):
        def e(mid, pos=''): return dict(material_id=mid, position=pos)
        paired, missing, moved = pair_children([e(9), e(1), e(2)], [e(1), e(2)])
        self.assertEqual(paired, {1: 0, 2: 1}); self.assertFalse(missing or moved)
        paired, missing, moved = pair_children([e(1, 'B'), e(1, 'new')], [e(1, 'A'), e(1, 'B')])
        self.assertEqual(paired, {0: 1, 1: 0}); self.assertFalse(missing); self.assertTrue(moved)

    def test_colors_fonts_and_deleted_reference_label(self):
        w = self.viewer(); root = w.tree.topLevelItem(0)
        changed, added, deleted = root.child(1), root.child(2), root.child(3)
        self.assertEqual(changed.foreground(0).color(), QColor(MODIFIED))
        self.assertTrue(changed.font(1).bold()); self.assertFalse(changed.font(0).bold())
        self.assertEqual(added.foreground(0).color(), QColor(ADDED))
        self.assertEqual(deleted.foreground(0).color(), QColor(DELETED)); self.assertTrue(deleted.font(0).strikeOut())
        self.assertTrue(any(root.child(i).background(0).color() == QColor(MOVED) for i in range(2)))
        w.tree.setCurrentItem(deleted)
        self.assertIn('已删除的对照节点', w.reference_label.text())
        self.assertTrue(w.attribute_values['name'].font().strikeOut())

    def test_properties_tooltips_alternates_and_html_escaping(self):
        w = self.viewer(); child = w.tree.topLevelItem(0).child(1); w.tree.setCurrentItem(child)
        self.assertEqual(w.attribute_values['unit'].text(), '套')
        for key in ('name', 'description', 'unit', 'quantity', 'position', 'remark', 'alternates'):
            self.assertTrue(w.attribute_values[key].font().bold(), key)
            self.assertEqual(w.attribute_values[key].palette().color(QPalette.WindowText), QColor(MODIFIED))
        rich = w.attribute_values['alternates'].text()
        self.assertIn('&lt;B&gt; &amp;', rich); self.assertIn('<s>', rich)
        self.assertIn('旧替代料', w.attribute_values['alternates'].toolTip())
        self.assertIn('旧替代料', child.toolTip(7))
        self.assertEqual(w.attribute_values['quantity'].toolTip(), '上一版本：1')

    def test_switch_clears_diff_and_view_is_readonly(self):
        before = '\n'.join(self.db.conn.iterdump()); changes = self.db.conn.total_changes
        w = self.viewer(); w.tree.setCurrentItem(w.tree.topLevelItem(0).child(1))
        for version in (100, 101, 100):
            w.version_combo.setCurrentIndex(w.version_combo.findData(version))
        self.assertEqual(w.tree.topLevelItem(0).childCount(), 3)
        w.tree.setCurrentItem(w.tree.topLevelItem(0).child(0))
        self.assertFalse(w.attribute_values['name'].font().bold())
        self.assertEqual(w.attribute_values['name'].toolTip(), '')
        self.assertNotIn('<s>', w.attribute_values['alternates'].text())
        self.assertEqual(self.db.conn.total_changes, changes)
        self.assertEqual('\n'.join(self.db.conn.iterdump()), before)

    def test_theme_recolors_without_database_reads(self):
        from ui.theme import apply_theme
        w = self.viewer(); w.show(); self.app.processEvents()
        w.tree.setCurrentItem(w.tree.topLevelItem(0).child(1))
        try:
            with patch.object(history, 'read', side_effect=AssertionError('theme reread')):
                apply_theme(True); self.app.processEvents()
                self.assertEqual(w.tree.topLevelItem(0).background(0).color(), level_background(0, True))
                self.assertEqual(w.tree.topLevelItem(0).child(2).foreground(0).color(), QColor('#85e6a2'))
                self.assertTrue(w.attribute_values['name'].font().bold())
                self.assertEqual(w.attribute_values['name'].palette().color(QPalette.WindowText), QColor('#ffd477'))
                apply_theme(False); self.app.processEvents()
                self.assertEqual(w.tree.topLevelItem(0).background(0).color(), level_background(0, False))
                self.assertTrue(w.attribute_values['name'].font().bold())
        finally: apply_theme(False)

    def test_added_subtree_and_changed_alternate_version(self):
        root = history.read(self.s, self.ids['R'], 101)
        alt = history.read(self.s, self.ids['B'], 100)
        with self.db.transaction():
            av = history.record(self.db.conn, self.ids['B'], dict(alt['attributes'], manufacturer='新厂商'), [])
            edges = [dict(e) for e in root['children']]
            edges[1] = dict(edges[1], alternates=[dict(material_id=self.ids['B'], history_version=av)])
            edges.append(dict(material_id=self.ids['D'], history_version=100, quantity=1, unit='pcs', position='D'))
            rv = history.record(self.db.conn, self.ids['R'], root['attributes'], edges)
        diff, _ = compare(self.s, self.ids['R'], rv)
        self.assertTrue(diff['children'][3]['children'][0]['added'])
        self.assertEqual(diff['children'][1]['alternatives'][0]['state'], 'modified')


if __name__ == '__main__': unittest.main()
