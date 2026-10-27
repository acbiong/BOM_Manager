from services.services import Services
from services.mirrors import MirrorDatabase

class MirrorServices(Services):
    def __init__(self,primary,sid):
        self.primary=primary;self.scope_id=int(sid);self.sku_id=int(sid)
        self.db=MirrorDatabase(primary.db,sid);self.config_service=primary.config_service;self.UNITS=primary.UNITS
    def skus(self):return [row for row in self.primary.skus() if row['id']==self.sku_id]
    def refresh_usage(self):
        row=self.db.conn.execute('SELECT material_id FROM skus WHERE id=?',(self.sku_id,)).fetchone()
        if row is None:return
        self.db.conn.execute('INSERT OR IGNORE INTO mirror_captured_materials VALUES(?,?)',(self.sku_id,row['material_id']))
        self.db.conn.execute('DELETE FROM mirror_material_usage WHERE sku_id=?',(self.sku_id,))
        for node in self.bom(row['material_id']):
            self.db.conn.execute('INSERT OR IGNORE INTO mirror_captured_materials VALUES(?,?)',(self.sku_id,node['material_id']))
            self.db.conn.execute('INSERT OR IGNORE INTO mirror_material_usage VALUES(?,?,?,?)',(self.sku_id,node['material_id'],node['parent_material_id'],'main'))
            for alternate in self.alternates(node['id']):
                self.db.conn.execute('INSERT OR IGNORE INTO mirror_material_usage VALUES(?,?,?,?)',(self.sku_id,alternate['material_id'],node['parent_material_id'],'alternate'))

    def ensure_material_bom(self, material_id):
        """Capture a newly selected material's definitions without changing the SKU tree.

        Already captured parents (including empty leaves) never follow global edits.
        """
        from services.snapshot_bom import enabled,template_service
        source=template_service(self.primary,material_id) if enabled(self.db) else self.primary
        with self.db.transaction():
            pending=[material_id]
            while pending:
                parent=pending.pop()
                if self.db.conn.execute('SELECT 1 FROM mirror_captured_materials WHERE sku_id=? AND material_id=?',(self.sku_id,parent)).fetchone():continue
                self.db.conn.execute('INSERT INTO mirror_captured_materials VALUES(?,?)',(self.sku_id,parent))
                for row in source.db.conn.execute('SELECT * FROM material_bom_items WHERE parent_material_id=? ORDER BY sort_no,id',(parent,)).fetchall():
                    relation=self.db.conn.execute('INSERT INTO material_bom_items(parent_material_id,child_material_id,quantity,unit,position,remark,sort_no) VALUES(?,?,?,?,?,?,?)',(parent,row['child_material_id'],row['quantity'],row['unit'],row['position'],row['remark'],row['sort_no'])).lastrowid
                    for alt in source.alternates(row['id']):
                        self.db.conn.execute('INSERT INTO alternates(bom_item_id,material_id,sort_no) VALUES(?,?,?)',(relation,alt['material_id'],alt['sort_no']))
                    pending.append(row['child_material_id'])

    def bom_graph_edges(self):
        from services.current_catalog import enabled
        if enabled(self):
            from services.current_catalog import catalog_edges
            return catalog_edges(self)
        captured={row[0] for row in self.db.conn.execute('SELECT material_id FROM mirror_captured_materials WHERE sku_id=?',(self.sku_id,))}
        return list(super().bom_graph_edges())+[row for row in self.primary.bom_graph_edges() if row[0] not in captured]

    def bom(self,root):
        if not self.db.conn.execute('SELECT 1 FROM mirror_captured_materials WHERE sku_id=? AND material_id=?',(self.sku_id,root)).fetchone():
            from services.snapshot_bom import enabled,template_service
            source=template_service(self.primary,root) if enabled(self.db) else self.primary
            if source is not self.primary and getattr(source,'scope_id',None)==self.scope_id:return super().bom(root)
            return Services.bom(source,root)
        return super().bom(root)
