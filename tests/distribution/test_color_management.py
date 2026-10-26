from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.color_management import resolve, image_space


class WorkingSpace(unittest.TestCase):
    def test_aces_images_are_not_decoded_as_srgb_and_data_stays_raw(self):
        self.assertEqual(image_space('ACEScg'),'ACEScg')
        self.assertEqual(image_space('scene-linear Rec.709-sRGB'),'Linear Rec.709')
        self.assertEqual(image_space('sRGB',noncolor=True),'Non-Color')

    def test_aces_scene_keeps_aces_constants_and_uses_aces_view(self):
        result=resolve({'rendering_space':'ACEScg','view':'ACES 1.0 SDR-video (sRGB)','enabled':True})
        self.assertEqual(result['working_space'],'ACEScg')
        self.assertEqual(result['view'],'ACES 1.3')
        self.assertTrue(result['view_approximation'])

    def test_linear_scene_does_not_get_interpreted_as_aces(self):
        result=resolve({'rendering_space':'scene-linear Rec.709-sRGB','view':'Un-tone-mapped (sRGB)'})
        self.assertEqual((result['working_space'],result['view']),('Linear Rec.709','Standard'))

    def test_disabled_display_management_is_raw(self):
        self.assertEqual(resolve({'enabled':False,'rendering_space':'ACEScg'})['view'],'Raw')

    def test_legacy_requests_keep_the_previous_color_pipeline(self):
        self.assertEqual((resolve(None)['working_space'],resolve(None)['view']),('Linear Rec.709','AgX'))
