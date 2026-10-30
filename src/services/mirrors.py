"""Independent SQLite BOM namespaces for copied SKU mirrors.

Material identities stay shared; graph, alternates and BOM history are private.
All namespace identifiers are generated from integer SKU IDs, never user input.
"""
import re
from contextlib import contextmanager

TABLES=('material_bom_items','alternates','bom_items','change_logs','bom_log_roots','sku_history_reset')

def table_name(sid, table):
    return f'mirror_{int(sid)}_{table}'

class MirrorConnection:
    def __init__(self, connection, sid):
        self.raw=connection;self.sid=int(sid)
        self.pattern=re.compile(r'\b('+'|'.join(TABLES)+r')\b')
    def sql(self,sql):return self.pattern.sub(lambda m:table_name(self.sid,m.group()),sql)
    def execute(self,sql,parameters=()):return self.raw.execute(self.sql(sql),parameters)
    def executemany(self,sql,parameters):return self.raw.executemany(self.sql(sql),parameters)
    def __getattr__(self,name):return getattr(self.raw,name)

class MirrorDatabase:
    def __init__(self,database,sid):
        self.path=database.path;self.conn=MirrorConnection(database.conn,sid);self.original=database
    @contextmanager
    def transaction(self):
        with self.original.transaction():yield self.conn

def create_namespace(database,sid,source):
    conn=database.conn
    from services.material_history import copy_bindings
    copy_bindings(source,sid)
    root=conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone()[0]
    nodes=source.bom(root);relation_ids={row['id'] for row in nodes}
    captured={root}|{row['material_id'] for row in nodes}
    conn.executemany('INSERT INTO mirror_captured_materials VALUES(?,?)',[(sid,mid) for mid in captured])
    color_keys={(row['parent_material_id'],row['material_id']) for row in nodes}|{(0,mid) for mid in captured}
    color_rows=[(sid,r['parent_id'],r['material_id'],r['color']) for r in conn.execute('SELECT * FROM bom_row_colors WHERE scope_id=?',(getattr(source,'scope_id',0),)) if (r['parent_id'],r['material_id']) in color_keys]
    conn.executemany('INSERT INTO bom_row_colors VALUES(?,?,?,?)',color_rows)
    for table in TABLES:
        schema=conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()[0]
        target=table_name(sid,table)
        schema=re.sub(r'(?i)CREATE TABLE(?: IF NOT EXISTS)?\s+["`]?'+table+r'["`]?',f'CREATE TABLE {target}',schema,count=1)
        conn.execute(schema)
        # Source may itself be a mirror. Copy IDs so alternate/history links stay valid.
        rows=source.db.conn.execute(f'SELECT * FROM {table}').fetchall()
        if table=='material_bom_items':rows=[row for row in rows if row['id'] in relation_ids]
        elif table=='alternates':rows=[row for row in rows if row['bom_item_id'] in relation_ids]
        elif table=='bom_items':rows=[]
        if rows:
            columns=rows[0].keys()
            conn.executemany(f'INSERT INTO {target} ('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[tuple(row) for row in rows])
    conn.execute(f'CREATE INDEX mirror_{sid}_parent ON {table_name(sid,"material_bom_items")}(parent_material_id)')
    conn.execute(f'CREATE INDEX mirror_{sid}_child ON {table_name(sid,"material_bom_items")}(child_material_id)')
    conn.execute(f'CREATE INDEX {table_name(sid,"alternates")}_relation ON {table_name(sid,"alternates")}(bom_item_id,sort_no)')

def drop_namespace(database,sid):
    from services.material_history import enabled
    if enabled(database):database.conn.execute('DELETE FROM material_history_bindings WHERE sku_id=?',(sid,))
    database.conn.execute('DELETE FROM bom_row_colors WHERE scope_id=?',(sid,))
    for table in TABLES:database.conn.execute(f'DROP TABLE IF EXISTS {table_name(sid,table)}')
    database.conn.execute('DELETE FROM mirror_material_usage WHERE sku_id=?',(sid,))
    database.conn.execute('DELETE FROM mirror_captured_materials WHERE sku_id=?',(sid,))
