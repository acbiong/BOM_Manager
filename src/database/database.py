"""数据库访问层：SQLite本地数据库，支持同目录文件配置；输入SQL参数，输出查询结果。编辑时间：2026-09-24。"""
import sqlite3
from contextlib import contextmanager
class Database:
 def __init__(self,path,exclusive=False):
  self._project_lock=None
  if exclusive:
   from infrastructure.project_lock import ProjectLock
   self._project_lock=ProjectLock(path).require()
  try:self.path=path; self.conn=sqlite3.connect(path); self.conn.row_factory=sqlite3.Row
  except Exception:
   if self._project_lock:self._project_lock.close()
   raise
  try:
   columns={row[1] for row in self.conn.execute('PRAGMA table_info(skus)')}
   if columns and 'mirror_version' not in columns and path!=':memory:':
    from pathlib import Path
    from datetime import datetime
    backup=Path(str(path)+'.pre-mirrors-'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
    destination=sqlite3.connect(str(backup))
    try:self.conn.backup(destination)
    finally:destination.close()
   self.create_schema()
  except Exception:self.close(); raise
 def create_schema(self):
  self.conn.execute("CREATE TABLE IF NOT EXISTS bom_row_colors(scope_id INTEGER NOT NULL,parent_id INTEGER NOT NULL,material_id INTEGER NOT NULL,color TEXT NOT NULL,PRIMARY KEY(scope_id,parent_id,material_id))")
  self.conn.executescript('''CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY,base_code TEXT NOT NULL,version TEXT NOT NULL,name TEXT NOT NULL,description TEXT DEFAULT '',unit TEXT NOT NULL,manufacturer TEXT DEFAULT '',mpn TEXT DEFAULT '',mp_flag TEXT DEFAULT 'M',has_bom INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(base_code,version));CREATE TABLE IF NOT EXISTS skus(id INTEGER PRIMARY KEY,material_id INTEGER UNIQUE,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS bom_items(id INTEGER PRIMARY KEY,bom_root_id INTEGER NOT NULL,parent_item_id INTEGER,material_id INTEGER NOT NULL,quantity REAL NOT NULL,unit TEXT NOT NULL,position TEXT DEFAULT '',level_no INTEGER DEFAULT 1,remark TEXT DEFAULT '',sort_no INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS material_bom_items(id INTEGER PRIMARY KEY,parent_material_id INTEGER NOT NULL,child_material_id INTEGER NOT NULL,quantity REAL NOT NULL,unit TEXT NOT NULL,position TEXT DEFAULT '',remark TEXT DEFAULT '',sort_no INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(parent_material_id,child_material_id,position));CREATE INDEX IF NOT EXISTS idx_material_bom_parent ON material_bom_items(parent_material_id);CREATE INDEX IF NOT EXISTS idx_material_bom_child ON material_bom_items(child_material_id);CREATE TABLE IF NOT EXISTS alternates(id INTEGER PRIMARY KEY,bom_item_id INTEGER NOT NULL,material_id INTEGER NOT NULL,sort_no INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS change_logs(id INTEGER PRIMARY KEY,object_type TEXT,object_id INTEGER,action TEXT,detail TEXT,changed_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS project(id INTEGER PRIMARY KEY CHECK(id=1),project_name TEXT DEFAULT '请输入项目名称',project_code TEXT DEFAULT '',product_name TEXT DEFAULT '',product_model TEXT DEFAULT '');INSERT OR IGNORE INTO project(id) VALUES(1);''')
  if 'grade' not in {r[1] for r in self.conn.execute('PRAGMA table_info(materials)')}:self.conn.execute("ALTER TABLE materials ADD COLUMN grade TEXT NOT NULL DEFAULT ''")
  self.conn.execute('CREATE TABLE IF NOT EXISTS bom_log_roots(log_id INTEGER NOT NULL,root_id INTEGER NOT NULL,PRIMARY KEY(log_id,root_id))')
  self.conn.execute('CREATE TABLE IF NOT EXISTS sku_history_reset(root_id INTEGER PRIMARY KEY,start_log_id INTEGER NOT NULL DEFAULT 0)')
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
  self.conn.execute('CREATE TABLE IF NOT EXISTS app_metadata(key TEXT PRIMARY KEY,value TEXT)')
  if 'mirror_version' not in {r[1] for r in self.conn.execute('PRAGMA table_info(skus)')}:
   self.conn.execute('ALTER TABLE skus RENAME TO skus_legacy')
   self.conn.execute("CREATE TABLE skus(id INTEGER PRIMARY KEY AUTOINCREMENT,material_id INTEGER,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,mirror_version INTEGER NOT NULL DEFAULT 100,scope_id INTEGER NOT NULL DEFAULT 0,UNIQUE(material_id,mirror_version))")
   self.conn.execute('INSERT INTO skus(id,material_id,updated_at) SELECT id,material_id,updated_at FROM skus_legacy')
   self.conn.execute('DROP TABLE skus_legacy')
  if 'change_description' not in {r[1] for r in self.conn.execute('PRAGMA table_info(skus)')}:self.conn.execute("ALTER TABLE skus ADD COLUMN change_description TEXT NOT NULL DEFAULT ''")
  if 'locked' not in {r[1] for r in self.conn.execute('PRAGMA table_info(skus)')}:self.conn.execute('ALTER TABLE skus ADD COLUMN locked INTEGER NOT NULL DEFAULT 0 CHECK(locked IN (0,1))')
  self.conn.execute('CREATE TABLE IF NOT EXISTS mirror_material_usage(sku_id INTEGER NOT NULL,material_id INTEGER NOT NULL,parent_id INTEGER NOT NULL,role TEXT NOT NULL,PRIMARY KEY(sku_id,material_id,parent_id,role))')
  self.conn.execute('CREATE TABLE IF NOT EXISTS mirror_captured_materials(sku_id INTEGER NOT NULL,material_id INTEGER NOT NULL,PRIMARY KEY(sku_id,material_id))')
  self.conn.execute('CREATE INDEX IF NOT EXISTS mirror_usage_material ON mirror_material_usage(material_id)')
  if not self.conn.execute("SELECT 1 FROM app_metadata WHERE key='local_log_time_v1'").fetchone():
   from datetime import datetime,timezone
   for row in self.conn.execute('SELECT id,changed_at FROM change_logs').fetchall():
    try:value=datetime.fromisoformat(row['changed_at']).replace(tzinfo=timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S.%f')[:-4]
    except (TypeError,ValueError):continue
    self.conn.execute('UPDATE change_logs SET changed_at=? WHERE id=?',(value,row['id']))
   self.conn.execute("INSERT INTO app_metadata VALUES('local_log_time_v1','1')")
  from services.mirrors import TABLES,table_name
  existing={row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
  for row in self.conn.execute('SELECT id,scope_id FROM skus WHERE scope_id<>0'):
   if row['scope_id']!=row['id'] or any(table_name(row['id'],table) not in existing for table in TABLES):raise ValueError('历史版本BOM数据表缺失或标识错误，请从备份恢复数据库')
  self.conn.commit()
 @contextmanager
 def transaction(self):
  depth=getattr(self,'_transaction_depth',0);self._transaction_depth=depth+1
  pending_start=len(getattr(self,'_pending_events',[]))
  name='bom_nested_'+str(depth)
  if depth:self.conn.execute('SAVEPOINT '+name)
  elif not self.conn.in_transaction:self.conn.execute('BEGIN')
  try:
   from services.sku_lock import locked_snapshots,check_locked_changes
   locked_before=locked_snapshots(self.conn) if not depth else {}
   yield self.conn
   if not depth:check_locked_changes(self.conn,locked_before)
   if depth:self.conn.execute('RELEASE SAVEPOINT '+name)
   else:self.conn.commit()
  except:
   self._pending_events=getattr(self,'_pending_events',[])[:pending_start]
   if depth:self.conn.execute('ROLLBACK TO SAVEPOINT '+name);self.conn.execute('RELEASE SAVEPOINT '+name)
   else:self.conn.rollback()
   raise
  finally:self._transaction_depth=depth
  if not depth:
   events=getattr(self,'_pending_events',[]);self._pending_events=[]
   if events:
    from infrastructure.events import WindowRefreshBus
    WindowRefreshBus.publish_many(events)
 def validate_schema(self):
  required={'materials','skus','bom_items','material_bom_items','alternates','change_logs','project'}
  got={r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  return required.issubset(got), sorted(required-got)
 def recreate_schema(self):
  self.create_schema(); return self.validate_schema()[0]
 def close(self):
  try:self.conn.execute('PRAGMA optimize')
  except sqlite3.DatabaseError:pass
  finally:
   try:self.conn.close()
   finally:
    if self._project_lock:self._project_lock.close()
