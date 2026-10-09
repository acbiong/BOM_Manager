"""按软件实际目录互斥启动；内核锁随进程退出释放，本地套接字负责激活窗口。"""
import errno
import fcntl
import hashlib
import os
import sys
from pathlib import Path
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication


def installation_directory():
 if getattr(sys, 'frozen', False):
  image = os.environ.get('APPIMAGE')
  return Path(image or sys.executable).expanduser().resolve().parent
 return Path(__file__).resolve().parents[2]


class SingleInstance:
 def __init__(self, directory=None, lock_directory=None):
  self.directory = Path(directory or installation_directory()).resolve()
  self.key = hashlib.sha256(os.fsencode(str(self.directory))).hexdigest()
  # 不依赖cwd、版本、挂载点、配置路径或TMPDIR，避免不同启动方式绕过锁。
  self.lock_path = Path(lock_directory or '/tmp') / ('bom-manager-' + self.key + '.lock')
  self.server_name = 'bom-manager-' + self.key
  self.fd = None
  self.server = None
  self.window = None
  self.pending_activation = False

 def acquire(self):
  fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
  try:
   fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except OSError as error:
   os.close(fd)
   if error.errno in (errno.EACCES, errno.EAGAIN):return False
   raise
  self.fd = fd
  try:
   # 只有持锁者清理异常退出遗留的本地套接字，绝不移除锁文件。
   QLocalServer.removeServer(self.server_name)
   self.server = QLocalServer()
   self.server.setSocketOptions(QLocalServer.UserAccessOption)
   self.server.newConnection.connect(self._connection)
   if not self.server.listen(self.server_name):raise RuntimeError('无法创建单实例通信端点：' + self.server.errorString())
  except Exception:
   self.close()
   raise
  return True

 def notify_existing(self):
  socket = QLocalSocket()
  socket.connectToServer(self.server_name)
  connected = socket.waitForConnected(1000)
  if connected:socket.disconnectFromServer()
  socket.close()
  return connected

 def _connection(self):
  while self.server and self.server.hasPendingConnections():
   socket = self.server.nextPendingConnection()
   socket.close(); socket.deleteLater()
   self.activate()

 def activate(self):
  window = QApplication.activeModalWidget() or self.window or QApplication.activeWindow()
  if window is None:
   self.pending_activation = True
   return
  if window.isMinimized():window.showNormal()
  else:window.show()
  window.raise_(); window.activateWindow()
  self.pending_activation = False

 def set_window(self, window):
  self.window = window
  if self.pending_activation:self.activate()

 def close(self):
  if self.server is not None:
   self.server.close(); self.server.deleteLater(); self.server = None
  if self.fd is not None:
   fcntl.flock(self.fd, fcntl.LOCK_UN); os.close(self.fd); self.fd = None
  # 文件保留，避免等待方持有旧inode时另一个进程创建新文件造成双锁。
