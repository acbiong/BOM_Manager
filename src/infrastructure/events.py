"""跨窗口变更事件总线：Qt界面可订阅BOM变更并提示刷新。编辑时间：2026-09-24。"""
from contextlib import contextmanager

class WindowRefreshBus:
 _handlers=[]
 _batch_depth=0
 _refreshes={}
 @classmethod
 def subscribe(cls,handler):
  if handler not in cls._handlers: cls._handlers.append(handler)
  return handler
 @classmethod
 def unsubscribe(cls,handler):
  if handler in cls._handlers: cls._handlers.remove(handler)
 @classmethod
 def refresh(cls,callback,priority=1):
  if cls._batch_depth:cls._refreshes[callback]=min(priority,cls._refreshes.get(callback,priority))
  else:callback()
 @classmethod
 @contextmanager
 def batch(cls):
  cls._batch_depth+=1
  try:yield
  finally:
   if cls._batch_depth==1:
    done=set()
    try:
     while cls._refreshes:
      callback=min(cls._refreshes,key=cls._refreshes.get);cls._refreshes.pop(callback)
      if callback in done:continue
      done.add(callback)
      from PyQt5 import sip
      from PyQt5.QtCore import QObject
      owner=getattr(callback,'__self__',None)
      if not isinstance(owner,QObject) or not sip.isdeleted(owner):callback()
    finally:cls._refreshes.clear();cls._batch_depth-=1
   else:cls._batch_depth-=1
 @classmethod
 def publish_many(cls,events):
  with cls.batch():
   for event in events:cls.publish(event)
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
