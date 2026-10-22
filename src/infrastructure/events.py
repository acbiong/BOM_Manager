"""跨窗口变更事件总线：Qt界面可订阅BOM变更并提示刷新。编辑时间：2026-09-24。"""
class WindowRefreshBus:
 _handlers=[]
 @classmethod
 def subscribe(cls,handler):
  if handler not in cls._handlers: cls._handlers.append(handler)
  return handler
 @classmethod
 def unsubscribe(cls,handler):
  if handler in cls._handlers: cls._handlers.remove(handler)
 @classmethod
 def publish(cls,event):
  from PyQt5 import sip
  from PyQt5.QtCore import QObject
  for h in list(cls._handlers):
   # A parent can destroy a child without sending that child's closeEvent.
   # Never call UI methods on an already-deleted C++ receiver.
   owner=getattr(h,'__self__',None)
   if isinstance(owner,QObject) and sip.isdeleted(owner):
    cls.unsubscribe(h);continue
   if h in cls._handlers:h(event)
