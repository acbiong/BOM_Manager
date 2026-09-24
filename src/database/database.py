"""数据库访问层：SQLite本地数据库，支持同目录文件配置；输入SQL参数，输出查询结果。编辑时间：2026-09-24。"""
import sqlite3
from contextlib import contextmanager
class Database:
 def __init__(self,path): self.path=path; self.conn=sqlite3.connect(path); self.conn.row_factory=sqlite3.Row; self.create_schema()
 def create_schema(self):
  self.conn.executescript('''CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY,base_code TEXT NOT NULL,version TEXT NOT NULL,name TEXT NOT NULL,description TEXT DEFAULT '',unit TEXT NOT NULL,manufacturer TEXT DEFAULT '',mpn TEXT DEFAULT '',mp_flag TEXT DEFAULT 'M',has_bom INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(base_code,version));CREATE TABLE IF NOT EXISTS skus(id INTEGER PRIMARY KEY,material_id INTEGER UNIQUE,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS bom_items(id INTEGER PRIMARY KEY,bom_root_id INTEGER NOT NULL,parent_item_id INTEGER,material_id INTEGER NOT NULL,quantity REAL NOT NULL,unit TEXT NOT NULL,position TEXT DEFAULT '',level_no INTEGER DEFAULT 1,remark TEXT DEFAULT '',sort_no INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS alternates(id INTEGER PRIMARY KEY,bom_item_id INTEGER NOT NULL,material_id INTEGER NOT NULL,sort_no INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS change_logs(id INTEGER PRIMARY KEY,object_type TEXT,object_id INTEGER,action TEXT,detail TEXT,changed_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS project(id INTEGER PRIMARY KEY CHECK(id=1),project_name TEXT DEFAULT '请输入项目名称',project_code TEXT DEFAULT '',product_name TEXT DEFAULT '',product_model TEXT DEFAULT '');INSERT OR IGNORE INTO project(id) VALUES(1);'''); self.conn.commit()
 @contextmanager
 def transaction(self):
  try: yield self.conn; self.conn.commit()
  except: self.conn.rollback(); raise
 def close(self): self.conn.close()
