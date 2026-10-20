"""Process-lifetime project ownership, separate from SQLite transaction locks."""
import errno,hashlib,os,tempfile,time
from pathlib import Path
if os.name=='nt':import msvcrt
else:import fcntl

class ProjectInUseError(RuntimeError):pass

class FileMutex:
 def __init__(self,identity):
  key=hashlib.sha256(identity.encode('utf-8')).hexdigest()
  self.path=Path(tempfile.gettempdir() if os.name=='nt' else '/tmp')/('bom-owner-'+key+'.lock');self.fd=None
 def acquire(self,timeout=0):
  if self.fd is not None:return True
  fd=os.open(self.path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_CLOEXEC',0),0o600)
  if os.name=='nt' and os.fstat(fd).st_size==0:os.write(fd,b'0')
  deadline=time.monotonic()+timeout
  while True:
   try:
    if os.name=='nt':os.lseek(fd,0,os.SEEK_SET);msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
    else:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    self.fd=fd;return True
   except OSError as error:
    if error.errno not in (errno.EACCES,errno.EAGAIN):os.close(fd);raise
    if time.monotonic()>=deadline:os.close(fd);return False
    time.sleep(.01)
 def close(self):
  if self.fd is None:return
  fd=self.fd;self.fd=None
  try:
   if os.name=='nt':os.lseek(fd,0,os.SEEK_SET);msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
   else:fcntl.flock(fd,fcntl.LOCK_UN)
  finally:os.close(fd)
 # Keep the inode: deleting a lock file could create two independent locks.
 def __enter__(self):
  if not self.acquire(timeout=5):raise TimeoutError('配置正在由其他软件实例更新，请稍后重试')
  return self
 def __exit__(self,*args):self.close()

class ProjectLock(FileMutex):
 def __init__(self,path):
  path=Path(path).expanduser().resolve();self.database_path=path
  # Native file identity also covers symlinks and hard links on this computer.
  stat=path.stat()
  identity=f'project-inode:{stat.st_dev}:{stat.st_ino}' if stat.st_ino else 'project-path:'+os.path.normcase(str(path))
  super().__init__(identity)
 def require(self):
  if not self.acquire():raise ProjectInUseError('当前项目已经被其他软件打开：\n'+str(self.database_path))
  return self
