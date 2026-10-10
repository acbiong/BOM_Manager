"""物料剪贴板：跨窗口共享物料身份，不复制未保存的BOM关系。编辑时间：2026-10-10。"""
import json
from pathlib import Path
from PyQt5.QtCore import QMimeData
from PyQt5.QtWidgets import QApplication

MIME = 'application/x-bom-manager-material'

def copy_material(svc, material_id):
    material = svc.material_snapshot(material_id)
    if not material:
        return
    payload = dict(database=str(Path(svc.db.path).resolve()), material_id=material_id,
                   base_code=material['base_code'], version=material['version'])
    mime = QMimeData()
    mime.setData(MIME, json.dumps(payload).encode('utf-8'))
    mime.setText(material['base_code'] + material['version'] + ' ' + material['name'])
    QApplication.clipboard().setMimeData(mime)

def clipboard_material(svc):
    mime = QApplication.clipboard().mimeData()
    if mime is None or not mime.hasFormat(MIME):
        return None
    try:
        payload = json.loads(bytes(mime.data(MIME)))
        if payload['database'] != str(Path(svc.db.path).resolve()):
            return None
        material = svc.material_snapshot(payload['material_id'])
        if material and all(material[k] == payload[k] for k in ('base_code', 'version')):
            return material
    except (ValueError, TypeError, KeyError):
        pass
    return None
