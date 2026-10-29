import os,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya import color_management as cm

class NativeOCIO(unittest.TestCase):
 def test_session_copy_preserves_empty_search_path_and_anchors_luts(self):
  for search in ('','ctfs'):
   with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);source=root/'source.ocio'
    text='ocio_profile_version: 2\nsearch_path: '+search+'\nenvironment: {}\nroles:\n  scene_linear: ACEScg\n'
    source.write_text(text)
    out=root/'session';out.mkdir()
    path=cm.prepare_native({'native_ocio':True,'config_path':str(source),'rendering_space':'scene-linear Rec.709-sRGB'},out)
    result=path.read_text()
    self.assertIn('environment: {}',result);self.assertIn('scene_linear: "scene-linear Rec.709-sRGB"',result)
    self.assertIn(root.as_posix(),result);self.assertEqual(source.read_text(),text)
    if search:self.assertIn((root/'ctfs').as_posix(),result)

 def test_missing_or_disabled_config_keeps_fallback(self):
  self.assertIsNone(cm.prepare_native({'native_ocio':False},'.'))
  self.assertIsNone(cm.prepare_native({'native_ocio':True,'config_path':'missing.ocio'},'.'))

 def test_native_image_spaces_and_data_names_match_source_config(self):
  with mock.patch.dict(os.environ,{'EEVEE_NATIVE_OCIO':'1'}):
   self.assertEqual(cm.image_space('scene-linear Rec.709-sRGB'),'scene-linear Rec.709-sRGB')
   self.assertEqual(cm.image_space('sRGB',True),'Raw')
   settings=cm.resolve({'rendering_space':'ACEScg','native_view':'ACES 1.0 SDR-video','display':'sRGB'})
   self.assertEqual(settings['view'],'ACES 1.0 SDR-video');self.assertFalse(settings['view_approximation'])
