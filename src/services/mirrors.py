"""Independent SQLite BOM namespaces for copied SKU mirrors.

Only SKU root relations and their alternates are private; child graphs are shared.
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
        from services.shared_bom import is_shared
        self.shared=is_shared(connection)
        self.root=connection.execute("SELECT material_id FROM skus WHERE id=?",(sid,)).fetchone()[0]
        self.pattern=re.compile(r'\b('+'|'.join(TABLES)+r')\b')
    def sql(self,sql):return self.pattern.sub(lambda m:table_name(self.sid,m.group()),sql)
    def execute(self,sql,parameters=()):
        if self.shared:
            match=re.match(r'\s*INSERT(?: OR \w+)? INTO (material_bom_items|alternates)\s*\(([^)]+)\)',sql,re.I)
            if match:
                table=match[1];columns=[v.strip() for v in match[2].split(',')]
                if table=='material_bom_items':local=parameters[columns.index('parent_material_id')]==self.root
                else:
                    rid=parameters[columns.index('bom_item_id')]
                    local=bool(self.raw.execute(f'SELECT 1 FROM {table_name(self.sid,"material_bom_items")}_local WHERE id=?',(rid,)).fetchone())
                converted=self.sql(sql);target=table_name(self.sid,table)+'_local' if local else table
                converted=re.sub(r'(INTO )'+table_name(self.sid,table)+r'\b',lambda m:m[1]+target,converted,count=1,flags=re.I)
                if local and table=='material_bom_items' and 'id' not in columns:
                    next_id=max(10**12+self.sid*10**8,self.raw.execute(f'SELECT COALESCE(MAX(id),0)+1 FROM {target}').fetchone()[0])
                    converted=converted.replace('('+match[2]+')','(id,'+match[2]+')',1)
                    converted=re.sub(r'VALUES\s*\(', 'VALUES(?,',converted,count=1,flags=re.I);parameters=(next_id,*parameters)
                return self.raw.execute(converted,parameters)
        return self.raw.execute(self.sql(sql),parameters)
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
    root=conn.execute('SELECT material_id FROM skus WHERE id=?',(sid,)).fetchone()[0]
    nodes=source.bom(root);relation_ids={row['id'] for row in nodes}
    captured={root}|{row['material_id'] for row in nodes}
    conn.executemany('INSERT INTO mirror_captured_materials VALUES(?,?)',[(sid,mid) for mid in captured])
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
            columns=[c for c in rows[0].keys() if table!='alternates' or c!='id']
            conn.executemany(f'INSERT INTO {target} ('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[tuple(row[c] for c in columns) for row in rows])
    conn.execute(f'CREATE INDEX mirror_{sid}_parent ON {table_name(sid,"material_bom_items")}(parent_material_id)')
    conn.execute(f'CREATE INDEX mirror_{sid}_child ON {table_name(sid,"material_bom_items")}(child_material_id)')
    from services.shared_bom import is_shared,install_overlay
    if is_shared(conn):install_overlay(conn,sid)

def drop_namespace(database,sid):
    for table in TABLES:
        name=table_name(sid,table)
        kind=database.conn.execute('SELECT type FROM sqlite_master WHERE name=?',(name,)).fetchone()
        if kind:database.conn.execute(f'DROP {kind[0].upper()} {name}')
        database.conn.execute(f'DROP TABLE IF EXISTS {name}_local')
    database.conn.execute('DELETE FROM mirror_material_usage WHERE sku_id=?',(sid,))
    database.conn.execute('DELETE FROM mirror_captured_materials WHERE sku_id=?',(sid,))
