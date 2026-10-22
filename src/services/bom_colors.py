"""Persistent, scope-local BOM presentation colors; never material metadata."""
import re

def normalize(value):
    value=str(value or '').lower()
    if value and not re.fullmatch(r'#[0-9a-f]{6}',value):raise ValueError('无效的BOM背景颜色')
    return value

def foreground(value):
    rgb=[int(normalize(value)[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
    luminance=sum(v*w for v,w in zip(linear,(0.2126,0.7152,0.0722)))
    return '#000000' if (luminance+0.05)/0.05 >= 1.05/(luminance+0.05) else '#ffffff'

def colors(service):
    return {(r['parent_id'],r['material_id']):r['color'] for r in service.db.conn.execute('SELECT * FROM bom_row_colors WHERE scope_id=?',(getattr(service,'scope_id',0),))}

def save(service,entries):
    scope=getattr(service,'scope_id',0);previous=colors(service);changed=set()
    for parent,mid,value in entries:
        value=normalize(value)
        if previous.get((parent,mid),'')==value:continue
        changed.add(parent or mid)
        service.db.conn.execute('DELETE FROM bom_row_colors WHERE scope_id=? AND parent_id=? AND material_id=?',(scope,parent,mid))
        if value:service.db.conn.execute('INSERT INTO bom_row_colors VALUES(?,?,?,?)',(scope,parent,mid,value))
    if changed:
        from datetime import datetime
        stamp=datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S.%f')[:-4]
        if scope:service.db.conn.execute('UPDATE skus SET updated_at=? WHERE id=?',(stamp,scope))
        for parent in changed:service.publish({'type':'bom_changed','root':parent})

def prune(service):
    scope=getattr(service,'scope_id',0)
    valid={(r[0],r[1]) for r in service.db.conn.execute('SELECT parent_material_id,child_material_id FROM material_bom_items')}
    for parent,mid in colors(service):
        if parent and (parent,mid) not in valid:service.db.conn.execute('DELETE FROM bom_row_colors WHERE scope_id=? AND parent_id=? AND material_id=?',(scope,parent,mid))
