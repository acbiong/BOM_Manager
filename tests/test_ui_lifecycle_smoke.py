"""Keep Qt native crashes isolated, but fail the release gate on any process crash."""
import os,sys,subprocess,json,unittest
from pathlib import Path

class UiLifecycleSmokeTests(unittest.TestCase):
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
