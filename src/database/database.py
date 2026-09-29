"""数据库访问层：SQLite本地数据库，支持同目录文件配置；输入SQL参数，输出查询结果。编辑时间：2026-09-24。"""
import sqlite3
from contextlib import contextmanager
class Database:
 def __init__(self,path):
  self.path=path; self.conn=sqlite3.connect(path); self.conn.row_factory=sqlite3.Row
  try:self.create_schema()
  except Exception:self.conn.close(); raise
 def create_schema(self):
  self.conn.executescript('''CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY,base_code TEXT NOT NULL,version TEXT NOT NULL,name TEXT NOT NULL,description TEXT DEFAULT '',unit TEXT NOT NULL,manufacturer TEXT DEFAULT '',mpn TEXT DEFAULT '',mp_flag TEXT DEFAULT 'M',has_bom INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(base_code,version));CREATE TABLE IF NOT EXISTS skus(id INTEGER PRIMARY KEY,material_id INTEGER UNIQUE,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS bom_items(id INTEGER PRIMARY KEY,bom_root_id INTEGER NOT NULL,parent_item_id INTEGER,material_id INTEGER NOT NULL,quantity REAL NOT NULL,unit TEXT NOT NULL,position TEXT DEFAULT '',level_no INTEGER DEFAULT 1,remark TEXT DEFAULT '',sort_no INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS material_bom_items(id INTEGER PRIMARY KEY,parent_material_id INTEGER NOT NULL,child_material_id INTEGER NOT NULL,quantity REAL NOT NULL,unit TEXT NOT NULL,position TEXT DEFAULT '',remark TEXT DEFAULT '',sort_no INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(parent_material_id,child_material_id,position));CREATE INDEX IF NOT EXISTS idx_material_bom_parent ON material_bom_items(parent_material_id);CREATE INDEX IF NOT EXISTS idx_material_bom_child ON material_bom_items(child_material_id);CREATE TABLE IF NOT EXISTS alternates(id INTEGER PRIMARY KEY,bom_item_id INTEGER NOT NULL,material_id INTEGER NOT NULL,sort_no INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS change_logs(id INTEGER PRIMARY KEY,object_type TEXT,object_id INTEGER,action TEXT,detail TEXT,changed_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS project(id INTEGER PRIMARY KEY CHECK(id=1),project_name TEXT DEFAULT '请输入项目名称',project_code TEXT DEFAULT '',product_name TEXT DEFAULT '',product_model TEXT DEFAULT '');INSERT OR IGNORE INTO project(id) VALUES(1);''')
  log_columns={r[1] for r in self.conn.execute('PRAGMA table_info(change_logs)')}
  for column in ('material_code','material_name'):
   if column not in log_columns:self.conn.execute(f'ALTER TABLE change_logs ADD COLUMN {column} TEXT')
  # 从旧的按SKU根节点存储方式迁移到父物料关系表，迁移只执行一次。
  if self.conn.execute('SELECT COUNT(*) FROM material_bom_items').fetchone()[0] == 0:
   old=self.conn.execute('SELECT id,bom_root_id,parent_item_id,material_id,quantity,unit,position,remark,sort_no FROM bom_items ORDER BY id').fetchall()
   by_id={r['id']:r for r in old}
   for r in old:
    parent=by_id.get(r['parent_item_id'])
    parent_id=parent['material_id'] if parent else r['bom_root_id']
    self.conn.execute('INSERT OR IGNORE INTO material_bom_items(parent_material_id,child_material_id,quantity,unit,position,remark,sort_no) VALUES(?,?,?,?,?,?,?)',(parent_id,r['material_id'],r['quantity'],r['unit'],r['position'],r['remark'],r['sort_no']))
  self.conn.execute('UPDATE materials SET has_bom=CASE WHEN EXISTS(SELECT 1 FROM material_bom_items b WHERE b.parent_material_id=materials.id) THEN 1 ELSE 0 END')
  self.conn.commit()
 @contextmanager
 def transaction(self):
  try: yield self.conn; self.conn.commit()
  except: self.conn.rollback(); raise
 def validate_schema(self):
  required={'materials','skus','bom_items','material_bom_items','alternates','change_logs','project'}
  got={r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  return required.issubset(got), sorted(required-got)
 def recreate_schema(self):
  self.create_schema(); return self.validate_schema()[0]
 def close(self): self.conn.close()
