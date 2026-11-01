"""Bounded native main-reference checks on disposable example data."""
import argparse,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--platform',choices=['windows','xcb'],required=True);parser.add_argument('--update-help',action='store_true');args=parser.parse_args()
os.environ['QT_QPA_PLATFORM']=args.platform
sys.path[:0]=[str(root/'src'),str(root/'tests')]
from PyQt5.QtCore import Qt,QPoint,QRect
from PyQt5.QtGui import QPainter,QPen,QColor
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication,QDialogButtonBox
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
from test_history_main_references import MainReferenceTests
from ui.material_history import MaterialHistoryChoiceDialog,MaterialHistoryDialog
from ui.theme import apply_theme
os.environ['QT_QPA_PLATFORM']=args.platform;apply_theme(False)
out=root/'test_reports'/('main_reference_'+args.platform);out.mkdir(parents=True,exist_ok=True)
case=MainReferenceTests();case.setUp();windows=[]
try:
 alt,_=case.alternate_owner(case.c);both,_=case.alternate_owner(case.c,True)
 case.s.set_sku_locked(alt.sku_id,True)
 before=list(case.db.conn.iterdump())
 choice=MaterialHistoryChoiceDialog(case.new,case.c,'删除替代料',impact_mid=case.p);windows.append(choice)
 choice.show();assert QTest.qWaitForWindowExposed(choice,3000)
 actual={choice.table.item(i,0).data(Qt.UserRole) for i in range(choice.table.rowCount())}
 assert actual=={case.sid,case.tid,both.sku_id}
 assert choice.grab().save(str(out/'main_scope.png'))
 if args.update_help:
  directory=root/'resources/help_screenshots';manifest=json.loads((directory/'actions.json').read_text(encoding='utf-8'))
  rect=QRect(choice.table.mapTo(choice,QPoint()),choice.table.size()).adjusted(-2,-2,2,2)
  pix=choice.grab();ratio=pix.devicePixelRatio();pix.setDevicePixelRatio(1)
  painter=QPainter(pix);painter.setPen(QPen(QColor('#ed1826'),3));painter.drawRect(QRect(round(rect.x()*ratio),round(rect.y()*ratio),round(rect.width()*ratio),round(rect.height()*ratio)));painter.end()
  key='action_material_history_choose';assert pix.save(str(directory/(key+'.png')))
  manifest[key]=dict(window=choice.windowTitle(),target=[rect.x(),rect.y(),rect.width(),rect.height()],size=[pix.width(),pix.height()])
  (directory/'actions.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 choice.select_all(True)
 QTest.mouseClick(choice.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),Qt.LeftButton)
 assert choice.result()==choice.Accepted
 viewer=MaterialHistoryDialog(case.s,case.c,100);windows.append(viewer);viewer.show();assert QTest.qWaitForWindowExposed(viewer,3000)
 assert {viewer.references.item(i,0).data(Qt.UserRole) for i in range(viewer.references.rowCount())}==actual|{case.newid}
 assert '主料' in viewer.references_group.title()
 assert viewer.grab().save(str(out/'main_history_view.png'))
 assert list(case.db.conn.iterdump())==before
 result=dict(passed=True,platform=app.platformName(),checks=['main_only_choice','alternate_only_lock_excluded_from_choice','exact_main_history_view','readonly_windows'],choices=len(actual),references=viewer.references.rowCount())
finally:
 for w in windows:w.close()
 case.tearDown()
(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
