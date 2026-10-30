import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from help_screenshot_cache import record,reusable

class HelpScreenshotCacheTests(unittest.TestCase):
 def test_ui_and_picture_changes_invalidate_but_version_and_service_do_not(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);out=root/'out';out.mkdir()
   ui=root/'src/ui';ui.mkdir(parents=True);(ui/'main_window.py').write_text('layout 1')
   (root/'tools').mkdir();(root/'tools/generate_help_screenshots.py').write_text('generator')
   (out/'example.png').write_bytes(b'image bytes');record(root,out)
   self.assertTrue(reusable(root,out,['example']))
   (root/'VERSION').write_text('0.6.66')
   services=root/'src/services';services.mkdir();(services/'services.py').write_text('business change')
   self.assertTrue(reusable(root,out,['example']))
   (ui/'main_window.py').write_text('layout 2');self.assertFalse(reusable(root,out,['example']))
   record(root,out);self.assertTrue(reusable(root,out,['example']))
   (out/'example.png').write_bytes(b'corrupt');self.assertFalse(reusable(root,out,['example']))
   record(root,out);(out/'example.png').unlink();self.assertFalse(reusable(root,out,['example']))
 def test_missing_manifest_or_added_guide_requires_generation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);out=root/'out';out.mkdir()
   self.assertFalse(reusable(root,out,['new']))
   (out/'old.png').write_bytes(b'image');record(root,out)
   self.assertFalse(reusable(root,out,['old','new']))
