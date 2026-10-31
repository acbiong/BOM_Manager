"""Keep Qt native crashes isolated, but fail the release gate on any process crash."""
import os,sys,subprocess,json,unittest
from pathlib import Path

class UiLifecycleSmokeTests(unittest.TestCase):
 def test_failed_smoke_preserves_error_and_removes_temporary_database(self):
  root=Path(__file__).parents[1]
  script=r'''
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()/'src'))
from infrastructure.smoke_test import run_smoke_test
temporary=tempfile.TemporaryDirectory
created=[]
def tracked(*args,**kwargs):
    directory=temporary(*args,**kwargs)
    created.append(Path(directory.name))
    return directory
with temporary() as directory:
    report=Path(directory)/'failure.json'
    with patch('tempfile.TemporaryDirectory',side_effect=tracked), patch('infrastructure.ui_smoke.exercise_windows',side_effect=RuntimeError('intentional-window-failure')):
        code=run_smoke_test(report)
    data=json.loads(report.read_text(encoding='utf-8'))
    assert code==1 and not data['passed'],data
    assert 'intentional-window-failure' in data['error'],data
    assert 'PermissionError' not in data['error'],data
    assert created and all(not path.exists() for path in created),created
'''
  env=dict(os.environ,QT_QPA_PLATFORM='windows' if os.name=='nt' else 'offscreen',PYTHONUTF8='1')
  result=subprocess.run([sys.executable,'-X','faulthandler','-c',script],cwd=root,env=env,capture_output=True,timeout=90)
  self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace')[-6000:])

 def test_real_save_notifications_and_all_dialog_families_in_child_process(self):
  root=Path(__file__).parents[1];reports=root/'test_reports';reports.mkdir(exist_ok=True)
  report=reports/'ui_lifecycle_regression.json';log=reports/'ui_lifecycle_regression.log'
  env=dict(os.environ,QT_QPA_PLATFORM='windows' if os.name=='nt' else 'offscreen')
  with log.open('w') as output:
   result=subprocess.run([sys.executable,'-X','faulthandler',str(root/'src/main.py'),'--smoke-test-report',str(report)],cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=90)
  self.assertEqual(result.returncode,0,log.read_text(errors='replace')[-6000:])
  data=json.loads(report.read_text());self.assertTrue(data['passed'],data)
  for name in ('ui_save_three_times_with_real_prompt','ui_compare_live_after_save','ui_close_reopen_saved_bom','dialog_QFileDialog','dialog_MaterialHeaderMappingDialog','message_information','message_warning','message_critical'):
   self.assertIn(name,data['checks'])
