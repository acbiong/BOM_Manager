"""Signing failures cannot produce publishable checksums; hash the final signed bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.windows_signing import SigningConfig,signing_config,sign_and_verify
from tools.build_windows import finalize_artifact


class WindowsSigningTests(unittest.TestCase):
    def test_unsigned_is_explicit_and_required_or_incomplete_config_is_rejected(self):
        self.assertIsNone(signing_config({}))
        self.assertIsNone(signing_config({'BOM_SIGN_MACHINE_STORE':'0','BOM_REQUIRE_SIGNED':'0'}))
        self.assertEqual(sign_and_verify(Path('test.exe'),None,{})['status'],'unsigned')
        for env in ({'BOM_REQUIRE_SIGNED':'1'},
                    {'BOM_REQUIRE_SIGNED':'true'},
                    {'BOM_SIGN_TIMESTAMP_URL':'https://example.com'},
                    {'BOM_SIGN_CERT_SHA1':'not-a-thumbprint'},
                    {'BOM_SIGN_CERT_SHA1':'a'*40}):
            with self.subTest(env=env),self.assertRaises(ValueError):signing_config(env)

    def test_selects_explicit_certificate_and_requires_trusted_timestamped_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool=Path(tmp)/'signtool.exe';tool.touch()
            env={'BOM_SIGN_CERT_SHA1':'ab'*20,'BOM_SIGNTOOL':str(tool),
                 'BOM_SIGN_TIMESTAMP_URL':'https://timestamp.example.com','BOM_SIGN_MACHINE_STORE':'1'}
            config=signing_config(env)
            with patch('tools.windows_signing.subprocess.run') as run:
                result=sign_and_verify(Path(tmp)/'应用.exe',config,env)
            self.assertEqual(result['status'],'verified')
            sign=run.call_args_list[0].args[0];verify=run.call_args_list[1].args[0]
            self.assertEqual(sign[sign.index('/sha1')+1],'AB'*20)
            self.assertEqual(sign[sign.index('/fd')+1],'SHA256')
            self.assertEqual(sign[sign.index('/td')+1],'SHA256');self.assertIn('/sm',sign)
            self.assertEqual(verify[1:5],['verify','/pa','/all','/tw'])
            self.assertTrue(all(call.kwargs['check'] for call in run.call_args_list))

    def test_failed_sign_or_trust_check_never_reports_success(self):
        config=SigningConfig('signtool.exe','A'*40,'https://timestamp.example.com')
        for results in ([subprocess.CalledProcessError(1,'sign')],
                        [subprocess.CompletedProcess([],0),subprocess.CalledProcessError(2,'verify')]):
            with self.subTest(results=results),patch('tools.windows_signing.subprocess.run',side_effect=results):
                with self.assertRaises(subprocess.CalledProcessError):sign_and_verify(Path('test.exe'),config,{})

    def test_checksum_uses_signed_bytes_and_failed_retry_removes_stale_success_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'app.exe';report=Path(tmp)/'app_smoke.json';exe.write_bytes(b'unsigned')
            def sign(path,config,env):
                path.write_bytes(b'signed');return {'status':'verified'}
            def smoke(*args,**kwargs):
                self.assertEqual(exe.read_bytes(),b'signed')
                report.write_text('{"passed":true}',encoding='utf-8')
                return subprocess.CompletedProcess([],0)
            with patch('tools.build_windows.sign_and_verify',side_effect=sign),patch('tools.build_windows.subprocess.run',side_effect=smoke):
                finalize_artifact(exe,report,None,{})
            checksum=exe.with_suffix('.exe.sha256');signed_report=Path(tmp)/'app_signing.json'
            self.assertEqual(checksum.read_text().split()[0],hashlib.sha256(b'signed').hexdigest())
            self.assertEqual(json.loads(signed_report.read_text())['sha256'],checksum.read_text().split()[0])
            with patch('tools.build_windows.sign_and_verify',side_effect=RuntimeError('sign failed')),patch('tools.build_windows.subprocess.run') as run:
                with self.assertRaisesRegex(RuntimeError,'sign failed'):finalize_artifact(exe,report,None,{})
                run.assert_not_called()
            for path in (checksum,report,signed_report):self.assertFalse(path.exists())

    def test_smoke_failure_after_signing_does_not_publish_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'app.exe';exe.write_bytes(b'signed');report=Path(tmp)/'app_smoke.json'
            with patch('tools.build_windows.sign_and_verify',return_value={'status':'verified'}),patch('tools.build_windows.subprocess.run',return_value=subprocess.CompletedProcess([],1)):
                with self.assertRaisesRegex(RuntimeError,'自检未通过'):finalize_artifact(exe,report,None,{})
            self.assertFalse(exe.with_suffix('.exe.sha256').exists())
