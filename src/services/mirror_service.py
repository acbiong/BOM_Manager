from services.services import Services
from services.mirrors import MirrorDatabase

class MirrorServices(Services):
    def __init__(self,primary,sid):
        self.primary=primary;self.scope_id=int(sid);self.sku_id=int(sid)
        super().__init__(MirrorDatabase(primary.db,sid),primary.config_service)
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
        # Non-root definitions are read directly from the shared public graph.
        return

    def bom_graph_edges(self):return super().bom_graph_edges()

    def bom(self,root):return super().bom(root)
