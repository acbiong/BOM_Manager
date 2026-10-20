"""跨平台配置路径和发布自检验证；Windows内核锁由Windows CI原生测试。"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
import main

class CrossPlatformTests(unittest.TestCase):
 def test_windows_portable_and_localappdata_fallback(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);install=base/'软件';install.mkdir();fallback=base/'local'
   with patch.object(main,'IS_WINDOWS',True),patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(install/'BOM.exe')),patch.dict(os.environ,{'APPIMAGE':'','LOCALAPPDATA':str(fallback)}):
    self.assertEqual(main.app_base(),install)
    with patch.object(main.tempfile,'NamedTemporaryFile',side_effect=PermissionError('protected')):
     self.assertEqual(main.app_base(),fallback/'BOM管理系统')
 def test_smoke_checks_windows_database_and_excel_without_user_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   report=Path(tmp)/'smoke.json';root=Path(__file__).parents[1]
   result=subprocess.run([sys.executable,str(root/'src/main.py'),'--smoke-test-report',str(report)],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONUTF8='1'),capture_output=True,timeout=40)
   self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
   data=json.loads(report.read_text(encoding='utf-8'));self.assertTrue(data['passed']);self.assertIn('project_ownership',data['checks']);self.assertIn('excel',data['checks'])
