"""Read saved BOMs from another project without opening it for editing."""
from contextlib import closing
from pathlib import Path
import sqlite3
import time

from database.database import Database
from infrastructure.operation_progress import checkpoint
from services.bom_compare import snapshot
from services.services import Services


def read_project(path, sku_id=None):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f'项目数据库不存在或为空：{path}')
    from infrastructure.live_project_cache import read_live_project
    live=read_live_project(path)
    if live is not None:
        if sku_id is None:return live
        if not any(s['id']==sku_id for s in live['skus']):
            raise ValueError('所选项目的SKU或历史版本已不存在，请重新载入其他项目。')
        if str(sku_id) in live['drafts']:
            return external_tree(live['drafts'][str(sku_id)],draft=True)
    # SQLite backup includes committed WAL pages. Never migrate, optimize, lock
    # for editing, or create a database at the original project's path.
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=3)) as source:
        with closing(Database(':memory:')) as db:
            deadline = time.monotonic()+10
            def progress(status, remaining, total):
                checkpoint()
                if time.monotonic()>deadline:
                    raise ValueError('读取项目超时，请等待该项目完成保存后重试。')
            source.backup(db.conn, pages=256, progress=progress, sleep=.05)
            if db.conn.execute('PRAGMA quick_check').fetchall()[0][0] != 'ok':
                raise ValueError('项目数据库完整性检查失败')
            required = {'materials','skus','bom_items','alternates','change_logs','project'}
            tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required.issubset(tables):
                raise ValueError('所选文件不是有效的BOM项目数据库')
            if db.conn.execute('SELECT 1 FROM project WHERE id=1').fetchone() is None:
                raise ValueError('数据库缺少项目信息')
            # Compatibility changes are confined to this disposable memory copy.
            db.create_schema()
            service = Services(db)
            skus = [dict(row) for row in service.skus()]
            if sku_id is None:
                return dict(project=dict(service.project()), skus=skus)
            sku = next((row for row in skus if row['id']==sku_id), None)
            if sku is None:
                raise ValueError('所选项目的SKU或历史版本已不存在，请重新载入其他项目。')
            tree = snapshot(service, sku)
            return external_tree(tree)


def external_tree(tree,draft=False):
    tree['_project_source']=True;tree['_draft']=draft
    pending=[tree]
    while pending:
        checkpoint();node=pending.pop();node['_external']=True
        node['alternate_codes']=frozenset(tuple(code) for code in node.get('alternate_codes',()))
        pending.extend(node['children'])
    return tree
