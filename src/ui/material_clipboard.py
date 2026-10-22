"""物料剪贴板：共享物料身份及可选BOM关系属性快照；子BOM沿用最新物料库结构。"""
import json
from pathlib import Path
from PyQt5.QtCore import QMimeData
from PyQt5.QtWidgets import QApplication

MIME = 'application/x-bom-manager-material'

def copy_material(svc, material_id, relation=None):
    material = svc.material_snapshot(material_id)
    if not material:
        return False
    payload = dict(database=str(Path(svc.db.path).resolve()), material_id=material_id,
                   base_code=material['base_code'], version=material['version'])
    if relation is not None:
        payload["relation"] = relation
    mime = QMimeData()
    mime.setData(MIME, json.dumps(payload).encode('utf-8'))
    mime.setText(material['base_code'] + material['version'] + ' ' + material['name'])
    QApplication.clipboard().setMimeData(mime)
    return True

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


def clipboard_relation(svc):
    if clipboard_material(svc) is None:
        return None
    try:
        relation = json.loads(bytes(QApplication.clipboard().mimeData().data(MIME))).get('relation')
        if not isinstance(relation, dict):
            return None
        quantity = float(relation['quantity'])
        if not 0 < quantity <= 1e12:
            return None
        alternates = relation.get('alternate_material_ids', [])
        if not isinstance(alternates, list) or any(not isinstance(mid, int) or not svc.material_snapshot(mid) for mid in alternates):
            return None
        return dict(quantity=quantity, position=str(relation.get('position', '')),
                    remark=str(relation.get('remark', '')), alternate_material_ids=alternates)
    except (ValueError, TypeError, KeyError):
        return None


def copy_materials(svc, entries):
    payload=[]
    for mid,relation in entries:
        material=svc.material_snapshot(mid)
        if not material:return False
        payload.append(dict(material_id=mid,base_code=material['base_code'],version=material['version'],relation=relation))
    if not payload:return False
    mime=QMimeData();mime.setData(MIME,json.dumps(dict(database=str(Path(svc.db.path).resolve()),items=payload)).encode('utf-8'))
    mime.setText('\n'.join(p['base_code']+p['version'] for p in payload));QApplication.clipboard().setMimeData(mime);return True

def clipboard_entries(svc):
    mime=QApplication.clipboard().mimeData()
    if mime is None or not mime.hasFormat(MIME):return []
    try:
        payload=json.loads(bytes(mime.data(MIME)))
        if payload['database']!=str(Path(svc.db.path).resolve()):return []
        if 'items' not in payload:
            material=clipboard_material(svc)
            return [(material,clipboard_relation(svc))] if material else []
        result=[]
        for item in payload['items']:
            material=svc.material_snapshot(item['material_id'])
            if not material or any(material[k]!=item[k] for k in ('base_code','version')):return []
            relation=item.get('relation')
            if relation is not None:
                quantity=float(relation['quantity']);alternates=relation['alternate_material_ids']
                if not 0<quantity<=1e12 or not isinstance(alternates,list) or any(not isinstance(mid,int) or not svc.material_snapshot(mid) for mid in alternates):return []
                relation=dict(quantity=quantity,position=str(relation.get('position','')),remark=str(relation.get('remark','')),alternate_material_ids=alternates)
            result.append((material,relation))
        return result
    except (ValueError,TypeError,KeyError):return []
