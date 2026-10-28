from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from eevee_maya.light_range import influence_distance


class LocalInfluence(unittest.TestCase):
    def test_fade_stays_outside_all_receiver_corners(self):
        bounds=[([-2,-3,-4],[5,6,7]),([20,-1,0],[21,1,2])]
        distance=influence_distance((0,0,0),bounds)
        self.assertGreater(distance,4*21)
        self.assertLess(distance,90)

    def test_receiver_motion_and_light_motion_update_support(self):
        bounds=[([-1,-1,-1],[1,1,1])]
        self.assertGreater(influence_distance((0,0,30),bounds),120)
        self.assertGreater(influence_distance((0,0,0),[([29,-1,-1],[31,1,1])]),120)

    def test_empty_links_have_a_finite_fallback(self):
        self.assertEqual(influence_distance((0,0,0),[],reference=5),20)

    def test_atmosphere_can_extend_beyond_surface_receivers(self):
        self.assertEqual(influence_distance((0,0,0),[],volume_distance=100),400)
