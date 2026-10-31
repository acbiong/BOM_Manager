"""Publish live editor data after changes, with no background process or DB writes."""
from PyQt5.QtCore import QObject,QTimer
from infrastructure.events import WindowRefreshBus
from infrastructure.operation_progress import silent_progress
from infrastructure.live_project_cache import LiveProjectWriter
from ui.bom_snapshot import draft_snapshot


class LiveProjectPublisher(QObject):
    def __init__(self,main):
        super().__init__(main);self.main=main;self.writer=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.flush)
        self.bind()
    def bind(self):
        self.close()
        db=self.main.svc.db
        if db is None or db.path==':memory:':return
        self.writer=LiveProjectWriter(db.path)
        # Destruction by a parent does not necessarily call closeEvent.
        self.destroyed.connect(self.writer.close)
        WindowRefreshBus.subscribe(self.on_change);self.timer.start(0)
    def close(self):
        self.timer.stop();WindowRefreshBus.unsubscribe(self.on_change)
        if self.writer:self.writer.close();self.writer=None
    def on_change(self,event):
        if event.get('type') in ('bom_draft_changed','bom_changed','material_changed','material_history_changed','sku_changed','project_changed'):
            self.timer.start(100)
    @silent_progress()
    def flush(self):
        self.timer.stop()
        if not self.writer or not self.writer.active:return
        try:
            svc=self.main.svc
            drafts={str(sid):draft_snapshot(window) for sid,window in self.main._bom_windows.items() if window.dirty}
            self.writer.write(dict(project=dict(svc.project()),skus=[dict(row) for row in svc.skus()],drafts=drafts))
        except Exception as exc:
            self.writer.write({'error':'其他项目的编辑缓存读取失败：'+str(exc)})
