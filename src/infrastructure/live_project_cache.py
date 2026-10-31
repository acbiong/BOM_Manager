"""Process-owned, disposable comparison snapshots; never a project save file."""
import hashlib,json,os,tempfile,uuid
from pathlib import Path
from infrastructure.project_lock import FileMutex


def cache_identity(path):
    path=Path(path).expanduser().resolve()
    try:
        stat=path.stat()
        identity=f'{stat.st_dev}:{stat.st_ino}' if stat.st_ino else os.path.normcase(str(path))
    except OSError:identity=os.path.normcase(str(path))
    user=hashlib.sha256(str(Path.home()).encode()).hexdigest()[:16]
    folder=Path(tempfile.gettempdir())/('bom-live-'+user)
    key=hashlib.sha256(identity.encode()).hexdigest()
    return folder/(key+'.json'),'bom-live:'+user+':'+key


def owner_active(path):
    _,identity=cache_identity(path);lock=FileMutex(identity)
    try:return not lock.acquire()
    finally:lock.close()


def read_live_project(path):
    cache,_=cache_identity(path)
    if not owner_active(path):return None  # A crashed writer's cache is never used.
    try:result=json.loads(cache.read_text(encoding='utf-8'))
    except FileNotFoundError:return None
    except (OSError,ValueError) as exc:raise ValueError('其他项目的编辑缓存暂不可用，请稍后重试。') from exc
    if not owner_active(path):return None
    if result.get('error'):raise ValueError(result['error'])
    return result


def project_signature(path):
    cache,_=cache_identity(path)
    def stat(p):
        try:s=Path(p).stat();return s.st_mtime_ns,s.st_size,s.st_ino
        except OSError:return None
    return owner_active(path),stat(cache),stat(path),stat(str(path)+'-wal')


class LiveProjectWriter:
    def __init__(self,path):
        self.path=path;self.cache,identity=cache_identity(path);self.lock=FileMutex(identity)
        self.active=self.lock.acquire();self.session=uuid.uuid4().hex;self._payload=None
        if self.active:
            self.cache.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            self.cache.unlink(missing_ok=True)
    def write(self,data):
        if not self.active:return
        temporary=self.cache.with_suffix('.'+self.session+'.tmp')
        payload=json.dumps(dict(data,session=self.session),ensure_ascii=False,
            default=lambda value:list(value) if isinstance(value,(set,frozenset)) else str(value))
        if payload==self._payload:return
        try:
            temporary.write_text(payload,encoding='utf-8')
            os.replace(temporary,self.cache)
            self._payload=payload
        finally:temporary.unlink(missing_ok=True)
    def close(self):
        if self.active:
            try:self.cache.unlink(missing_ok=True)
            finally:self.lock.close();self.active=False
