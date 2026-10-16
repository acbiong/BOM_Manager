"""A real Qt child process must clean up and preserve assertion failures."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TestModuleRunnerTests(unittest.TestCase):
    def test_qt_cleanup_and_assertion_failure_exit_codes(self):
        runner=Path(__file__).resolve().parents[1]/'tools/run_test_module.py'
        with tempfile.TemporaryDirectory() as tmp:
            for success in (True,False):
                with self.subTest(success=success):
                    path=Path(tmp)/'test_fixture.py'
                    path.write_text('''import unittest
from PyQt5.QtWidgets import QApplication,QWidget,QDialog,QComboBox,QVBoxLayout,QCompleter
class Fixture(unittest.TestCase):
    app=QApplication([])
    window=QWidget()
    child_dialog=QDialog(window)
    layout=QVBoxLayout(window)
    combo=QComboBox(window)
    combo.setEditable(True)
    combo.addItems(['Alpha','Beta'])
    layout.addWidget(combo)
    completer=QCompleter(combo.model(),combo)
    combo.setCompleter(completer)
    window.show()
    completer.complete()
    app.processEvents()
    def test_assertion(self):
        self.assertTrue(%s)
''' % success,encoding='utf-8')
                    result=subprocess.run([sys.executable,'-X','faulthandler',str(runner),str(path)],
                                          env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),
                                          capture_output=True,text=True,encoding='utf-8',timeout=30)
                    self.assertEqual(result.returncode,0 if success else 1,result.stdout+result.stderr)
                    self.assertIn('QT_CLEANUP_OK windows=1',result.stdout)
                    if not success:self.assertIn('FAILED (failures=1)',result.stderr)
