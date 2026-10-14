import os,sys,tempfile,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from PyQt5.QtWidgets import QApplication,QDialog,QLabel
from PyQt5.QtCore import Qt
from database.database import Database
from services.services import Services
from ui.main_window import BomWindow,MaterialDialog

class BomEditMaterialTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_edit_root_child_cancel_validation_and_refresh(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Database(str(Path(tmp)/'db'));s=Services(db)
   root,child=[s.create_material(dict(base_code=x,version='100',name=x,unit='pcs')) for x in ('R','C')]
   s.create_sku(root);s.save_bom(root,[dict(material_id=child,quantity=2,unit='pcs',remark='保留备注')])
   w=BomWindow(s,root)
   try:
    item=w.root_item.child(0)
    def edit(dialog):
     self.assertIsInstance(dialog.e['base_code'],QLabel);self.assertIsInstance(dialog.e['version'],QLabel)
     dialog.e['name'].setText('新名称');dialog.e['grade'].setText('A级');return QDialog.Accepted
    with patch.object(MaterialDialog,'exec_',edit):w.edit_tree_material(item)
    self.assertEqual(s.material_snapshot(child)['name'],'新名称');self.assertEqual(s.material_snapshot(child)['grade'],'A级')
    self.assertTrue(w.refresh_action.isEnabled());self.assertFalse(w.dirty)
    self.assertEqual(s.bom(root)[0]['quantity'],2);self.assertEqual(s.bom(root)[0]['remark'],'保留备注')
    with patch.object(MaterialDialog,'exec_',return_value=QDialog.Rejected),patch.object(s,'update_material') as update:
     w.edit_tree_material(item);update.assert_not_called()
    with patch.object(MaterialDialog,'exec_',edit):w.edit_tree_material(w.root_item)
    self.assertEqual(s.material_snapshot(root)['name'],'新名称')
    with patch.object(MaterialDialog,'exec_',edit),patch.object(s,'update_material',side_effect=ValueError('保存失败')),patch('ui.main_window.QMessageBox.warning') as warning:
     w.edit_tree_material(item);warning.assert_called_once()
    data=dict(item.data(0,Qt.UserRole));data['_deleted']=True;item.setData(0,Qt.UserRole,data)
    with patch.object(MaterialDialog,'exec_') as execute:w.edit_tree_material(item);execute.assert_not_called()
   finally:w.dirty=False;w.close();db.close()
